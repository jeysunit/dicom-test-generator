"""予約から画像への値の写し方（spec/12 の 5.4・6 章）の試験."""

from __future__ import annotations

import hashlib

import pytest
from pydicom.dataelem import RawDataElement
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.tag import Tag

from app.core.exceptions import WorklistMappingError
from app.core.models import ScheduledPatient
from app.core.worklist_mapping import (
    apply_scheduled_context,
    build_carrier_patient,
    emergency_context,
    ensure_modality_matches,
    make_worklist_key,
    scheduled_context_from_item,
    worklist_item_from_identifier,
)

UTF8 = ["ISO_IR 192"]


def _code_item(value: str, meaning: str) -> Dataset:
    item = Dataset()
    item.CodeValue = value
    item.CodingSchemeDesignator = "99DTG"
    item.CodeMeaning = meaning
    return item


def _identifier(**overrides: object) -> Dataset:
    ds = Dataset()
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.PatientName = "YAMADA^TARO=山田^太郎=やまだ^たろう"
    ds.PatientID = "P000001"
    ds.IssuerOfPatientID = "DTG"
    ds.PatientBirthDate = "19800115"
    ds.PatientSex = "M"
    ds.PatientWeight = "65.5"
    ds.PatientSize = "1.72"
    ds.StudyInstanceUID = "2.25.1111"
    ds.AccessionNumber = "A0001"
    issuer = Dataset()
    issuer.LocalNamespaceEntityID = "DTG_RIS"
    ds.IssuerOfAccessionNumberSequence = [issuer]
    ds.ReferringPhysicianName = "REFERRING^DOCTOR"
    ds.RequestedProcedureID = "RP0001"
    ds.RequestedProcedureDescription = "胸部 CT"
    ds.RequestedProcedureCodeSequence = [_code_item("RPC1", "胸部 CT")]
    ds.ReasonForTheRequestedProcedure = "精査"
    ref_study = Dataset()
    ref_study.ReferencedSOPClassUID = "1.2.840.10008.3.1.2.3.1"
    ref_study.ReferencedSOPInstanceUID = "2.25.1111"
    ds.ReferencedStudySequence = [ref_study]
    ds.InstitutionName = "Example Hospital"
    sps = Dataset()
    sps.ScheduledStationAETitle = "DTG_CT01"
    sps.ScheduledProcedureStepStartDate = "20261018"
    sps.ScheduledProcedureStepStartTime = "090000"
    sps.Modality = "CT"
    sps.ScheduledPerformingPhysicianName = ""
    sps.ScheduledProcedureStepID = "SPS0001"
    sps.ScheduledProcedureStepDescription = "胸部 単純"
    sps.ScheduledProtocolCodeSequence = [_code_item("PROT1", "胸部 単純")]
    ds.ScheduledProcedureStepSequence = [sps]
    for keyword, value in overrides.items():
        if value is None:
            delattr(ds, keyword)
        else:
            setattr(ds, keyword, value)
    return ds


def _image() -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.PatientName = "CARRIER"
    ds.PatientID = "CARRIER"
    ds.PatientBirthDate = "20261018"
    ds.PatientSex = "O"
    ds.PatientAge = "000Y"
    ds.StudyInstanceUID = "2.25.9999"
    ds.StudyDate = "20261018"
    ds.StudyTime = "100000"
    ds.AccessionNumber = "CARRIER"
    ds.StudyID = ""
    ds.InstitutionName = "Template Hospital"
    ds.Modality = "CT"
    return ds


def test_make_worklist_key_is_sha1_prefix() -> None:
    key = make_worklist_key("2.25.1", "RP1", "SPS1", "A1")

    assert key == hashlib.sha1(b"2.25.1|RP1|SPS1|A1").hexdigest()[:10]
    assert len(key) == 10


def test_item_from_identifier_reads_values() -> None:
    item = worklist_item_from_identifier(_identifier())

    assert item.patient_name == "YAMADA^TARO=山田^太郎=やまだ^たろう"
    assert item.patient_id == "P000001"
    assert item.birth_date == "19800115"
    assert item.size == "1.72"
    assert item.accession_number == "A0001"
    assert item.scheduled_procedure_step_id == "SPS0001"
    assert item.scheduled_station_ae_title == "DTG_CT01"
    assert item.modality == "CT"
    assert item.specific_character_set == UTF8
    assert item.key == make_worklist_key("2.25.1111", "RP0001", "SPS0001", "A0001")
    assert set(item.sequences) == {
        "IssuerOfAccessionNumberSequence",
        "RequestedProcedureCodeSequence",
        "ReferencedStudySequence",
        "ScheduledProtocolCodeSequence",
    }
    assert item.unreadable_attributes == []


