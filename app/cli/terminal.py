"""相手から来る値を端末に出す前に、制御文字を見える形にする（spec/12_modality_emulator.md 11.7）.

ワークリストの値（氏名・記述など）は相手の SCP が自由に入れられる。ESC・CSI・OSC などの
制御文字をそのまま端末に出すと、表示や端末の題を書き換えられる。
"""

from __future__ import annotations

import json
from typing import Any

_C0_MAX = 0x1F
_DEL = 0x7F
_C1_MIN = 0x80
_C1_MAX = 0x9F
# Unicode の双方向の制御文字（Trojan Source の類）と行・段落の区切り
_BIDI_AND_SEPARATORS = frozenset(
    {0x061C, 0x200E, 0x200F, 0x2028, 0x2029}
    | set(range(0x202A, 0x202F))
    | set(range(0x2066, 0x206A))
)


def is_unsafe_char(char: str) -> bool:
    """端末に生で出すと危ない字か（C0・DEL・C1・双方向の制御・行の区切り）."""
    code = ord(char)
    return (
        code <= _C0_MAX
        or code == _DEL
        or _C1_MIN <= code <= _C1_MAX
        or code in _BIDI_AND_SEPARATORS
    )


def sanitize_for_terminal(text: str) -> str:
    """危ない字を `\\x1b`・`\\u202e` のような見える形に置き換える."""
    return "".join(_visible(char) if is_unsafe_char(char) else char for char in text)


def json_for_terminal(data: Any) -> str:
    """JSON にする。危ない字は JSON の `\\uXXXX` に直す（読み戻すと元の値に戻る）."""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    # json.dumps は C0 を必ず \\uXXXX にする。残る DEL・C1・双方向の制御は文字列の中にしか
    # 現れないので、ここで \\uXXXX に直しても JSON として同じ値のまま
    return "".join(
        f"\\u{ord(char):04x}" if is_unsafe_char(char) and ord(char) > _C0_MAX else char
        for char in text
    )


def _visible(char: str) -> str:
    code = ord(char)
    if code <= 0xFF:
        return f"\\x{code:02x}"
    return f"\\u{code:04x}"
