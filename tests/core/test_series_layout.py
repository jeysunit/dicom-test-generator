"""シリーズの種類ごとの Image Type・向き・位置と線量の画面の行（ADR-0025）."""

from __future__ import annotations

import pytest

from app.core.models import SeriesConfig
from app.core.series_layout import dose_report_lines, image_type, series_spatial


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
