"""生成したファイルの UID の一意・Type 2 の属性の試験（PS3.5 9、PS3.3 C.7.2.1・C.7.5.1）."""

from __future__ import annotations

import pydicom

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.uid_format import is_valid_uid
from app.services.study_generator import StudyGeneratorService
from app.services.template_loader import TemplateLoaderService

UID_KEYWORDS = ("StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID", "FrameOfReferenceUID")


def _config(tmp_path, name: str, **overrides) -> GenerationConfig:
    values = {
        "job_name": name,
        "output_dir": str(tmp_path / name),
        "patient": Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^PATIENT"),
            birth_date="20000101",
            sex="M",
        ),
        "study": StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        "series_list": [SeriesConfig(series_number=1, num_images=2)],
        "modality_template": "ct_generic",
        "pixel_spec": PixelSpecSimple(width=64, height=64),
        "transfer_syntax": TransferSyntaxConfig(),
        "character_set": CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    }
    values.update(overrides)
    return GenerationConfig(**values)


def _read(tmp_path, name: str, **overrides) -> list[pydicom.Dataset]:
    output_dir = StudyGeneratorService().generate(_config(tmp_path, name, **overrides))
    return [pydicom.dcmread(p) for p in sorted(output_dir.glob("*.dcm"))]


def _uids(datasets: list[pydicom.Dataset]) -> set[str]:
    return {str(ds[k].value) for ds in datasets for k in UID_KEYWORDS}


# 違反 2：custom_root で 2 回生成しても UID が重ならない（PS3.5 9）


def test_custom_root_generations_do_not_share_uids(tmp_path) -> None:
    custom = {"uid_method": "custom_root", "uid_custom_root": "1.2.392.999"}

    first = _read(tmp_path, "first", **custom)
    second = _read(tmp_path, "second", **custom)

    assert not _uids(first) & _uids(second)
    for ds in first + second:
        for keyword in UID_KEYWORDS:
            uid = str(ds[keyword].value)
            assert uid.startswith("1.2.392.999.")
            assert is_valid_uid(uid)


# 違反 8：Referring Physician's Name は Type 2（PS3.3 C.7.2.1）


def test_referring_physician_name_is_present_even_when_unknown(tmp_path) -> None:
    for ds in _read(tmp_path, "no_referrer"):
        assert "ReferringPhysicianName" in ds
        assert ds.ReferringPhysicianName == ""


# 違反 7：病院テンプレートを重ねても Manufacturer は残る（PS3.3 C.7.5.1、Type 2）


def test_hospital_template_keeps_modality_manufacturer() -> None:
    merged = TemplateLoaderService().merge_templates("ct_generic", "hospital_a")

    assert merged["general_equipment"]["manufacturer"] == "DTG Synthetic"
    assert merged["general_equipment"]["institution_name"] == "A Hospital"
    assert merged["general_equipment"]["station_name"] == "CT_A_01"


def test_merge_does_not_change_loaded_modality_template() -> None:
    service = TemplateLoaderService()
    before = service.load_modality_template("ct_generic")

    service.merge_templates("ct_generic", "hospital_b")

    assert service.load_modality_template("ct_generic") == before


def test_generated_file_with_hospital_template_has_manufacturer(tmp_path) -> None:
    for ds in _read(tmp_path, "hospital_b", hospital_template="hospital_b"):
        assert ds.Manufacturer == "DTG Synthetic"
        assert ds.InstitutionName == "B Hospital"
