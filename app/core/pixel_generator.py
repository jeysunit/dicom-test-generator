"""Pixel data generation utilities."""

from __future__ import annotations

from typing import Literal

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .exceptions import PixelGenerationError


class PixelGenerator:
    """ピクセルデータ生成器."""

    def generate_simple_text(
        self,
        sop_instance_uid: str,
        width: int = 512,
        height: int = 512,
    ) -> np.ndarray:
        """Simple Textモード: 黒背景に白文字でSOP Instance UIDを描画.

        Returns: shape=(height, width), dtype=uint8
        """
        try:
            img = Image.new("L", (width, height), color=0)
            draw = ImageDraw.Draw(img)

            try:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
                    16,
                )
            except (OSError, IOError):
                font = ImageFont.load_default()

            max_chars_per_line = max(1, width // 10)
            lines = [
                sop_instance_uid[i : i + max_chars_per_line]
                for i in range(0, len(sop_instance_uid), max_chars_per_line)
            ]

            y_offset = height // 4
            for line in lines:
                draw.text((10, y_offset), line, fill=255, font=font)
                y_offset += 20

            return np.array(img, dtype=np.uint8)
        except Exception as exc:
            if isinstance(exc, PixelGenerationError):
                raise
            raise PixelGenerationError(
                f"Failed to generate simple text pixel data: {exc}",
                mode="simple_text",
            ) from exc

    def generate_ct_realistic(
        self,
        width: int = 512,
        height: int = 512,
        pattern: Literal["gradient", "circle", "noise"] = "gradient",
        bits_stored: int = 12,
    ) -> np.ndarray:
        """CT Realisticモード: 16bit signed, HU値対応.

        Rescale Intercept = -1024, Rescale Slope = 1
        Pixel Value 0 -> HU -1024 (Air)
        Pixel Value 1024 -> HU 0 (Water)
        Pixel Value 2048 -> HU 1024 (Bone)

        Returns: shape=(height, width), dtype=int16
        """
        try:
            max_val = (1 << bits_stored) - 1

            if pattern == "gradient":
                row = np.linspace(0, max_val, width, dtype=np.float64)
                pixels = np.tile(row, (height, 1)).astype(np.int16)

            elif pattern == "circle":
                y, x = np.ogrid[:height, :width]
                cx, cy = width // 2, height // 2
                radius = min(width, height) // 4
                dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)

                soft_tissue_pv = 1064
                bone_pv = 2048

                pixels = np.full((height, width), soft_tissue_pv, dtype=np.int16)
                mask = dist <= radius
                pixels[mask] = bone_pv

            elif pattern == "noise":
                rng = np.random.default_rng()
                pixels = rng.integers(
                    0,
                    max_val + 1,
                    size=(height, width),
                    dtype=np.int16,
                )

            else:
                raise PixelGenerationError(
                    f"Unknown pattern: {pattern}",
                    mode="ct_realistic",
                )

            return pixels
        except Exception as exc:
            if isinstance(exc, PixelGenerationError):
                raise
            raise PixelGenerationError(
                f"Failed to generate CT realistic pixel data: {exc}",
                mode="ct_realistic",
            ) from exc
