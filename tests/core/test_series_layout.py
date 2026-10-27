"""シリーズの種類ごとの Image Type・向き・位置と線量の画面の行（ADR-0025）."""

from __future__ import annotations

import pytest

from app.core.models import SeriesConfig
from app.core.series_layout import dose_report_lines, image_type, mr_plane, series_spatial


def _series(kind: str, **extra: object) -> SeriesConfig:
    return SeriesConfig(series_number=1, num_images=3, kind=kind, **extra)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("axial", ["ORIGINAL", "PRIMARY", "AXIAL"]),
        ("localizer", ["ORIGINAL", "PRIMARY", "LOCALIZER"]),
        ("coronal", ["DERIVED", "SECONDARY", "AXIAL"]),
        ("sagittal", ["DERIVED", "SECONDARY", "AXIAL"]),
        ("dose_report", ["DERIVED", "SECONDARY"]),
    ],
)
def test_image_type(kind: str, expected: list[str]) -> None:
    assert image_type(_series(kind)) == expected


def test_axial_is_the_same_as_before() -> None:
    spatial = series_spatial(_series("axial", slice_spacing=5.0), 2)

    assert spatial.image_position_patient == [0.0, 0.0, 10.0]
    assert spatial.image_orientation_patient == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert spatial.slice_location == 10.0


def test_coronal_advances_front_to_back() -> None:
    positions = [
        series_spatial(_series("coronal", slice_spacing=3.0), index) for index in range(3)
    ]

    assert [p.image_position_patient for p in positions] == [
        [0.0, 0.0, 0.0],
        [0.0, 3.0, 0.0],
        [0.0, 6.0, 0.0],
    ]
    assert positions[0].image_orientation_patient == [1.0, 0.0, 0.0, 0.0, 0.0, -1.0]


def test_sagittal_advances_left_to_right() -> None:
    spatial = series_spatial(_series("sagittal", slice_spacing=2.0), 1)

    assert spatial.image_position_patient == [2.0, 0.0, 0.0]
    assert spatial.image_orientation_patient == [0.0, 1.0, 0.0, 0.0, 0.0, -1.0]


def test_localizer_views_repeat() -> None:
    series = _series("localizer", views=["frontal", "lateral"])

    orientations = [series_spatial(series, index).image_orientation_patient for index in range(3)]

    assert orientations == [
        [1.0, 0.0, 0.0, 0.0, 0.0, -1.0],
        [0.0, 1.0, 0.0, 0.0, 0.0, -1.0],
        [1.0, 0.0, 0.0, 0.0, 0.0, -1.0],
    ]


def test_dose_report_lists_acquired_series_only() -> None:
    series_list = [
        SeriesConfig(series_number=1, num_images=1, kind="localizer"),
        SeriesConfig(series_number=2, num_images=60, kind="axial", slice_spacing=5.0),
        SeriesConfig(series_number=3, num_images=83, kind="coronal", slice_spacing=3.0),
        SeriesConfig(series_number=4, num_images=1, kind="dose_report"),
    ]

    lines = dose_report_lines(series_list)

    assert lines[0] == "Dose Report"
    rows = [line for line in lines if line[:1].isdigit()]
    assert [row.split()[0] for row in rows] == ["1", "2"]
    # 軸位 60 枚 × 5mm = 30cm、CTDIvol 10 mGy で DLP 300
    assert rows[1].split()[-1] == "300.00"


def _mr(kind: str = "acquisition", **extra: object) -> SeriesConfig:
    return SeriesConfig(series_number=1, num_images=5, kind=kind, modality="MR", **extra)


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("acquisition", ["ORIGINAL", "PRIMARY", "M", "ND"]),
        ("localizer", ["ORIGINAL", "PRIMARY", "M", "ND"]),
        ("derived", ["DERIVED", "SECONDARY"]),
    ],
)
def test_mr_image_type(kind: str, expected: list[str]) -> None:
    assert image_type(_mr(kind)) == expected


def test_mr_series_kind_needs_the_mr_modality() -> None:
    with pytest.raises(ValueError, match="needs modality MR"):
        SeriesConfig(series_number=1, num_images=1, kind="acquisition", modality="CT")
    with pytest.raises(ValueError, match="not an MR series kind"):
        SeriesConfig(series_number=1, num_images=1, kind="axial", modality="MR")


def test_mr_planes_follow_the_orientation_of_the_plane() -> None:
    axial = series_spatial(_mr(plane="axial", slice_spacing=6.0), 2)
    sagittal = series_spatial(_mr(plane="sagittal", slice_spacing=6.0), 2)
    coronal = series_spatial(_mr(plane="coronal", slice_spacing=6.0), 2)

    assert axial.image_position_patient == [0.0, 0.0, 12.0]
    assert axial.image_orientation_patient == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    assert sagittal.image_position_patient == [12.0, 0.0, 0.0]
    assert sagittal.image_orientation_patient == [0.0, 1.0, 0.0, 0.0, 0.0, -1.0]
    assert coronal.image_position_patient == [0.0, 12.0, 0.0]
    assert coronal.image_orientation_patient == [1.0, 0.0, 0.0, 0.0, 0.0, -1.0]


def test_mr_three_plane_localizer_splits_images_into_three_planes() -> None:
    series = SeriesConfig(
        series_number=1, num_images=15, kind="localizer", modality="MR", plane="three_plane"
    )

    assert [mr_plane(series, index) for index in (0, 4, 5, 9, 10, 14)] == [
        ("axial", 0),
        ("axial", 4),
        ("coronal", 0),
        ("coronal", 4),
        ("sagittal", 0),
        ("sagittal", 4),
    ]


def test_mr_three_plane_remainder_goes_to_the_last_plane() -> None:
    series = SeriesConfig(
        series_number=1, num_images=7, kind="localizer", modality="MR", plane="three_plane"
    )

    assert [mr_plane(series, index)[0] for index in range(7)] == [
        "axial",
        "axial",
        "coronal",
        "coronal",
        "sagittal",
        "sagittal",
        "sagittal",
    ]
