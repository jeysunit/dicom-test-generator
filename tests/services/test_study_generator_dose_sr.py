"""CT の検査に入る線量の報告の SR（X-Ray Radiation Dose SR。ADR-0029）."""

from __future__ import annotations

from pathlib import Path

import pydicom
import pytest

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
from app.core.dose_sr import XRAY_RADIATION_DOSE_SR_STORAGE
from app.core.exceptions import DICOMBuildError
from app.services.study_generator import StudyGeneratorService

SR_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.88.67"


def _series(with_exposure: bool = True) -> list[SeriesConfig]:
    series = []
    if with_exposure:
        series += [
            SeriesConfig(series_number=1, num_images=1, kind="localizer"),
            SeriesConfig(series_number=2, num_images=3, kind="axial"),
        ]
    series.append(SeriesConfig(series_number=3, num_images=1, kind="dose_report"))
    series.append(
        SeriesConfig(
            series_number=4,
            num_images=1,
            kind="dose_sr",
            series_description="Radiation Dose SR",
        )
    )
    return series


def _config(
    tmp_path: Path,
    series_list: list[SeriesConfig],
    profile: str | None = None,
    abnormal: str = "none",
    template: str = "ct_generic",
) -> GenerationConfig:
    return GenerationConfig(
        job_name="sr",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P1",
            patient_name=PatientName(alphabetic="TEST^SR"),
            birth_date="19800101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A1",
            study_date="20261025",
            study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template=template,
        device_profile=profile,
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
        abnormal={"level": abnormal},
    )


def _generate(tmp_path: Path, **kwargs) -> list[pydicom.Dataset]:
    output = StudyGeneratorService().generate(_config(tmp_path, **kwargs))
    return [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]


@pytest.fixture(scope="module")
def study(tmp_path_factory: pytest.TempPathFactory) -> list[pydicom.Dataset]:
    return _generate(tmp_path_factory.mktemp("sr"), series_list=_series())


def _sr(study: list[pydicom.Dataset]) -> pydicom.Dataset:
    (ds,) = [d for d in study if d.get("Modality") == "SR"]
    return ds


def test_study_has_ct_images_the_dose_screen_and_one_sr(study) -> None:
    assert [d.Modality for d in study] == ["CT"] * 5 + ["SR"]
    assert study[-2].SOPClassUID == "1.2.840.10008.5.1.4.1.1.7"  # 線量の画面（SC）


def test_file_names_follow_the_written_order(tmp_path: Path) -> None:
    """モダリティが混ざっても、名前の順が書いた順（送る順）になる."""
    output = StudyGeneratorService().generate(_config(tmp_path, _series()))

    names = [path.name for path in sorted(output.glob("*.dcm"))]
    assert names == [f"P1_20261025_CT_{index:04d}.dcm" for index in range(1, 7)]


def test_sr_is_in_the_same_study_as_the_images(study) -> None:
    sr = _sr(study)

    assert len({d.StudyInstanceUID for d in study}) == 1
    assert sr.SeriesNumber == "4"
    assert sr.SeriesInstanceUID not in {d.SeriesInstanceUID for d in study if d is not sr}
    assert sr.AccessionNumber == "A1"
    assert sr.PatientID == "P1"


def test_sr_sop_class_and_file_meta(study) -> None:
    sr = _sr(study)

    assert sr.SOPClassUID == SR_SOP_CLASS == XRAY_RADIATION_DOSE_SR_STORAGE
    assert sr.file_meta.MediaStorageSOPClassUID == SR_SOP_CLASS
    assert sr.file_meta.MediaStorageSOPInstanceUID == sr.SOPInstanceUID


def test_sr_document_modules(study) -> None:
    sr = _sr(study)

    # SR Document Series（PS3.3 C.17.1）・SR Document General（C.17.2）
    assert sr.Modality == "SR"
    assert sr.SeriesDescription == "Radiation Dose SR"
    assert sr.InstanceNumber == "1"
    assert sr.CompletionFlag == "COMPLETE"
    assert sr.VerificationFlag == "UNVERIFIED"
    assert sr.ContentDate == "20261025" and sr.ContentTime == "090000"
    assert "PerformedProcedureCodeSequence" in sr
    assert "ReferencedPerformedProcedureStepSequence" in sr
    # Enhanced General Equipment（C.7.5.2）の Type 1
    for keyword in ("Manufacturer", "ManufacturerModelName", "DeviceSerialNumber", "SoftwareVersions"):
        assert sr.get(keyword), keyword


