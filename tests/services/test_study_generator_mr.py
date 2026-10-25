"""MR の画像（MR Image Storage。ADR-0028）."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecCTRealistic,
    PixelSpecSimple,
    ProfileMismatchError,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.device_profile import ProfileAttributes
from app.core.exceptions import DICOMValidationError
from app.core.generator import MR_IMAGE_STORAGE
from app.core.routine import routine_series_configs
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

MR_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.4"


def _config(
    tmp_path: Path,
    series_list: list[SeriesConfig],
    template: str = "mr_generic",
    profile: str | None = None,
    pixel_spec: PixelSpecSimple | PixelSpecCTRealistic | None = None,
) -> GenerationConfig:
    return GenerationConfig(
        job_name="mr",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P1",
            patient_name=PatientName(alphabetic="TEST^MR"),
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
        pixel_spec=pixel_spec or PixelSpecCTRealistic(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _generate_routine(tmp_path: Path, name: str, images: int = 2, **kwargs) -> dict[str, list]:
    routine = RoutineLoaderService().get(name)
    keep = list(range(len(routine.series)))
    series_list = routine_series_configs(
        routine, [index + 1 for index in keep], keep, [images] * len(keep)
    )
    output = StudyGeneratorService().generate(_config(tmp_path, series_list, **kwargs))
    by_description: dict[str, list] = {}
    for path in sorted(output.glob("*.dcm")):
        ds = pydicom.dcmread(path)
        by_description.setdefault(str(ds.SeriesDescription), []).append(ds)
    return by_description


@pytest.fixture(scope="module")
def head(tmp_path_factory: pytest.TempPathFactory) -> dict[str, list]:
    return _generate_routine(tmp_path_factory.mktemp("mr_head"), "mr_head")


def test_every_image_is_an_mr_image(head: dict[str, list]) -> None:
    datasets = [ds for series in head.values() for ds in series]

    assert {ds.Modality for ds in datasets} == {"MR"}
    assert {ds.SOPClassUID for ds in datasets} == {MR_SOP_CLASS}
    assert {ds.file_meta.MediaStorageSOPClassUID for ds in datasets} == {MR_SOP_CLASS}
    assert MR_SOP_CLASS == MR_IMAGE_STORAGE


def test_series_follow_the_routine_order(head: dict[str, list]) -> None:
    assert list(head) == [
        "Localizer",
        "DWI b1000",
        "ADC",
        "T2*",
        "T1 SAG",
        "T2 AX",
        "FLAIR",
        "TOF MRA",
    ]
    assert {ds.ProtocolName for series in head.values() for ds in series} == {"BRAIN ROUTINE"}


def test_mr_image_module_type_1_and_2_attributes(head: dict[str, list]) -> None:
    for series in head.values():
        for ds in series:
            # PS3.3 C.8.3.1 の Type 1・Type 2
            assert ds.ImageType[0] in ("ORIGINAL", "DERIVED")
            assert ds.SamplesPerPixel == 1
            assert ds.PhotometricInterpretation == "MONOCHROME2"
            assert ds.BitsAllocated == 16
            assert ds.HighBit == ds.BitsStored - 1
            assert ds.ScanningSequence in ("SE", "IR", "GR", "EP")
            assert "SequenceVariant" in ds
            assert "ScanOptions" in ds
            assert ds.MRAcquisitionType in ("2D", "3D")
            assert "EchoTime" in ds
            assert "EchoTrainLength" in ds
            # Repetition Time は Scanning Sequence が EP でないか Variant が SK のとき必須
            assert "RepetitionTime" in ds


def test_pixels_are_unsigned_16_bit(head: dict[str, list]) -> None:
    ds = head["T2 AX"][0]
    pixels = ds.pixel_array

    assert ds.PixelRepresentation == 0
    assert pixels.dtype == np.uint16
    assert int(pixels.max()) < 1 << ds.BitsStored
    # MR の画素間隔は視野 240 mm ÷ 画素数
    assert [float(v) for v in ds.PixelSpacing] == [240 / ds.Rows, 240 / ds.Columns]
    assert "RescaleSlope" not in ds
    assert "KVP" not in ds


@pytest.mark.parametrize(
    ("description", "sequence", "acquisition"),
    [
        ("Localizer", "GR", "2D"),
        ("DWI b1000", "EP", "2D"),
        ("T2*", "GR", "2D"),
        ("T2 AX", "SE", "2D"),
        ("FLAIR", "IR", "2D"),
        ("TOF MRA", "GR", "3D"),
    ],
)
def test_sequence_and_acquisition_type(
    head: dict[str, list], description: str, sequence: str, acquisition: str
) -> None:
    ds = head[description][0]

    assert ds.ScanningSequence == sequence
    assert ds.MRAcquisitionType == acquisition


def test_inversion_time_only_for_inversion_recovery(head: dict[str, list]) -> None:
    # Inversion Time は Scanning Sequence が IR のとき必須（Type 2C。PS3.3 C.8.3.1）
    assert float(head["FLAIR"][0].InversionTime) == 2500.0
    assert "InversionTime" not in head["T2 AX"][0]


def test_derived_series_is_marked_derived(head: dict[str, list]) -> None:
    assert list(head["ADC"][0].ImageType) == ["DERIVED", "SECONDARY"]
    assert list(head["T2 AX"][0].ImageType) == ["ORIGINAL", "PRIMARY", "M", "ND"]


def test_planes_set_orientation_and_the_slice_gap(head: dict[str, list]) -> None:
    sagittal = head["T1 SAG"]
    axial = head["T2 AX"]

    assert [float(v) for v in sagittal[0].ImageOrientationPatient] == [0, 1, 0, 0, 0, -1]
    assert [float(v) for v in axial[0].ImageOrientationPatient] == [1, 0, 0, 0, 1, 0]
    # 5mm／1mm のすきま：画像の間隔は 6mm
    assert float(axial[1].SliceLocation) - float(axial[0].SliceLocation) == 6.0
    assert float(axial[0].SpacingBetweenSlices) == 6.0
    assert float(axial[0].SliceThickness) == 5.0


def test_one_frame_of_reference_for_the_study(head: dict[str, list]) -> None:
    datasets = [ds for series in head.values() for ds in series]

    assert len({ds.FrameOfReferenceUID for ds in datasets}) == 1
    assert len({ds.StudyInstanceUID for ds in datasets}) == 1
    assert len({ds.SeriesInstanceUID for ds in datasets}) == len(head)


def test_template_gives_the_magnet_and_equipment(head: dict[str, list]) -> None:
    ds = head["T2 AX"][0]

    assert ds.MagneticFieldStrength == "1.5" or float(ds.MagneticFieldStrength) == 1.5
    assert ds.ImagedNucleus == "1H"
    assert ds.Manufacturer == "DTG Synthetic"
    assert ds.ManufacturerModelName == "DTG Synthetic MR"
    assert ds.StationName == "DTG_MR"


def test_manual_series_with_an_mr_template_makes_mr_acquisitions(tmp_path: Path) -> None:
    series = [SeriesConfig(series_number=1, num_images=2)]

    output = StudyGeneratorService().generate(_config(tmp_path, series))

    datasets = [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]
    assert {ds.Modality for ds in datasets} == {"MR"}
    assert {ds.SOPClassUID for ds in datasets} == {MR_SOP_CLASS}
    assert list(datasets[0].ImageType) == ["ORIGINAL", "PRIMARY", "M", "ND"]


def test_simple_text_pixels_are_scaled_to_the_stored_bits(tmp_path: Path) -> None:
    series = [SeriesConfig(series_number=1, num_images=1)]

    output = StudyGeneratorService().generate(
        _config(tmp_path, series, pixel_spec=PixelSpecSimple())
    )

    (ds,) = [pydicom.dcmread(path) for path in output.glob("*.dcm")]
    assert ds.PixelRepresentation == 0
    assert int(ds.pixel_array.max()) == (1 << ds.BitsStored) - 1


def test_mr_profile_gives_the_device_values(tmp_path: Path) -> None:
    routine = RoutineLoaderService().get("mr_head")
    series = routine_series_configs(routine, [1], [0], [2])

    output = StudyGeneratorService().generate(
        _config(tmp_path, series, profile="dtg_synthetic_mr")
    )

    datasets = [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]
    assert {ds.Modality for ds in datasets} == {"MR"}
    assert {ds.ManufacturerModelName for ds in datasets} == {"DTG Synthetic MR 1.5T"}
    assert {ds.DeviceSerialNumber for ds in datasets} == {"DTG000456"}
    assert {ds.BodyPartExamined for ds in datasets} == {"HEAD"}
    assert {ds.file_meta.ImplementationVersionName for ds in datasets} == {"DTG_MR_301"}


def test_ct_profile_does_not_fit_an_mr_template(tmp_path: Path) -> None:
    series = [SeriesConfig(series_number=1, num_images=1)]

    with pytest.raises(ProfileMismatchError, match="does not match template modality"):
        StudyGeneratorService().generate(_config(tmp_path, series, profile="dtg_synthetic_ct"))


def test_explicit_ct_series_keeps_the_ct_sop_class_under_an_mr_template(tmp_path: Path) -> None:
    series = [SeriesConfig(series_number=1, num_images=1, modality="CT")]

    output = StudyGeneratorService().generate(_config(tmp_path, series))

    (ds,) = [pydicom.dcmread(path) for path in output.glob("*.dcm")]
    assert ds.Modality == "CT"
    assert ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.2"
    assert ds.file_meta.MediaStorageSOPClassUID == "1.2.840.10008.5.1.4.1.1.2"
    assert "ScanningSequence" not in ds


@pytest.mark.parametrize("kind", ["coronal", "sagittal", "dose_report"])
def test_ct_only_kind_cannot_be_made_with_an_mr_template(tmp_path: Path, kind: str) -> None:
    series = [SeriesConfig(series_number=1, num_images=1, kind=kind)]

    with pytest.raises(DICOMValidationError, match="cannot be made with the MR template"):
        StudyGeneratorService().generate(_config(tmp_path, series))


def test_mr_series_has_no_contrast() -> None:
    with pytest.raises(ValueError, match="contrast is not supported"):
        SeriesConfig(series_number=1, num_images=1, kind="acquisition", modality="MR", contrast=True)


@pytest.mark.parametrize("keyword", ["RepetitionTime", "InversionTime", "ScanningSequence"])
def test_profile_cannot_omit_the_mr_required_attributes(keyword: str) -> None:
    with pytest.raises(ValueError, match="cannot be omitted"):
        ProfileAttributes.model_validate({"omit": [keyword]})


def test_explicit_mr_series_stays_mr_under_a_ct_template(tmp_path: Path) -> None:
    routine = RoutineLoaderService().get("mr_head")
    series = routine_series_configs(routine, [1], [1], [1])

    output = StudyGeneratorService().generate(_config(tmp_path, series, template="ct_generic"))

    # 明示した MR のシリーズは、CT のテンプレートでも MR の画像になる（テンプレートの
    # 撮影の値だけが CT）。予約との食い違いは撮影の入口（ModalityService）が断る
    (ds,) = [pydicom.dcmread(path) for path in output.glob("*.dcm")]
    assert ds.Modality == "MR"
    assert "KVP" not in ds
