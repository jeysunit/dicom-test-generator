"""図形の画素（phantom。docs/spec/06 の 4.6・ADR-0033）.

各画素の患者座標（Image Position・Image Orientation・Pixel Spacing から計算する
画素の中心の x・y・z。PS3.3 C.7.6.2.1.1）で回転楕円体を評価し、シリーズの中の
番号で角度を変える位置の目印を描く。図形は1回の撮影（同じ Frame of Reference）で
一度だけ決めるので、軸位・冠状断・矢状断は同じ図形の断面になる。画素に文字は
描かない。通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import astuple, dataclass

import numpy as np

from .exceptions import PixelGenerationError
from .models import PhantomRegion, SeriesConfig, SpatialCoordinates
from .phantom_region import (
    Segment,
    ct_segment_values,
    mr_segment_values,
    mr_weighting_of,
    region_solids,
    render_solids,
    xray_segment_values,
)
from .series_layout import MR_FIELD_OF_VIEW_MM

# 図形で画素を作った画像に書く偽物の印。装置のプロファイルの後に書き、
# プロファイルの値より優先する（docs/spec/06 の 4.6）
PHANTOM_MARKS = {
    "Manufacturer": "DTG SYNTHETIC",
    "ManufacturerModelName": "DTG SYNTHETIC",
    "ImageComments": "SYNTHETIC TEST DATA",
    "BurnedInAnnotation": "NO",
    "RecognizableVisualFeatures": "NO",
}
# CT の画像の画素間隔（行, 列。mm）。SpatialCoordinates の既定の値
CT_PIXEL_SPACING_MM: tuple[float, float] = tuple(
    SpatialCoordinates.model_fields["pixel_spacing"].default
)
# 回転楕円体の x・y の半径は視野の 0.4 倍、z の半径は軸位の範囲の 0.55 倍
SHAPE_RADIUS_FRACTION = 0.4
SHAPE_Z_RADIUS_FRACTION = 0.55
# 位置の目印：1辺は画像の小さいほうの辺の 0.04 倍、画像の中心から 0.3 倍の円の上
MARKER_SIZE_FRACTION = 0.04
MARKER_ORBIT_FRACTION = 0.3
MARKER_MIN_SIZE = 2
# CT の値（HU）。画素は HU + 1024（Rescale Intercept -1024）
CT_RESCALE_OFFSET = 1024
CT_BACKGROUND_HU = -1000
CT_SHAPE_HU = 40
CT_MARKER_HU = 1000
# MR の値（Bits Stored の上限に対する割合）
MR_BACKGROUND_FRACTION = 0.0
MR_SHAPE_FRACTION = 0.40
MR_MARKER_FRACTION = 0.90
# CR・DX の値（MONOCHROME2 の、Bits Stored の上限に対する割合。ADR-0034）
XRAY_BACKGROUND_FRACTION = 0.05
XRAY_SHAPE_FRACTION = 0.35
XRAY_MARKER_FRACTION = 0.80


@dataclass(frozen=True)
class PhantomValues:
    """区分ごとの画素の値."""

    background: int
    shape: int
    marker: int


CT_PHANTOM_VALUES = PhantomValues(
    background=CT_BACKGROUND_HU + CT_RESCALE_OFFSET,
    shape=CT_SHAPE_HU + CT_RESCALE_OFFSET,
    marker=CT_MARKER_HU + CT_RESCALE_OFFSET,
)


def _fraction_values(
    bits_stored: int, background: float, shape: float, marker: float
) -> PhantomValues:
    """符号なしの Bits Stored の上限に割合を掛けて丸めた値."""
    upper = (1 << bits_stored) - 1
    return PhantomValues(
        background=int(np.rint(upper * background)),
        shape=int(np.rint(upper * shape)),
        marker=int(np.rint(upper * marker)),
    )


def mr_phantom_values(bits_stored: int) -> PhantomValues:
    """MR の値。符号なしの Bits Stored の上限に割合を掛けて丸める."""
    return _fraction_values(
        bits_stored, MR_BACKGROUND_FRACTION, MR_SHAPE_FRACTION, MR_MARKER_FRACTION
    )


def xray_phantom_values(bits_stored: int) -> PhantomValues:
    """CR・DX の値（MONOCHROME2）。符号なしの Bits Stored の上限に割合を掛けて丸める."""
    return _fraction_values(
        bits_stored, XRAY_BACKGROUND_FRACTION, XRAY_SHAPE_FRACTION, XRAY_MARKER_FRACTION
    )


def projection_phantom_pixels(
    rows: int, cols: int, index: int, count: int, values: PhantomValues
) -> np.ndarray:
    """CR・DX の投影の画像の基本の図形（体の楕円1つと位置の目印。符号なしの uint16）.

    投影の画像は位置を持たないので、楕円は画像の中央に置き、半径は列・行の数の
    0.4 倍にする。方向は画素に描かず、View Position などのタグで示す（ADR-0034）。
    """
    if count < 1 or not 0 <= index < count:
        raise PixelGenerationError(
            f"Image index {index} is outside the series of {count} images", mode="phantom"
        )
    r = (np.arange(rows, dtype=np.float64)[:, None] + 0.5 - rows / 2) / (
        rows * SHAPE_RADIUS_FRACTION
    )
    c = (np.arange(cols, dtype=np.float64)[None, :] + 0.5 - cols / 2) / (
        cols * SHAPE_RADIUS_FRACTION
    )
    pixels = np.where(r**2 + c**2 <= 1.0, values.shape, values.background).astype(np.uint16)
    r0, r1, c0, c1 = marker_bounds(rows, cols, index, count)
    pixels[max(r0, 0) : max(r1, 0), max(c0, 0) : max(c1, 0)] = values.marker
    return pixels


@dataclass(frozen=True)
class PhantomShape:
    """撮影ごとに一度だけ決める回転楕円体（患者座標、mm）.

    `top_z` は軸位の範囲の上端で、冠状断・矢状断・位置決めの Image Position
    (Patient) の z に使う。
    """

    center: tuple[float, float, float]
    radii: tuple[float, float, float]
    top_z: float


def _is_axial(series: SeriesConfig) -> bool:
    if series.modality == "MR":
        return series.kind in ("acquisition", "derived") and series.plane == "axial"
    return series.modality in (None, "CT") and series.kind == "axial"


def phantom_shape(
    series_list: Sequence[SeriesConfig], field_of_view_mm: tuple[float, float]
) -> PhantomShape:
    """図形の中心と半径を決める.

    x・y は軸位の視野（列方向の幅, 行方向の高さ。mm）の中央に置く。z は、位置の
    範囲がいちばん長い軸位のシリーズの範囲の中央に置く。軸位が無ければ、今の
    冠状断・矢状断が写す範囲（z が 0 から視野の高さだけ下）を使い、位置は変えない。
    """
    width_mm, height_mm = field_of_view_mm
    axial = [series for series in series_list if _is_axial(series)]
    if axial:
        reference = max(axial, key=lambda s: (s.num_images - 1) * s.slice_spacing)
        length = (reference.num_images - 1) * reference.slice_spacing
        bottom = reference.start_z
        top_z = bottom + length
        z_length = max(length, reference.slice_spacing)
        center_z = bottom + length / 2
    else:
        top_z = 0.0
        z_length = height_mm
        center_z = -height_mm / 2
    return PhantomShape(
        center=(width_mm / 2, height_mm / 2, center_z),
        radii=(
            width_mm * SHAPE_RADIUS_FRACTION,
            height_mm * SHAPE_RADIUS_FRACTION,
            z_length * SHAPE_Z_RADIUS_FRACTION,
        ),
        top_z=top_z,
    )


def marker_bounds(rows: int, cols: int, index: int, count: int) -> tuple[int, int, int, int]:
    """位置の目印の範囲（行の始め, 行の終わり, 列の始め, 列の終わり。終わりは含まない）.

    角度は 360° × index / count。0° は画像の中心の右で、番号が進むと上へ回る。
    """
    side = max(MARKER_MIN_SIZE, round(min(rows, cols) * MARKER_SIZE_FRACTION))
    orbit = min(rows, cols) * MARKER_ORBIT_FRACTION
    angle = 2 * math.pi * index / count
    centre_row = rows / 2 - orbit * math.sin(angle)
    centre_col = cols / 2 + orbit * math.cos(angle)
    r0 = round(centre_row - side / 2)
    c0 = round(centre_col - side / 2)
    return r0, r0 + side, c0, c0 + side


def _pixel_coordinates(
    position: Sequence[float],
    orientation: Sequence[float],
    pixel_spacing: tuple[float, float],
    rows: int,
    cols: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """各画素の中心の患者座標（PS3.3 C.7.6.2.1.1）.

    Pixel Spacing は（行の間隔, 列の間隔）。列の番号が進むと行の向き、行の番号が
    進むと列の向きに進む。
    """
    row_spacing, col_spacing = pixel_spacing
    row_dir = np.asarray(orientation[:3], dtype=np.float64)
    col_dir = np.asarray(orientation[3:], dtype=np.float64)
    r = np.arange(rows, dtype=np.float64)[:, None] * row_spacing
    c = np.arange(cols, dtype=np.float64)[None, :] * col_spacing
    coords = [position[axis] + c * row_dir[axis] + r * col_dir[axis] for axis in range(3)]
    return coords[0], coords[1], coords[2]


def render_phantom(
    shape: PhantomShape,
    *,
    position: Sequence[float],
    orientation: Sequence[float],
    pixel_spacing: tuple[float, float],
    rows: int,
    cols: int,
    index: int,
    count: int,
    values: PhantomValues,
    projection: bool = False,
    dtype: type[np.integer] = np.int16,
) -> np.ndarray:
    """1枚の画像の画素（CT は int16、MR は符号なしの uint16）.

    `projection` は投影の画像（位置決め）で、画像の面に垂直な向きの座標を図形の
    中心に置いて評価する（回転楕円体の影は中心を通る断面と同じ形になる）。
    """
    if count < 1 or not 0 <= index < count:
        raise PixelGenerationError(
            f"Image index {index} is outside the series of {count} images", mode="phantom"
        )
    limits = np.iinfo(dtype)
    if min(astuple(values)) < limits.min or max(astuple(values)) > limits.max:
        raise PixelGenerationError(
            f"Phantom values {astuple(values)} do not fit {np.dtype(dtype).name}",
            mode="phantom",
        )
    x, y, z = _pixel_coordinates(position, orientation, pixel_spacing, rows, cols)
    coords = [x, y, z]
    if projection:
        normal = np.cross(orientation[:3], orientation[3:])
        axis = int(np.argmax(np.abs(normal)))
        coords[axis] = np.full_like(coords[axis], shape.center[axis])
    inside = sum(
        ((coords[axis] - shape.center[axis]) / shape.radii[axis]) ** 2 for axis in range(3)
    ) <= 1.0
    pixels = np.where(inside, values.shape, values.background).astype(dtype)
    r0, r1, c0, c1 = marker_bounds(rows, cols, index, count)
    pixels[max(r0, 0) : max(r1, 0), max(c0, 0) : max(c1, 0)] = values.marker
    return pixels


def _check_values_fit(values: Sequence[int], dtype: type[np.integer]) -> None:
    limits = np.iinfo(dtype)
    if min(values) < limits.min or max(values) > limits.max:
        raise PixelGenerationError(
            f"Phantom values {tuple(values)} do not fit {np.dtype(dtype).name}",
            mode="phantom",
        )


def _draw_marker(pixels: np.ndarray, index: int, count: int, value: int) -> None:
    rows, cols = pixels.shape
    r0, r1, c0, c1 = marker_bounds(rows, cols, index, count)
    pixels[max(r0, 0) : max(r1, 0), max(c0, 0) : max(c1, 0)] = value


def render_region(
    shape: PhantomShape,
    region: PhantomRegion,
    *,
    position: Sequence[float],
    orientation: Sequence[float],
    pixel_spacing: tuple[float, float],
    rows: int,
    cols: int,
    index: int,
    count: int,
    values: dict[Segment, int],
    marker: int,
    projection: bool = False,
    dtype: type[np.integer] = np.int16,
) -> np.ndarray:
    """部位の図形の1枚の画像の画素（docs/spec/06 の 4.6）.

    図形は撮影の回転楕円体（`shape`）の中心と半径から決める。`projection` は投影の
    画像（CT の位置決め）で、画像の面に垂直な向きに見た図形の影を描く。
    """
    if count < 1 or not 0 <= index < count:
        raise PixelGenerationError(
            f"Image index {index} is outside the series of {count} images", mode="phantom"
        )
    _check_values_fit([*values.values(), marker], dtype)
    coords = _pixel_coordinates(position, orientation, pixel_spacing, rows, cols)
    drop_axis = None
    if projection:
        normal = np.cross(orientation[:3], orientation[3:])
        drop_axis = int(np.argmax(np.abs(normal)))
    solids = region_solids(region, shape.center, shape.radii)
    pixels = render_solids(solids, coords, values, drop_axis=drop_axis, dtype=dtype)
    _draw_marker(pixels, index, count, marker)
    return pixels


def projection_region_pixels(
    rows: int,
    cols: int,
    index: int,
    count: int,
    *,
    region: PhantomRegion,
    lateral: bool,
    bits_stored: int,
    pixel_spacing_mm: float,
) -> np.ndarray:
    """CR・DX の部位の図形（符号なしの uint16。MONOCHROME2 の値）.

    投影の画像は位置を持たないので、画像の中央に、半径が列・行の数の 0.4 倍の回転
    楕円体を置き、そこから部位の図形を決めて影を描く。列は正面なら患者の左（x）、
    側面なら背側（y）へ、行は足の向き（−z）へ進む（Patient Orientation の L\\F・P\\F）。
    """
    if count < 1 or not 0 <= index < count:
        raise PixelGenerationError(
            f"Image index {index} is outside the series of {count} images", mode="phantom"
        )
    width_mm, height_mm = cols * pixel_spacing_mm, rows * pixel_spacing_mm
    center = (width_mm / 2, width_mm / 2, -height_mm / 2)
    radii = (
        width_mm * SHAPE_RADIUS_FRACTION,
        width_mm * SHAPE_RADIUS_FRACTION,
        height_mm * SHAPE_RADIUS_FRACTION,
    )
    across = (np.arange(cols, dtype=np.float64)[None, :] + 0.5) * pixel_spacing_mm
    down = -(np.arange(rows, dtype=np.float64)[:, None] + 0.5) * pixel_spacing_mm
    across, down = np.broadcast_arrays(across, down)
    fixed = np.zeros_like(across)
    coords = (fixed, across, down) if lateral else (across, fixed, down)
    pixels = render_solids(
        region_solids(region, center, radii),
        coords,
        xray_segment_values(bits_stored),
        drop_axis=0 if lateral else 1,
        dtype=np.uint16,
    )
    _draw_marker(pixels, index, count, xray_phantom_values(bits_stored).marker)
    return pixels


def study_phantom_shape(
    series_list: Sequence[SeriesConfig], rows: int, cols: int
) -> PhantomShape:
    """撮影の図形。視野は MR の撮影なら 240 mm、ほかは CT の 画素数 × 画素間隔."""
    if any(series.modality == "MR" for series in series_list):
        field_of_view = (MR_FIELD_OF_VIEW_MM, MR_FIELD_OF_VIEW_MM)
    else:
        row_spacing, col_spacing = CT_PIXEL_SPACING_MM
        field_of_view = (cols * col_spacing, rows * row_spacing)
    return phantom_shape(series_list, field_of_view)


def series_phantom_pixels(
    shape: PhantomShape,
    series: SeriesConfig,
    spatial: SpatialCoordinates,
    image_index: int,
    *,
    rows: int,
    cols: int,
    bits_stored: int,
) -> np.ndarray:
    """CT・MR のシリーズの1枚の図形の画素.

    MR の画素間隔は DICOMBuilder.build_mr_image と同じく 視野 ÷ 画素数。CT の
    位置決めは投影の画像、MR の位置決めは断層の画像として評価する。`series.phantom`
    があれば部位の図形、無ければ基本の図形（回転楕円体）にする。
    """
    mr_series = series.modality == "MR"
    if mr_series:
        pixel_spacing = (MR_FIELD_OF_VIEW_MM / rows, MR_FIELD_OF_VIEW_MM / cols)
        values = mr_phantom_values(bits_stored)
    else:
        pixel_spacing = (spatial.pixel_spacing[0], spatial.pixel_spacing[1])
        values = CT_PHANTOM_VALUES
    geometry = {
        "position": spatial.image_position_patient,
        "orientation": spatial.image_orientation_patient,
        "pixel_spacing": pixel_spacing,
        "rows": rows,
        "cols": cols,
        "index": image_index,
        "count": series.num_images,
        "projection": not mr_series and series.kind == "localizer",
        "dtype": np.uint16 if mr_series else np.int16,
    }
    if series.phantom is not None:
        segment_values = (
            mr_segment_values(mr_weighting_of(series), bits_stored)
            if mr_series
            else ct_segment_values(series)
        )
        return render_region(
            shape, series.phantom, values=segment_values, marker=values.marker, **geometry
        )
    return render_phantom(shape, values=values, **geometry)
