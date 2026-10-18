from __future__ import annotations

from unittest.mock import MagicMock

import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    ScheduledContext,
    ScheduledPatient,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
    WorklistMappingError,
)
from app.services.study_generator import StudyGeneratorService


def _make_config(tmp_path, num_series=1, images_per_series=None):
    if images_per_series is None:
        images_per_series = [1]
    return GenerationConfig(
        job_name="test",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^PATIENT"),
            birth_date="20000101",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=num_series,
        ),
        series_list=[
            SeriesConfig(series_number=i + 1, num_images=n)
            for i, n in enumerate(images_per_series)
        ],
        modality_template="ct_generic",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="",
            use_ideographic=False,
            use_phonetic=False,
        ),
    )


def test_generate_minimal(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(config=config)
    files = list(output_dir.glob("*.dcm"))

    assert output_dir == tmp_path / "output"
    assert len(files) == 1
    assert files[0].name.endswith("_0001.dcm")


def test_generate_multiple_series(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=2, images_per_series=[2, 2])

    output_dir = service.generate(config=config)
    files = list(output_dir.glob("*.dcm"))

    assert output_dir == tmp_path / "output"
    assert len(files) == 4


def test_progress_callback(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])
    progress_callback = MagicMock()

    service.generate(config=config, progress_callback=progress_callback)

    progress_callback.assert_called_once_with(1, 1)


def test_generated_file_has_dicm_preamble(tmp_path) -> None:
    """生成ファイルが DICOM File Format (128-byte preamble + DICM) であることを検証."""
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(config=config)
    dcm_file = next(output_dir.glob("*.dcm"))

    with open(dcm_file, "rb") as f:
        preamble_and_magic = f.read(132)

    assert len(preamble_and_magic) == 132
    assert preamble_and_magic[128:132] == b"DICM"


def test_sop_class_uid_consistency(tmp_path) -> None:
    """File Meta の MediaStorageSOPClassUID と Dataset の SOPClassUID が一致することを検証."""
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(config=config)
    dcm_file = next(output_dir.glob("*.dcm"))

    ds = pydicom.dcmread(str(dcm_file))
    media_storage_sop_class = str(ds.file_meta.MediaStorageSOPClassUID)
    sop_class = str(ds.SOPClassUID)

    assert media_storage_sop_class == sop_class


def test_japanese_patient_name_roundtrip(tmp_path) -> None:
    """日本語患者名の書き出し→再読込で PatientName と SpecificCharacterSet が保持されることを検証."""
    config = GenerationConfig(
        job_name="test_jp",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(
                alphabetic="TANAKA^HIROSHI",
                ideographic="田中^博",
                phonetic="タナカ^ヒロシ",
            ),
            birth_date="19980312",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        series_list=[SeriesConfig(series_number=1, num_images=1)],
        modality_template="ct_generic",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
    )

    service = StudyGeneratorService()
    output_dir = service.generate(config=config)
    dcm_file = next(output_dir.glob("*.dcm"))

    ds = pydicom.dcmread(str(dcm_file))

    assert str(ds.PatientName) == "TANAKA^HIROSHI=田中^博=タナカ^ヒロシ"
    assert ds.SpecificCharacterSet == ["ISO 2022 IR 6", "ISO 2022 IR 87"]


def test_sequence_width_minimum_four() -> None:
    assert StudyGeneratorService._sequence_width(1) == 4
    assert StudyGeneratorService._sequence_width(9999) == 4


def test_sequence_width_expands_with_total_images() -> None:
    assert StudyGeneratorService._sequence_width(10000) == 5
    assert StudyGeneratorService._sequence_width(100000) == 6


def _scheduled_context(**overrides):
    values = {
        "scheduled": True,
        "patient": ScheduledPatient(
            patient_id="P000002",
            patient_name="YAMADA^TARO=山田^太郎",
            birth_date="",
            sex="",
        ),
        "study_instance_uid": "2.25.123456789",
        "accession_number": "A0001",
        "study_id": "RP0001",
        "study_description": "胸部 CT",
        "performed_procedure_step_id": "PPS000001",
        "request_attributes": {"00401001": {"vr": "SH", "Value": ["RP0001"]}},
        "specific_character_set": ["ISO_IR 192"],
        "source_ae_title": "DTG_CT01",
    }
    values.update(overrides)
    return ScheduledContext(**values)


def test_generate_with_scheduled_context_copies_values(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[2])

    output_dir = service.generate(config=config, scheduled=_scheduled_context())
    files = sorted(output_dir.glob("*.dcm"))
    ds = pydicom.dcmread(files[0])

    assert len(files) == 2
    assert ds.StudyInstanceUID == "2.25.123456789"
    assert str(ds.PatientName) == "YAMADA^TARO=山田^太郎"
    assert ds.PatientID == "P000002"
    assert ds.PatientBirthDate == ""
    assert "PatientAge" not in ds
    assert ds.AccessionNumber == "A0001"
    assert ds.SpecificCharacterSet == "ISO_IR 192"
    assert ds.RequestAttributesSequence[0].RequestedProcedureID == "RP0001"
    assert ds.file_meta.SourceApplicationEntityTitle == "DTG_CT01"


def test_generate_with_scheduled_context_generates_study_uid_when_missing(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(
        config=config, scheduled=_scheduled_context(study_instance_uid=None)
    )
    ds = pydicom.dcmread(next(output_dir.glob("*.dcm")))

    assert ds.StudyInstanceUID.startswith("2.25.")
    assert ds.StudyInstanceUID != "2.25.123456789"


def test_generate_with_scheduled_context_stops_on_unrepresentable_char(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])
    ctx = _scheduled_context(
        patient=ScheduledPatient(patient_id="P000002", patient_name="TAKAHASHI=髙橋"),
        specific_character_set=["", "ISO 2022 IR 87"],
    )

    with pytest.raises(WorklistMappingError):
        service.generate(config=config, scheduled=ctx)

    assert list((tmp_path / "output").glob("*.dcm")) == []
