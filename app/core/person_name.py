"""手で入れた氏名を PN（DICOM の Person Name）の形にする（spec/12_modality_emulator.md 10.5）.

人は姓と名の区切りの `^` を打たないので、空白を `^` に置き換える。Pure な処理。
"""

from __future__ import annotations

import re

from .exceptions import ValidationError
from .text_safety import is_unsafe_char

GROUP_SEPARATOR = "="
COMPONENT_SEPARATOR = "^"
# 前後の空白は落とす。`^` の前後の空白は `^` に寄せる。続いた空白（全角を含む）は1つの `^`
_SPACES_AROUND_CARET = re.compile(r"\s*\^\s*")
_SPACES = re.compile(r"\s+")


def normalize_name_group(value: str) -> str:
    """氏名の1つの群（英字・漢字・かなのどれか）の空白を `^` にする.

    `=`（群の区切り）と制御文字は断る（`ValidationError`）。空白だけなら空を返す。
    """
    if GROUP_SEPARATOR in value:
        # 誤りの文に入れた値を出さない（spec/12 の 12 章）
        raise ValidationError("氏名に「=」は使えません（英字・漢字・かなは別の欄に入れてください）")
    if any(is_unsafe_char(char) for char in value):
        raise ValidationError("氏名に制御文字は使えません")
    text = _SPACES_AROUND_CARET.sub(COMPONENT_SEPARATOR, value.strip())
    return _SPACES.sub(COMPONENT_SEPARATOR, text)


def compose_person_name(alphabetic: str, ideographic: str, phonetic: str) -> str:
    """英字・漢字・かなの3つの欄を PN にする。後ろの空の群は付けない."""
    groups = [normalize_name_group(value) for value in (alphabetic, ideographic, phonetic)]
    while groups and not groups[-1]:
        groups.pop()
    return GROUP_SEPARATOR.join(groups)
