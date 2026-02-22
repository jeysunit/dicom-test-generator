from __future__ import annotations

import numpy as np
import pytest

from app.core.exceptions import PixelGenerationError
from app.core.pixel_generator import PixelGenerator


def test_simple_text_default_size() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_simple_text("2.25.123456")

    assert pixels.shape == (512, 512)
    assert pixels.dtype == np.uint8


def test_simple_text_custom_size() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_simple_text("2.25.123456", width=128, height=64)

    assert pixels.shape == (64, 128)
    assert pixels.dtype == np.uint8


def test_simple_text_has_nonzero_pixels() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_simple_text("2.25.123456")

    assert np.any(pixels > 0)


def test_ct_realistic_gradient_shape_dtype() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_ct_realistic(pattern="gradient")

    assert pixels.shape == (512, 512)
    assert pixels.dtype == np.int16


def test_ct_realistic_circle_pattern() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_ct_realistic(width=128, height=128, pattern="circle")

    center_value = int(pixels[64, 64])
    edge_value = int(pixels[0, 0])

    assert center_value > edge_value


def test_ct_realistic_noise_pattern() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_ct_realistic(width=128, height=128, pattern="noise")

    assert float(np.var(pixels)) > 0.0


def test_ct_realistic_bits_stored_12() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_ct_realistic(bits_stored=12)

    assert int(pixels.max()) <= 4095


def test_ct_realistic_bits_stored_16() -> None:
    generator = PixelGenerator()

    pixels = generator.generate_ct_realistic(bits_stored=16)

    assert int(pixels.max()) <= np.iinfo(np.int16).max


def test_ct_realistic_unknown_pattern_raises_error() -> None:
    generator = PixelGenerator()

    with pytest.raises(PixelGenerationError):
        generator.generate_ct_realistic(pattern="unknown")