def test_item_from_identifier_marks_unreadable_value() -> None:
    ds = _identifier()
    tag = Tag(0x00100010)
    ds[tag] = RawDataElement(tag, "PN", 4, b"\xff\xfeAB", 0, True, True)

    item = worklist_item_from_identifier(ds)

    assert item.unreadable_attributes == ["PatientName"]


def test_scheduled_context_copies_values() -> None:
    item = worklist_item_from_identifier(_identifier())

    ctx = scheduled_context_from_item(
        item,
        performed_procedure_step_id="PPS000001",
        specific_character_set=UTF8,
        source_ae_title="DTG_CT01",
    )

    assert ctx.scheduled is True
    assert ctx.study_instance_uid == "2.25.1111"
    assert ctx.study_id == "RP0001"
    assert ctx.study_description == "胸部 CT"
    assert ctx.accession_number == "A0001"
    assert ctx.request_attributes is not None
    assert set(ctx.sequences) == {
        "IssuerOfAccessionNumberSequence",
        "ProcedureCodeSequence",
        "ReferencedStudySequence",
    }


def test_scheduled_context_without_study_uid_is_none() -> None:
    item = worklist_item_from_identifier(_identifier(StudyInstanceUID=""))

    ctx = scheduled_context_from_item(
        item,
        performed_procedure_step_id="PPS000001",
        specific_character_set=UTF8,
        source_ae_title="DTG_CT01",
    )

    assert ctx.study_instance_uid is None


def test_scheduled_context_rejects_unreadable_item() -> None:
    ds = _identifier()
    tag = Tag(0x00100010)
    ds[tag] = RawDataElement(tag, "PN", 4, b"\xff\xfeAB", 0, True, True)
    item = worklist_item_from_identifier(ds)

    with pytest.raises(WorklistMappingError) as exc_info:
        scheduled_context_from_item(
            item,
            performed_procedure_step_id="PPS000001",
            specific_character_set=UTF8,
            source_ae_title="DTG_CT01",
        )

    assert exc_info.value.details["attribute"] == "PatientName"


@pytest.mark.parametrize(
    ("keyword", "value", "attribute"),
    [
        ("PatientID", "P" * 17, "PatientID"),
        ("AccessionNumber", "A" * 17, "AccessionNumber"),
        ("RequestedProcedureDescription", "X" * 65, "RequestedProcedureDescription"),
    ],
)
def test_scheduled_context_enforces_length_limits(
    keyword: str, value: str, attribute: str
) -> None:
    item = worklist_item_from_identifier(_identifier(**{keyword: value}))

    with pytest.raises(WorklistMappingError) as exc_info:
        scheduled_context_from_item(
            item,
            performed_procedure_step_id="PPS000001",
            specific_character_set=UTF8,
            source_ae_title="DTG_CT01",
        )

    assert exc_info.value.details["attribute"] == attribute


def test_apply_scheduled_context_writes_table_rows() -> None:
    item = worklist_item_from_identifier(_identifier())
    ctx = scheduled_context_from_item(
        item,
        performed_procedure_step_id="PPS000001",
        specific_character_set=UTF8,
        source_ae_title="DTG_CT01",
    )
    ds = _image()

    apply_scheduled_context(ds, ctx)

    assert ds.SpecificCharacterSet == "ISO_IR 192"
    assert str(ds.PatientName) == "YAMADA^TARO=山田^太郎=やまだ^たろう"
    assert ds.PatientID == "P000001"
    assert ds.IssuerOfPatientID == "DTG"
    assert ds.PatientBirthDate == "19800115"
    assert ds.PatientSex == "M"
    assert str(ds.PatientWeight) == "65.5"
    assert str(ds.PatientSize) == "1.72"
    assert ds.PatientAge == "000Y"  # 年齢は生成側が生年月日から作る（ここでは消さない）
    assert ds.StudyInstanceUID == "2.25.9999"  # UID は生成の引数で渡す
    assert ds.AccessionNumber == "A0001"
    assert ds.IssuerOfAccessionNumberSequence[0].LocalNamespaceEntityID == "DTG_RIS"
    assert ds.ReferencedStudySequence[0].ReferencedSOPInstanceUID == "2.25.1111"
    assert str(ds.ReferringPhysicianName) == "REFERRING^DOCTOR"
    assert ds.StudyID == "RP0001"
    assert ds.StudyDescription == "胸部 CT"
    assert ds.ProcedureCodeSequence[0].CodeValue == "RPC1"
    request = ds.RequestAttributesSequence[0]
    assert request.RequestedProcedureID == "RP0001"
    assert request.RequestedProcedureDescription == "胸部 CT"
    assert request.ScheduledProcedureStepID == "SPS0001"
    assert request.ScheduledProcedureStepDescription == "胸部 単純"
    assert request.ScheduledProtocolCodeSequence[0].CodeValue == "PROT1"
    assert request.ReasonForTheRequestedProcedure == "精査"
    assert ds.PerformedProcedureStepID == "PPS000001"
    assert ds.PerformedProcedureStepStartDate == "20261018"
    assert ds.PerformedProcedureStepStartTime == "100000"
    assert ds.PerformedProcedureStepDescription == "胸部 CT"
    assert ds.InstitutionName == "Example Hospital"
    assert ds.Modality == "CT"
    assert ds.file_meta.SourceApplicationEntityTitle == "DTG_CT01"
    assert "ScheduledStationAETitle" not in ds


