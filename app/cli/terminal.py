"""相手から来る値を端末に出す前に、制御文字を見える形にする（spec/12a_web_screens_and_cli.md 11.7）.

ワークリストの値（氏名・記述など）は相手の SCP が自由に入れられる。ESC・CSI・OSC などの
制御文字をそのまま端末に出すと、表示や端末の題を書き換えられる。
字の判定と置き換えは、画面（app/web/）と同じく app/core/text_safety.py を使う。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.text_safety import is_unsafe_char, make_visible

_C0_MAX = 0x1F

__all__ = [
    "TerminalSafeFormatter",
    "is_unsafe_char",
    "json_for_terminal",
    "sanitize_for_terminal",
]


def sanitize_for_terminal(text: str) -> str:
    """危ない字を `\\x1b`・`\\u202e` のような見える形に置き換える."""
    return make_visible(text)


class TerminalSafeFormatter(logging.Formatter):
    """整えた後のログの文を、行ごとに sanitize_for_terminal に通す（改行は残す）.

    例外の Traceback も整えた文に入るので、同じく見える形になる。
    """

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        return "\n".join(sanitize_for_terminal(line) for line in text.split("\n"))


def json_for_terminal(data: Any) -> str:
    """JSON にする。危ない字は JSON の `\\uXXXX` に直す（読み戻すと元の値に戻る）."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    # json.dumps は C0 を必ず \\uXXXX にする。残る DEL・C1・双方向の制御は文字列の中にしか
    # 現れないので、ここで \\uXXXX に直しても JSON として同じ値のまま
    return "".join(
        f"\\u{ord(char):04x}" if is_unsafe_char(char) and ord(char) > _C0_MAX else char
        for char in text
    )
