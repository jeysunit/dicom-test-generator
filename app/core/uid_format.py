"""DICOM の UID の形の確かめ（PS3.5 9.1）.

相手から来る UID（ワークリストの予約・保管の確認の応答）は、
そのまま画像やパスに使う前にこの形を確かめる。
Core Engine の Pure な処理（ファイル・通信・ログを使わない）。
"""

from __future__ import annotations

import re

UID_MAX_LENGTH = 64
_UID_PATTERN = re.compile(r"[0-9]+(?:\.[0-9]+)*")
_ZERO_COMPONENT = "0"


def is_valid_uid(value: str) -> bool:
    """`value` が UID の形か.

    - 数字と `.` だけで、`.` で始まらず終わらず、`..` を含まない
    - 64 字まで
    - 各成分は `0` か、`0` で始まらない数字の並び
    """
    if not value or len(value) > UID_MAX_LENGTH or not _UID_PATTERN.fullmatch(value):
        return False
    return all(
        component == _ZERO_COMPONENT or not component.startswith(_ZERO_COMPONENT)
        for component in value.split(".")
    )
