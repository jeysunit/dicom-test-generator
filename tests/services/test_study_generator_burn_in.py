"""焼き込み（burn_in）を選んだ画像の試験（docs/spec/06 の 4.7・ADR-0033 の決定5）."""

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
    PixelSpecPhantom,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.phantom import CT_PHANTOM_VALUES, mr_phantom_values, xray_phantom_values
from app.core.routine import routine_series_configs
from app.services.profile_loader import ProfileLoaderService
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

CT_SERIES = [
    SeriesConfig(series_number=1, num_images=2, kind="localizer", views=["frontal", "lateral"]),
    SeriesConfig(series_number=2, num_images=6, slice_spacing=5.0, slice_thickness=5.0),
    SeriesConfig(series_number=3, num_images=4, kind="coronal", slice_spacing=12.0),
    SeriesConfig(series_number=4, num_images=4, kind="sagittal", slice_spacing=12.0),
    SeriesConfig(series_number=5, num_images=1, kind="dose_report"),
]
CT_HIGH = 2047  # 12 ビットの符号ありの上限
MR_BITS = 12


def _routine_series(name: str) -> list[SeriesConfig]:
    routine = RoutineLoaderService().get(name)
    count = len(routine.series)
    return routine_series_configs(
        routine, list(range(1, count + 1)), list(range(count)),
        [series.images for series in routine.series],
    )


