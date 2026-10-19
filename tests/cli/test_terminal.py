"""端末への制御文字の注入を防ぐ（spec/12a の 11.7）の試験."""

from __future__ import annotations

import json
import logging

import pytest

from app.cli.main import setup_logging
from app.cli.terminal import json_for_terminal, sanitize_for_terminal

UNSAFE = [
    "\x1b[2J",  # CSI：画面を消す
    "\x1b]0;owned\x07",  # OSC：端末の題を書き換える
    "\x9b31m",  # C1 の CSI
    "\x7f",  # DEL
    "a\rb",  # 行の頭へ戻る
    "\u202eevil",  # 右から左への上書き
    "\u2066x\u2069",  # 双方向の分離
]


@pytest.mark.parametrize("value", UNSAFE)
def test_sanitize_makes_control_chars_visible(value: str) -> None:
    result = sanitize_for_terminal(value)

    assert all(ord(c) >= 0x20 and c != "\x7f" and not 0x80 <= ord(c) <= 0x9F for c in result)
    assert "\u202e" not in result and "\u2066" not in result
    assert "\\x" in result or "\\u" in result


def test_sanitize_keeps_japanese_and_ascii() -> None:
    text = "YAMADA^TARO=山田^太郎=やまだ^たろう ﾔﾏﾀﾞ"

    assert sanitize_for_terminal(text) == text


def test_sanitize_examples() -> None:
    assert sanitize_for_terminal("\x1b[2J") == "\\x1b[2J"
    assert sanitize_for_terminal("\u202e") == "\\u202e"


@pytest.mark.parametrize("value", UNSAFE)
def test_json_escapes_but_round_trips(value: str) -> None:
    text = json_for_terminal({"name": value, "kanji": "山田"})

    assert all(not (ord(c) < 0x20 and c not in "\n ") for c in text)
    assert not any(c == "\x7f" or 0x80 <= ord(c) <= 0x9F for c in text)
    assert "\u202e" not in text and "\u2066" not in text
    assert json.loads(text) == {"name": value, "kanji": "山田"}
    assert "山田" in text


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    yield
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in saved_handlers:
        root.addHandler(handler)
    root.setLevel(saved_level)


def test_console_log_neutralizes_control_chars_but_keeps_newlines(
    tmp_path, capsys, restore_root_logging
) -> None:
    """端末に出すログを行ごとに sanitize_for_terminal に通す（spec/12a の 11.7）."""
    log_file = tmp_path / "cli.log"
    setup_logging(verbose=False, quiet=False, log_file=str(log_file))
    logger = logging.getLogger("tests.terminal")

    logger.info("first \x1b[2J line\nsecond ‮ line")
    try:
        raise RuntimeError("boom \x1b]0;owned\x07")
    except RuntimeError:
        logger.error("failed", exc_info=True)

    err = capsys.readouterr().err
    assert "\x1b" not in err and "\x07" not in err and "‮" not in err
    assert "first \\x1b[2J line\nsecond \\u202e line" in err
    assert "boom \\x1b]0;owned\\x07" in err
    assert "Traceback (most recent call last):\n" in err
    # ファイルのログはそのまま
    assert "first \x1b[2J line" in log_file.read_text(encoding="utf-8")
