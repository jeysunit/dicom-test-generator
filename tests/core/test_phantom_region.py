"""部位の図形（phantom の部位・MR の強調・CT の相）の試験（docs/spec/06 の 4.6）."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.models import SeriesConfig
from app.core.phantom import (
    CT_PHANTOM_VALUES,
    marker_bounds,
    phantom_shape,
    projection_region_pixels,
    render_region,
)
from app.core.phantom_region import (
    CT_PHASE_HU,
    CT_PLAIN_HU,
    MR_FRACTIONS,
    ct_segment_values,
    mr_segment_values,
    mr_weighting_of,
    xray_segment_values,
)
from app.core.series_layout import AXIAL_ORIENTATION, SAGITTAL_ORIENTATION, VIEW_ORIENTATIONS

SIZE = 512
SPACING = 0.5
FOV = (SIZE * SPACING, SIZE * SPACING)
CT_AXIAL = SeriesConfig(series_number=1, num_images=30, slice_spacing=5.0, modality="CT")
SHAPE = phantom_shape([CT_AXIAL], FOV)
CT_VALUES = ct_segment_values(CT_AXIAL)
XRAY = xray_segment_values(12)


def _ct(region, z, orientation=AXIAL_ORIENTATION, position=None, projection=False, values=None):
    return render_region(
        SHAPE,
        region,
        position=position or [0.0, 0.0, z],
        orientation=orientation,
        pixel_spacing=(SPACING, SPACING),
        rows=SIZE,
        cols=SIZE,
        index=0,
        count=1,
        values=values or CT_VALUES,
        marker=CT_PHANTOM_VALUES.marker,
        projection=projection,
    )


def _runs(line: np.ndarray, value: int) -> int:
    """1列の中で `value` が続く区間の数."""
    hits = np.concatenate([[False], line == value, [False]])
    return int(np.count_nonzero(np.diff(hits.astype(np.int8)) == 1))


def _without_marker(pixels: np.ndarray, value: int) -> np.ndarray:
    """目印（骨と同じ値）を `value` で塗りつぶした写し."""
    pixels = pixels.copy()
    r0, r1, c0, c1 = marker_bounds(*pixels.shape, 0, 1)
    pixels[r0:r1, c0:c1] = value
    return pixels


def _projection(region: str, lateral: bool) -> np.ndarray:
    pixels = projection_region_pixels(
        1248, 1024, 0, 1, region=region, lateral=lateral, bits_stored=12,
        pixel_spacing_mm=0.342,
    )
    return _without_marker(pixels, XRAY["air"])


def test_ct_values_are_hu_plus_1024_and_change_with_the_phase() -> None:
    assert CT_VALUES["vessel"] == CT_PLAIN_HU["vessel"] + 1024 == 40 + 1024
    arterial = SeriesConfig(series_number=1, num_images=1, contrast=True, phase="arterial")
    assert ct_segment_values(arterial)["vessel"] == 300 + 1024
    assert ct_segment_values(arterial)["soft"] == CT_VALUES["soft"]


def test_contrast_without_a_phase_uses_the_portal_values() -> None:
    contrast = SeriesConfig(series_number=1, num_images=1, contrast=True)
    assert ct_segment_values(contrast)["vessel"] == CT_PHASE_HU["portal"]["vessel"] + 1024
    assert ct_segment_values(contrast)["parenchyma"] == 120 + 1024


def test_mr_fluid_is_bright_on_t2_and_dark_on_t1() -> None:
    t1 = mr_segment_values("T1", 12)
    t2 = mr_segment_values("T2", 12)
    assert t2["fluid"] > t2["soft"]
    assert t1["fluid"] < t1["soft"]


def test_mra_makes_the_vessel_the_brightest_segment() -> None:
    values = mr_segment_values("MRA", 12)
    assert values["vessel"] == max(values.values())
    assert values["vessel"] == round(4095 * 0.95)


def test_every_weighting_has_values_below_the_upper_limit() -> None:
    for weighting in MR_FRACTIONS:
        values = mr_segment_values(weighting, 16)
        assert values["air"] == values["lung"] == 0
        assert max(values.values()) <= 65535


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        ({"kind": "localizer", "sequence": "GR"}, "T1"),
        ({"kind": "derived", "sequence": "EP"}, "ADC"),
        ({"kind": "acquisition", "sequence": "SE"}, "T2"),
        ({"kind": "acquisition", "sequence": "IR"}, "FLAIR"),
        ({"kind": "acquisition", "sequence": "GR"}, "T2STAR"),
        ({"kind": "acquisition", "sequence": "EP"}, "DWI"),
        ({"kind": "acquisition", "sequence": "GR", "weighting": "MRA"}, "MRA"),
    ],
)
def test_mr_weighting_falls_back_to_the_kind_and_sequence(fields, expected) -> None:
    series = SeriesConfig(series_number=1, num_images=1, modality="MR", **fields)
    assert mr_weighting_of(series) == expected


def test_head_axial_has_a_bone_ring_around_soft_tissue() -> None:
    pixels = _without_marker(_ct("head", SHAPE.center[2]), CT_VALUES["soft"])
    row = pixels[SIZE // 2]
    bone = np.flatnonzero(row == CT_VALUES["bone"])
    soft = np.flatnonzero(row == CT_VALUES["soft"])
    # 中央の行は、外から 骨・軟部・液・軟部・骨 の順に並ぶ
    assert bone.min() < soft.min() and soft.max() < bone.max()
    assert row[SIZE // 2] == CT_VALUES["fluid"]
    assert _runs(row, CT_VALUES["bone"]) == 2
    # 骨の殻の厚さは 6 mm（12 画素）
    assert soft.min() - bone.min() == pytest.approx(12, abs=1)


def test_spine_bone_and_gap_alternate_along_z() -> None:
    lumbar = SeriesConfig(series_number=1, num_images=75, slice_spacing=2.0, modality="CT")
    shape = phantom_shape([lumbar], FOV)
    has_bone = []
    for index in range(75):
        pixels = render_region(
            shape, "spine", position=[0.0, 0.0, index * 2.0], orientation=AXIAL_ORIENTATION,
            pixel_spacing=(SPACING, SPACING), rows=SIZE, cols=SIZE, index=index, count=75,
            values=CT_VALUES, marker=CT_PHANTOM_VALUES.marker,
        )
        r0, r1, c0, c1 = marker_bounds(SIZE, SIZE, index, 75)
        pixels[r0:r1, c0:c1] = CT_VALUES["air"]
        has_bone.append(bool((pixels == CT_VALUES["bone"]).any()))
    changes = sum(a != b for a, b in zip(has_bone, has_bone[1:], strict=False))
    assert True in has_bone and False in has_bone
    assert changes >= 4


def test_chest_frontal_projection_has_two_lungs_and_lateral_has_one() -> None:
    frontal = _projection("chest", lateral=False)
    lateral = _projection("chest", lateral=True)
    middle = 1248 // 2
    assert _runs(frontal[middle], XRAY["lung"]) == 2
    assert _runs(lateral[middle], XRAY["lung"]) == 1
    assert XRAY["bone"] not in np.unique(frontal[:, :])  # 胸部の投影に背側の骨は描かない


def test_limb_projection_has_two_bones_with_a_gap() -> None:
    pixels = _projection("limb", lateral=False)
    column = pixels[:, 1024 // 2]
    assert _runs(column, XRAY["bone"]) == 2
    gap = np.flatnonzero(column != XRAY["bone"])
    gap = gap[(gap > 100) & (gap < 1148)]
    # すきまは 8 mm（約 23 画素）
    assert len(gap) == pytest.approx(8 / 0.342, abs=2)


def test_ct_localizer_shows_the_shadow_of_the_spine() -> None:
    lateral = _ct(
        "spine", 0, orientation=VIEW_ORIENTATIONS["lateral"],
        position=[0.0, 0.0, SHAPE.center[2] + SHAPE.radii[2]], projection=True,
    )
    column = lateral[:, int((SHAPE.center[1] + 0.6 * 0.7 * SHAPE.radii[1]) / SPACING)]
    assert _runs(column, CT_VALUES["bone"]) >= 3


def test_region_pixels_have_only_the_segment_values() -> None:
    allowed = set(CT_VALUES.values()) | {CT_PHANTOM_VALUES.marker}
    for region in ("head", "chest", "trunk", "abdomen", "spine", "limb"):
        for orientation in (AXIAL_ORIENTATION, SAGITTAL_ORIENTATION):
            position = [SHAPE.center[0], 0.0, SHAPE.center[2] + 60]
            if orientation is AXIAL_ORIENTATION:
                position = [0.0, 0.0, SHAPE.center[2]]
            pixels = _ct(region, 0, orientation=orientation, position=position)
            assert set(np.unique(pixels).tolist()) <= allowed, region
    for region in ("chest", "abdomen", "spine", "limb"):
        for lateral in (False, True):
            values = set(np.unique(_projection(region, lateral)).tolist())
            assert values <= set(XRAY.values()) | {round(4095 * 0.80)}, region


def test_trunk_is_chest_above_the_centre_and_abdomen_below() -> None:
    upper = _ct("trunk", SHAPE.center[2] + SHAPE.radii[2] / 2)
    lower = _ct("trunk", SHAPE.center[2] - SHAPE.radii[2] / 2)
    assert (upper == CT_VALUES["lung"]).any() and not (upper == CT_VALUES["parenchyma"]).any()
    assert (lower == CT_VALUES["parenchyma"]).any() and not (lower == CT_VALUES["lung"]).any()


def test_weighting_is_only_for_mr_series() -> None:
    with pytest.raises(PydanticValidationError, match="weighting"):
        SeriesConfig(series_number=1, num_images=1, weighting="T1")


def test_phase_needs_a_contrast_ct_series() -> None:
    with pytest.raises(PydanticValidationError, match="contrast"):
        SeriesConfig(series_number=1, num_images=1, phase="arterial")
    with pytest.raises(PydanticValidationError, match="phase"):
        SeriesConfig(
            series_number=1, num_images=1, modality="MR", kind="acquisition",
            phase="arterial",
        )
