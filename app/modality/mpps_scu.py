"""MPPS（Modality Performed Procedure Step）の SCU（spec/12 の 6.4・8.4）.

送る値を組み立てる関数（外の資源を使わない）と、N-CREATE・N-SET を送る関数。
MPPS そのものの SOP Class・Instance UID は DIMSE のコマンドの欄で送り、
データセットの一番上に SOP Class UID・SOP Instance UID を置かない（IHE-A.1.4・A.1.5）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from datetime import datetime
from typing import Final

from pydantic import BaseModel
from pydicom import dcmread
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence as DicomSequence
from pynetdicom.sop_class import ModalityPerformedProcedureStep

from app.core.exceptions import AssociationError, MPPSError
from app.core.models import ScheduledContext
from app.core.uid_generator import UIDGenerator

from .association import association_error, make_ae
from .config import MppsPeerConfig, NodeConfig, WorklistPeerConfig
from .mpps_queue import MppsOperation, MppsQueue, MppsRecord, MppsState

logger = logging.getLogger(__name__)

MppsPeer = MppsPeerConfig | WorklistPeerConfig

STATE_IN_PROGRESS: Final = "IN PROGRESS"
STATE_COMPLETED: Final = "COMPLETED"
STATE_DISCONTINUED: Final = "DISCONTINUED"
STATUS_SUCCESS = 0x0000
STATUS_DUPLICATE_INSTANCE = 0x0111
STATUS_PROCESSING_FAILURE = 0x0110
# N-CREATE・N-SET の Warning（PS3.4 F.7.2・PS3.7 C）。送れた扱いにする
WARNING_STATUSES = frozenset({0x0001, 0x0107, 0x0116})
DEFAULT_PROTOCOL_NAME = "DTG"
_SCHEDULED_STEP_KEYWORDS = (
    "RequestedProcedureID",
    "RequestedProcedureDescription",
    "ScheduledProcedureStepID",
    "ScheduledProcedureStepDescription",
)


def build_n_create(
    ctx: ScheduledContext,
    *,
    modality: str,
    study_instance_uid: str,
    station_ae_title: str,
    station_name: str,
    started: datetime,
) -> Dataset:
    """N-CREATE（IN PROGRESS）の値（6.4。予約なしは RAD TF-2x Table A.1-2 の形）."""
    ds = Dataset()
    if ctx.specific_character_set:
        ds.SpecificCharacterSet = ctx.specific_character_set
    ds.ScheduledStepAttributesSequence = [_scheduled_step(ctx, study_instance_uid)]
    patient = ctx.patient
    ds.PatientName = patient.patient_name
    ds.PatientID = patient.patient_id
    ds.IssuerOfPatientID = patient.issuer_of_patient_id
    ds.PatientBirthDate = patient.birth_date
    ds.PatientSex = patient.sex
    ds.ReferencedPatientSequence = []
    ds.PerformedProcedureStepID = ctx.performed_procedure_step_id
    ds.PerformedStationAETitle = station_ae_title
    ds.PerformedStationName = station_name
    ds.PerformedLocation = ""
    ds.PerformedProcedureStepStartDate = started.strftime("%Y%m%d")
    ds.PerformedProcedureStepStartTime = started.strftime("%H%M%S")
    ds.PerformedProcedureStepStatus = STATE_IN_PROGRESS
    ds.PerformedProcedureStepDescription = ctx.study_description
    ds.PerformedProcedureTypeDescription = ""
    ds.ProcedureCodeSequence = _sequence(ctx, "ProcedureCodeSequence")
    ds.PerformedProcedureStepEndDate = ""
    ds.PerformedProcedureStepEndTime = ""
    ds.Modality = modality
    ds.StudyID = ctx.study_id
    ds.PerformedProtocolCodeSequence = []
    ds.PerformedSeriesSequence = []
    return ds


def build_n_set(
    state: str, files: Sequence[str], ended: datetime, character_set: Sequence[str]
) -> Dataset:
    """終わりの N-SET（COMPLETED・DISCONTINUED）の値。シリーズは作った画像のヘッダーから."""
    ds = Dataset()
    if character_set:
        ds.SpecificCharacterSet = list(character_set)
    ds.PerformedProcedureStepStatus = state
    ds.PerformedProcedureStepEndDate = ended.strftime("%Y%m%d")
    ds.PerformedProcedureStepEndTime = ended.strftime("%H%M%S")
    ds.PerformedSeriesSequence = _performed_series(files)
    return ds


class MPPSNoResponseError(AssociationError):
    """要求を送った後に、応答が来ないまま時間切れ・切断になった（届いていたかもしれない）."""


def send_n_create(
    own_ae_title: str,
    peer: NodeConfig,
    timeout_seconds: float,
    sop_instance_uid: str,
    dataset: Dataset,
    duplicate_ok: bool = False,
) -> None:
    """N-CREATE を送る。`duplicate_ok` なら 0x0111 を送れた扱いにする.

    `duplicate_ok` は、前の N-CREATE が「応答なし」で終わっていたときだけ渡す（8.4.1）。
    """
    allowed = {STATUS_DUPLICATE_INSTANCE} if duplicate_ok else set()
    _send(own_ae_title, peer, timeout_seconds, "N-CREATE", sop_instance_uid, dataset, allowed)


def send_n_set(
    own_ae_title: str,
    peer: NodeConfig,
    timeout_seconds: float,
    sop_instance_uid: str,
    dataset: Dataset,
    already_final_ok: bool = False,
) -> None:
    """終わりの N-SET を送る。`already_final_ok` なら 0x0110 を送れた扱いにする.

    前の N-SET が届いていれば、相手は終わった MPPS を更新できないので 0x0110 を返す
    （PS3.4 F.7.2.2）。`already_final_ok` は、前の同じ N-SET が「応答なし」で終わって
    いたときだけ渡す（8.4.1。0x0110 は一般の処理の失敗でもあるため）。
    """
    allowed = {STATUS_PROCESSING_FAILURE} if already_final_ok else set()
    _send(own_ae_title, peer, timeout_seconds, "N-SET", sop_instance_uid, dataset, allowed)


def _send(
    own_ae_title: str,
    peer: NodeConfig,
    timeout_seconds: float,
    operation: str,
    sop_instance_uid: str,
    dataset: Dataset,
    allowed: set[int],
) -> None:
    ae = make_ae(own_ae_title, timeout_seconds)
    ae.add_requested_context(ModalityPerformedProcedureStep)
    assoc = ae.associate(peer.host, peer.port, ae_title=peer.ae_title)
    if not assoc.is_established:
        raise association_error(assoc, peer.ae_title, peer.host, peer.port)
    try:
        if operation == "N-CREATE":
            status, _attrs = assoc.send_n_create(
                dataset, ModalityPerformedProcedureStep, sop_instance_uid
            )
        else:
            status, _attrs = assoc.send_n_set(
                dataset, ModalityPerformedProcedureStep, sop_instance_uid
            )
    except (ValueError, RuntimeError) as exc:
        # 相手が MPPS の Presentation Context を受けなかったときなど
        raise MPPSError(
            f"{operation} could not be sent: {type(exc).__name__}",
            {"peer": peer.ae_title, "sop_instance_uid": sop_instance_uid},
        ) from exc
    finally:
        if assoc.is_established:
            assoc.release()
    if not status:
        # 要求は送った後なので、相手に届いていたかもしれない（8.4.1 の「応答なし」）
        raise MPPSNoResponseError(
            f"{operation} timed out or the association was aborted",
            {"peer": peer.ae_title, "sop_instance_uid": sop_instance_uid},
        )
    code = int(status.Status)
    if code != STATUS_SUCCESS and code not in WARNING_STATUSES and code not in allowed:
        raise MPPSError(
            f"{operation} failed with status 0x{code:04X}",
            {"peer": peer.ae_title, "status": f"0x{code:04X}"},
        )
    logger.info(
        "%s ok: peer=%s sop_instance_uid=%s status=0x%04X",
        operation,
        peer.ae_title,
        sop_instance_uid,
        code,
    )


class MppsOutcome(BaseModel):
    """撮影の MPPS の状態（撮影の画面と CLI の `--json` に出す）."""

    model_config = {"frozen": True}

    id: int
    sop_instance_uid: str
    state: str
    sent: bool
    error: str = ""


class MppsManager:
    """撮影の開始・終わりに MPPS を送り、送れない知らせを残す（8.4.1）."""

    def __init__(
        self,
        own_ae_title: str,
        station_name: str,
        peer: MppsPeer,
        attempts: int,
        queue: MppsQueue,
    ) -> None:
        self._own_ae_title = own_ae_title
        self._station_name = station_name
        self._peer = peer
        self._attempts = attempts
        self._queue = queue

    def start_exam(self, ctx: ScheduledContext, modality: str, started: datetime) -> int:
        """撮影の開始：予約の値から N-CREATE を組んで送る（6.4）."""
        create = build_n_create(
            ctx,
            modality=modality,
            study_instance_uid=ctx.study_instance_uid or "",
            station_ae_title=self._own_ae_title,
            station_name=self._station_name,
            started=started,
        )
        return self.start(create, ctx.accession_number)

    def finish_exam(
        self,
        record_id: int,
        state: MppsState,
        files: Sequence[str],
        ctx: ScheduledContext,
        output_dir: str,
    ) -> MppsOutcome:
        """撮影の終わり：作った画像から N-SET を組んで送る."""
        modification = build_n_set(state, files, datetime.now(), ctx.specific_character_set)
        outcome = self.finish(record_id, state, modification, output_dir)
        logger.info("MPPS %s: mpps_id=%s sent=%s", state, record_id, outcome.sent)
        return outcome

    def start(self, create: Dataset, accession_number: str) -> int:
        """N-CREATE（IN PROGRESS）を残して送る。送れなくても撮影は止めない."""
        uid = UIDGenerator().generate_sop_uid()
        # 送り先は行に固定する（設定を後で変えても、送り直しは同じ相手へ。8.4.1）
        peer = (self._peer.ae_title, self._peer.host, self._peer.port)
        record_id = self._queue.add(uid, accession_number, create, peer)
        self._with_claim(record_id, lambda: self._send_create(record_id))
        return record_id

    def finish(
        self, record_id: int, state: MppsState, modification: Dataset, output_dir: str
    ) -> MppsOutcome:
        """終わりの N-SET を残し、N-CREATE が送れていれば送る."""
        self._queue.set_final(record_id, state, modification, output_dir)
        record = self._queue.get(record_id)
        if record.create_sent:
            self._with_claim(record_id, lambda: self._send_set(record_id))
        elif not record.last_error:
            self._queue.record_error(record_id, "N-CREATE has not been sent yet")
        return self.outcome(record_id)

    def retry(self) -> list[MppsRecord]:
        """送れていない知らせを古い順に送り直す。N-CREATE を先に（8.4.1）."""
        retried = []
        for record in self._queue.unsent():
            self._with_claim(record.id, lambda record_id=record.id: self._resend(record_id))
            retried.append(self._queue.get(record.id))
        return retried

    def _resend(self, record_id: int) -> None:
        if not self._queue.get(record_id).create_sent:
            self._send_create(record_id)
        current = self._queue.get(record_id)
        if current.create_sent and current.has_set and not current.set_sent:
            self._send_set(record_id)

    def _with_claim(self, record_id: int, send: Callable[[], None]) -> None:
        """送る権利の札を取れたときだけ送る。取れなければ送らずに残す（8.4.1）."""
        token = self._queue.claim(record_id)
        if token is None:
            self._queue.record_error(record_id, "being sent by another process")
            logger.info("MPPS message is being sent elsewhere: mpps_id=%s", record_id)
            return
        try:
            send()
        finally:
            self._queue.release(record_id, token)

    def outcome(self, record_id: int) -> MppsOutcome:
        record = self._queue.get(record_id)
        return MppsOutcome(
            id=record.id,
            sop_instance_uid=record.sop_instance_uid,
            state=record.state,
            sent=record.sent,
            error="" if record.sent else record.last_error,
        )

    def _send_create(self, record_id: int) -> None:
        dataset = self._queue.create_dataset(record_id)
        if self._try(
            record_id,
            "create",
            lambda record, maybe_delivered: send_n_create(
                self._own_ae_title,
                _peer_of(record),
                self._peer.timeout_seconds,
                record.sop_instance_uid,
                dataset,
                duplicate_ok=maybe_delivered,
            ),
        ):
            self._queue.mark_create_sent(record_id)

    def _send_set(self, record_id: int) -> None:
        dataset = self._queue.set_dataset(record_id)
        if self._try(
            record_id,
            "set",
            lambda record, maybe_delivered: send_n_set(
                self._own_ae_title,
                _peer_of(record),
                self._peer.timeout_seconds,
                record.sop_instance_uid,
                dataset,
                already_final_ok=maybe_delivered,
            ),
        ):
            self._queue.mark_set_sent(record_id)

    def _try(
        self,
        record_id: int,
        operation: MppsOperation,
        send: Callable[[MppsRecord, bool], None],
    ) -> bool:
        """`retry.max_attempts` の分だけすぐ試す。だめなら理由を残して False.

        `0x0111`・`0x0110` を送れた扱いにしてよいのは、前の同じ知らせが「応答なし」で
        終わっていたと行の記録から言えるときだけ（8.4.1）。
        """
        for attempt in range(1 + self._attempts):
            record = self._queue.get(record_id)
            maybe_delivered = (
                record.create_no_response if operation == "create" else record.set_no_response
            )
            try:
                send(record, maybe_delivered)
                return True
            except (AssociationError, MPPSError) as exc:
                if isinstance(exc, MPPSNoResponseError):
                    self._queue.mark_no_response(record_id, operation)
                self._queue.record_error(record_id, str(exc))
                logger.warning(
                    "MPPS message not sent: mpps_id=%s attempt=%s reason=%s",
                    record_id,
                    attempt + 1,
                    type(exc).__name__,
                )
        return False


def _peer_of(record: MppsRecord) -> NodeConfig:
    """行に固定した送り先（8.4.1）."""
    return NodeConfig(ae_title=record.peer_ae_title, host=record.peer_host, port=record.peer_port)


def _scheduled_step(ctx: ScheduledContext, study_instance_uid: str) -> Dataset:
    step = Dataset()
    step.StudyInstanceUID = study_instance_uid
    step.ReferencedStudySequence = _sequence(ctx, "ReferencedStudySequence")
    step.AccessionNumber = ctx.accession_number
    step.IssuerOfAccessionNumberSequence = _sequence(ctx, "IssuerOfAccessionNumberSequence")
    request = Dataset.from_json(ctx.request_attributes) if ctx.request_attributes else Dataset()
    for keyword in _SCHEDULED_STEP_KEYWORDS:
        setattr(step, keyword, str(request.get(keyword, "") or ""))
    step.ScheduledProtocolCodeSequence = request.get("ScheduledProtocolCodeSequence", None) or []
    return step


def _sequence(ctx: ScheduledContext, keyword: str) -> DicomSequence:
    return DicomSequence([Dataset.from_json(item) for item in ctx.sequences.get(keyword, [])])


def _performed_series(files: Sequence[str]) -> list[Dataset]:
    series: dict[str, Dataset] = {}
    for path in files:
        image = dcmread(path, stop_before_pixels=True)
        uid = str(image.SeriesInstanceUID)
        item = series.get(uid)
        if item is None:
            item = Dataset()
            item.PerformingPhysicianName = ""
            item.ProtocolName = str(
                image.get("ProtocolName", "") or image.get("SeriesDescription", "")
                or DEFAULT_PROTOCOL_NAME
            )
            item.OperatorsName = ""
            item.SeriesInstanceUID = uid
            item.SeriesDescription = str(image.get("SeriesDescription", "") or "")
            item.RetrieveAETitle = ""
            item.ReferencedImageSequence = []
            item.ReferencedNonImageCompositeSOPInstanceSequence = []
            series[uid] = item
        reference = Dataset()
        reference.ReferencedSOPClassUID = str(image.SOPClassUID)
        reference.ReferencedSOPInstanceUID = str(image.SOPInstanceUID)
        item.ReferencedImageSequence.append(reference)
    return list(series.values())
