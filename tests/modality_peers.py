"""モダリティのダミーの試験の道具：手元に MWL と Storage の SCP を立てる（spec/12 の 14 章）.

実の PACS・RIS にはつながない。どの SCP も 127.0.0.1 の空いているポートで立てる。
"""

from __future__ import annotations

import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydicom.dataset import Dataset
from pynetdicom import AE, AllStoragePresentationContexts, evt
from pynetdicom.sop_class import ModalityWorklistInformationFind, Verification

LOCALHOST = "127.0.0.1"
WORKLIST_YAML = Path(__file__).parent / "modality" / "data" / "worklist.yaml"
STATUS_PENDING = 0xFF00
STATUS_CANCEL = 0xFE00
STATUS_SUCCESS = 0x0000
# 試験の SCP の handler が返し続ける時間の上限（試験が止まらないことを防ぐ）
MAX_HANDLER_SECONDS = 10


def free_port() -> int:
    """空いているポートを1つ返す（閉じた後なので、つながらない先としても使える）."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((LOCALHOST, 0))
        return int(sock.getsockname()[1])


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
    cancelled: bool = False
    port: int = 0

    def handle_find(self, event: Any) -> Iterator[tuple[int, Dataset | None]]:
        query = event.identifier
        self.queries.append(query)
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
    port: int = 0

    def handle_store(self, event: Any) -> int:
        ds = event.dataset
        ds.file_meta = event.file_meta
        self.received.append(ds)
        return self.status


def _start(ae: AE, handlers: list[tuple[Any, Any]]) -> tuple[Any, int]:
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
    server, scp.port = _start(ae, [(evt.EVT_C_FIND, scp.handle_find)])
    yield scp
    server.shutdown()


@pytest.fixture
def storage_scp() -> Iterator[StorageRecorder]:
    recorder = StorageRecorder()
    ae = AE(ae_title=recorder.ae_title)
    ae.supported_contexts = AllStoragePresentationContexts
    ae.add_supported_context(Verification)
    server, recorder.port = _start(ae, [(evt.EVT_C_STORE, recorder.handle_store)])
    yield recorder
    server.shutdown()
