"""ファイル・フォルダの名前に信用できない値を使わない（docs/spec/12 の 6.5）の試験."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import FileWriteError
from app.core.path_safety import (
    SAFE_COMPONENT_MAX_LENGTH,
    ensure_within,
    safe_path_component,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("A0001", "A0001"),
        ("P000001", "P000001"),
        ("ct_generic-1.2", "ct_generic-1.2"),
        ("../../etc", ".._.._etc"),
        ("/etc/passwd", "_etc_passwd"),
        ("C:\\Windows", "C__Windows"),
        ("a\x00b", "a_b"),
        ("山田^太郎", "_____"),
        ("A 0001", "A_0001"),
    ],
)
def test_safe_path_component_replaces_unsafe_chars(value: str, expected: str) -> None:
    result = safe_path_component(value, fallback="x")

    assert result == expected
    assert "/" not in result
    assert "\\" not in result
    assert "\x00" not in result


@pytest.mark.parametrize("value", ["", ".", "..", "...", "   "])
def test_safe_path_component_uses_fallback_for_dot_or_empty(value: str) -> None:
    assert safe_path_component(value, fallback="emergency") == "emergency"


@pytest.mark.parametrize("value", ["CON", "nul", "Com1", "LPT9.txt", "aux.dcm"])
def test_safe_path_component_avoids_windows_reserved_names(value: str) -> None:
    result = safe_path_component(value, fallback="x")

    assert result.startswith("_")


def test_safe_path_component_limits_length() -> None:
    result = safe_path_component("A" * 500, fallback="x")

    assert len(result) == SAFE_COMPONENT_MAX_LENGTH


def test_safe_path_component_rejects_unsafe_fallback() -> None:
    with pytest.raises(ValueError):
        safe_path_component("..", fallback="../x")


def test_ensure_within_accepts_child(tmp_path: Path) -> None:
    child = tmp_path / "a" / "b.dcm"

    assert ensure_within(tmp_path, child) == child.resolve()


@pytest.mark.parametrize("relative", ["../outside.dcm", "a/../../outside.dcm"])
def test_ensure_within_rejects_escape(tmp_path: Path, relative: str) -> None:
    root = tmp_path / "root"
    root.mkdir()

    with pytest.raises(FileWriteError):
        ensure_within(root, root / relative)


def test_ensure_within_rejects_absolute_path(tmp_path: Path) -> None:
    with pytest.raises(FileWriteError):
        ensure_within(tmp_path / "root", Path("/etc/passwd"))