def _config(tmp_path: Path, series_list, template: str, burn_in: bool, patient_id="P000001"):
    return GenerationConfig(
        job_name="burn_in",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id=patient_id,
            patient_name=PatientName(alphabetic="TEST^BURN"),
            birth_date="19800101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A1", study_date="20261027", study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template=template,
        pixel_spec=PixelSpecPhantom(burn_in=burn_in),
        transfer_syntax=TransferSyntaxConfig(
            uid="1.2.840.10008.1.2.1", name="Explicit VR Little Endian", is_implicit_vr=False
        ),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _generate(config: GenerationConfig) -> list[pydicom.Dataset]:
    service = StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    output = service.generate(config)
    return [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]


def _stored(ds: pydicom.Dataset) -> np.ndarray:
    raw = np.frombuffer(ds.PixelData, dtype=np.int16 if ds.PixelRepresentation else np.uint16)
    return raw.reshape(int(ds.Rows), int(ds.Columns))


def _band_rows(pixels: np.ndarray, high: int) -> int:
    """上端から、最大の値がある最後の行まで（帯の文字の範囲）."""
    return int(np.where((pixels == high).any(axis=1))[0].max()) + 1


def _outside_values(pixels: np.ndarray, high: int) -> set[int]:
    """帯の外の値。帯の高さは、上端から最大の値がある最後の行までより下の最初の行."""
    band = _band_rows(pixels, high)
    # 帯の背景（最小の値）が続く行は帯の中にある
    while band < pixels.shape[0] and (pixels[band] == 0).all():
        band += 1
    return set(np.unique(pixels[band:]).tolist())


@pytest.fixture(scope="module")
def ct_study(tmp_path_factory) -> list[pydicom.Dataset]:
    return _generate(_config(tmp_path_factory.mktemp("burn_ct"), CT_SERIES, "ct_generic", True))


def test_every_burned_in_image_says_yes_and_keeps_the_other_marks(ct_study) -> None:
    images = [ds for ds in ct_study if int(ds.SeriesNumber) != 5]

    assert len(images) == 16
    for ds in images:
        assert ds.BurnedInAnnotation == "YES"
        assert ds.RecognizableVisualFeatures == "NO"
        assert ds.Manufacturer == "DTG SYNTHETIC"
        assert ds.ImageComments == "SYNTHETIC TEST DATA"


def test_every_ct_image_has_a_band_with_the_maximum_value(ct_study) -> None:
    allowed = {CT_PHANTOM_VALUES.background, CT_PHANTOM_VALUES.shape, CT_PHANTOM_VALUES.marker}
    for ds in ct_study:
        if int(ds.SeriesNumber) == 5:
            continue
        pixels = _stored(ds)
        assert (pixels[:24] == CT_HIGH).any(), ds.SeriesNumber
        assert pixels.max() == CT_HIGH
        assert pixels.min() == 0
        assert _outside_values(pixels, CT_HIGH) <= allowed


def test_the_dose_screen_has_no_band(ct_study) -> None:
    dose = next(ds for ds in ct_study if int(ds.SeriesNumber) == 5)

    assert "BurnedInAnnotation" not in dose
    assert dose.Manufacturer != "DTG SYNTHETIC"


def test_the_default_has_no_band_and_says_no(tmp_path) -> None:
    datasets = _generate(_config(tmp_path, CT_SERIES, "ct_generic", False))

    allowed = {CT_PHANTOM_VALUES.background, CT_PHANTOM_VALUES.shape, CT_PHANTOM_VALUES.marker}
    for ds in datasets:
        if int(ds.SeriesNumber) == 5:
            continue
        assert ds.BurnedInAnnotation == "NO"
        assert set(np.unique(_stored(ds)).tolist()) <= allowed


def test_the_band_leaves_the_rest_of_the_image_as_without_burn_in(tmp_path) -> None:
    with_band = _generate(_config(tmp_path / "on", CT_SERIES, "ct_generic", True))
    without = _generate(_config(tmp_path / "off", CT_SERIES, "ct_generic", False))

    for on, off in zip(with_band, without):
        if int(on.SeriesNumber) == 5:
            continue
        assert (_stored(on)[100:] == _stored(off)[100:]).all()
        assert not (_stored(on)[:100] == _stored(off)[:100]).all()


def test_mr_images_burn_in_with_the_unsigned_maximum(tmp_path) -> None:
    series = _routine_series("mr_head")
    with_band = _generate(_config(tmp_path / "on", series, "mr_generic", True))
    without = _generate(_config(tmp_path / "off", series, "mr_generic", False))

    high = (1 << MR_BITS) - 1
    assert with_band
    for on, off in zip(with_band, without):
        pixels = _stored(on)
        assert on.BurnedInAnnotation == "YES"
        assert pixels.max() == high
        assert pixels.min() == 0
        assert (pixels[:24] == high).any()
        assert _outside_values(pixels, high) <= set(np.unique(_stored(off)).tolist())
    assert mr_phantom_values(MR_BITS).marker < high


@pytest.mark.parametrize(
    ("routine", "template"), [("cr_chest", "cr_generic"), ("dx_chest", "dx_generic")]
)
def test_projection_images_burn_in(tmp_path, routine, template) -> None:
    datasets = _generate(_config(tmp_path, _routine_series(routine), template, True))

    high = (1 << 12) - 1
    values = xray_phantom_values(12)
    assert len(datasets) == 2
    for ds in datasets:
        pixels = _stored(ds)
        assert ds.BurnedInAnnotation == "YES"
        assert ds.RecognizableVisualFeatures == "NO"
        assert (pixels[:80] == high).any()
        assert pixels.min() == 0
        assert values.marker < high


def test_drawn_lines_hold_the_exam_values(tmp_path, monkeypatch) -> None:
    drawn: list[list[str]] = []
    import app.services.study_generator as module

    original = module.burn_in_lines

    def record(*args):
        lines = original(*args)
        drawn.append(lines)
        return lines

    monkeypatch.setattr(module, "burn_in_lines", record)
    _generate(_config(tmp_path, CT_SERIES, "ct_generic", True))

    assert len(drawn) == 16
    assert all("TEST / SYNTHETIC" in lines[0] for lines in drawn)
    assert all("P000001" in lines[0] and "20261027" in lines[0] for lines in drawn)
    # 位置：位置決めは方向、軸位は Z、冠状断は Y、矢状断は X
    assert [lines[2][:1] for lines in drawn] == ["V"] * 2 + ["Z"] * 6 + ["Y"] * 4 + ["X"] * 4
    assert drawn[0][2] == "VIEW FRONTAL"
    assert drawn[2][1] == "SE 2  IM 1/6"
