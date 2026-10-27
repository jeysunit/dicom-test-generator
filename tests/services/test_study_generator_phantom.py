"""図形の方式（phantom）の画像の試験（docs/spec/06 の 4.6・ADR-0033）."""

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
from app.core.phantom import CT_PHANTOM_VALUES, marker_bounds, mr_phantom_values
from app.core.routine import routine_series_configs
from app.services.profile_loader import ProfileLoaderService
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

MARK_MANUFACTURER = "DTG SYNTHETIC"
MARK_COMMENTS = "SYNTHETIC TEST DATA"

CT_SERIES = [
    SeriesConfig(series_number=1, num_images=2, kind="localizer", views=["frontal", "lateral"]),
    SeriesConfig(series_number=2, num_images=30, slice_spacing=5.0, slice_thickness=5.0),
    SeriesConfig(series_number=3, num_images=59, slice_spacing=2.5, slice_thickness=2.5),
    SeriesConfig(series_number=4, num_images=20, kind="coronal", slice_spacing=12.0),
    SeriesConfig(series_number=5, num_images=20, kind="sagittal", slice_spacing=12.0),
    SeriesConfig(series_number=6, num_images=1, kind="dose_report"),
]


def _config(tmp_path: Path, series_list, template="ct_generic", profile=None, **extra):
    return GenerationConfig(
        job_name="phantom",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^PHANTOM"),
            birth_date="19800101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A1",
            study_date="20261027",
            study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template=template,
        device_profile=profile,
        pixel_spec=extra.pop("pixel_spec", PixelSpecPhantom()),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _generate(config: GenerationConfig) -> dict[int, list[pydicom.Dataset]]:
    service = StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    output = service.generate(config)
    by_series: dict[int, list[pydicom.Dataset]] = {}
    for path in sorted(output.glob("*.dcm")):
        ds = pydicom.dcmread(path)
        by_series.setdefault(int(ds.SeriesNumber), []).append(ds)
    return by_series


@pytest.fixture(scope="module")
def ct_study(tmp_path_factory) -> dict[int, list[pydicom.Dataset]]:
    tmp_path = tmp_path_factory.mktemp("phantom_ct")
    return _generate(_config(tmp_path, CT_SERIES, profile="dtg_synthetic_ct"))


def _stored(ds: pydicom.Dataset) -> np.ndarray:
    """画素の格納値（Rescale を当てない）."""
    raw = np.frombuffer(ds.PixelData, dtype=np.int16 if ds.PixelRepresentation else np.uint16)
    return raw.reshape(int(ds.Rows), int(ds.Columns))


def _without_marker(ds: pydicom.Dataset, index: int, count: int) -> np.ndarray:
    pixels = _stored(ds).astype(np.int64)
    r0, r1, c0, c1 = marker_bounds(int(ds.Rows), int(ds.Columns), index, count)
    pixels[r0:r1, c0:c1] = -1
    return pixels


def test_every_phantom_image_carries_the_synthetic_marks(ct_study) -> None:
    for number in (1, 2, 3, 4, 5):
        for ds in ct_study[number]:
            assert ds.Manufacturer == MARK_MANUFACTURER
            assert ds.ManufacturerModelName == MARK_MANUFACTURER
            assert ds.ImageComments == MARK_COMMENTS
            assert ds.BurnedInAnnotation == "NO"
            assert ds.RecognizableVisualFeatures == "NO"


def test_profile_values_other_than_the_marks_are_kept(ct_study) -> None:
    ds = ct_study[2][0]

    assert ds.DeviceSerialNumber
    assert ds.SoftwareVersions


def test_dose_report_keeps_the_profile_manufacturer(ct_study) -> None:
    dose = ct_study[6][0]

    assert dose.Manufacturer == "DTG Synthetic"
    assert "ImageComments" not in dose
    assert "BurnedInAnnotation" not in dose


def test_one_frame_of_reference_and_one_shape(ct_study) -> None:
    uids = {ds.FrameOfReferenceUID for number in (1, 2, 3, 4, 5) for ds in ct_study[number]}

    assert len(uids) == 1


def test_pixels_have_only_the_phantom_classes(ct_study) -> None:
    allowed = {CT_PHANTOM_VALUES.background, CT_PHANTOM_VALUES.shape, CT_PHANTOM_VALUES.marker}
    for number in (1, 2, 3, 4, 5):
        for ds in ct_study[number]:
            assert set(np.unique(_stored(ds)).tolist()) <= allowed


def test_coronal_sagittal_and_localizer_sit_on_top_of_the_axial_range(ct_study) -> None:
    top = 145.0
    for number in (1, 4, 5):
        for ds in ct_study[number]:
            assert float(ds.ImagePositionPatient[2]) == top


def test_two_axial_series_agree_at_the_same_position(ct_study) -> None:
    five_mm = ct_study[2]
    half = ct_study[3]
    for k in (0, 7, 14, 28):
        a = five_mm[k]
        b = half[2 * k]
        assert float(a.ImagePositionPatient[2]) == float(b.ImagePositionPatient[2])
        mask = (_without_marker(a, k, 30) >= 0) & (_without_marker(b, 2 * k, 59) >= 0)
        assert np.array_equal(_stored(a)[mask], _stored(b)[mask])


def test_axial_and_coronal_agree_where_they_cross(ct_study) -> None:
    axial = ct_study[2][10]
    coronal_index = 10
    coronal = ct_study[4][coronal_index]
    y = float(coronal.ImagePositionPatient[1])
    z = float(axial.ImagePositionPatient[2])
    axial_row = round(y / 0.5)
    coronal_row = round((145.0 - z) / 0.5)

    a = _without_marker(axial, 10, 30)[axial_row]
    c = _without_marker(coronal, coronal_index, 20)[coronal_row]
    keep = (a >= 0) & (c >= 0)

    assert np.array_equal(a[keep], c[keep])
    assert CT_PHANTOM_VALUES.shape in set(a[keep].tolist())
    assert CT_PHANTOM_VALUES.background in set(a[keep].tolist())


def test_axial_cross_section_peaks_in_the_middle(ct_study) -> None:
    series = ct_study[2]
    counts = []
    for ds in series:
        pixels = _stored(ds)
        rows, cols = np.indices(pixels.shape)
        distance = np.hypot(rows + 0.5 - 256, cols + 0.5 - 256)
        ring = np.abs(distance - 0.3 * 512) <= 0.04 * 512
        counts.append(int(np.count_nonzero((pixels == CT_PHANTOM_VALUES.shape) & ~ring)))

    assert all(a <= b for a, b in zip(counts[:15], counts[1:15]))
    assert all(a >= b for a, b in zip(counts[15:], counts[16:]))
    assert counts[14] == counts[15] == max(counts)
    assert not np.array_equal(_stored(series[0]), _stored(series[29]))
    assert not np.array_equal(_stored(series[14]), _stored(series[15]))


def test_chest_routine_coronal_middle_image_shows_the_shape(tmp_path) -> None:
    routine = RoutineLoaderService().get("ct_chest_plain")
    keep = list(range(len(routine.series)))
    images = [1, 60, 2, 3, 83, 1]
    series_list = routine_series_configs(routine, [i + 1 for i in keep], keep, images)

    by_series = _generate(_config(tmp_path, series_list))
    coronal = next(s for s in by_series.values() if "COR" in str(s[0].SeriesDescription))
    middle = coronal[len(coronal) // 2]

    assert CT_PHANTOM_VALUES.shape in set(np.unique(_stored(middle)).tolist())


def test_mr_images_use_mr_values_and_marks(tmp_path) -> None:
    series_list = [
        SeriesConfig(
            series_number=1, num_images=6, kind="localizer", modality="MR", plane="three_plane"
        ),
        SeriesConfig(
            series_number=2, num_images=10, kind="acquisition", modality="MR", plane="axial"
        ),
        SeriesConfig(
            series_number=3, num_images=4, kind="acquisition", modality="MR", plane="coronal"
        ),
    ]
    by_series = _generate(_config(tmp_path, series_list, template="mr_generic"))
    values = mr_phantom_values(12)

    for datasets in by_series.values():
        for ds in datasets:
            assert ds.Manufacturer == MARK_MANUFACTURER
            assert ds.BurnedInAnnotation == "NO"
            assert set(np.unique(_stored(ds)).tolist()) <= {
                values.background,
                values.shape,
                values.marker,
            }
    assert values.shape in set(np.unique(_stored(by_series[2][5])).tolist())
    assert float(by_series[3][0].ImagePositionPatient[2]) == 45.0


def test_petct_keeps_pet_pixels_and_marks_only_ct(tmp_path) -> None:
    series_list = [
        SeriesConfig(series_number=1, num_images=1, kind="localizer"),
        SeriesConfig(series_number=2, num_images=3, modality="CT"),
        SeriesConfig(series_number=3, num_images=3, kind="pet_ac", modality="PT"),
    ]
    by_series = _generate(_config(tmp_path, series_list, template="petct_generic"))

    assert by_series[2][0].Manufacturer == MARK_MANUFACTURER
    pet = by_series[3][0]
    assert pet.Manufacturer != MARK_MANUFACTURER
    assert "ImageComments" not in pet
    row = _stored(pet)[0]
    assert np.all(np.diff(row.astype(np.int64)) >= 0)


def test_mr_three_plane_localizer_shares_the_shape_with_the_axial_series(tmp_path) -> None:
    # MR の画素間隔は 240 / 512 = 0.46875 mm。37.5 mm と 15 mm はその整数倍
    series_list = [
        SeriesConfig(
            series_number=1, num_images=6, kind="localizer", modality="MR",
            plane="three_plane", slice_spacing=37.5,
        ),
        SeriesConfig(
            series_number=2, num_images=10, kind="acquisition", modality="MR", plane="axial"
        ),
    ]
    by_series = _generate(_config(tmp_path, series_list, template="mr_generic"))
    localizer, axial = by_series[1], by_series[2]
    coronal = localizer[3]
    spacing = 240.0 / 512

    assert len({ds.FrameOfReferenceUID for s in by_series.values() for ds in s}) == 1
    assert float(coronal.ImagePositionPatient[1]) == 37.5
    assert float(coronal.ImagePositionPatient[2]) == 45.0
    assert float(axial[6].ImagePositionPatient[2]) == 30.0
    a = _without_marker(axial[6], 6, 10)[round(37.5 / spacing)]
    c = _without_marker(coronal, 3, 6)[round((45.0 - 30.0) / spacing)]
    keep = (a >= 0) & (c >= 0)
    assert np.array_equal(a[keep], c[keep])
    assert mr_phantom_values(12).shape in set(a[keep].tolist())


def test_sixteen_bit_mr_phantom(tmp_path) -> None:
    series_list = [
        SeriesConfig(
            series_number=1, num_images=3, kind="acquisition", modality="MR", plane="axial"
        )
    ]
    by_series = _generate(
        _config(
            tmp_path, series_list, template="mr_generic",
            pixel_spec=PixelSpecPhantom(bits_stored=16),
        )
    )
    ds = by_series[1][1]

    assert int(ds.BitsStored) == 16
    assert int(_stored(ds).max()) == mr_phantom_values(16).marker


def test_dose_sr_does_not_get_the_marks(tmp_path) -> None:
    series_list = [
        SeriesConfig(series_number=1, num_images=2),
        SeriesConfig(series_number=2, num_images=1, kind="dose_sr"),
    ]
    by_series = _generate(_config(tmp_path, series_list))
    sr = by_series[2][0]

    assert sr.Modality == "SR"
    assert sr.Manufacturer != MARK_MANUFACTURER
    assert "ImageComments" not in sr
    assert by_series[1][0].Manufacturer == MARK_MANUFACTURER


def test_marks_are_written_before_the_abnormal_data(tmp_path, monkeypatch) -> None:
    import app.services.study_generator as study_generator

    seen: list[str] = []
    original = study_generator.apply_abnormal_to_dataset

    def record(dataset, generator):
        seen.append(str(dataset.get("Manufacturer", "")))
        return original(dataset, generator)

    monkeypatch.setattr(study_generator, "apply_abnormal_to_dataset", record)
    _generate(_config(tmp_path, [SeriesConfig(series_number=1, num_images=2)]))

    assert seen == [MARK_MANUFACTURER, MARK_MANUFACTURER]
