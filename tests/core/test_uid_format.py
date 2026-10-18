"""UID の形の確かめ（PS3.5 9.1）の試験."""

from __future__ import annotations

import pytest

from app.core.uid_format import UID_MAX_LENGTH, is_valid_uid


@pytest.mark.parametrize(
    "value",
    ["0", "0.1.2", "2.25.0", "1.2.840.10008.1.2.1", "1." + "2" * (UID_MAX_LENGTH - 2)],
)
def test_valid_uids(value: str) -> None:
    assert is_valid_uid(value)


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1..2",
        "../x",
        "..",
        "01.2",
        "1.02.3",
        "1.2.a",
        "1.2.",
        ".1.2",
        "1.2\x00",
        "1.2\n",
        "/1.2",
        "1.2/3",
        "1" * (UID_MAX_LENGTH + 1),
        "１.２",
    ],
)
def test_invalid_uids(value: str) -> None:
    assert not is_valid_uid(value)
