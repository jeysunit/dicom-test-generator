"""相手から来る値の制御文字を見える形にする（docs/spec/12a_web_screens_and_cli.md 10.8・11.7）.

端末（CLI）と画面（ウェブ）の両方が使う Pure な処理。
"""

from __future__ import annotations

_C0_MAX = 0x1F
_DEL = 0x7F
_C1_MIN = 0x80
_C1_MAX = 0x9F
_LATIN1_MAX = 0xFF
# Unicode の双方向の制御文字（Trojan Source の類）と行・段落の区切り
_BIDI_AND_SEPARATORS = frozenset(
    {0x061C, 0x200E, 0x200F, 0x2028, 0x2029}
    | set(range(0x202A, 0x202F))
    | set(range(0x2066, 0x206A))
)


def is_unsafe_char(char: str) -> bool:
    """生で出すと危ない字か（C0・DEL・C1・双方向の制御・行の区切り）."""
    code = ord(char)
    return (
        code <= _C0_MAX
        or code == _DEL
        or _C1_MIN <= code <= _C1_MAX
        or code in _BIDI_AND_SEPARATORS
    )


def make_visible(text: str) -> str:
    """危ない字を `\\x1b`・`\\u202e` のような見える形に置き換える."""
    return "".join(_visible(char) if is_unsafe_char(char) else char for char in text)


def _visible(char: str) -> str:
    code = ord(char)
    if code <= _LATIN1_MAX:
        return f"\\x{code:02x}"
    return f"\\u{code:04x}"
