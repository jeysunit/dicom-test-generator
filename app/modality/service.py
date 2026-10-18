"""モダリティのダミーの手順をまとめる（spec/12_modality_emulator.md 3・5・6・8 章）.

CLI（Phase 3a）とウェブの画面（Phase 3b）は、ここだけを呼ぶ。
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from pydicom import dcmread

from app.core.exceptions import (
    AssociationError,
    ConfigurationError,
    DICOMGeneratorError,
    FileReadError,
    FileWriteError,
    ModalityError,
    ProfileError,
    ProfileMismatchError,
    ValidationError,
    WorklistQueryError,
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
from app.core.worklist_charset import resolve_image_character_set
from app.core.worklist_mapping import (
    build_carrier_patient,
    emergency_context,
    ensure_modality_matches,
    scheduled_context_from_item,
)
from app.services import ProfileLoaderService, StudyGeneratorService, TemplateLoaderService
from app.services.profile_loader import profile_transfer_syntax

from .config import ModalityConfig
from .queue import QUEUE_DB_NAME, QueueJob, SendQueue
from .store_scu import EchoResult, StoreFileResult, echo, store_files
from .worklist_scu import WorklistQuery, WorklistQueryResult, query_worklist

logger = logging.getLogger(__name__)

WORKLIST_STATE_FILE = "worklist_last.json"
EMERGENCY_FOLDER_NAME = "emergency"
STUDY_ID_COUNTER = "emergency_study_id"
PPS_ID_COUNTER = "performed_procedure_step_id"
STUDY_ID_PREFIX = "E"
PPS_ID_PREFIX = "PPS"
COUNTER_WIDTH = 6
DEFAULT_TEMPLATE_MODALITY = "CT"
MAX_FOLDER_SUFFIX = 100


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


class ExamResult(BaseModel):
    model_config = {"frozen": True}

    output_dir: str
    files: list[str]
    worklist_key: str | None
    accession_number: str
    study_instance_uid: str
    character_set: list[str]
    notices: list[str] = Field(default_factory=list)


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
    ) -> None:
        self.config = config
        self._profile_loader = profile_loader or ProfileLoaderService()
        self._generator = generator or StudyGeneratorService(self._profile_loader)
        self._template_loader = template_loader or TemplateLoaderService()
        self._state_dir = Path(config.state_dir)
        self._queue: SendQueue | None = None

    @property
    def queue(self) -> SendQueue:
        if self._queue is None:
            self._queue = SendQueue(self._state_dir / QUEUE_DB_NAME)
        return self._queue

    # --- C-ECHO ---------------------------------------------------------

    def echo(self, destination: str | None = None, worklist: bool = False) -> EchoResult:
        if worklist:
            peer = self.config.worklist
            return echo(self.config.ae_title, peer, peer.timeout_seconds)
        node = self.config.destination(destination)
        return echo(self.config.ae_title, node, node.timeout_seconds)

    # --- ワークリスト ---------------------------------------------------

    def default_query(self, today: date) -> WorklistQuery:
        """既定の条件：今日・テンプレートのモダリティ・自分の AE タイトル（5.1）."""
        value = today.strftime("%Y%m%d")
        return WorklistQuery(
            date_range=f"{value}-{value}",
            modality=self.template_modality(self.config.default_template),
            station_ae_title=self.config.ae_title,
        )

    def query_worklist(self, query: WorklistQuery) -> WorklistQueryResult:
        result = query_worklist(self.config.ae_title, self.config.worklist, query)
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
        except (OSError, ValueError) as exc:
            raise FileReadError(str(path), str(exc)) from exc

    def find_item(self, key: str) -> WorklistItem:
        for item in self.last_worklist():
            if item.key == key:
                return item
        raise ModalityError(
            f"Worklist item not found in the last query: {key}",
            {"worklist_key": key, "hint": "run 'worklist query' first"},
        )

    def refresh_item(self, key: str) -> WorklistItem:
        """その予約だけを、受付番号と Requested Procedure ID で引き直す（10.4）."""
        current = self.find_item(key)
        result = query_worklist(
            self.config.ae_title,
            self.config.worklist,
            WorklistQuery(
                accession_number=current.accession_number,
                requested_procedure_id=current.requested_procedure_id,
            ),
        )
        if result.partial:
            # 途中までの応答で撮ると、引き直した値が古いまま・欠けたままになりうる（5.4）
            raise WorklistQueryError(
                f"Worklist refresh was cut off by the time limit: {key}",
                {"worklist_key": key, "timeout_seconds": self.config.worklist.timeout_seconds},
            )
        for item in result.items:
            if item.key == key:
                self._replace_item(item)
                return item
        raise ModalityError(
            f"Worklist item no longer found on the worklist: {key}",
            {"worklist_key": key, "accession_number": current.accession_number},
        )

    # --- 撮影 -----------------------------------------------------------

    @staticmethod
    def emergency_person_name(alphabetic: str, ideographic: str, phonetic: str) -> str:
        """手で入れた3つの氏名の欄を PN にする。空白は `^` にする（spec/12 の 10.5）.

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
        """読める装置のプロファイルと、読めなかった物の誤り（spec/13 の 7.2）."""
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
        """プロファイルのモダリティが予約・テンプレートと違えば止める（spec/13 の 8）."""
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
        if (request.worklist_key is None) == (request.emergency_patient is None):
            raise ConfigurationError(
                "Specify exactly one of worklist_key or emergency_patient",
                {"worklist_key": request.worklist_key},
            )
        template = request.template or self.config.default_template
        modality = self.template_modality(template)
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
                source_ae_title=self.config.ae_title,
            )
            notices.extend(self._scheduled_notices(item))
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
                # 緊急の患者の氏名（英字）は必須（spec/12 の 10.5）。画面と CLI の両方に効く
                raise ValidationError(
                    "緊急の患者の氏名（英字）は必須です",
                    {"patient_id": emergency_patient.patient_id},
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
                source_ae_title=self.config.ae_title,
            )
            notices.append("予約なし（受付番号は空）")
            if not ctx.patient.birth_date:
                notices.append("生年月日が空です")

        output_dir = self._exam_output_dir(request, ctx, now)
        config = self._generation_config(request, ctx, template, output_dir, now)
        try:
            self._generator.generate(config=config, scheduled=ctx)
        except DICOMGeneratorError:
            self._remove_if_empty(output_dir)
            raise
        files = sorted(str(path) for path in output_dir.glob("*.dcm"))
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
        )

    # --- 送信 -----------------------------------------------------------

    def send(self, folder: str, destination: str | None = None) -> SendResult:
        """フォルダの *.dcm を待ち行列に1件入れ、すぐに送る（8.2）."""
        node = self.config.destination(destination)
        folder_path = Path(folder)
        if not folder_path.is_dir():
            raise FileReadError(str(folder_path), "Folder does not exist")
        files = sorted(str(path) for path in folder_path.glob("*.dcm"))
        if not files:
            raise FileReadError(str(folder_path), "No .dcm files in the folder")
        job_id = self.queue.add_job(str(folder_path), node.name, files)
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
        """失敗の分だけを送り直す（8.2）.

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
            if job.status != "failed":
                raise ModalityError(
                    f"Queue job is not failed: {job.id}", {"job_id": job.id, "status": job.status}
                )
            results.append(self._send_job(job.id, self.queue.unsent_files(job.id)))
        return results

    def list_queue(self, status: str | None = None) -> list[QueueJob]:
        return self.queue.list_jobs(status)

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
                results = store_files(
                    self.config.ae_title,
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
        return SendResult(
            job_id=job_id, destination=node.name, status=status, results=results, error=error
        )

    # --- 内部 -----------------------------------------------------------

    def _scheduled_notices(self, item: WorklistItem) -> list[str]:
        notices = []
        if item.scheduled_station_ae_title and item.scheduled_station_ae_title != self.config.ae_title:
            notices.append("この予約は別の装置の予定です")
        if not item.study_instance_uid:
            notices.append("予約に Study Instance UID が無いため、この道具が作りました")
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
        return str(dcmread(files[0], stop_before_pixels=True).StudyInstanceUID)

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
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError as exc:
            raise FileWriteError(str(path), str(exc)) from exc