def test_apply_scheduled_context_with_empty_birth_date_and_sex() -> None:
    item = worklist_item_from_identifier(
        _identifier(PatientBirthDate="", PatientSex="", InstitutionName=None)
    )
    ctx = scheduled_context_from_item(
        item,
        performed_procedure_step_id="PPS000001",
        specific_character_set=UTF8,
        source_ae_title="DTG_CT01",
    )
    ds = _image()

    apply_scheduled_context(ds, ctx)

    assert ds.PatientBirthDate == ""
    assert ds.PatientSex == ""
    assert "PatientAge" not in ds
    assert ds.InstitutionName == "Template Hospital"


def test_emergency_context_follows_unscheduled_case() -> None:
    patient = ScheduledPatient(
        patient_id="E0001",
        patient_name="KINKYU^TARO=緊急^太郎",
        birth_date="19800101",
        sex="M",
    )
    ctx = emergency_context(
        patient,
        study_id="E000001",
        study_description="緊急 CT",
        performed_procedure_step_id="PPS000002",
        specific_character_set=UTF8,
        source_ae_title="DTG_CT01",
    )
    ds = _image()

    apply_scheduled_context(ds, ctx)

    assert ctx.scheduled is False
    assert ctx.study_instance_uid is None
    assert ds.AccessionNumber == ""
    assert "RequestAttributesSequence" not in ds
    assert "ReferencedStudySequence" not in ds
    assert "ProcedureCodeSequence" not in ds
    assert "IssuerOfAccessionNumberSequence" not in ds
    assert ds.ReferringPhysicianName == ""
    assert ds.IssuerOfPatientID == ""
    assert ds.StudyID == "E000001"
    assert ds.StudyDescription == "緊急 CT"
    assert ds.PerformedProcedureStepID == "PPS000002"
    assert ds.PerformedProcedureStepDescription == "緊急 CT"
    assert "PatientWeight" not in ds
    assert "PatientSize" not in ds


def test_emergency_patient_validates_values() -> None:
    with pytest.raises(ValueError):
        ScheduledPatient(patient_id="E0001", patient_name="A", birth_date="1980")
    with pytest.raises(ValueError):
        ScheduledPatient(patient_id="E0001", patient_name="A", sex="X")
    with pytest.raises(ValueError):
        ScheduledPatient(patient_id="E" * 17, patient_name="A")


def test_ensure_modality_matches() -> None:
    item = worklist_item_from_identifier(_identifier())

    ensure_modality_matches(item, "CT")
    with pytest.raises(WorklistMappingError) as exc_info:
        ensure_modality_matches(item, "MR")
    assert "予約は CT、テンプレートは MR です" in str(exc_info.value)


def test_ensure_modality_matches_accepts_empty_scheduled_modality() -> None:
    sps = _identifier().ScheduledProcedureStepSequence[0]
    sps.Modality = ""
    item = worklist_item_from_identifier(_identifier(ScheduledProcedureStepSequence=[sps]))

    ensure_modality_matches(item, "CT")


def test_build_carrier_patient_handles_empty_birth_date() -> None:
    patient = ScheduledPatient(patient_id="P1", patient_name="A^B=山田^太郎")

    carrier = build_carrier_patient(patient, study_date="20261018")

    assert carrier.patient_id == "P1"
    assert carrier.birth_date == "20261018"
    assert carrier.sex == "O"

    patient = ScheduledPatient(
        patient_id="P1", patient_name="A^B", birth_date="19800115", sex="F"
    )
    carrier = build_carrier_patient(patient, study_date="20261018")
    assert carrier.birth_date == "19800115"
    assert carrier.sex == "F"
