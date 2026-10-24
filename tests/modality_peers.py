"""モダリティのダミーの試験の道具：手元に MWL と Storage の SCP を立てる（docs/development.md の 4 章）.

実の PACS・RIS にはつながない。どの SCP も 127.0.0.1 の空いているポートで立てる。
"""

from __future__ import annotations

import socket
import sqlite3
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import closing
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydicom.dataset import Dataset
from pynetdicom import AE, AllStoragePresentationContexts, build_role, evt
from pynetdicom.sop_class import (
    ModalityPerformedProcedureStep,
    ModalityWorklistInformationFind,
    StorageCommitmentPushModel,
    Verification,
)

LOCALHOST = "127.0.0.1"
WORKLIST_YAML = Path(__file__).parent / "modality" / "data" / "worklist.yaml"
STATUS_PENDING = 0xFF00
STATUS_CANCEL = 0xFE00
STATUS_SUCCESS = 0x0000
# 試験の SCP の handler が返し続ける時間の上限（試験が止まらないことを防ぐ）
MAX_HANDLER_SECONDS = 10
# 保管の確認の SCP の、よく知られた SOP Instance UID（PS3.4 J.3.5）
COMMITMENT_INSTANCE_UID = "1.2.840.10008.1.20.1.1"
FAILURE_REASON_NO_SUCH_INSTANCE = 0x0112
MPPS_PROCESSING_FAILURE = 0x0110
MPPS_DUPLICATE_INSTANCE = 0x0111
MPPS_NO_SUCH_INSTANCE = 0x0112
REPORT_WAIT_SECONDS = 10


EXAMPLE_PROFILE = Path(__file__).resolve().parent.parent / "profiles" / "examples" / "dtg_synthetic_ct.yaml"


def write_service_profile(
    directory: Path, name: str, *, mpps: bool, storage_commitment: bool
) -> None:
    """例のプロファイルを写し、`services` の MPPS・保管の確認だけを替えて置く（docs/spec/13 の 8）."""
    data = yaml.safe_load(EXAMPLE_PROFILE.read_text(encoding="utf-8"))
    data["name"] = name
    data["services"] = {
        "modality_worklist": True,
        "mpps": mpps,
        "storage_commitment": storage_commitment,
    }
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )


def _calling_ae_title(event: Any) -> str:
    """要求を送ってきた側（DTG）が名乗った AEタイトル."""
    return str(event.assoc.requestor.ae_title).strip()