def test_sr_has_no_image_attributes(study) -> None:
    sr = _sr(study)

    for keyword in ("PixelData", "Rows", "FrameOfReferenceUID", "KVP", "PatientPosition"):
        assert keyword not in sr, keyword


def test_sr_content_refers_to_the_study_and_the_exposures(study) -> None:
    sr = _sr(study)

    assert sr.ValueType == "CONTAINER"
    assert sr.ConceptNameCodeSequence[0].CodeValue == "113701"
    names = [item.ConceptNameCodeSequence[0].CodeMeaning for item in sr.ContentSequence]
    assert names.count("CT Acquisition") == 2  # 位置決めと軸位。線量の画面と SR は撮影ではない
    (scope,) = [
        item
        for item in sr.ContentSequence
        if item.ConceptNameCodeSequence[0].CodeMeaning == "Scope of Accumulation"
    ]
    assert scope.ContentSequence[0].UID == sr.StudyInstanceUID


def test_sr_text_is_ascii_and_dataset_round_trips(tmp_path: Path, study) -> None:
    sr = _sr(study)
    path = tmp_path / "sr.dcm"

    pydicom.dcmwrite(path, sr, enforce_file_format=True)

    again = pydicom.dcmread(path)
    assert again.ContentSequence[0].ConceptCodeSequence[0].CodeValue == "77477000"


def test_sr_series_without_an_exposure_is_refused(tmp_path: Path) -> None:
    with pytest.raises(DICOMBuildError, match="at least one localizer or axial"):
        _generate(tmp_path, series_list=_series(with_exposure=False))


def test_empty_equipment_values_are_filled_for_the_sr() -> None:
    """Enhanced General Equipment は Type 1。テンプレートが空にしても空では出さない."""
    ds = pydicom.Dataset()
    ds.Manufacturer = ""
    ds.SoftwareVersions = "V1"

    StudyGeneratorService._keep_sr_shape(ds)

    assert ds.Manufacturer == "DTG Synthetic"
    assert ds.ManufacturerModelName == "DTG Synthetic"
    assert ds.DeviceSerialNumber == "DTG0001"
    assert ds.SoftwareVersions == "V1"  # 入っている値は変えない


def test_sr_with_a_device_profile_drops_image_attributes(tmp_path: Path) -> None:
    study = _generate(tmp_path, series_list=_series(), profile="dtg_synthetic_ct")

    sr = _sr(study)
    assert sr.ManufacturerModelName == "DTG Synthetic CT 64"
    assert sr.DeviceSerialNumber == "DTG000123"  # プロファイルの値が既定の値に勝つ
    assert "SliceLocation" not in sr


@pytest.mark.parametrize("level", ["mild", "moderate", "severe"])
def test_sr_survives_the_abnormal_levels(tmp_path: Path, level: str) -> None:
    study = _generate(tmp_path, series_list=_series(), abnormal=level)

    # 異常のデータは値を壊す（Modality も）。SR も含め、全部書き出せる
    assert len(study) == 6


def test_sr_under_an_mr_template_is_refused_for_lack_of_exposures(tmp_path: Path) -> None:
    series = [
        SeriesConfig(series_number=1, num_images=1, kind="acquisition", modality="MR"),
        SeriesConfig(series_number=2, num_images=1, kind="dose_sr"),
    ]

    with pytest.raises(DICOMBuildError, match="at least one localizer or axial"):
        _generate(tmp_path, series_list=series, template="mr_generic")


def test_dose_sr_kind_needs_the_sr_modality() -> None:
    with pytest.raises(ValueError, match="needs modality SR"):
        SeriesConfig(series_number=1, num_images=1, kind="dose_sr", modality="CT")
    with pytest.raises(ValueError, match="not an SR series kind"):
        SeriesConfig(series_number=1, num_images=1, kind="axial", modality="SR")
