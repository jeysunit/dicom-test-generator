"""部位の図形（phantom の head・chest・trunk・abdomen・spine・limb。docs/spec/06 の 4.6）.

部位の図形は、楕円体・楕円柱・円柱・直方体とその殻（外側の図形の上に内側の図形を
重ねて描く）の組み合わせだけで作り、区分（空気・肺・液・軟部・実質・血管・骨）ごとに
一定の値にする。臓器や骨の輪郭は描かない（ADR-0033 の「明らかに偽物」）。図形の
大きさと位置は、撮影ごとに一度だけ決める基本の回転楕円体（PhantomShape の中心と
半径）から決めるので、軸位・冠状断・矢状断・位置決めは同じ図形の断面と影になる。

値は design.md の架空の値で、CT は HU、MR と X 線は Bits Stored の上限に対する割合。
通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from .models import ContrastPhase, MRWeighting, PhantomRegion, SeriesConfig

Segment = Literal["air", "lung", "fluid", "soft", "parenchyma", "vessel", "bone"]
Vector = tuple[float, float, float]

# CT の値（HU。架空）。単純と、造影の相で実質と血管の値を変える
CT_PLAIN_HU: dict[Segment, int] = {
    "air": -1000,
    "lung": -850,
    "fluid": 5,
    "soft": 40,
    "parenchyma": 55,
    "vessel": 40,
    "bone": 1000,
}
CT_PHASE_HU: dict[ContrastPhase, dict[Segment, int]] = {
    "arterial": {"parenchyma": 90, "vessel": 300},
    "portal": {"parenchyma": 120, "vessel": 180},
    "delayed": {"parenchyma": 95, "vessel": 110},
}
# 相を書いていない造影のシリーズは門脈相の値で描く
DEFAULT_CONTRAST_PHASE: ContrastPhase = "portal"
CT_RESCALE_OFFSET = 1024

# MR の値（符号なしの Bits Stored の上限に対する割合。架空）。空気と肺は 0
_MR_SEGMENTS: tuple[Segment, ...] = ("soft", "fluid", "parenchyma", "vessel", "bone")
MR_FRACTIONS: dict[MRWeighting, tuple[float, ...]] = {
    # 区分の並びは _MR_SEGMENTS（軟部・液・実質・血管・骨）
    "T1": (0.40, 0.10, 0.45, 0.10, 0.60),
    "T2": (0.35, 0.90, 0.25, 0.05, 0.30),
    "PD": (0.45, 0.60, 0.40, 0.10, 0.50),
    "FLAIR": (0.40, 0.05, 0.30, 0.05, 0.35),
    "T2STAR": (0.30, 0.80, 0.25, 0.05, 0.10),
    "DWI": (0.40, 0.05, 0.35, 0.05, 0.10),
    "ADC": (0.30, 0.90, 0.25, 0.20, 0.10),
    "MRA": (0.10, 0.10, 0.10, 0.95, 0.05),
}
# weighting を書いていない MR のシリーズの強調。位置決めは T1、計算で作った画像は ADC、
# ほかはシーケンス（Scanning Sequence）から決める
MR_LOCALIZER_WEIGHTING: MRWeighting = "T1"
MR_DERIVED_WEIGHTING: MRWeighting = "ADC"
MR_SEQUENCE_WEIGHTING: dict[str, MRWeighting] = {
    "SE": "T2",
    "IR": "FLAIR",
    "GR": "T2STAR",
    "EP": "DWI",
}

# X 線（CR・DX）の値（MONOCHROME2 の、Bits Stored の上限に対する割合。架空）
XRAY_FRACTIONS: dict[Segment, float] = {
    "air": 0.05,
    "lung": 0.15,
    "fluid": 0.35,
    "soft": 0.35,
    "parenchyma": 0.40,
    "vessel": 0.35,
    "bone": 0.80,
}

# 図形の寸法。割合は基本の回転楕円体の半径に対する割合、mm は患者座標の長さ
HEAD_SKULL_MM = 6.0
HEAD_FLUID_FRACTION = 0.25
# 体の楕円柱の前後の半径（y の半径に対する割合。体は左右に広い）
BODY_DEPTH_FRACTION = 0.7
VESSEL_RADIUS_FRACTION = 0.08
SPINE_RADIUS_FRACTION = 0.12
SPINE_DEPTH_FRACTION = 0.75
# 脊椎の直方体（架空の高さ）と、直方体の間のすきま
VERTEBRA_HEIGHT_MM = 25.0
VERTEBRA_GAP_MM = 5.0
VERTEBRA_HALF_WIDTH_FRACTION = 0.15
VERTEBRA_HALF_DEPTH_FRACTION = 0.18
VERTEBRA_DEPTH_FRACTION = 0.6
# 四肢：細い円柱（軟部）と、同じ軸の2本の円柱（骨）の間のすきま
LIMB_RADIUS_FRACTION = 0.5
LIMB_BONE_RADIUS_FRACTION = 0.2
LIMB_GAP_MM = 8.0


@dataclass(frozen=True)
class Solid:
    """1つの図形。`form` は ellipsoid（楕円体）・cylinder（z の向きの楕円柱）・box（直方体）.

    `z_range` は z の範囲（下端を含み、上端を含まない）。`period` は直方体を z の向きに
    （周期, 長さ）で並べる。`projected` が偽なら投影の画像（位置決め・CR・DX）に描かない。
    """

    segment: Segment
    form: Literal["ellipsoid", "cylinder", "box"]
    center: Vector
    radii: Vector
    z_range: tuple[float, float] | None = None
    period: tuple[float, float] | None = None
    projected: bool = True


def _inside(
    solid: Solid, coords: Sequence[np.ndarray], drop_axis: int | None
) -> np.ndarray:
    """図形の内側か。`drop_axis` は投影の向き（その座標を見ないので、図形の影になる）."""
    if solid.form == "ellipsoid":
        axes = [axis for axis in range(3) if axis != drop_axis]
        mask = sum(
            ((coords[axis] - solid.center[axis]) / solid.radii[axis]) ** 2 for axis in axes
        ) <= 1.0
    elif solid.form == "cylinder":
        axes = [axis for axis in (0, 1) if axis != drop_axis]
        mask = sum(
            ((coords[axis] - solid.center[axis]) / solid.radii[axis]) ** 2 for axis in axes
        ) <= 1.0
    else:
        box_axes = (0, 1) if solid.period is not None else (0, 1, 2)
        mask = np.ones(np.shape(coords[0]), dtype=bool)
        for axis in box_axes:
            if axis != drop_axis:
                mask &= np.abs(coords[axis] - solid.center[axis]) <= solid.radii[axis]
    mask = np.broadcast_to(mask, np.shape(coords[0])).copy()
    if drop_axis != 2:
        z = coords[2]
        if solid.z_range is not None:
            mask &= (z >= solid.z_range[0]) & (z < solid.z_range[1])
        if solid.period is not None:
            period, length = solid.period
            mask &= np.mod(z - solid.center[2] + length / 2, period) < length
    return mask


def _body(center: Vector, radii: Vector) -> Solid:
    """体の楕円柱（軟部）."""
    return Solid(
        "soft", "cylinder", center, (radii[0], radii[1] * BODY_DEPTH_FRACTION, radii[2])
    )


def _circle(segment: Segment, x: float, y: float, radius: float, **extra) -> Solid:
    return Solid(segment, "cylinder", (x, y, 0.0), (radius, radius, 1.0), **extra)


def _head(center: Vector, radii: Vector) -> list[Solid]:
    """楕円体の殻（骨）・その中の楕円体（軟部）・中央の小さい楕円体（液）."""
    inner = tuple(max(r - HEAD_SKULL_MM, r / 2) for r in radii)
    fluid = tuple(r * HEAD_FLUID_FRACTION for r in inner)
    return [
        Solid("bone", "ellipsoid", center, radii),
        Solid("soft", "ellipsoid", center, inner),
        Solid("fluid", "ellipsoid", center, fluid, projected=False),
    ]


def _back_bone(center: Vector, radii: Vector, **extra) -> Solid:
    depth = radii[1] * BODY_DEPTH_FRACTION
    return _circle(
        "bone",
        center[0],
        center[1] + depth * SPINE_DEPTH_FRACTION,
        radii[0] * SPINE_RADIUS_FRACTION,
        **extra,
    )


def _chest_inside(
    center: Vector, radii: Vector, z_range: tuple[float, float] | None = None
) -> list[Solid]:
    """中央の円柱（血管）・左右の楕円体2つ（肺）・背側の円柱（骨。投影には描かない）.

    断層の画像では血管と肺は重ならない。側面の投影では肺を血管の上に描き、肺の楕円を
    1つにする。
    """
    cx, cy, cz = center
    bx, by = radii[0], radii[1] * BODY_DEPTH_FRACTION
    lung_radii = (0.35 * bx, 0.6 * by, 0.9 * radii[2])
    return [
        _circle("vessel", cx, cy - 0.1 * by, VESSEL_RADIUS_FRACTION * bx, z_range=z_range),
        Solid("lung", "ellipsoid", (cx - 0.45 * bx, cy - 0.05 * by, cz), lung_radii,
              z_range=z_range),
        Solid("lung", "ellipsoid", (cx + 0.45 * bx, cy - 0.05 * by, cz), lung_radii,
              z_range=z_range),
        _back_bone(center, radii, z_range=z_range, projected=False),
    ]


def _abdomen_inside(
    center: Vector, radii: Vector, z_range: tuple[float, float] | None = None
) -> list[Solid]:
    """大きい楕円体1つと小さい楕円体2つ（実質）・中央の円柱（血管）・背側の円柱（骨）.

    投影の画像には骨の円柱（縦の棒）だけを描く。
    """
    cx, cy, cz = center
    bx, by, rz = radii[0], radii[1] * BODY_DEPTH_FRACTION, radii[2]
    organs = [
        ((cx - 0.4 * bx, cy - 0.15 * by, cz), (0.4 * bx, 0.5 * by, 0.7 * rz)),
        ((cx + 0.5 * bx, cy - 0.2 * by, cz + 0.1 * rz), (0.2 * bx, 0.3 * by, 0.4 * rz)),
        ((cx + 0.35 * bx, cy + 0.4 * by, cz - 0.2 * rz), (0.15 * bx, 0.2 * by, 0.35 * rz)),
    ]
    return [
        *(
            Solid("parenchyma", "ellipsoid", c, r, z_range=z_range, projected=False)
            for c, r in organs
        ),
        _circle(
            "vessel", cx, cy + 0.2 * by, VESSEL_RADIUS_FRACTION * bx,
            z_range=z_range, projected=False,
        ),
        _back_bone(center, radii, z_range=z_range),
    ]


def _spine(center: Vector, radii: Vector) -> list[Solid]:
    """体の楕円柱・背側に並ぶ直方体の列（骨）。直方体の間は 5 mm のすきま（軟部）."""
    cx, cy, cz = center
    bx, by = radii[0], radii[1] * BODY_DEPTH_FRACTION
    vertebra = Solid(
        "bone",
        "box",
        (cx, cy + VERTEBRA_DEPTH_FRACTION * by, cz),
        (VERTEBRA_HALF_WIDTH_FRACTION * bx, VERTEBRA_HALF_DEPTH_FRACTION * by, 0.0),
        period=(VERTEBRA_HEIGHT_MM + VERTEBRA_GAP_MM, VERTEBRA_HEIGHT_MM),
    )
    return [_body(center, radii), vertebra]


def _limb(center: Vector, radii: Vector) -> list[Solid]:
    """細い円柱（軟部）・同じ軸の2本の円柱（骨）。2本の間は 8 mm のすきま."""
    cx, cy, cz = center
    bone = LIMB_BONE_RADIUS_FRACTION * radii[0]
    return [
        _circle("soft", cx, cy, LIMB_RADIUS_FRACTION * radii[0]),
        _circle("bone", cx, cy, bone, z_range=(cz + LIMB_GAP_MM / 2, math.inf)),
        _circle("bone", cx, cy, bone, z_range=(-math.inf, cz - LIMB_GAP_MM / 2)),
    ]


def region_solids(region: PhantomRegion, center: Vector, radii: Vector) -> list[Solid]:
    """部位の図形。後の図形ほど上に描く（殻は外側の上に内側を重ねる）."""
    if region == "head":
        return _head(center, radii)
    if region == "chest":
        return [_body(center, radii), *_chest_inside(center, radii)]
    if region == "abdomen":
        return [_body(center, radii), *_abdomen_inside(center, radii)]
    if region == "trunk":
        # 上半分は chest、下半分は abdomen（それぞれ半分の範囲に収める）
        cx, cy, cz = center
        half = (radii[0], radii[1], radii[2] / 2)
        upper = (cx, cy, cz + radii[2] / 2)
        lower = (cx, cy, cz - radii[2] / 2)
        return [
            _body(center, radii),
            *_chest_inside(upper, half, z_range=(cz, math.inf)),
            *_abdomen_inside(lower, half, z_range=(-math.inf, cz)),
        ]
    if region == "spine":
        return _spine(center, radii)
    return _limb(center, radii)


def render_solids(
    solids: Sequence[Solid],
    coords: Sequence[np.ndarray],
    values: dict[Segment, int],
    *,
    drop_axis: int | None = None,
    dtype: type[np.integer] = np.int16,
) -> np.ndarray:
    """画素ごとに、上に描いた図形の区分の値にする。どの図形にも入らなければ空気.

    `drop_axis` を渡すと投影の画像で、`projected` の図形の影を描く。
    """
    pixels = np.full(np.shape(coords[0]), values["air"], dtype=dtype)
    for solid in solids:
        if drop_axis is not None and not solid.projected:
            continue
        pixels[_inside(solid, coords, drop_axis)] = values[solid.segment]
    return pixels


def ct_segment_values(series: SeriesConfig) -> dict[Segment, int]:
    """CT の区分の格納値（HU + 1024）。造影のシリーズは相（省けば門脈相）の値."""
    hu = dict(CT_PLAIN_HU)
    if series.contrast:
        hu.update(CT_PHASE_HU[series.phase or DEFAULT_CONTRAST_PHASE])
    return {segment: value + CT_RESCALE_OFFSET for segment, value in hu.items()}


def mr_weighting_of(series: SeriesConfig) -> MRWeighting:
    """MR のシリーズの強調。書いていなければ種類とシーケンスから決める."""
    if series.weighting is not None:
        return series.weighting
    if series.kind == "localizer":
        return MR_LOCALIZER_WEIGHTING
    if series.kind == "derived":
        return MR_DERIVED_WEIGHTING
    return MR_SEQUENCE_WEIGHTING[series.sequence]


def _fraction(upper: int, fraction: float) -> int:
    return int(np.rint(upper * fraction))


def mr_segment_values(weighting: MRWeighting, bits_stored: int) -> dict[Segment, int]:
    """MR の区分の値。符号なしの Bits Stored の上限に割合を掛けて丸める."""
    upper = (1 << bits_stored) - 1
    values: dict[Segment, int] = {"air": 0, "lung": 0}
    for segment, fraction in zip(_MR_SEGMENTS, MR_FRACTIONS[weighting], strict=True):
        values[segment] = _fraction(upper, fraction)
    return values


def xray_segment_values(bits_stored: int) -> dict[Segment, int]:
    """CR・DX の区分の値（MONOCHROME2）."""
    upper = (1 << bits_stored) - 1
    return {segment: _fraction(upper, f) for segment, f in XRAY_FRACTIONS.items()}
