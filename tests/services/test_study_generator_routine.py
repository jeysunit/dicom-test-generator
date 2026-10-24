"""ルーチンのシリーズの種類ごとの画像（CT と線量の画面の Secondary Capture。ADR-0025）."""

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
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.generator import CT_IMAGE_STORAGE, SECONDARY_CAPTURE_IMAGE_STORAGE
from app.core.routine import ct_series_configs
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

# 胸部 単純の各シリーズを 2〜3 枚に減らして作る（並びと種類を見る）
CHEST_IMAGES = [1, 2, 2, 2, 3, 1]


def _generate(tmp_path: Path, routine_name: str, images: list[int]) -> dict[int, list]:
    routine = RoutineLoaderService().get(routine_name)
    keep = list(range(len(routine.series)))
    series_list = ct_series_configs(routine, [index + 1 for index in keep], keep, images)
    config = GenerationConfig(
        job_name="routine",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P1",
            patient_name=PatientName(alphabetic="TEST^ROUTINE"),
            birth_date="19800101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A1",
            study_date="20261024",
            study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template="ct_generic",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )
    output = StudyGeneratorService().generate(config)
    by_series: dict[int, list] = {}
    for path in sorted(output.glob("*.dcm")):
        ds = pydicom.dcmread(path)
        by_series.setdefault(int(ds.SeriesNumber), []).append(ds)
    return by_series


@pytest.fixture(scope="module")
def chest(tmp_path_factory: pytest.TempPathFactory) -> dict[int, list]:
    return _generate(tmp_path_factory.mktemp("chest"), "ct_chest_plain", CHEST_IMAGES)


def test_series_follow_the_routine(chest: dict[int, list]) -> None:
    assert [len(chest[number]) for number in sorted(chest)] == CHEST_IMAGES
    assert [chest[number][0].SeriesDescription for number in sorted(chest)] == [
        "Scout",
        "Mediastinum 5mm",
        "Lung 5mm",
        "Lung 1mm",
        "COR 3mm",
        "Dose Report",
    ]
    assert {ds.ProtocolName for series in chest.values() for ds in series} == {"CHEST ROUTINE"}


def test_localizer(chest: dict[int, list]) -> None:
    ds = chest[1][0]

    assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY", "LOCALIZER"]
    assert [float(v) for v in ds.ImageOrientationPatient] == [1, 0, 0, 0, 0, -1]
    assert ds.SOPClassUID == CT_IMAGE_STORAGE


def test_axial_series_keep_the_routine_thickness(chest: dict[int, list]) -> None:
    lung = chest[4]

    assert list(lung[0].ImageType) == ["ORIGINAL", "PRIMARY", "AXIAL"]
    assert float(lung[0].SliceThickness) == 1.0
    assert float(lung[1].ImagePositionPatient[2]) - float(lung[0].ImagePositionPatient[2]) == 1.0


def test_coronal_series(chest: dict[int, list]) -> None:
    coronal = chest[5]

    assert list(coronal[0].ImageType) == ["DERIVED", "SECONDARY", "AXIAL"]
    assert [float(v) for v in coronal[0].ImageOrientationPatient] == [1, 0, 0, 0, 0, -1]
    ys = [float(ds.ImagePositionPatient[1]) for ds in coronal]
    assert ys == [0.0, 3.0, 6.0]


def test_dose_report_is_a_secondary_capture(chest: dict[int, list]) -> None:
    ds = chest[6][0]

    assert ds.SOPClassUID == SECONDARY_CAPTURE_IMAGE_STORAGE
    assert ds.file_meta.MediaStorageSOPClassUID == SECONDARY_CAPTURE_IMAGE_STORAGE
    assert ds.Modality == "CT"
    assert list(ds.ImageType) == ["DERIVED", "SECONDARY"]
    assert ds.ConversionType == "WSD"
    assert "PatientOrientation" in ds and ds.PatientOrientation == ""
    assert ds.BitsAllocated == 8 and ds.PixelRepresentation == 0
    for keyword in (
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "FrameOfReferenceUID",
        "RescaleIntercept",
        "KVP",
        "SliceThickness",
    ):
        assert keyword not in ds, keyword
    # 同じ Study の画像（患者と Study の値は CT の画像と同じ）
    assert ds.StudyInstanceUID == chest[1][0].StudyInstanceUID
    assert ds.PatientID == "P1"


def test_secondary_capture_shape_survives_a_profile() -> None:
    """装置のプロファイルが CT の属性を足しても、SC の必須の属性を外しても、SC の形に戻す."""
    from pydicom.dataset import Dataset

    ds = Dataset()
    ds.KVP = "120"
    ds.ImagePositionPatient = [0, 0, 0]
    ds.FrameOfReferenceUID = "2.25.1"

    StudyGeneratorService._keep_secondary_capture_shape(ds)

    assert "KVP" not in ds and "ImagePositionPatient" not in ds
    assert "FrameOfReferenceUID" not in ds
    assert ds.ConversionType == "WSD"
    assert ds.PatientOrientation == ""


def test_contrast_series_have_the_contrast_agent(tmp_path: Path) -> None:
    study = _generate(tmp_path, "ct_abdomen_pelvis", [1, 1, 1, 1, 1, 1])

    assert "ContrastBolusAgent" not in study[2][0]  # AX 5mm（単純）
    assert study[3][0].ContrastBolusAgent == "IOPAMIDOL"  # AX 5mm +C
    assert study[5][0].ContrastBolusAgent == "IOPAMIDOL"  # SAG 3mm +C
    assert [float(v) for v in study[5][0].ImageOrientationPatient] == [0, 1, 0, 0, 0, -1]


def test_two_view_localizer(tmp_path: Path) -> None:
    study = _generate(tmp_path, "ct_lumbar_spine", [2, 1, 1, 1, 1, 1, 1])

    orientations = [[float(v) for v in ds.ImageOrientationPatient] for ds in study[1]]
    assert orientations == [[1, 0, 0, 0, 0, -1], [0, 1, 0, 0, 0, -1]]
