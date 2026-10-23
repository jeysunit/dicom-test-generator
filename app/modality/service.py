"""モダリティのダミーの手順をまとめる（docs/spec/12_modality_emulator.md 3・5・6・8 章）.

CLI（Phase 3a）とウェブの画面（Phase 3b）は、ここだけを呼ぶ。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
import threading
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError
from pydicom import dcmread
from pydicom.errors import InvalidDicomError

from app.core.exceptions import (
    AssociationError,
    ConfigurationError,
    DICOMGeneratorError,
    FileReadError,
    FileWriteError,
    ModalityConfigError,
    ModalityError,
    MPPSError,
    ProfileError,
    ProfileMismatchError,
    ValidationError,
    WorklistItemGoneError,
    WorklistItemNotFoundError,
    WorklistRefreshTimeoutError,
)
from app.core.models import (
    AbnormalConfig,
    CharacterSetConfig,
    GenerationConfig,
    PixelSpecCTRealistic,
    PixelSpecSimple,
    ScheduledContext,
    ScheduledPatient,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
    WorklistItem,
)
from app.core.path_safety import ensure_within, safe_path_component
from app.core.person_name import GROUP_SEPARATOR, compose_person_name
from app.core.uid_generator import UIDGenerator
from app.core.validation_text import describe_validation_error
from app.core.worklist_charset import resolve_image_character_set
from app.core.worklist_mapping import (
    build_carrier_patient,
    emergency_context,
    ensure_modality_matches,
    scheduled_context_from_item,
)
from app.services import ProfileLoaderService, StudyGeneratorService, TemplateLoaderService
from app.services.profile_loader import profile_transfer_syntax

from .commitment_scu import CommitmentListener, CommitmentManager
from .config import DestinationConfig, ModalityConfig, StationConfig
from .mpps_queue import MppsQueue, MppsRecord
from .mpps_scu import (
    IMAGE_READ_ERRORS,
    STATE_COMPLETED,
    STATE_DISCONTINUED,
    MppsManager,
    MppsOutcome,
)
from .queue import QUEUE_DB_NAME, CommitmentState, QueueJob, SendQueue
from .store_scu import EchoResult, StoreFileResult, echo, store_files
from .worklist_scu import WorklistQuery, WorklistQueryResult, query_worklist

logger = logging.getLogger(__name__)

WORKLIST_STATE_FILE = "worklist_last.json"
STATION_STATE_FILE = "station.json"  # 画面で選んだ装置（ADR-0023）
STATION_BUSY_MESSAGE = "撮影・送信の最中は装置を切り替えられません"
EMERGENCY_FOLDER_NAME = "emergency"
STUDY_ID_COUNTER = "emergency_study_id"
PPS_ID_COUNTER = "performed_procedure_step_id"
STUDY_ID_PREFIX = "E"
PPS_ID_PREFIX = "PPS"
COUNTER_WIDTH = 6
DEFAULT_TEMPLATE_MODALITY = "CT"
MAX_FOLDER_SUFFIX = 100
DICOM_DATE_LENGTH = 8
DICOM_TIME_MIN_LENGTH = 4
EXAM_BUSY_MESSAGE ="ほかの撮影が走っています。終わってから撮ってください"
# DICOM の値の区切り（PS3.5 6.2）。LO・PN・SH の値に入れると VM が増える
VALUE_DELIMITER = "\\"


def _reject_value_delimiter(fields: tuple[tuple[str, str], ...]) -> None:
    """手で入れた値に `\\` があれば断る（ValidationError）."""
    for label, value in fields:
        if VALUE_DELIMITER in value:
            # 誤りの文に入れた値を出さない（docs/spec/12 の 12 章）
            raise ValidationError(f"{label}に「\\」は使えません（DICOM の値の区切り）")


def check_send_files(folder: Path, files: list[str]) -> None:
    """送るファイルを確かめる：symbolic link を断り、フォルダの中の普通のファイルだけ（8.2）.

    中を指す link も断る（送るまでに指す先を替えられるため）。外れたら FileReadError。
    """
    root = folder.resolve()
    for name in files:
        path = Path(name)
        if path.is_symlink():
            raise FileReadError(name, "symbolic links are not sent")
        resolved = path.resolve()
        if resolved.parent != root or not resolved.is_file():
            raise FileReadError(name, f"not a regular file directly inside {root}")


def _read_source_ae_title(folder: Path) -> str:
    """フォルダの最初の画像の File Meta の Source Application Entity Title。読めなければ空."""
    try:
        first = next(
            path for path in sorted(folder.glob("*.dcm")) if path.is_file() and not path.is_symlink()
        )
        meta = dcmread(first, stop_before_pixels=True, specific_tags=["PatientID"]).file_meta
    except (StopIteration, OSError, InvalidDicomError, AttributeError):
        return ""
    return str(meta.get("SourceApplicationEntityTitle", "")).strip()


def _read_job_summary(folder: Path) -> tuple[str, str, str, str]:
    """フォルダの最初の画像から（患者 ID・氏名・検査日時・受付番号）を読む。読めなければ空."""
    try:
        first = next(
            path for path in sorted(folder.glob("*.dcm")) if path.is_file() and not path.is_symlink()
        )
        dataset = dcmread(
            first,
            stop_before_pixels=True,
            specific_tags=["PatientID", "PatientName", "StudyDate", "StudyTime", "AccessionNumber"],
        )
    except (StopIteration, OSError, InvalidDicomError):
        return "", "", "", ""
    study_date = str(dataset.get("StudyDate", ""))
    study_time = str(dataset.get("StudyTime", ""))
    study_datetime = ""
    if len(study_date) == DICOM_DATE_LENGTH and study_date.isdigit():
        study_datetime = f"{study_date[:4]}/{study_date[4:6]}/{study_date[6:]}"
        if len(study_time) >= DICOM_TIME_MIN_LENGTH:
            study_datetime += f" {study_time[:2]}:{study_time[2:4]}"
    return (
        str(dataset.get("PatientID", "")),
        str(dataset.get("PatientName", "")),
        study_datetime,
        str(dataset.get("AccessionNumber", "")),
    )


class ExamRequest(BaseModel):
    """撮影の依頼。`worklist_key` か `emergency_patient` のどちらか1つ."""

    model_config = {"frozen": True}

    worklist_key: str | None = None
    refresh: bool = False
    emergency_patient: ScheduledPatient | None = None
    study_description: str = ""
    template: str | None = None
    profile: str | None = None
    hospital: str | None = None
    images_per_series: list[int] = Field(default_factory=lambda: [1], min_length=1)
    pixel_mode: str | None = None
    abnormal_level: str = "none"
    charset: str | None = None
    output_dir: str | None = None
    mpps: bool | None = None  # None は設定（worklist.use_mpps）。8.4.1


class ExamResult(BaseModel):
    model_config = {"frozen": True}

    output_dir: str
    files: list[str]
    worklist_key: str | None
    accession_number: str
    study_instance_uid: str
    character_set: list[str]
    notices: list[str] = Field(default_factory=list)
    mpps: MppsOutcome | None = None  # MPPS を使わない撮影では None（11.4）


class SendResult(BaseModel):
    model_config = {"frozen": True}

    job_id: int
    destination: str
    status: str
    results: list[StoreFileResult] = Field(default_factory=list)
    error: str = ""


class WorklistState(BaseModel):
    """最後に引いたワークリスト（状態の置き場に保存した物。5.4）."""

    model_config = {"frozen": True}

    queried_at: str = ""
    response_character_set: list[str] = Field(default_factory=list)
    partial: bool = False
    items: list[WorklistItem] = Field(default_factory=list)


class ProfileInfo(BaseModel):
    """撮影の画面の「装置」に並べる、装置のプロファイルの要約."""

    model_config = {"frozen": True}

    name: str
    modality: str
    manufacturer: str
    model_name: str


class ModalityService:
    """ワークリストを引く・予約で撮る・送る、の手順."""

    def __init__(
        self,
        config: ModalityConfig,
        generator: StudyGeneratorService | None = None,
        template_loader: TemplateLoaderService | None = None,
        profile_loader: ProfileLoaderService | None = None,
        auto_commitment: bool = False,
        station: str | None = None,
    ) -> None:
        """`station` はこの service だけで使う装置の表示名（CLI の `--station`）.

        無ければ、状態の保存先に記録した装置（画面で選んだ装置）を使う。
        """
        if station is not None:
            config.station(station)  # 設定に無い名前なら ModalityConfigError
        self.config = config
        self._station_override = station
        self._profile_loader = profile_loader or ProfileLoaderService()
        self._generator = generator or StudyGeneratorService(self._profile_loader)
        self._template_loader = template_loader or TemplateLoaderService()
        self._state_dir = Path(config.state_dir)
        self._queue: SendQueue | None = None
        self._mpps_queue: MppsQueue | None = None
        # 「送れた」になったらすぐに保管の確認を求める（画面のプロセス。8.3.3）
        self._auto_commitment = auto_commitment
        # 同時に走る撮影は1つ（画面のプロセスの中。docs/spec/12a の 10.5）
        self._exam_lock = threading.Lock()
        # 送信ジョブの一覧に出す患者・検査の値（元のファイルから読み、ジョブの番号で覚える）
        self._job_summaries: dict[int, tuple[str, str, str, str]] = {}

    @property
    def queue(self) -> SendQueue:
        if self._queue is None:
            # AE タイトルの列が無い前の版の行は、既定の装置の AE タイトルで埋める
            self._queue = SendQueue(self._state_dir / QUEUE_DB_NAME, self.config.ae_title)
        return self._queue

    @property
    def mpps_queue(self) -> MppsQueue:
        if self._mpps_queue is None:
            self._mpps_queue = MppsQueue(self._state_dir / QUEUE_DB_NAME, self.config.ae_title)
        return self._mpps_queue

    # --- 装置（docs/spec/12 の 12 章・ADR-0023） --------------------------

    def current_station(self) -> StationConfig:
        """いま名乗る装置：`--station`、無ければ記録した装置、無ければ既定の装置."""
        if self._station_override is not None:
            return self.config.station(self._station_override)
        recorded = self._recorded_station_name()
        if recorded is not None and any(s.name == recorded for s in self.config.stations):
            return self.config.station(recorded)
        return self.config.station()

    def station_notice(self) -> str:
        """記録した装置が設定に無くなって、既定の装置に戻したときの知らせ。無ければ空."""
        if self._station_override is not None:
            return ""
        recorded = self._recorded_station_name()
        if recorded is None or any(s.name == recorded for s in self.config.stations):
            return ""
        return (
            f"前に選んだ装置（{recorded}）は設定にありません。"
            f"既定の装置（{self.config.default_station}）を使います"
        )

    def select_station(self, name: str) -> StationConfig:
        """装置を切り替えて記録する。撮影・送信の最中は断る（ModalityError）."""
        station = self.config.station(name)
        # 撮影と同じ錠を取ってから確かめて書く（確かめた後に撮影が始まらないように）
        if not self._exam_lock.acquire(blocking=False):
            raise ModalityError(STATION_BUSY_MESSAGE)
        try:
            if any(not job.stale for job in self.queue.list_jobs("sending")):
                raise ModalityError(STATION_BUSY_MESSAGE)
            self._write_state(self._state_dir / STATION_STATE_FILE, {"name": station.name})
        finally:
            self._exam_lock.release()
        logger.info("Station selected: %s (%s)", station.name, station.ae_title)
        return station

    def _recorded_station_name(self) -> str | None:
        path = self._state_dir / STATION_STATE_FILE
        if not path.exists():
            return None
        try:
            name = json.loads(path.read_text(encoding="utf-8")).get("name")
        except (OSError, ValueError, AttributeError):
            logger.warning("Could not read the selected station; using the default")
            return None
        return name if isinstance(name, str) else None

    # --- 保管の確認（Phase 3c。8.3） -------------------------------------

    def uses_commitment(self) -> bool:
        return any(destination.storage_commitment for destination in self.config.destinations)

    def start_commitment_listener(self) -> CommitmentListener | None:
        """待ち受けを立てる。保管の確認を使う送り先が無ければ立てずに None（8.3）."""
        if not self.uses_commitment():
            return None
        listener = self._new_listener()
        listener.start()
        return listener

    def _new_listener(self) -> CommitmentListener:
        listen = self.config.listen
        # 切り替えた後に届く前の装置あての結果も受ける（設定の装置の AE タイトルの全部）
        return CommitmentListener(
            [station.ae_title for station in self.config.stations],
            listen.bind_address,
            listen.port,
            self._commitments().receive,
        )

    def request_commitment(self, job_id: int) -> CommitmentState:
        """送れた件の保管の確認を求める（8.3.3。CLI の `commit`、画面の自動）."""
        return self._commitments().request(
            job_id, self._commitment_node(job_id), self._job_ae_title(job_id)
        )

    def _station_ae_title_of(self, folder: Path) -> str:
        """画像を作った装置の AE タイトル。設定の装置でなければ、いまの装置."""
        source = _read_source_ae_title(folder)
        if any(station.ae_title == source for station in self.config.stations):
            return source
        return self.current_station().ae_title

    def _job_ae_title(self, job_id: int) -> str:
        """件を作った装置の AE タイトル。記録が無ければいまの装置."""
        return self.queue.get_job(job_id).calling_ae_title or self.current_station().ae_title

    def commit_and_wait(self, job_id: int, wait_seconds: float | None = None) -> CommitmentState:
        """CLI の `commit`：待ち受けを立ててから求め、結果か `wait_seconds` まで待つ（11.8）.

        待ち受けを立てられなければ、N-ACTION を送らずに ModalityConfigError。
        """
        node = self._commitment_node(job_id)
        listener = self._new_listener()
        listener.start()
        try:
            state = self._commitments().request(job_id, node, self._job_ae_title(job_id))
            if state.status == "waiting":
                seconds = node.commitment_timeout_seconds if wait_seconds is None else wait_seconds
                state = self.wait_commitment(state.transaction_uid, seconds)
        finally:
            listener.shutdown()
        return state

    def _commitment_node(self, job_id: int) -> DestinationConfig:
        """保管の確認を求めてよい件かを確かめ、送り先を返す."""
        job = self.queue.get_job(job_id)
        node = self.config.destination(job.destination)
        if not node.storage_commitment:
            raise ModalityConfigError(
                f"Destination does not use storage commitment: {node.name}",
                {"destination": node.name, "hint": "set storage_commitment: true"},
            )
        if not self._profile_allows(job.folder, "storage_commitment"):
            raise ModalityConfigError(
                "The device profile of this exam does not support storage commitment",
                {"job_id": job_id},
            )
        if job.status != "sent":
            raise ModalityError(
                f"Queue job is not sent: {job_id}", {"job_id": job_id, "status": job.status}
            )
        return node

    def wait_commitment(self, transaction_uid: str, seconds: float) -> CommitmentState:
        return self._commitments().wait(transaction_uid, seconds)

    def _commitments(self) -> CommitmentManager:
        return CommitmentManager(self.current_station().ae_title, self.queue)

    def _auto_commit(self, job_id: int) -> None:
        """送れた件の保管の確認を自動で求める。求められなくても送れた結果は変えない."""
        job = self.queue.get_job(job_id)
        node = self.config.destination(job.destination)
        try:
            if node.storage_commitment and self._profile_allows(job.folder, "storage_commitment"):
                self._commitments().request(job_id, node, self._job_ae_title(job_id))
        except (ModalityError, ConfigurationError, sqlite3.Error) as exc:
            # sqlite3.Error：待ち受けのスレッドが同じ DB に書いている間の「locked」など
            logger.warning(
                "Storage commitment was not requested: job_id=%s reason=%s",
                job_id,
                type(exc).__name__,
            )

    def _profile_allows(self, folder: str, service: str) -> bool:
        """撮影に使った装置のプロファイルが、その働きに対応するか（docs/spec/13 の 8）."""
        profile_name = self.queue.exam_profile(folder)
        return profile_name is None or self._profile_supports(profile_name, service)

    def _profile_supports(self, profile_name: str | None, service: str) -> bool:
        if not profile_name:
            return True
        services = self._profile_loader.load(profile_name).services
        return bool(getattr(services, service))

    # --- MPPS（Phase 3c。8.4） -------------------------------------------

    def list_mpps(self) -> list[MppsRecord]:
        return self.mpps_queue.list_all()

    def retry_mpps(self) -> list[MppsRecord]:
        """送れていない MPPS の知らせを送り直す。残れば MPPSError（11.9）."""
        # `exam --mpps` で作った知らせは、設定で使わなくても送り直せる（8.4.1）
        if not self.config.worklist.use_mpps and not self.mpps_queue.unsent():
            raise ModalityConfigError(
                "MPPS is not used (worklist.use_mpps is false) and nothing is left to send",
                {"use_mpps": False},
            )
        records = self._mpps().retry()
        unsent = [record for record in records if not record.sent]
        if unsent:
            raise MPPSError(
                "Some MPPS messages were not sent",
                {"mpps_ids": ", ".join(str(r.id) for r in unsent), "reason": unsent[0].last_error},
            )
        return records

    def _mpps(self, station: StationConfig | None = None) -> MppsManager:
        """`station` は撮影する装置。送り直しは行に記録した AE タイトルで送る（8.4.1）."""
        station = station or self.current_station()
        return MppsManager(
            station.ae_title,
            station.station_name,
            self.config.mpps_peer(),
            self.config.retry.max_attempts,
            self.mpps_queue,
        )

    def _uses_mpps(self, request: ExamRequest, profile_name: str | None) -> bool:
        wanted = self.config.worklist.use_mpps if request.mpps is None else request.mpps
        return wanted and self._profile_supports(profile_name, "mpps")

    # --- C-ECHO ---------------------------------------------------------

    def echo(self, destination: str | None = None, worklist: bool = False) -> EchoResult:
        own_ae_title = self.current_station().ae_title
        if worklist:
            peer = self.config.worklist
            return echo(own_ae_title, peer, peer.timeout_seconds)
        node = self.config.destination(destination)
        return echo(own_ae_title, node, node.timeout_seconds)

    # --- ワークリスト ---------------------------------------------------

    def default_query(self, today: date) -> WorklistQuery:
        """既定の条件：今日・テンプレートのモダリティ・自分の AE タイトル（5.1）."""
        value = today.strftime("%Y%m%d")
        return WorklistQuery(
            date_range=f"{value}-{value}",
            modality=self.template_modality(self.config.default_template),
            station_ae_title=self.current_station().ae_title,
        )

    def query_worklist(self, query: WorklistQuery) -> WorklistQueryResult:
        result = query_worklist(self.current_station().ae_title, self.config.worklist, query)
        self._save_worklist(result)
        return result

    def last_worklist(self) -> list[WorklistItem]:
        return self.last_worklist_state().items

    def last_worklist_state(self) -> WorklistState:
        """最後に引いた結果を、引いた時刻・応答の文字コードと一緒に返す（画面の帯。7.1）."""
        path = self._state_dir / WORKLIST_STATE_FILE
        if not path.exists():
            return WorklistState()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorklistState.model_validate(data)
        except PydanticValidationError as exc:
            # 値（氏名など）を出さず、項目の名前と原因だけにする（docs/spec/12 の 12 章）
            raise FileReadError(str(path), describe_validation_error(exc)) from exc
        except (OSError, ValueError) as exc:
            raise FileReadError(str(path), str(exc)) from exc

    def find_item(self, key: str) -> WorklistItem:
        for item in self.last_worklist():
            if item.key == key:
                return item
        raise WorklistItemNotFoundError(
            f"Worklist item not found in the last query: {key}",
            {"worklist_key": key, "hint": "run 'worklist query' first"},
        )

    def refresh_item(self, key: str) -> WorklistItem:
        """その予約だけを、受付番号と Requested Procedure ID で引き直す（10.4）."""
        current = self.find_item(key)
        result = query_worklist(
            self.current_station().ae_title,
            self.config.worklist,
            WorklistQuery(
                accession_number=current.accession_number,
                requested_procedure_id=current.requested_procedure_id,
            ),
        )
        if result.partial:
            # 途中までの応答で撮ると、引き直した値が古いまま・欠けたままになりうる（5.4）
            raise WorklistRefreshTimeoutError(
                f"Worklist refresh was cut off by the time limit: {key}",
                {"worklist_key": key, "timeout_seconds": self.config.worklist.timeout_seconds},
            )
        for item in result.items:
            if item.key == key:
                self._replace_item(item)
                return item
        raise WorklistItemGoneError(
            f"Worklist item no longer found on the worklist: {key}",
            {"worklist_key": key, "accession_number": current.accession_number},
        )

    # --- 撮影 -----------------------------------------------------------

    @staticmethod
    def emergency_person_name(alphabetic: str, ideographic: str, phonetic: str) -> str:
        """手で入れた3つの氏名の欄を PN にする。空白は `^` にする（docs/spec/12a の 10.5）.

        画面のスクリプトの置き換えは補助で、ここで必ず同じ置き換えをする。
        """
        return compose_person_name(alphabetic, ideographic, phonetic)

    def image_character_set(
        self, worklist_character_set: list[str] | None, choice: str | None = None
    ) -> list[str]:
        """画像に使う文字コード（7.1）。`choice` が無ければ設定の既定."""
        return resolve_image_character_set(
            choice or self.config.character_set,
            worklist_character_set,
            self.config.character_set_fallback,
        )

    def available_templates(self) -> list[str]:
        return self._template_loader.list_modality_templates()

    def available_profiles(self) -> tuple[list[ProfileInfo], list[ProfileError]]:
        """読める装置のプロファイルと、読めなかった物の誤り（docs/spec/13 の 7.2）."""
        entries, errors = self._profile_loader.list_profiles()
        infos = [
            ProfileInfo(
                name=entry.name,
                modality=entry.profile.device.modality,
                manufacturer=entry.profile.device.manufacturer,
                model_name=entry.profile.device.manufacturers_model_name,
            )
            for entry in entries
        ]
        return infos, errors

    def check_profile_modality(self, profile_name: str | None, modality: str) -> None:
        """プロファイルのモダリティが予約・テンプレートと違えば止める（docs/spec/13 の 8）."""
        if not profile_name:
            return
        profile = self._profile_loader.load(profile_name)
        if profile.device.modality != modality:
            raise ProfileMismatchError(
                f"Device profile modality {profile.device.modality} does not match {modality}",
                {"profile": profile_name},
            )

    def template_modality(self, template_name: str) -> str:
        template = self._template_loader.load_modality_template(template_name)
        info = template.get("info", {})
        if isinstance(info, dict) and isinstance(info.get("modality"), str):
            return info["modality"]
        return DEFAULT_TEMPLATE_MODALITY

    def exam(self, request: ExamRequest) -> ExamResult:
        """予約（または緊急の患者）で撮る。量の上限と、同時に1つだけを守る（10.5）."""
        total = sum(request.images_per_series)
        limit = self.config.max_images_per_exam
        if total > limit:
            raise ValidationError(
                f"1回の撮影は合計 {limit} 画像までです（{total} 画像が指定されました）",
                {"max_images_per_exam": limit, "requested": total},
            )
        if not self._exam_lock.acquire(blocking=False):
            raise ModalityError(EXAM_BUSY_MESSAGE)
        try:
            return self._exam(request)
        finally:
            self._exam_lock.release()

    def _exam(self, request: ExamRequest) -> ExamResult:
        if (request.worklist_key is None) == (request.emergency_patient is None):
            raise ConfigurationError(
                "Specify exactly one of worklist_key or emergency_patient",
                {"worklist_key": request.worklist_key},
            )
        template = request.template or self.config.default_template
        modality = self.template_modality(template)
        # 撮影は始めたときの装置で最後まで行う（途中で切り替えは受けない。ADR-0023）
        station = self.current_station()
        now = datetime.now()
        notices: list[str] = []
        pps_id = f"{PPS_ID_PREFIX}{self.queue.next_value(PPS_ID_COUNTER):0{COUNTER_WIDTH}d}"
        choice = request.charset or self.config.character_set

        if request.worklist_key is not None:
            item = (
                self.refresh_item(request.worklist_key)
                if request.refresh
                else self.find_item(request.worklist_key)
            )
            ensure_modality_matches(item, modality)
            character_set = resolve_image_character_set(
                choice, item.specific_character_set, self.config.character_set_fallback
            )
            ctx = scheduled_context_from_item(
                item,
                performed_procedure_step_id=pps_id,
                specific_character_set=character_set,
                source_ae_title=station.ae_title,
            )
            notices.extend(self._scheduled_notices(item, station.ae_title))
            if ctx.study_instance_uid is None:
                # 予約に UID が無いとき、同じ予約の2回目は前に作った UID を使う（6.3）
                remembered = self.queue.generated_study_uid(item.key)
                if remembered:
                    ctx = ctx.model_copy(update={"study_instance_uid": remembered})
        else:
            emergency_patient = request.emergency_patient
            if emergency_patient is None:
                raise ConfigurationError("emergency_patient is required for an emergency exam")
            if not emergency_patient.patient_name.split(GROUP_SEPARATOR, 1)[0].strip():
                # 緊急の患者の氏名（英字）は必須（docs/spec/12a の 10.5）。画面と CLI の両方に効く
                raise ValidationError(
                    "緊急の患者の氏名（英字）は必須です",
                    {"patient_id": emergency_patient.patient_id},
                )
            _reject_value_delimiter(
                (
                    ("Patient ID", emergency_patient.patient_id),
                    ("氏名", emergency_patient.patient_name),
                    ("検査の説明", request.study_description),
                )
            )
            character_set = resolve_image_character_set(
                choice, None, self.config.character_set_fallback
            )
            study_number = self.queue.next_value(STUDY_ID_COUNTER)
            study_id = f"{STUDY_ID_PREFIX}{study_number:0{COUNTER_WIDTH}d}"
            ctx = emergency_context(
                emergency_patient,
                study_id=study_id,
                study_description=request.study_description,
                performed_procedure_step_id=pps_id,
                specific_character_set=character_set,
                source_ae_title=station.ae_title,
            )
            notices.append("予約なし（受付番号は空）")
            if not ctx.patient.birth_date:
                notices.append("生年月日が空です")

        if station.station_name:
            ctx = ctx.model_copy(update={"station_name": station.station_name})
        profile_name = request.profile or self.config.default_profile
        use_mpps = self._uses_mpps(request, profile_name)
        if use_mpps and ctx.study_instance_uid is None:
            # MPPS と画像の Study をそろえるため、N-CREATE より前に UID を作る（8.4.1）
            ctx = ctx.model_copy(update={"study_instance_uid": UIDGenerator().generate_study_uid()})
        output_dir = self._exam_output_dir(request, ctx, now)
        config = self._generation_config(request, ctx, template, output_dir, now)
        mpps = self._mpps(station)
        mpps_id = mpps.start_exam(ctx, modality, now) if use_mpps else None
        if mpps_id is not None:
            # 画像に MPPS への参照を入れる（IHE RAD TF-2x A.1.3・A.2.2）
            mpps_uid = self.mpps_queue.get(mpps_id).sop_instance_uid
            ctx = ctx.model_copy(update={"performed_procedure_step_sop_instance_uid": mpps_uid})
        try:
            self._generator.generate(config=config, scheduled=ctx)
        except (DICOMGeneratorError, OSError):
            # 止まる前に書けた画像も DISCONTINUED の N-SET で知らせる（PS3.4 F.7.2.2.2）
            partial = sorted(str(path) for path in output_dir.glob("*.dcm"))
            self._remove_if_empty(output_dir)
            if mpps_id is not None:
                # N-CREATE の後に撮影が止まった＝取り消し（DISCONTINUED。8.4.1）
                mpps.finish_exam(
                    mpps_id, STATE_DISCONTINUED, partial, ctx, str(output_dir)
                )
            raise
        files = sorted(str(path) for path in output_dir.glob("*.dcm"))
        mpps_outcome = None
        if mpps_id is not None:
            try:
                mpps_outcome = mpps.finish_exam(
                    mpps_id, STATE_COMPLETED, files, ctx, str(output_dir)
                )
            except IMAGE_READ_ERRORS:
                # 作った画像のヘッダーを読めなければ、開いたままにせず DISCONTINUED を残す。
                # DISCONTINUED は読めた画像だけを知らせる
                mpps.finish_exam(
                    mpps_id, STATE_DISCONTINUED, files, ctx, str(output_dir)
                )
                raise
        if profile_name:
            self.queue.remember_exam_profile(str(output_dir), profile_name)
        study_uid = self._read_study_uid(files)
        if request.worklist_key is not None and study_uid:
            self.queue.remember_study_uid(request.worklist_key, study_uid)
        logger.info(
            "Exam completed: worklist_key=%s accession=%r files=%s output_dir=%s",
            request.worklist_key,
            ctx.accession_number,
            len(files),
            output_dir,
        )
        return ExamResult(
            output_dir=str(output_dir),
            files=files,
            worklist_key=request.worklist_key,
            accession_number=ctx.accession_number,
            study_instance_uid=study_uid,
            character_set=character_set,
            notices=notices,
            mpps=mpps_outcome,
        )

    # --- 送信 -----------------------------------------------------------

    def send(
        self, folder: str, destination: str | None = None, calling_ae_title: str | None = None
    ) -> SendResult:
        """フォルダの *.dcm を待ち行列に1件入れ、すぐに送る（8.2）.

        名乗る AE タイトル（件に記録する）は、`calling_ae_title`、無ければ画像を作った
        装置（画像の Source AE Title が設定の装置のどれかなら、その AE タイトル）、それも
        無ければいまの装置。撮った後に切り替えても、画像と送信の名乗りをそろえるため。
        """
        node = self.config.destination(destination)
        folder_path = Path(folder)
        if not folder_path.is_dir():
            raise FileReadError(str(folder_path), "Folder does not exist")
        files = sorted(str(path) for path in folder_path.glob("*.dcm"))
        if not files:
            raise FileReadError(str(folder_path), "No .dcm files in the folder")
        # 待ち行列に入れる前に、送ってよいファイルかを確かめる（8.2）
        check_send_files(folder_path, files)
        # 件の受付番号は、送る画像の Accession Number（読めなければ空のまま送る）
        accession_number = _read_job_summary(folder_path)[3]
        calling = calling_ae_title or self._station_ae_title_of(folder_path)
        job_id = self.queue.add_job(
            str(folder_path), node.name, files, accession_number, calling_ae_title=calling
        )
        return self._send_job(job_id, files)

    def send_exam_output(self, folder: str, destination: str | None = None) -> SendResult:
        """撮影の出力のフォルダを送る。出力の根の中のフォルダだけを受ける（6.5）.

        画面のフォームから来るフォルダの名前は信用しない。根の外を指せば送らずに止める。
        """
        root = Path(self.config.output_dir)
        resolved = ensure_within(root, Path(folder))
        if resolved == root.resolve():
            raise FileWriteError(str(folder), "the output root itself is not an exam folder")
        return self.send(str(resolved), destination)

    def retry(
        self, job_id: int | None = None, all_failed: bool = False, stale: bool = False
    ) -> list[SendResult]:
        """送り直す（8.2）。送信失敗の件は、送れていない画像だけを同じ件で送る.

        `job_id` が送信完了の件なら、同じフォルダの画像をすべて、同じ送信先へ新しい件として
        送る（回数の上限は無い。画像は作り直さないので UID は変わらない）。
        `stale` は、送信中のまま止まった件を失敗に戻してから送り直す。
        """
        if sum((job_id is not None, all_failed, stale)) != 1:
            raise ConfigurationError("Specify exactly one of job_id, all_failed or stale")
        if job_id is not None:
            jobs = [self.queue.get_job(job_id)]
        elif stale:
            jobs = [self.queue.get_job(reset_id) for reset_id in self.queue.reset_stale_sending()]
        else:
            jobs = self.queue.list_jobs("failed")
        results = []
        for job in jobs:
            if job_id is not None and job.status == "sent":
                # 送れた件は変えずに残し、履歴と保管の確認を件ごとに分ける。名乗る AE
                # タイトルは元の件のもの（あとで装置を切り替えても変えない）
                results.append(
                    self.send(job.folder, job.destination, job.calling_ae_title or None)
                )
                continue
            if job.status != "failed":
                raise ModalityError(
                    f"Queue job is not failed: {job.id}", {"job_id": job.id, "status": job.status}
                )
            results.append(self._send_job(job.id, self.queue.unsent_files(job.id)))
        return results

    def list_queue(self, status: str | None = None) -> list[QueueJob]:
        """送信ジョブの一覧。患者 ID・氏名・検査日時は、元のファイルの先頭から読んで足す."""
        return [self._with_summary(job) for job in self.queue.list_jobs(status)]

    def _with_summary(self, job: QueueJob) -> QueueJob:
        summary = self._job_summaries.get(job.id)
        if summary is None:
            summary = _read_job_summary(Path(job.folder))
            if any(summary):
                self._job_summaries[job.id] = summary
        patient_id, patient_name, study_datetime, accession_number = summary
        return job.model_copy(
            update={
                "patient_id": patient_id,
                "patient_name": patient_name,
                "study_datetime": study_datetime,
                # 受付番号を記録していない前の件は、画像の値で補う
                "accession_number": job.accession_number or accession_number,
            }
        )

    def _send_job(self, job_id: int, files: list[str]) -> SendResult:
        job = self.queue.get_job(job_id)
        node = self.config.destination(job.destination)
        attempts = 1 + self.config.retry.max_attempts
        status = "failed"
        results: list[StoreFileResult] = []
        error = ""
        pending = [Path(path) for path in files]
        for _attempt in range(attempts):
            token = self.queue.mark_sending(job_id)
            try:
                # 再送でも確かめる。入れた後にファイルが替えられても送らない（8.2）
                check_send_files(Path(job.folder), [str(path) for path in pending])
            except FileReadError as exc:
                error = str(exc)
                self.queue.record_job_failure(job_id, error, token=token)
                logger.warning("Send refused: job_id=%s unsafe file in the folder", job_id)
                break
            try:
                results = store_files(
                    # 件を作ったときの装置の AE タイトルで名乗る（切り替えた後の再送も同じ）
                    job.calling_ae_title or self.current_station().ae_title,
                    node,
                    pending,
                    node.timeout_seconds,
                    # 1ファイルごとに時刻を進め、札が違えば（引き取られたら）残りを送らない
                    on_progress=lambda token=token: self.queue.touch_sending(job_id, token),
                )
            except AssociationError as exc:
                error = str(exc)
                self.queue.record_job_failure(job_id, error, token=token)
                logger.warning("Send failed: job_id=%s destination=%s", job_id, node.name)
                continue
            status = self.queue.record_results(job_id, results, token=token)
            if status == "sent":
                error = ""
                break
            error = next((r.reason for r in results if not r.sent), "")
            pending = [Path(path) for path in self.queue.unsent_files(job_id)]
        logger.info("Send finished: job_id=%s destination=%s status=%s", job_id, node.name, status)
        if self._auto_commitment and status == "sent":
            self._auto_commit(job_id)
        return SendResult(
            job_id=job_id, destination=node.name, status=status, results=results, error=error
        )

    # --- 内部 -----------------------------------------------------------

    def _scheduled_notices(self, item: WorklistItem, own_ae_title: str) -> list[str]:
        notices = []
        if item.scheduled_station_ae_title and item.scheduled_station_ae_title != own_ae_title:
            notices.append("この予約は別の装置の予定です")
        if not item.study_instance_uid:
            notices.append("予約に Study Instance UID が無いため、このツールが生成しました")
        if not item.birth_date:
            notices.append("生年月日が空です")
        if not item.sex:
            notices.append("性別が空です")
        return notices

    def _exam_output_dir(self, request: ExamRequest, ctx: ScheduledContext, now: datetime) -> Path:
        root = Path(request.output_dir or self.config.output_dir)
        # 受付番号は相手から来る信用できない値なので、名前に直してから使う（6.5）
        name = safe_path_component(ctx.accession_number, EMERGENCY_FOLDER_NAME)
        base = f"{name}_{now:%Y%m%d%H%M%S}"
        for suffix in range(1, MAX_FOLDER_SUFFIX + 1):
            folder = base if suffix == 1 else f"{base}_{suffix}"
            output_dir = ensure_within(root, root / folder)
            if not output_dir.exists():
                return output_dir
        raise FileWriteError(str(root / base), "Too many exams in the same second")

    def _generation_config(
        self,
        request: ExamRequest,
        ctx: ScheduledContext,
        template: str,
        output_dir: Path,
        now: datetime,
    ) -> GenerationConfig:
        pixel_mode = request.pixel_mode or self.config.default_pixel_mode
        if pixel_mode == "simple_text":
            pixel_spec: PixelSpecSimple | PixelSpecCTRealistic = PixelSpecSimple()
        elif pixel_mode == "ct_realistic":
            pixel_spec = PixelSpecCTRealistic()
        else:
            raise ConfigurationError("Unsupported pixel mode", {"pixel_mode": pixel_mode})
        study_date = now.strftime("%Y%m%d")
        profile_name = request.profile or self.config.default_profile
        transfer_syntax = (
            profile_transfer_syntax(self._profile_loader.load(profile_name))
            if profile_name
            else TransferSyntaxConfig()
        )
        return GenerationConfig(
            job_name=f"exam_{request.worklist_key or EMERGENCY_FOLDER_NAME}",
            output_dir=str(output_dir),
            patient=build_carrier_patient(ctx.patient, study_date),
            study=StudyConfig(
                accession_number=ctx.accession_number,
                study_date=study_date,
                study_time=now.strftime("%H%M%S"),
                num_series=len(request.images_per_series),
            ),
            series_list=[
                SeriesConfig(series_number=index + 1, num_images=count)
                for index, count in enumerate(request.images_per_series)
            ],
            modality_template=template,
            device_profile=profile_name,
            hospital_template=request.hospital or self.config.default_hospital,
            pixel_spec=pixel_spec,
            transfer_syntax=transfer_syntax,
            character_set=CharacterSetConfig(
                specific_character_set="\\".join(ctx.specific_character_set),
                use_ideographic=True,
                use_phonetic=True,
            ),
            abnormal=AbnormalConfig(level=request.abnormal_level),
        )

    @staticmethod
    def _remove_if_empty(output_dir: Path) -> None:
        """撮影が止まったとき、撮影のために作った出力のフォルダが空なら消す（7.2）.

        フォルダは _exam_output_dir が無いことを確かめた名前なので、この撮影が作ったもの。
        中にファイルが残っていれば消さない（rmdir は空のときだけ消える）。
        """
        try:
            if output_dir.is_dir() and not any(output_dir.iterdir()):
                output_dir.rmdir()
        except OSError:
            logger.warning("Could not remove the empty output folder: %s", output_dir, exc_info=True)

    @staticmethod
    def _read_study_uid(files: list[str]) -> str:
        if not files:
            return ""
        # 異常のデータ（moderate・severe）では Study Instance UID が無いことがある
        return str(getattr(dcmread(files[0], stop_before_pixels=True), "StudyInstanceUID", ""))

    def _save_worklist(self, result: WorklistQueryResult) -> None:
        path = self._state_dir / WORKLIST_STATE_FILE
        data = {
            "queried_at": datetime.now().isoformat(timespec="seconds"),
            "response_character_set": result.response_character_set,
            "partial": result.partial,
            "items": [item.model_dump() for item in result.items],
        }
        self._write_state(path, data)

    def _replace_item(self, new_item: WorklistItem) -> None:
        path = self._state_dir / WORKLIST_STATE_FILE
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise FileReadError(str(path), str(exc)) from exc
        data["items"] = [
            new_item.model_dump() if raw.get("key") == new_item.key else raw
            for raw in data.get("items", [])
        ]
        self._write_state(path, data)

    def _write_state(self, path: Path, data: dict) -> None:
        """状態のファイルを書く。一時のファイルに書いてから置き換える（別のプロセスの画面・
        CLI が、書きかけのファイルを読まないように）."""
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
            ) as fp:
                fp.write(json.dumps(data, ensure_ascii=False, indent=2))
                temporary = Path(fp.name)
            temporary.replace(path)
        except OSError as exc:
            raise FileWriteError(str(path), str(exc)) from exc
