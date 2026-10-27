"""図形の画素（phantom）の試験（openspec の change add-modality-synthetic-images）."""

from __future__ import annotations

import numpy as np
import pytest

from app.core.exceptions import PixelGenerationError
from app.core.models import SeriesConfig
from app.core.phantom import (
    CT_PHANTOM_VALUES,
    PhantomValues,
    marker_bounds,
    mr_phantom_values,
    phantom_shape,
    render_phantom,
)
from app.core.series_layout import (
    AXIAL_ORIENTATION,
    CORONAL_ORIENTATION,
    SAGITTAL_ORIENTATION,
)

SIZE = 512
SPACING = 0.5
FOV = (SIZE * SPACING, SIZE * SPACING)
VALUES = CT_PHANTOM_VALUES


def _axial(num_images: int = 30, spacing: float = 5.0, number: int = 1) -> SeriesConfig:
    return SeriesConfig(
        series_number=number, num_images=num_images, slice_spacing=spacing, modality="CT"
    )


def _render(shape, position, orientation, index=0, count=1, projection=False):
    return render_phantom(
        shape,
        position=position,
        orientation=orientation,
        pixel_spacing=(SPACING, SPACING),
        rows=SIZE,
        cols=SIZE,
        index=index,
        count=count,
        values=VALUES,
        projection=projection,
    )


def _shape_count(pixels: np.ndarray) -> int:
    """目印が通る輪（どの画像の目印も入る幅）を除いた、図形の値の画素の数."""
    rows, cols = np.indices(pixels.shape)
    distance = np.hypot(rows + 0.5 - SIZE / 2, cols + 0.5 - SIZE / 2)
    outside_ring = np.abs(distance - 0.3 * SIZE) > 0.04 * SIZE
    return int(np.count_nonzero((pixels == VALUES.shape) & outside_ring))


def test_shape_is_centred_on_the_longest_axial_range() -> None:
    shape = phantom_shape([_axial(10, 2.0), _axial(30, 5.0, number=2)], FOV)

    assert shape.center == pytest.approx((128.0, 128.0, 72.5))
    assert shape.radii == pytest.approx((102.4, 102.4, 0.55 * 145.0))
    assert shape.top_z == pytest.approx(145.0)


def test_shape_without_axial_series_uses_the_current_coronal_range() -> None:
    coronal = SeriesConfig(series_number=1, num_images=10, kind="coronal", modality="CT")

    shape = phantom_shape([coronal], FOV)

    assert shape.center == pytest.approx((128.0, 128.0, -128.0))
    assert shape.top_z == 0.0


def test_mr_axial_acquisition_is_the_reference() -> None:
    series = [
        SeriesConfig(
            series_number=1, num_images=15, kind="localizer", modality="MR", plane="three_plane"
        ),
        SeriesConfig(
            series_number=2, num_images=25, kind="acquisition", modality="MR", plane="sagittal"
        ),
        SeriesConfig(
            series_number=3, num_images=25, kind="acquisition", modality="MR", plane="axial"
        ),
    ]

    shape = phantom_shape(series, (240.0, 240.0))

    assert shape.center == pytest.approx((120.0, 120.0, 60.0))
    assert shape.top_z == pytest.approx(120.0)


def test_axial_cross_section_grows_to_the_middle_and_shrinks() -> None:
    series = _axial()
    shape = phantom_shape([series], FOV)
    counts = [
        _shape_count(_render(shape, [0.0, 0.0, k * 5.0], AXIAL_ORIENTATION, k, 30))
        for k in range(30)
    ]

    assert all(a <= b for a, b in zip(counts[:15], counts[1:15]))
    assert all(a >= b for a, b in zip(counts[15:], counts[16:]))
    assert counts[14] == counts[15] == max(counts)
    assert counts[0] < counts[14]
    assert counts[0] > 0 and counts[29] > 0


def test_marker_differs_between_images_at_the_same_distance() -> None:
    shape = phantom_shape([_axial()], FOV)
    first = _render(shape, [0.0, 0.0, 0.0], AXIAL_ORIENTATION, 0, 30)
    last = _render(shape, [0.0, 0.0, 145.0], AXIAL_ORIENTATION, 29, 30)
    middle = _render(shape, [0.0, 0.0, 70.0], AXIAL_ORIENTATION, 14, 30)
    next_middle = _render(shape, [0.0, 0.0, 75.0], AXIAL_ORIENTATION, 15, 30)

    assert marker_bounds(SIZE, SIZE, 0, 30) != marker_bounds(SIZE, SIZE, 29, 30)
    assert not np.array_equal(first, last)
    assert not np.array_equal(middle, next_middle)
    assert _shape_count(first) == _shape_count(last)


def test_marker_is_drawn_with_the_marker_value() -> None:
    shape = phantom_shape([_axial()], FOV)
    pixels = _render(shape, [0.0, 0.0, 70.0], AXIAL_ORIENTATION, 3, 30)
    r0, r1, c0, c1 = marker_bounds(SIZE, SIZE, 3, 30)

    assert r1 - r0 >= 2 and c1 - c0 >= 2
    assert np.all(pixels[r0:r1, c0:c1] == VALUES.marker)


