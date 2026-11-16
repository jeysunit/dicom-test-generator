"""焼き込みの帯（docs/spec/06 の 4.7・ADR-0033 の決定5）の試験.

文字の形は比べない（Pillow の既定のフォントは版で違う）。帯の範囲に最小と最大の値だけが
あること、行が帯の幅に収まること、帯の外は変わらないことを確認する。
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core import PixelSpecCTRealistic, PixelSpecSimple, SpatialCoordinates
from app.core.burn_in import ascii_text, burn_in_band, burn_in_lines, plane_location

LINES = burn_in_lines("P000001", "20261027", 3, 12, 60, "Z +55.0 mm")


def test_lines_hold_the_required_texts() -> None:
    assert LINES == [
        "TEST / SYNTHETIC  ID P000001  20261027",
        "SE 3  IM 12/60",
        "Z +55.0 mm",
    ]


def test_non_ascii_characters_become_question_marks() -> None:
    assert ascii_text("ID 患者01\tA") == "ID ??01?A"
    lines = burn_in_lines("Ｐ０１", "20261027", 1, 1, 1, "VIEW PA")

    assert lines[0] == "TEST / SYNTHETIC  ID ???  20261027"


@pytest.mark.parametrize(
    ("orientation", "position", "expected"),
    [
        ([1, 0, 0, 0, 1, 0], [0.0, 0.0, 55.0], "Z +55.0 mm"),
        ([1, 0, 0, 0, 0, -1], [0.0, -12.5, 145.0], "Y -12.5 mm"),
        ([0, 1, 0, 0, 0, -1], [30.0, 0.0, 145.0], "X +30.0 mm"),
    ],
)
def test_plane_location_names_the_axis_of_the_plane(orientation, position, expected) -> None:
    spatial = SpatialCoordinates(
        instance_number=1,
        image_position_patient=position,
        slice_location=0.0,
        image_orientation_patient=orientation,
    )

    assert plane_location(spatial) == expected


@pytest.mark.parametrize(("rows", "cols", "dtype", "high"), [
    (512, 512, np.int16, 2047),
    (512, 512, np.uint16, 4095),
    (1248, 1024, np.uint16, 4095),
])
def test_band_holds_only_the_minimum_and_the_maximum(rows, cols, dtype, high) -> None:
    pixels = np.full((rows, cols), 1000, dtype=dtype)

    result, band = burn_in_band(pixels, LINES, low=0, high=high)

    assert result.dtype == dtype
    assert set(np.unique(result[:band]).tolist()) == {0, high}
    assert (result[band:] == pixels[band:]).all()
    assert 0 < band < rows // 2


def test_band_does_not_change_the_input() -> None:
    pixels = np.full((512, 512), 1000, dtype=np.int16)

    burn_in_band(pixels, LINES, low=0, high=2047)

    assert (pixels == 1000).all()


def test_each_line_fits_in_the_band_width_at_the_default_size() -> None:
    result, band = burn_in_band(np.zeros((512, 512), dtype=np.uint16), LINES, low=0, high=4095)

    inked = np.where((result[:band] == 4095).any(axis=0))[0]
    assert inked.size > 0
    assert inked.max() < 512 - 2
    # 3 行とも文字がある（行ごとの高さの範囲に最大の値がある）
    height = band // 3
    for row in range(3):
        assert (result[row * height : (row + 1) * height] == 4095).any()


def test_long_lines_shrink_the_scale_then_are_cut_to_the_width() -> None:
    long_id = "P" + "0" * 15
    lines = burn_in_lines(long_id, "20261027", 3, 12, 60, "Z +55.0 mm")

    result, band = burn_in_band(np.zeros((64, 64), dtype=np.uint16), lines, low=0, high=4095)

    assert set(np.unique(result[:band]).tolist()) == {0, 4095}
    assert result.shape == (64, 64)


def test_band_is_cut_to_the_image_height() -> None:
    result, band = burn_in_band(np.zeros((16, 512), dtype=np.uint16), LINES, low=0, high=4095)

    assert band == 16
    assert result.shape == (16, 512)


@pytest.mark.parametrize("spec", [PixelSpecSimple, PixelSpecCTRealistic])
@pytest.mark.parametrize("value", [True, False])
def test_burn_in_is_rejected_with_other_modes(spec, value) -> None:
    with pytest.raises(ValueError, match="burn_in"):
        spec(burn_in=value)
    assert spec().burn_in is None
