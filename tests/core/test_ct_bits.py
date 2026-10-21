"""CT Image の Bits Allocated・Bits Stored・Rescale の試験（PS3.3 C.8.2.1.1.4・C.8.2.1.1.5）."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.models import PixelSpecCTRealistic
from tests.core.test_ct_image_conformance import _build


def test_text_image_is_written_as_16_bit_ct() -> None:
    # simple_text の uint8 の画像も、CT では Bits Allocated 16・Bits Stored 12〜16
    pixels = np.array([[0, 128, 255]], dtype=np.uint8)

    ds = _build(pixels=pixels, bits_stored=12)

    assert ds.BitsAllocated == 16
    assert ds.BitsStored == 12
    assert ds.HighBit == 11
    assert ds.PixelRepresentation == 1
    assert str(ds.RescaleIntercept) == "-1024"
    assert str(ds.RescaleSlope) == "1"
    values = np.frombuffer(ds.PixelData, dtype="<i2")
    assert values.tolist() == [0, 1028, 2047]


def test_ct_realistic_bits_stored_below_12_is_rejected() -> None:
    with pytest.raises(ValidationError):
        PixelSpecCTRealistic(bits_stored=11)


@pytest.mark.parametrize("bits_stored", [12, 16])
def test_ct_realistic_bits_stored_12_to_16_is_accepted(bits_stored: int) -> None:
    assert PixelSpecCTRealistic(bits_stored=bits_stored).bits_stored == bits_stored