def free_port() -> int:
    """空いているポートを1つ返す（閉じた後なので、接続できない先としても使える）."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOCALHOST, 0))
        return int(sock.getsockname()[1])


def age_job(db_path: Path, job_id: int, seconds: int) -> None:
    """待ち行列の件の updated_at を過去にする（送信中のまま止まった件を作る）."""
    old = (datetime.now() - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("UPDATE jobs SET updated_at = ? WHERE id = ?", (old, job_id))


def _code_sequence(values: list[str] | None) -> list[Dataset]:
    if not values:
        return []
    item = Dataset()
    item.CodeValue = values[0]
    item.CodingSchemeDesignator = "99DTG"
    item.CodeMeaning = values[1]
    return [item]


def build_worklist_dataset(raw: dict[str, Any], character_set: list[str]) -> Dataset:
    """YAML の1件（合成の患者）から MWL の応答を作る."""
    ds = Dataset()
    if character_set:
        ds.SpecificCharacterSet = character_set if len(character_set) > 1 else character_set[0]
    ds.PatientName = raw.get("patient_name", "")
    ds.PatientID = raw.get("patient_id", "")
    ds.IssuerOfPatientID = raw.get("issuer_of_patient_id", "")
    ds.PatientBirthDate = raw.get("birth_date", "")
    ds.PatientSex = raw.get("sex", "")
    if raw.get("weight"):
        ds.PatientWeight = raw["weight"]
    if raw.get("size"):
        ds.PatientSize = raw["size"]
    ds.StudyInstanceUID = raw.get("study_instance_uid", "")
    ds.AccessionNumber = raw.get("accession_number", "")
    ds.ReferringPhysicianName = raw.get("referring_physician_name", "")
    if raw.get("requesting_physician"):
        ds.RequestingPhysician = raw["requesting_physician"]
    ds.RequestedProcedureID = raw.get("requested_procedure_id", "")
    ds.RequestedProcedureDescription = raw.get("requested_procedure_description", "")
    ds.RequestedProcedureCodeSequence = _code_sequence(raw.get("requested_procedure_code"))
    if raw.get("reason_for_requested_procedure"):
        ds.ReasonForTheRequestedProcedure = raw["reason_for_requested_procedure"]
    if raw.get("institution_name"):
        ds.InstitutionName = raw["institution_name"]
    sps_raw = raw.get("sps", {})
    sps = Dataset()
    sps.ScheduledStationAETitle = sps_raw.get("station_ae_title", "")
    start_date = sps_raw.get("start_date", "")
    sps.ScheduledProcedureStepStartDate = (
        date.today().strftime("%Y%m%d") if start_date == "TODAY" else start_date
    )
    sps.ScheduledProcedureStepStartTime = sps_raw.get("start_time", "")
    sps.Modality = sps_raw.get("modality", "")
    sps.ScheduledProcedureStepID = sps_raw.get("id", "")
    sps.ScheduledProcedureStepDescription = sps_raw.get("description", "")
    sps.ScheduledProtocolCodeSequence = _code_sequence(sps_raw.get("protocol_code"))
    ds.ScheduledProcedureStepSequence = [sps]
    return ds


def _matches(item: Dataset, query: Dataset) -> bool:
    """試験に要る分だけの一致（完全な MWL の SCP ではない）."""
    for keyword in ("PatientID", "AccessionNumber", "RequestedProcedureID"):
        wanted = str(query.get(keyword, "") or "")
        if wanted and wanted != str(item.get(keyword, "")):
            return False
    wanted_name = str(query.get("PatientName", "") or "")
    if wanted_name:
        prefix = wanted_name.split("*", 1)[0]
        if not str(item.PatientName).startswith(prefix):
            return False
    query_sps = query.get("ScheduledProcedureStepSequence")
    if query_sps:
        q = query_sps[0]
        s = item.ScheduledProcedureStepSequence[0]
        for keyword in ("Modality", "ScheduledStationAETitle"):
            wanted = str(q.get(keyword, "") or "")
            if wanted and wanted != str(s.get(keyword, "")):
                return False
        date_range = str(q.get("ScheduledProcedureStepStartDate", "") or "")
        if date_range:
            low, _, high = date_range.partition("-")
            value = str(s.ScheduledProcedureStepStartDate)
            if not (low <= value <= (high or low)):
                return False
    return True


@dataclass
class WorklistSCP:
    """試験の MWL の SCP の振る舞いと、受けた問い合わせの記録."""

    ae_title: str = "RIS_TEST"
    character_set: list[str] = field(default_factory=lambda: ["ISO_IR 192"])
    items: list[dict[str, Any]] = field(default_factory=list)
    endless_pending: bool = False
    first_response_delay: float = 0.0
    final_status: int = STATUS_SUCCESS
    ignore_cancel: bool = False
    repeat: int = 1
    big_value_bytes: int = 0
    queries: list[Dataset] = field(default_factory=list)
    # 受けた要求の Calling AE Title（装置の切り替えの試験。docs/spec/12 の 12 章）
    calling_ae_titles: list[str] = field(default_factory=list)
    cancelled: bool = False
    port: int = 0

    def handle_find(self, event: Any) -> Iterator[tuple[int, Dataset | None]]:
        query = event.identifier
        self.queries.append(query)
        self.calling_ae_titles.append(_calling_ae_title(event))
        if self.first_response_delay:
            time.sleep(self.first_response_delay)
        if self.final_status != STATUS_SUCCESS:
            yield (self.final_status, None)
            return
        matched = [
            build_worklist_dataset(raw, self.character_set)
            for raw in self.items
            if _matches(build_worklist_dataset(raw, self.character_set), query)
        ]
        if self.big_value_bytes and matched:
            matched[0].RequestedProcedureDescription = "X" * 64
            matched[0].PatientComments = "X" * self.big_value_bytes
        matched = matched * self.repeat
        index = 0
        stop_at = time.monotonic() + MAX_HANDLER_SECONDS
        while time.monotonic() < stop_at and event.assoc.is_established:
            if event.is_cancelled:
                self.cancelled = True
                if not self.ignore_cancel:
                    yield (STATUS_CANCEL, None)
                    return
            if index < len(matched):
                yield (STATUS_PENDING, matched[index])
                index += 1
                continue
            if not self.endless_pending or not matched:
                return
            time.sleep(0.05)
            yield (STATUS_PENDING, matched[-1])


@dataclass
class StorageRecorder:
    """試験の Storage の SCP：受けた画像を覚え、決めた Status を返す."""

    ae_title: str = "PACS_TEST"
    status: int = STATUS_SUCCESS
    received: list[Dataset] = field(default_factory=list)
    calling_ae_titles: list[str] = field(default_factory=list)
    port: int = 0

    def handle_store(self, event: Any) -> int:
        ds = event.dataset
        ds.file_meta = event.file_meta
        self.received.append(ds)
        self.calling_ae_titles.append(_calling_ae_title(event))
        return self.status


@dataclass
class CommitmentPACS(StorageRecorder):
    """試験の PACS：C-STORE を受け、保管の確認（N-ACTION）に答える偽の相手（docs/spec/12 の 8.4.2）.

    `report_path` で結果の道を選ぶ：`separate`（この相手が新しい Association を
    張って、この道具の待ち受けへ送る）・`same`（N-ACTION の Association で送る）・
    `none`（結果を送らない）。`mutate_report` で送る値を壊せる（悪い値の試験）。
    """

    report_path: str = "separate"
    action_status: int = STATUS_SUCCESS
    fail_instance_uids: set[str] = field(default_factory=set)
    event_type: int | None = None  # None なら失敗の有無で 1・2 を決める
    report_delay: float = 0.0
    listener_port: int = 0
    listener_ae_title: str = "DTG_CT01"
    calling_ae_title: str | None = None  # 別の道で名乗る AE（None なら自分の AE）
    mutate_report: Callable[[Dataset], None] | None = None
    actions: list[Dataset] = field(default_factory=list)
    action_calling_ae_titles: list[str] = field(default_factory=list)
    report_statuses: list[int] = field(default_factory=list)
    reported: threading.Event = field(default_factory=threading.Event)
    report_started: bool = False

    def handle_action(self, event: Any) -> tuple[int, Dataset | None]:
        request = event.action_information
        self.actions.append(request)
        self.action_calling_ae_titles.append(_calling_ae_title(event))
        if self.action_status != STATUS_SUCCESS:
            return self.action_status, None
        if self.report_path != "none":
            self.report_started = True
            threading.Thread(
                target=self._report, args=(event.assoc, request), daemon=True
            ).start()
        return STATUS_SUCCESS, None

    def build_report(self, request: Dataset) -> tuple[int, Dataset]:
        report = Dataset()
        report.TransactionUID = request.TransactionUID
        succeeded, failed = [], []
        for ref in request.ReferencedSOPSequence:
            item = Dataset()
            item.ReferencedSOPClassUID = ref.ReferencedSOPClassUID
            item.ReferencedSOPInstanceUID = ref.ReferencedSOPInstanceUID
            if ref.ReferencedSOPInstanceUID in self.fail_instance_uids:
                item.FailureReason = FAILURE_REASON_NO_SUCH_INSTANCE
                failed.append(item)
            else:
                succeeded.append(item)
        report.ReferencedSOPSequence = succeeded
        if failed:
            report.FailedSOPSequence = failed
        event_type = self.event_type if self.event_type is not None else (2 if failed else 1)
        if self.mutate_report is not None:
            self.mutate_report(report)
        return event_type, report

    def _report(self, assoc: Any, request: Dataset) -> None:
        try:
            time.sleep(self.report_delay)
            event_type, report = self.build_report(request)
            if self.report_path == "same":
                self._send_report(assoc, event_type, report)
                return
            ae = AE(ae_title=self.calling_ae_title or self.ae_title)
            ae.add_requested_context(StorageCommitmentPushModel)
            # 別の道では、この相手が SCP の役を求める（PS3.4 J.3.3 の役の交渉）
            role = build_role(StorageCommitmentPushModel, scp_role=True)
            new_assoc = ae.associate(
                LOCALHOST, self.listener_port, ae_title=self.listener_ae_title, ext_neg=[role]
            )
            if not new_assoc.is_established:
                self.report_statuses.append(-1)
                return
            try:
                self._send_report(new_assoc, event_type, report)
            finally:
                new_assoc.release()
        finally:
            self.reported.set()

    def _send_report(self, assoc: Any, event_type: int, report: Dataset) -> None:
        status, _reply = assoc.send_n_event_report(
            report, event_type, StorageCommitmentPushModel, COMMITMENT_INSTANCE_UID
        )
        self.report_statuses.append(int(status.Status) if status else -1)


@dataclass
class MppsRecorder:
    """試験の MPPS の SCP：N-CREATE・N-SET を覚え、決めた Status を返す偽の相手.

    状態を持つ（PS3.4 F.7.2）：作った Instance の N-CREATE は 0x0111、知らない Instance の
    N-SET は 0x0112、COMPLETED・DISCONTINUED の後の N-SET は 0x0110。届いた順を `events`
    に残す。`*_delay_first` は、最初の1回だけ記録してから応答を遅らせる（応答が失われる形）。
    """

    ae_title: str = "RIS_TEST"
    create_statuses: list[int] = field(default_factory=list)  # 空になったら状態で決める
    set_status: int = STATUS_SUCCESS
    create_delay_first: float = 0.0
    set_delay_first: float = 0.0
    created: dict[str, Dataset] = field(default_factory=dict)
    sets: list[tuple[str, Dataset]] = field(default_factory=list)
    events: list[tuple[str, str, int]] = field(default_factory=list)  # (操作, UID, 返した Status)
    finished: set[str] = field(default_factory=set)
    calling_ae_titles: list[str] = field(default_factory=list)
    port: int = 0

    def handle_create(self, event: Any) -> tuple[int, Dataset | None]:
        self.calling_ae_titles.append(_calling_ae_title(event))
        uid = str(event.request.AffectedSOPInstanceUID)
        if self.create_statuses:
            status = self.create_statuses.pop(0)
        else:
            status = MPPS_DUPLICATE_INSTANCE if uid in self.created else STATUS_SUCCESS
        if status == STATUS_SUCCESS:
            self.created[uid] = event.attribute_list
        self.events.append(("N-CREATE", uid, status))
        if self.create_delay_first and status == STATUS_SUCCESS:
            delay, self.create_delay_first = self.create_delay_first, 0.0
            time.sleep(delay)
        return status, event.attribute_list if status == STATUS_SUCCESS else None

    def handle_set(self, event: Any) -> tuple[int, Dataset | None]:
        self.calling_ae_titles.append(_calling_ae_title(event))
        uid = str(event.request.RequestedSOPInstanceUID)
        modification = event.modification_list
        if uid not in self.created:
            status = MPPS_NO_SUCH_INSTANCE
        elif uid in self.finished:
            status = MPPS_PROCESSING_FAILURE  # 終わった MPPS は更新できない
        else:
            status = self.set_status
        if status == STATUS_SUCCESS:
            self.sets.append((uid, modification))
            if str(modification.get("PerformedProcedureStepStatus", "")) != "IN PROGRESS":
                self.finished.add(uid)
        self.events.append(("N-SET", uid, status))
        if self.set_delay_first and status == STATUS_SUCCESS:
            delay, self.set_delay_first = self.set_delay_first, 0.0
            time.sleep(delay)
        return status, modification if status == STATUS_SUCCESS else None


def start_server(ae: AE, handlers: list[tuple[Any, Any]]) -> tuple[Any, int]:
    """手元の空いているポートで、止めずに待ち受ける SCP を立てる."""
    server = ae.start_server((LOCALHOST, 0), block=False, evt_handlers=handlers)
    return server, int(server.server_address[1])


@pytest.fixture
def worklist_items() -> list[dict[str, Any]]:
    with WORKLIST_YAML.open(encoding="utf-8") as fp:
        return list(yaml.safe_load(fp)["items"])


@pytest.fixture
def worklist_scp(worklist_items: list[dict[str, Any]]) -> Iterator[WorklistSCP]:
    scp = WorklistSCP(items=worklist_items)
    ae = AE(ae_title=scp.ae_title)
    ae.add_supported_context(ModalityWorklistInformationFind)
    ae.add_supported_context(Verification)
    server, scp.port = start_server(ae, [(evt.EVT_C_FIND, scp.handle_find)])
    yield scp
    server.shutdown()


@pytest.fixture
def storage_scp() -> Iterator[StorageRecorder]:
    recorder = StorageRecorder()
    ae = AE(ae_title=recorder.ae_title)
    ae.supported_contexts = AllStoragePresentationContexts
    ae.add_supported_context(Verification)
    server, recorder.port = start_server(ae, [(evt.EVT_C_STORE, recorder.handle_store)])
    yield recorder
    server.shutdown()


@pytest.fixture
def commitment_pacs() -> Iterator[CommitmentPACS]:
    """C-STORE と保管の確認を受ける偽の PACS（`listener_port` は試験が入れる）."""
    pacs = CommitmentPACS()
    ae = AE(ae_title=pacs.ae_title)
    ae.supported_contexts = AllStoragePresentationContexts
    ae.add_supported_context(Verification)
    ae.add_supported_context(StorageCommitmentPushModel)
    server, pacs.port = start_server(
        ae,
        [(evt.EVT_C_STORE, pacs.handle_store), (evt.EVT_N_ACTION, pacs.handle_action)],
    )
    yield pacs
    if pacs.report_started:
        # 結果を送る手順が終わってから止める（止めた後に送らせない）
        pacs.reported.wait(REPORT_WAIT_SECONDS)
    server.shutdown()


@pytest.fixture
def mpps_scp() -> Iterator[MppsRecorder]:
    """N-CREATE・N-SET を受ける偽の MPPS の相手."""
    recorder, server = start_mpps_recorder()
    yield recorder
    server.shutdown()


def start_mpps_recorder(port: int = 0) -> tuple[MppsRecorder, Any]:
    """偽の MPPS の相手を立てる。`port` を決めれば、そのポートで（落ちていた相手が戻る形）."""
    recorder = MppsRecorder()
    ae = AE(ae_title=recorder.ae_title)
    ae.add_supported_context(ModalityPerformedProcedureStep)
    ae.add_supported_context(Verification)
    server = ae.start_server(
        (LOCALHOST, port),
        block=False,
        evt_handlers=[
            (evt.EVT_N_CREATE, recorder.handle_create),
            (evt.EVT_N_SET, recorder.handle_set),
        ],
    )
    recorder.port = int(server.server_address[1])
    return recorder, server
