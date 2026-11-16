"""選んだときだけの焼き込み（burn_in。docs/spec/06 の 4.8・ADR-0033 の決定5）.

`phantom` の画素の上端に帯を敷き、画素の値の最小と最大だけで文字を描く。文字は
Pillow の既定のフォントで、ASCII の印字できる字だけを使う。匿名化ツールが画素の
焼き込みを見つけられるかの試験に使う。通信・ファイル・ログを持たない（app/core の決まり）。
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .models import SpatialCoordinates

# 画像の幅 256 画素ごとに 1 倍ずつ拡大する（最近傍）
SCALE_PER_WIDTH = 256
# 帯の左右と上下の余白（拡大の前の画素）
MARGIN = 2
# 描く字が ASCII の印字できる字でないときの代わり
REPLACEMENT_CHAR = "?"
_ASCII_PRINTABLE_MIN, _ASCII_PRINTABLE_MAX = 0x20, 0x7E
_MASK_THRESHOLD = 128


def ascii_text(text: str) -> str:
    """ASCII の印字できる字以外を `?` にする."""
    return "".join(
        char if _ASCII_PRINTABLE_MIN <= ord(char) <= _ASCII_PRINTABLE_MAX else REPLACEMENT_CHAR
        for char in text
    )


def plane_location(spatial: SpatialCoordinates) -> str:
    """断層の画像の位置。軸位は `Z`、冠状断は `Y`、矢状断は `X` と、その軸の位置（mm）."""
    row, col = spatial.image_orientation_patient[:3], spatial.image_orientation_patient[3:]
    normal = (
        row[1] * col[2] - row[2] * col[1],
        row[2] * col[0] - row[0] * col[2],
        row[0] * col[1] - row[1] * col[0],
    )
    axis = max(range(3), key=lambda index: abs(normal[index]))
    return f"{'XYZ'[axis]} {spatial.image_position_patient[axis]:+.1f} mm"


def burn_in_lines(
    patient_id: str,
    study_date: str,
    series_number: int,
    image_number: int,
    image_count: int,
    location: str,
) -> list[str]:
    """帯に描く3行。`TEST / SYNTHETIC`・患者 ID・検査日、シリーズと何枚目か、位置か方向."""
    lines = [
        f"TEST / SYNTHETIC  ID {patient_id}  {study_date}",
        f"SE {series_number}  IM {image_number}/{image_count}",
        location,
    ]
    return [ascii_text(line) for line in lines]


def _fit(font: ImageFont.ImageFont, lines: list[str], cols: int) -> tuple[list[str], int]:
    """幅に収まる拡大の倍率と行を決める。倍率 1 でも収まらない行は、収まる字までに切る."""
    for scale in range(max(1, cols // SCALE_PER_WIDTH), 0, -1):
        available = cols // scale - 2 * MARGIN
        if all(font.getlength(line) <= available for line in lines):
            return lines, scale
    available = cols - 2 * MARGIN
    cut = []
    for line in lines:
        while line and font.getlength(line) > available:
            line = line[:-1]
        cut.append(line)
    return cut, 1


def burn_in_band(
    pixels: np.ndarray, lines: list[str], *, low: int, high: int
) -> tuple[np.ndarray, int]:
    """上端の帯を `low` で敷き、`lines` を `high` で描いた新しい配列と帯の高さを返す.

    帯の高さは、行数 × 行の高さ × 拡大の倍率 + 余白。画像の高さを超えるときは
    入る行までを描く。画素の型は変えない。
    """
    rows, cols = pixels.shape
    font = ImageFont.load_default()
    lines, scale = _fit(font, lines, cols)
    ascent, descent = font.getmetrics() if hasattr(font, "getmetrics") else (10, 2)
    line_height = ascent + descent
    small_rows = 2 * MARGIN + line_height * len(lines)
    canvas = Image.new("L", (max(1, cols // scale), small_rows), color=0)
    draw = ImageDraw.Draw(canvas)
    for number, line in enumerate(lines):
        draw.text((MARGIN, MARGIN + number * line_height), line, fill=255, font=font)
    mask = np.asarray(canvas) >= _MASK_THRESHOLD
    mask = np.kron(mask, np.ones((scale, scale), dtype=bool))
    band_rows = min(rows, mask.shape[0])
    banner = np.full((band_rows, cols), low, dtype=pixels.dtype)
    width = min(cols, mask.shape[1])
    banner[:, :width][mask[:band_rows, :width]] = high
    result = pixels.copy()
    result[:band_rows] = banner
    return result, band_rows

