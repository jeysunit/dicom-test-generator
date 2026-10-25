"""PET/CT：同じ検査に CT のシリーズと PT のシリーズが入る（ADR-0030）."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    DICOMBuilder,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecCTRealistic,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.exceptions import DICOMBuildError, DICOMValidationError
from app.core.routine import apply_dose_report_mode, routine_series_configs
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

PT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.128"
CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"
SC_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.7"
SR_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.88.67"


def _config(
    tmp_path: Path,
    series_list: list[SeriesConfig],
    profile: str | None = None,
    pixel_spec: PixelSpecSimple | PixelSpecCTRealistic | None = None,
) -> GenerationConfig:
    return GenerationConfig(
        job_name="petct",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P1",
            patient_name=PatientName(alphabetic="TEST^PET"),
            birth_date="19800101",
            sex="F",
            weight=60.0,
            size=165.0,
        ),
        study=StudyConfig(
            accession_number="A1",
            study_date="20261025",
            study_time="110000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template="petct_generic",
        device_profile=profile,
        pixel_spec=pixel_spec or PixelSpecCTRealistic(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _in_written_order(output: Path) -> list[Path]:
    """書いた順（ファイル名の最後の連番）。名前の途中のモダリティ（CT・PT・SR）では並べない."""
    return sorted(output.glob("*.dcm"), key=lambda path: int(path.stem.rsplit("_", 1)[1]))


def _generate_routine(
    tmp_path: Path, name: str = "pt_whole_body", mode: str = "screen", **kwargs
) -> dict[str, list]:
    routine = RoutineLoaderService().get(name)
    keep = list(range(len(routine.series)))
    routine, keep, images = apply_dose_report_mode(routine, keep, [2] * len(keep), mode)
    series_list = routine_series_configs(
        routine, list(range(1, len(keep) + 1)), keep, images
    )
    output = StudyGeneratorService().generate(_config(tmp_path, series_list, **kwargs))
    by_description: dict[str, list] = {}
    for path in _in_written_order(output):
        ds = pydicom.dcmread(path)
        by_description.setdefault(str(ds.SeriesDescription), []).append(ds)
    return by_description


@pytest.fixture(scope="module")
def study(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list]:
    return _generate_routine(tmp_path_factory.mktemp("petct"), mode="both")


def _all(study: dict[str, list]) -> list[pydicom.Dataset]:
    return [ds for series in study.values() for ds in series]


def test_one_study_has_ct_pt_and_sr_series(study) -> None:
    datasets = _all(study)

    assert {ds.Modality for ds in datasets} == {"CT", "PT", "SR"}
    assert len({ds.StudyInstanceUID for ds in datasets}) == 1
    assert list(study) == [
        "Topogram",
        "CT WB 3mm",
        "PET WB AC",
        "PET WB NAC",
        "Dose Report",
        "Radiation Dose SR",
    ]


def test_each_series_has_one_modality_and_its_sop_class(study) -> None:
    expected = {
        "Topogram": ("CT", CT_SOP_CLASS),
        "CT WB 3mm": ("CT", CT_SOP_CLASS),
        "PET WB AC": ("PT", PT_SOP_CLASS),
        "PET WB NAC": ("PT", PT_SOP_CLASS),
        "Dose Report": ("CT", SC_SOP_CLASS),
        "Radiation Dose SR": ("SR", SR_SOP_CLASS),
    }
    for description, (modality, sop_class) in expected.items():
        for ds in study[description]:
            assert (ds.Modality, ds.SOPClassUID) == (modality, sop_class), description
            assert ds.file_meta.MediaStorageSOPClassUID == sop_class


def test_ct_and_pt_share_the_frame_of_reference_and_the_geometry(study) -> None:
    ct = study["CT WB 3mm"]
    pt = study["PET WB AC"]

    assert {ds.FrameOfReferenceUID for ds in ct + pt} == {ct[0].FrameOfReferenceUID}
    assert [float(v) for v in pt[0].ImageOrientationPatient] == [1, 0, 0, 0, 1, 0]
    assert float(pt[1].SliceLocation) - float(pt[0].SliceLocation) == pytest.approx(3.27)
    assert float(pt[0].SliceThickness) == pytest.approx(3.27)
    assert float(ct[1].SliceLocation) - float(ct[0].SliceLocation) == pytest.approx(3.0)


def test_pet_series_module(study) -> None:
    ds = study["PET WB AC"][0]

    # PS3.3 C.8.9.1 の Type 1・Type 2
    assert ds.SeriesDate == "20261025" and ds.SeriesTime == "110000"
    assert ds.Units == "BQML"
    assert ds.CountsSource == "EMISSION"
    assert list(ds.SeriesType) == ["WHOLE BODY", "IMAGE"]
    assert ds.NumberOfSlices == 2
    assert ds.DecayCorrection == "START"
    assert ds.CollimatorType == "NONE"
    assert "CorrectedImage" in ds


def test_attenuation_correction_differs_between_ac_and_nac(study) -> None:
    ac = list(study["PET WB AC"][0].CorrectedImage)
    nac = list(study["PET WB NAC"][0].CorrectedImage)

    assert {"ATTN", "SCAT"} <= set(ac)
    assert not {"ATTN", "SCAT"} & set(nac)
    assert {"DECY"} <= set(nac)


def test_pet_isotope_module_is_fdg(study) -> None:
    (item,) = study["PET WB AC"][0].RadiopharmaceuticalInformationSequence

    assert item.RadionuclideCodeSequence[0].CodeValue == "77004003"
    assert item.RadionuclideCodeSequence[0].CodeMeaning == "^18^Fluorine"
    assert item.RadiopharmaceuticalCodeSequence[0].CodeValue == "35321007"
    assert float(item.RadionuclideHalfLife) == pytest.approx(6586.2)
    # 投与は撮影の 60 分前
    assert item.RadiopharmaceuticalStartDateTime == "20261025100000"


def test_pet_image_module_and_pixels(study) -> None:
    ds = study["PET WB AC"][1]

    assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY"]
    assert ds.ImageIndex == 2
    assert float(ds.RescaleIntercept) == 0.0  # PET では常に 0（C.8.9.4）
    assert float(ds.RescaleSlope) == 1.0
    assert ds.FrameReferenceTime == "0"
    assert ds.ActualFrameDuration == 120000
    assert float(ds.DecayFactor) > 1.0  # Decay Correction が NONE でないときは必須（1C）
    assert (ds.BitsAllocated, ds.BitsStored, ds.HighBit) == (16, 16, 15)
    assert ds.PixelRepresentation == 0
    assert ds.pixel_array.dtype == np.uint16
    assert (ds.Rows, ds.Columns) == (128, 128)
    assert [float(v) for v in ds.PixelSpacing] == pytest.approx([700 / 128, 700 / 128])
    assert "PatientOrientationCodeSequence" in ds  # NM/PET Patient Orientation（Type 2）
    assert "KVP" not in ds


def test_ct_series_keep_the_ct_values_of_the_template(study) -> None:
    ds = study["CT WB 3mm"][0]

    assert ds.Modality == "CT"
    assert ds.KVP == "120"
    assert ds.BitsAllocated == 16 and (ds.Rows, ds.Columns) == (512, 512)
    assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY", "AXIAL"]


def test_the_dose_report_covers_the_ct_exposures_only(study) -> None:
    sr = study["Radiation Dose SR"][0]

    names = [item.ConceptNameCodeSequence[0].CodeMeaning for item in sr.ContentSequence]
    assert names.count("CT Acquisition") == 2  # Topogram と CT。PET は撮影に入れない


def test_pet_first_routine_sends_pt_before_ct(tmp_path: Path) -> None:
    study = _generate_routine(tmp_path, "pt_whole_body_pet_first")

    assert list(study) == ["PET WB AC", "PET WB NAC", "Topogram", "CT WB 3mm", "Dose Report"]
    assert {ds.Modality for ds in _all(study)} == {"PT", "CT"}


def test_simple_text_pet_is_scaled_to_the_signed_range(tmp_path: Path) -> None:
    study = _generate_routine(tmp_path, pixel_spec=PixelSpecSimple())

    ds = study["PET WB AC"][0]
    assert int(ds.pixel_array.max()) == 32767
    assert (ds.Rows, ds.Columns) == (128, 128)


def test_device_profile_gives_the_pet_ct_device_values(tmp_path: Path) -> None:
    study = _generate_routine(tmp_path, profile="dtg_synthetic_petct")

    datasets = _all(study)
    assert {ds.ManufacturerModelName for ds in datasets} == {"DTG Synthetic PET/CT 128"}
    assert {ds.DeviceSerialNumber for ds in datasets} == {"DTG000789"}
    assert {ds.BodyPartExamined for ds in datasets} == {"WHOLEBODY"}
    assert {ds.file_meta.ImplementationVersionName for ds in datasets} == {"DTG_PETCT_120"}


def test_manual_series_under_the_petct_template(tmp_path: Path) -> None:
    series = [
        SeriesConfig(series_number=1, num_images=1, kind="localizer"),
        SeriesConfig(series_number=2, num_images=1),
        SeriesConfig(series_number=3, num_images=1, kind="dose_report"),
    ]

    output = StudyGeneratorService().generate(_config(tmp_path, series))

    modalities = [pydicom.dcmread(p).Modality for p in _in_written_order(output)]
    assert modalities == ["CT", "PT", "CT"]


@pytest.mark.parametrize("kind", ["coronal", "sagittal"])
def test_ct_only_kind_cannot_be_made_with_the_petct_template(tmp_path: Path, kind: str) -> None:
    series = [SeriesConfig(series_number=1, num_images=1, kind=kind)]

    with pytest.raises(DICOMValidationError, match="cannot be made with the PT template"):
        StudyGeneratorService().generate(_config(tmp_path, series))


def test_pet_series_kind_needs_the_pt_modality() -> None:
    with pytest.raises(ValueError, match="needs modality PT"):
        SeriesConfig(series_number=1, num_images=1, kind="pet_ac")
    with pytest.raises(ValueError, match="needs modality PT"):
        SeriesConfig(series_number=1, num_images=1, kind="pet_ac", modality="CT")
    with pytest.raises(ValueError, match="not an PT series kind"):
        SeriesConfig(series_number=1, num_images=1, kind="axial", modality="PT")
    with pytest.raises(ValueError, match="contrast is not supported"):
        SeriesConfig(series_number=1, num_images=1, kind="pet_ac", modality="PT", contrast=True)


def test_negative_pet_pixels_are_refused() -> None:
    ds = pydicom.Dataset()

    with pytest.raises(DICOMBuildError, match="must not be negative"):
        DICOMBuilder._set_pt_pixel_data(ds, np.full((4, 4), -1, dtype=np.int16))
