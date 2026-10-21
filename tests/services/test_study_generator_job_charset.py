"""Job の生成でも、表せない字を黙って書かない試験（PS3.3 C.12.1、PS3.5 6.1）."""

from __future__ import annotations

import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    DICOMValidationError,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.services.study_generator import StudyGeneratorService


def _config(tmp_path, *, charset: str, hospital: str | None = None, **study) -> GenerationConfig:
    return GenerationConfig(
        job_name="charset",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TANAKA^JIRO"),
            birth_date="20000101",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
            **study,
        ),
        series_list=[SeriesConfig(series_number=1, num_images=1)],
        modality_template="ct_generic",
        hospital_template=hospital,
        pixel_spec=PixelSpecSimple(width=64, height=64),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set=charset, use_ideographic=False, use_phonetic=False
        ),
    )


@pytest.mark.parametrize(
    "study",
    [
        {"referring_physician_name": "SATO^HANAKO=佐藤^花子"},
        {"study_description": "胸部CT"},
        {"study_description": "Thorax é"},
    ],
)
def test_job_with_unrepresentable_text_stops(tmp_path, study: dict) -> None:
    # 文字コードが空（ASCII だけ）の Job で、ASCII にない字を書かない
    with pytest.raises(DICOMValidationError, match="表せない字"):
        StudyGeneratorService().generate(_config(tmp_path, charset="", **study))
    assert not list((tmp_path / "output").glob("*.dcm"))


def test_unrepresentable_text_is_not_in_error_or_log(tmp_path, caplog) -> None:
    # 氏名などの字（PHI）を誤りの文とログに出さない（docs/development.md の 3.4）
    config = _config(tmp_path, charset="", referring_physician_name="SATO^HANAKO=佐藤^花子")

    with caplog.at_level("DEBUG"), pytest.raises(DICOMValidationError) as exc_info:
        StudyGeneratorService().generate(config)

    assert exc_info.value.details["attribute"] == "ReferringPhysicianName"
    assert "佐" not in str(exc_info.value)
    assert exc_info.value.__cause__ is None
    assert "佐" not in caplog.text


def test_hospital_without_charset_stops_on_japanese_description(tmp_path) -> None:
    # hospital_b は文字コードを空にする
    config = _config(
        tmp_path, charset=r"ISO 2022 IR 6\ISO 2022 IR 87", hospital="hospital_b",
        study_description="胸部CT",
    )

    with pytest.raises(DICOMValidationError):
        StudyGeneratorService().generate(config)


def test_job_with_declared_charset_writes_japanese(tmp_path) -> None:
    config = _config(
        tmp_path, charset=r"ISO 2022 IR 6\ISO 2022 IR 87", study_description="胸部CT"
    )

    output_dir = StudyGeneratorService().generate(config)

    (path,) = output_dir.glob("*.dcm")
    assert pydicom.dcmread(path).StudyDescription == "胸部CT"
