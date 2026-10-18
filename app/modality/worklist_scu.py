"""C-FIND（Modality Worklist）の SCU（spec/12_modality_emulator.md 5 章）."""

from __future__ import annotations

import logging
import re
import time
from datetime import date

from pydantic import BaseModel, Field
from pydicom.dataset import Dataset
from pynetdicom.sop_class import ModalityWorklistInformationFind

from app.core.exceptions import ValidationError, WorklistQueryError
from app.core.models import WorklistItem
from app.core.worklist_charset import CHOICE_TO_CHARACTER_SET
from app.core.worklist_mapping import worklist_item_from_identifier

from .association import association_error, make_ae
from .config import WorklistPeerConfig

logger = logging.getLogger(__name__)

STATUS_SUCCESS = 0x0000
STATUS_CANCEL = 0xFE00
PENDING_STATUSES = frozenset({0xFF00, 0xFF01})
MESSAGE_ID = 1
DATE_FORMAT = "%Y%m%d"
_DATE_PATTERN = re.compile(r"^\d{8}$")
_ASCII_MAX = 0x7F
_QUERY_CHARACTER_SETS = {
    "ISO_IR 192": CHOICE_TO_CHARACTER_SET["utf8"],
    **CHOICE_TO_CHARACTER_SET,
}

# 応答に求める値（RAD TF-2 Table 4.5-3 の R+・R+*。5.2）
_TOP_LEVEL_RETURN_KEYS = (
    "PatientName",
    "PatientID",
    "IssuerOfPatientID",
    "PatientBirthDate",
    "PatientSex",
    "PatientWeight",
    "PatientSize",
    "StudyInstanceUID",
    "AccessionNumber",
    "RequestingPhysician",
    "ReferringPhysicianName",
    "RequestedProcedureID",
    "RequestedProcedureDescription",
    "ReasonForTheRequestedProcedure",
    "InstitutionName",
)
_TOP_LEVEL_RETURN_SEQUENCES = (
    "ReferencedStudySequence",
    "IssuerOfAccessionNumberSequence",
    "RequestedProcedureCodeSequence",
)
_SPS_RETURN_KEYS = (
    "ScheduledStationAETitle",
    "ScheduledProcedureStepStartDate",
    "ScheduledProcedureStepStartTime",
    "Modality",
    "ScheduledPerformingPhysicianName",
    "ScheduledProcedureStepID",
    "ScheduledProcedureStepDescription",
)


class WorklistQuery(BaseModel):
    """引く条件（5.1）。空の値は条件にしない."""

    model_config = {"frozen": True}

    date_range: str = ""
    modality: str = ""
    station_ae_title: str = ""
    patient_id: str = ""
    patient_name: str = ""
    accession_number: str = ""
    requested_procedure_id: str = ""


class WorklistQueryResult(BaseModel):
    model_config = {"frozen": True}

    items: list[WorklistItem] = Field(default_factory=list)
    partial: bool = False
    response_character_set: list[str] = Field(default_factory=list)
    query_non_ascii: bool = False


def parse_date_option(text: str, today: date) -> str:
    """`today`・`YYYYMMDD`・`YYYYMMDD-YYYYMMDD` を範囲の形にする（単一の日も範囲で送る）."""
    if text == "today":
        value = today.strftime(DATE_FORMAT)
        return f"{value}-{value}"
    low, separator, high = text.partition("-")
    high = high if separator else low
    if not (_DATE_PATTERN.match(low) and _DATE_PATTERN.match(high)) or low > high:
        raise ValidationError(
            "Date must be today, YYYYMMDD or YYYYMMDD-YYYYMMDD",
            {"date": text},
        )
    return f"{low}-{high}"


def add_name_wildcards(name: str) -> str:
    """氏名の各成分の末尾に `*` を足す。利用者が `*` を入れていれば足さない（5.1）."""
    if not name or "*" in name:
        return name
    groups = name.split("=")
    return "=".join(
        "^".join(f"{component}*" if component else "" for component in group.split("^"))
        for group in groups
    )