def test_pixels_have_only_the_three_classes() -> None:
    shape = phantom_shape([_axial()], FOV)
    pixels = _render(shape, [0.0, 0.0, 70.0], AXIAL_ORIENTATION, 5, 30)

    assert set(np.unique(pixels).tolist()) == {VALUES.background, VALUES.shape, VALUES.marker}
    assert pixels.dtype == np.int16


def test_axial_and_coronal_agree_where_they_cross() -> None:
    shape = phantom_shape([_axial()], FOV)
    axial_z = 40.0
    coronal_y = 99.0
    axial = _render(shape, [0.0, 0.0, axial_z], AXIAL_ORIENTATION)
    coronal = _render(shape, [0.0, coronal_y, shape.top_z], CORONAL_ORIENTATION)
    axial_row = int(coronal_y / SPACING)
    coronal_row = int((shape.top_z - axial_z) / SPACING)
    r0, r1, c0, c1 = marker_bounds(SIZE, SIZE, 0, 1)
    columns = [c for c in range(SIZE) if not c0 <= c < c1]

    line_axial = axial[axial_row, columns]
    line_coronal = coronal[coronal_row, columns]

    assert np.array_equal(line_axial, line_coronal)
    assert set(line_axial.tolist()) == {VALUES.background, VALUES.shape}


def test_axial_and_sagittal_agree_where_they_cross() -> None:
    shape = phantom_shape([_axial()], FOV)
    axial_z = 100.0
    sagittal_x = 150.0
    axial = _render(shape, [0.0, 0.0, axial_z], AXIAL_ORIENTATION)
    sagittal = _render(shape, [sagittal_x, 0.0, shape.top_z], SAGITTAL_ORIENTATION)
    axial_col = int(sagittal_x / SPACING)
    sagittal_row = int((shape.top_z - axial_z) / SPACING)
    _, _, c0, c1 = marker_bounds(SIZE, SIZE, 0, 1)
    # 軸位の列の行の番号（y）と、矢状断の行の列の番号（y）は同じ位置を指す
    ys = [y for y in range(SIZE) if not c0 <= y < c1]

    assert np.array_equal(axial[ys, axial_col], sagittal[sagittal_row, ys])
    assert VALUES.shape in set(axial[ys, axial_col].tolist())


def test_projection_shows_the_largest_outline() -> None:
    shape = phantom_shape([_axial()], FOV)
    frontal = _render(
        shape, [0.0, 0.0, shape.top_z], CORONAL_ORIENTATION, projection=True
    )
    centre_slice = _render(
        shape, [0.0, shape.center[1], shape.top_z], CORONAL_ORIENTATION
    )

    assert np.array_equal(frontal, centre_slice)


def test_mr_values_are_fractions_of_the_bits_stored_range() -> None:
    values = mr_phantom_values(12)

    assert values == PhantomValues(background=0, shape=1638, marker=3686)


def test_ct_values_are_hu_plus_1024() -> None:
    assert CT_PHANTOM_VALUES == PhantomValues(background=24, shape=1064, marker=2024)


def test_marker_moves_around_the_centre() -> None:
    bounds = {marker_bounds(SIZE, SIZE, k, 4) for k in range(4)}

    assert len(bounds) == 4
    for r0, r1, c0, c1 in bounds:
        centre_r, centre_c = (r0 + r1) / 2, (c0 + c1) / 2
        distance = np.hypot(centre_r - SIZE / 2, centre_c - SIZE / 2)
        assert distance == pytest.approx(0.3 * SIZE, abs=2.0)


def test_render_rejects_a_count_smaller_than_the_index() -> None:
    shape = phantom_shape([_axial()], FOV)

    with pytest.raises(PixelGenerationError):
        _render(shape, [0.0, 0.0, 0.0], AXIAL_ORIENTATION, index=3, count=3)


def test_render_rejects_values_that_do_not_fit_the_dtype() -> None:
    shape = phantom_shape([_axial()], FOV)

    with pytest.raises(PixelGenerationError):
        render_phantom(
            shape,
            position=[0.0, 0.0, 0.0],
            orientation=AXIAL_ORIENTATION,
            pixel_spacing=(SPACING, SPACING),
            rows=SIZE,
            cols=SIZE,
            index=0,
            count=1,
            values=mr_phantom_values(16),
        )


def test_sixteen_bit_mr_values_fit_unsigned_pixels() -> None:
    shape = phantom_shape([_axial()], FOV)
    values = mr_phantom_values(16)

    pixels = render_phantom(
        shape,
        position=[0.0, 0.0, 70.0],
        orientation=AXIAL_ORIENTATION,
        pixel_spacing=(SPACING, SPACING),
        rows=SIZE,
        cols=SIZE,
        index=0,
        count=1,
        values=values,
        dtype=np.uint16,
    )

    assert pixels.dtype == np.uint16
    assert int(pixels.max()) == values.marker == 58982


def test_a_single_axial_image_still_has_a_z_radius() -> None:
    shape = phantom_shape([_axial(1, 5.0)], FOV)

    assert shape.radii[2] == pytest.approx(0.55 * 5.0)
