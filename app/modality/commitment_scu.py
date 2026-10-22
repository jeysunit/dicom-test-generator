"""保管の確認（Storage Commitment Push Model）の SCU と結果の待ち受け（docs/spec/12 の 8.3）.

- N-ACTION（Action Type 1）で、送れた画像の組を送り先に問う
- 結果（N-EVENT-REPORT）は、同じ Association（送り先の `commitment_wait_seconds` を
  入れたときだけ待つ）か、待ち受け（別の Association）で受ける（8.3.1）
- 結果の値は相手から来る信用できない値として読む（8.3.2）。ここでは形を確かめて
  読むだけにし、どの要求の結果かを確かめて書くのは呼ぶ側（ModalityService）
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from pydantic import BaseModel
from pydicom.dataset import Dataset
from pynetdicom import AE, evt
from pynetdicom.sop_class import StorageCommitmentPushModel, Verification

from app.core.exceptions import AssociationError, ModalityConfigError, StorageCommitmentError
from app.core.uid_format import is_valid_uid
from app.core.uid_generator import UIDGenerator

from .association import association_error, make_ae
from .config import DestinationConfig
from .queue import CommitmentState, SendQueue

logger = logging.getLogger(__name__)

# 保管の確認の SCP の、よく知られた SOP Instance UID（PS3.4 J.3.5）
COMMITMENT_INSTANCE_UID = "1.2.840.10008.1.20.1.1"
ACTION_TYPE_REQUEST = 1
EVENT_TYPE_ALL_SUCCESS = 1
EVENT_TYPE_SOME_FAILED = 2
STATUS_SUCCESS = 0x0000
STATUS_PROCESSING_FAILURE = 0x0110
STATUS_NO_SUCH_EVENT_TYPE = 0x0113
LISTENER_MAX_ASSOCIATIONS = 4
# 結果の Event Information の大きさの上限（2000 枚の参照を十分に入れられる。8.3.2）
MAX_REPORT_BYTES = 1024 * 1024
WAIT_POLL_SECONDS = 0.05
RESPONSE_GRACE_SECONDS = 0.2
# 結果を受ける要求の状態（時間切れの後に来た結果も受ける。8.3.2）
RECEIVABLE_STATUSES = ("waiting", "timed_out")
# 結果の Dataset を読むときに pydicom が上げうる誤り（遅れて読む値の形の誤り）
_DECODE_ERRORS = (AttributeError, KeyError, TypeError, ValueError, IndexError)

SopReference = tuple[str, str]  # (SOP Class UID, SOP Instance UID)
# 結果を受けたときに呼ぶ：(相手の AE タイトル, Event Type, Event Information) → 返す Status
ReportHandler = Callable[[str, int | None, Dataset], int]


class CommitmentReferences(BaseModel):
    """結果の参照の並びを読んだもの（要求と照らした後に読む。8.3.2）."""

    model_config = {"frozen": True}

    confirmed: frozenset[SopReference]
    failed: dict[SopReference, int | None]


class CommitmentReportRefused(StorageCommitmentError):
    """受け取れない結果。`status` を相手に返す."""

    def __init__(self, status: int, reason: str) -> None:
        super().__init__(f"Storage commitment report refused: {reason}", {"status": f"0x{status:04X}"})
        self.status = status


def build_action_information(transaction_uid: str, references: Sequence[SopReference]) -> Dataset:
    """N-ACTION の Action Information（PS3.4 J.3.2）."""
    ds = Dataset()
    ds.TransactionUID = transaction_uid
    items = []
    for sop_class_uid, sop_instance_uid in references:
        item = Dataset()
        item.ReferencedSOPClassUID = sop_class_uid
        item.ReferencedSOPInstanceUID = sop_instance_uid
        items.append(item)
    ds.ReferencedSOPSequence = items
    return ds


def read_transaction_uid(event_type: int | None, info: Dataset) -> str:
    """Event Type と Transaction UID だけを読む（参照の並びはまだ読まない。8.3.2）."""
    if event_type not in (EVENT_TYPE_ALL_SUCCESS, EVENT_TYPE_SOME_FAILED):
        raise CommitmentReportRefused(STATUS_NO_SUCH_EVENT_TYPE, "unknown event type")
    try:
        transaction_uid = str(info.get("TransactionUID", "") or "")
    except _DECODE_ERRORS as exc:
        raise CommitmentReportRefused(
            STATUS_PROCESSING_FAILURE, f"unreadable event information ({type(exc).__name__})"
        ) from exc
    if not is_valid_uid(transaction_uid):
        raise CommitmentReportRefused(
            STATUS_PROCESSING_FAILURE, "transaction UID is missing or not a UID"
        )
    return transaction_uid


def read_references(info: Dataset, max_items: int) -> CommitmentReferences:
    """参照の並びを読む。合計の件数が `max_items`（要求で問うた数）を超えれば断る（8.3.2）."""
    try:
        referenced = info.get("ReferencedSOPSequence", None) or []
        failed_items = info.get("FailedSOPSequence", None) or []
        if len(referenced) + len(failed_items) > max_items:
            raise CommitmentReportRefused(
                STATUS_PROCESSING_FAILURE, "more references than requested"
            )
        confirmed = frozenset(
            reference for item in referenced if (reference := _reference(item)) is not None
        )
        failed: dict[SopReference, int | None] = {}
        for item in failed_items:
            reference = _reference(item)
            if reference is not None:
                failed[reference] = _failure_reason(item)
    except _DECODE_ERRORS as exc:
        raise CommitmentReportRefused(
            STATUS_PROCESSING_FAILURE, f"unreadable event information ({type(exc).__name__})"
        ) from exc
    return CommitmentReferences(confirmed=confirmed, failed=failed)


def request_commitment(
    own_ae_title: str,
    node: DestinationConfig,
    transaction_uid: str,
    references: Sequence[SopReference],
    on_report: ReportHandler,
) -> None:
    """N-ACTION で問う。送れなければ AssociationError・StorageCommitmentError.

    送り先の `commitment_wait_seconds` が 0 でなければ、その秒まで同じ Association を
    開けたまま、そこで来る結果を待つ（8.3.1 の例外）。0 ならすぐに離す。
    """
    ae = make_ae(own_ae_title, node.timeout_seconds)
    ae.add_requested_context(StorageCommitmentPushModel)
    received = threading.Event()

    def handle(event: Any) -> tuple[int, None]:
        try:
            return _dispatch(event, on_report), None
        finally:
            received.set()

    assoc = ae.associate(
        node.host,
        node.port,
        ae_title=node.ae_title,
        evt_handlers=[(evt.EVT_N_EVENT_REPORT, handle)],
    )
    if not assoc.is_established:
        raise association_error(assoc, node.ae_title, node.host, node.port)
    try:
        status, _reply = assoc.send_n_action(
            build_action_information(transaction_uid, references),
            ACTION_TYPE_REQUEST,
            StorageCommitmentPushModel,
            COMMITMENT_INSTANCE_UID,
        )
        if not status:
            raise StorageCommitmentError(
                "N-ACTION timed out or the association was aborted",
                {"peer": node.ae_title, "transaction_uid": transaction_uid},
            )
        code = int(status.Status)
        if code != STATUS_SUCCESS:
            raise StorageCommitmentError(
                f"N-ACTION failed with status 0x{code:04X}",
                {"peer": node.ae_title, "status": f"0x{code:04X}"},
            )
        logger.info(
            "Storage commitment requested: peer=%s transaction_uid=%s images=%s",
            node.ae_title,
            transaction_uid,
            len(references),
        )
        if node.commitment_wait_seconds > 0 and received.wait(node.commitment_wait_seconds):
            # 結果への応答を相手に返し終えてから離す（handler の後で応答が送られる）
            time.sleep(RESPONSE_GRACE_SECONDS)
    finally:
        if assoc.is_established:
            assoc.release()


class CommitmentListener:
    """結果（N-EVENT-REPORT）だけを受ける待ち受け（4.1・8.3.1。既定は 127.0.0.1）."""

    def __init__(
        self, ae_title: str, bind_address: str, port: int, on_report: ReportHandler
    ) -> None:
        self._address = (bind_address, port)
        self._on_report = on_report
        self._server: Any = None
        ae = AE(ae_title=ae_title)
        # 呼ばれる AE タイトルが自分と違う Association は断る（8.3.1）
        ae.require_called_aet = True
        ae.maximum_associations = LISTENER_MAX_ASSOCIATIONS
        # 相手が SCP の役を求める役の交渉を受ける（別の道。PS3.4 J.3.3）
        ae.add_supported_context(StorageCommitmentPushModel, scu_role=True, scp_role=True)
        ae.add_supported_context(Verification)
        self._ae = ae

    @property
    def port(self) -> int:
        if self._server is None:
            return self._address[1]
        return int(self._server.server_address[1])

    def start(self) -> None:
        try:
            self._server = self._ae.start_server(
                self._address,
                block=False,
                evt_handlers=[(evt.EVT_N_EVENT_REPORT, self._handle)],
            )
        except OSError as exc:
            raise ModalityConfigError(
                "Could not start the storage commitment listener",
                {
                    "bind_address": self._address[0],
                    "port": self._address[1],
                    "reason": str(exc),
                    "hint": "is the web screen (python -m app.web) already listening on this port?",
                },
            ) from exc
        logger.info("Storage commitment listener on %s:%s", self._address[0], self.port)

    def shutdown(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server = None

    def _handle(self, event: Any) -> tuple[int, None]:
        return _dispatch(event, self._on_report), None


class CommitmentManager:
    """要求を出し、結果を待ち行列に書く（8.3.2・8.3.3）。待ち受けと同じ手順を通す."""

    def __init__(self, own_ae_title: str, queue: SendQueue) -> None:
        self._own_ae_title = own_ae_title
        self._queue = queue

    def request(self, job_id: int, node: DestinationConfig) -> CommitmentState:
        """送れた画像の組で N-ACTION を送り、要求の状態を返す。送れなければ「確認の失敗」."""
        references = self._queue.sent_references(job_id)
        if not references:
            raise StorageCommitmentError(
                f"No sent images to commit: {job_id}", {"job_id": job_id}
            )
        transaction_uid = UIDGenerator().generate_sop_uid()
        self._queue.add_commitment(
            job_id,
            node.name,
            node.ae_title,
            transaction_uid,
            references,
            node.commitment_timeout_seconds,
        )
        try:
            request_commitment(
                self._own_ae_title, node, transaction_uid, references, self.receive
            )
        except (AssociationError, StorageCommitmentError) as exc:
            self._queue.fail_commitment(transaction_uid, str(exc))
            logger.warning(
                "Storage commitment request failed: job_id=%s destination=%s", job_id, node.name
            )
        return self._queue.get_commitment(transaction_uid)

    def receive(self, peer_ae_title: str, event_type: int | None, info: Dataset) -> int:
        """結果を確かめて書く。返す値は相手に返す Status（8.3.2）."""
        # 先に Event Type・Transaction UID・相手の AE だけを確かめ、合ったときだけ参照を読む
        try:
            transaction_uid = read_transaction_uid(event_type, info)
        except CommitmentReportRefused as exc:
            logger.warning("Storage commitment report refused from %r: %s", peer_ae_title, exc)
            return exc.status
        known = self._queue.commitment_peer(transaction_uid)
        if known is None or known[0] not in RECEIVABLE_STATUSES:
            logger.warning(
                "Storage commitment report for an unknown or finished request from %r: %r",
                peer_ae_title,
                transaction_uid,
            )
            return STATUS_PROCESSING_FAILURE
        status, expected_ae_title = known
        if peer_ae_title != expected_ae_title:
            logger.warning(
                "Storage commitment report from another AE: got=%r expected=%r",
                peer_ae_title,
                expected_ae_title,
            )
            return STATUS_PROCESSING_FAILURE
        try:
            references = read_references(
                info, len(self._queue.commitment_requested(transaction_uid))
            )
        except CommitmentReportRefused as exc:
            logger.warning("Storage commitment report refused from %r: %s", peer_ae_title, exc)
            return exc.status
        if not self._queue.record_commitment_report(
            transaction_uid, set(references.confirmed), references.failed
        ):
            # 確かめた後に、別の道の結果か N-ACTION の失敗が先に書いた
            logger.warning("Storage commitment report came after another: %r", transaction_uid)
            return STATUS_PROCESSING_FAILURE
        if status == "timed_out":
            logger.info("Late storage commitment report: %r", transaction_uid)
        logger.info(
            "Storage commitment report: transaction_uid=%r event_type=%s failed=%s",
            transaction_uid,
            event_type,
            len(references.failed),
        )
        return STATUS_SUCCESS

    def wait(self, transaction_uid: str, seconds: float) -> CommitmentState:
        """結果か `seconds` まで待つ（CLI の `commit`。11.8）."""
        deadline = time.monotonic() + seconds
        while True:
            state = self._queue.get_commitment(transaction_uid)
            if state.status != "waiting" or time.monotonic() >= deadline:
                return state
            time.sleep(WAIT_POLL_SECONDS)


def _dispatch(event: Any, on_report: ReportHandler) -> int:
    """N-EVENT-REPORT を読み、呼ぶ側に渡して、相手に返す Status を決める."""
    assoc = event.assoc
    peer = assoc.acceptor if assoc.is_requestor else assoc.requestor
    peer_ae_title = str(peer.ae_title).strip()
    if str(event.request.AffectedSOPInstanceUID) != COMMITMENT_INSTANCE_UID:
        logger.warning("Storage commitment report with an unknown instance from %r", peer_ae_title)
        return STATUS_PROCESSING_FAILURE
    raw = getattr(event.request, "EventInformation", None)
    size = len(raw.getvalue()) if raw is not None else 0
    if size > MAX_REPORT_BYTES:
        # 読む前に大きさで断る（大きな偽の知らせで読ませない。8.3.2）
        logger.warning(
            "Storage commitment report too large from %r: %s bytes", peer_ae_title, size
        )
        return STATUS_PROCESSING_FAILURE
    try:
        info = event.event_information
    except _DECODE_ERRORS:
        logger.warning("Unreadable storage commitment report from %r", peer_ae_title)
        return STATUS_PROCESSING_FAILURE
    return on_report(peer_ae_title, event.event_type, info)


def _reference(item: Dataset) -> SopReference | None:
    sop_class_uid = str(item.get("ReferencedSOPClassUID", "") or "")
    sop_instance_uid = str(item.get("ReferencedSOPInstanceUID", "") or "")
    if is_valid_uid(sop_class_uid) and is_valid_uid(sop_instance_uid):
        return sop_class_uid, sop_instance_uid
    return None


def _failure_reason(item: Dataset) -> int | None:
    value = item.get("FailureReason", None)
    return int(value) if isinstance(value, int) else None