def build_query_identifier(query: WorklistQuery, query_character_set: str) -> Dataset:
    """問い合わせの Identifier を作る（5.1・5.2・5.3）."""
    ds = Dataset()
    criteria = [
        query.patient_id,
        query.patient_name,
        query.accession_number,
        query.requested_procedure_id,
        query.modality,
        query.station_ae_title,
    ]
    if any(ord(char) > _ASCII_MAX for value in criteria for char in value):
        character_set = _QUERY_CHARACTER_SETS[query_character_set]
        ds.SpecificCharacterSet = character_set if len(character_set) > 1 else character_set[0]

    for keyword in _TOP_LEVEL_RETURN_KEYS:
        setattr(ds, keyword, "")
    for keyword in _TOP_LEVEL_RETURN_SEQUENCES:
        setattr(ds, keyword, [])
    ds.PatientID = query.patient_id
    ds.PatientName = add_name_wildcards(query.patient_name)
    ds.AccessionNumber = query.accession_number
    ds.RequestedProcedureID = query.requested_procedure_id

    sps = Dataset()
    for keyword in _SPS_RETURN_KEYS:
        setattr(sps, keyword, "")
    sps.ScheduledProtocolCodeSequence = []
    sps.ScheduledStationAETitle = query.station_ae_title
    sps.ScheduledProcedureStepStartDate = query.date_range
    sps.Modality = query.modality
    ds.ScheduledProcedureStepSequence = [sps]
    return ds


def query_worklist(
    own_ae_title: str,
    peer: WorklistPeerConfig,
    query: WorklistQuery,
) -> WorklistQueryResult:
    """ワークリストを引く.

    相手が Pending を返し続けて `peer.timeout_seconds` を過ぎたら C-CANCEL を送り、
    受け取った分を「途中まで」（partial）として返す（5.4）。
    """
    identifier = build_query_identifier(query, peer.query_character_set)
    ae = make_ae(own_ae_title, peer.timeout_seconds)
    ae.add_requested_context(ModalityWorklistInformationFind)
    logger.info(
        "C-FIND MWL start: peer=%s@%s:%s", peer.ae_title, peer.host, peer.port
    )
    assoc = ae.associate(peer.host, peer.port, ae_title=peer.ae_title)
    if not assoc.is_established:
        raise association_error(assoc, peer.ae_title, peer.host, peer.port)

    items: list[WorklistItem] = []
    response_character_set: list[str] = []
    cancelled = False
    started = time.monotonic()
    try:
        responses = assoc.send_c_find(identifier, ModalityWorklistInformationFind, msg_id=MESSAGE_ID)
        for status, response in responses:
            if not status:
                if cancelled:
                    break
                raise WorklistQueryError(
                    "C-FIND timed out or the association was aborted",
                    {"peer": peer.ae_title, "received": len(items)},
                )
            code = int(status.Status)
            if code in PENDING_STATUSES:
                if response is not None and not cancelled:
                    item = worklist_item_from_identifier(response)
                    items.append(item)
                    response_character_set = response_character_set or item.specific_character_set
                if not cancelled and time.monotonic() - started > peer.timeout_seconds:
                    logger.warning(
                        "C-FIND pending over %ss; sending C-CANCEL (received=%s)",
                        peer.timeout_seconds,
                        len(items),
                    )
                    assoc.send_c_cancel(MESSAGE_ID, query_model=ModalityWorklistInformationFind)
                    cancelled = True
                continue
            if code == STATUS_CANCEL:
                cancelled = True
                break
            if code == STATUS_SUCCESS:
                break
            raise WorklistQueryError(
                f"C-FIND failed with status 0x{code:04X}",
                {"peer": peer.ae_title, "status": f"0x{code:04X}"},
            )
    finally:
        if assoc.is_established:
            assoc.release()

    logger.info(
        "C-FIND MWL done: peer=%s items=%s partial=%s", peer.ae_title, len(items), cancelled
    )
    return WorklistQueryResult(
        items=items,
        partial=cancelled,
        response_character_set=response_character_set,
        query_non_ascii="SpecificCharacterSet" in identifier,
    )
