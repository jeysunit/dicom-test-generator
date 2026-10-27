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
from dataclasses import dataclass

import numpy as np

from .models import SeriesConfig, SpatialCoordinates
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


def mr_phantom_values(bits_stored: int) -> PhantomValues:
    """MR の値。符号なしの Bits Stored の上限に割合を掛けて丸める."""
    upper = (1 << bits_stored) - 1
    return PhantomValues(
        background=int(np.rint(upper * MR_BACKGROUND_FRACTION)),
        shape=int(np.rint(upper * MR_SHAPE_FRACTION)),
        marker=int(np.rint(upper * MR_MARKER_FRACTION)),
    )


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
) -> np.ndarray:
    """1枚の画像の画素（int16）.

    `projection` は投影の画像（位置決め）で、画像の面に垂直な向きの座標を図形の
    中心に置いて評価する（回転楕円体の影は中心を通る断面と同じ形になる）。
    """
    if count < 1 or not 0 <= index < count:
        raise ValueError(f"index must be in 0..count-1, got index={index} count={count}")
    x, y, z = _pixel_coordinates(position, orientation, pixel_spacing, rows, cols)
    coords = [x, y, z]
    if projection:
        normal = np.cross(orientation[:3], orientation[3:])
        axis = int(np.argmax(np.abs(normal)))
        coords[axis] = np.full_like(coords[axis], shape.center[axis])
    inside = sum(
        ((coords[axis] - shape.center[axis]) / shape.radii[axis]) ** 2 for axis in range(3)
    ) <= 1.0
    pixels = np.where(inside, values.shape, values.background).astype(np.int16)
    r0, r1, c0, c1 = marker_bounds(rows, cols, index, count)
    pixels[max(r0, 0) : max(r1, 0), max(c0, 0) : max(c1, 0)] = values.marker
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
    位置決めは投影の画像、MR の位置決めは断層の画像として評価する。
    """
    mr_series = series.modality == "MR"
    if mr_series:
        pixel_spacing = (MR_FIELD_OF_VIEW_MM / rows, MR_FIELD_OF_VIEW_MM / cols)
        values = mr_phantom_values(bits_stored)
    else:
        pixel_spacing = (spatial.pixel_spacing[0], spatial.pixel_spacing[1])
        values = CT_PHANTOM_VALUES
    return render_phantom(
        shape,
        position=spatial.image_position_patient,
        orientation=spatial.image_orientation_patient,
        pixel_spacing=pixel_spacing,
        rows=rows,
        cols=cols,
        index=image_index,
        count=series.num_images,
        values=values,
        projection=not mr_series and series.kind == "localizer",
    )
