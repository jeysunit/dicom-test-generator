"""ファイル・フォルダの名前を、信用できない値から安全に作る（spec/12_modality_emulator.md 6.5）.

ワークリストの応答や Job YAML の値（Patient ID・受付番号など）は、相手や
利用者が自由に入れられる。そのままパスに使うと、`../`・`/`・NUL・
Windows の予約名などで、決めたフォルダの外に書けてしまう。
Core Engine の Pure な処理（ファイルを作らない）。
"""

from __future__ import annotations

import re
from pathlib import Path

from .exceptions import FileWriteError

SAFE_COMPONENT_MAX_LENGTH = 64
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]")
_WINDOWS_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


def safe_path_component(value: str, fallback: str) -> str:
    """`value` を、1つのファイル・フォルダの名前に使える形にする.

    - `[A-Za-z0-9._-]` 以外の字は `_` に置き換える（区切り・NUL・空白を含む）
    - 長さは SAFE_COMPONENT_MAX_LENGTH まで
    - 空・`.` だけの名前（`.`・`..` など）は `fallback` にする
    - Windows の予約名（CON・NUL・COM1 など）は先頭に `_` を足す
    """
    if _UNSAFE_CHARS.search(fallback) or not fallback.strip("."):
        raise ValueError(f"fallback must be a safe path component: {fallback!r}")

    component = _UNSAFE_CHARS.sub("_", value.strip())[:SAFE_COMPONENT_MAX_LENGTH]
    if not component.strip("."):
        return fallback
    if component.split(".", 1)[0].upper() in _WINDOWS_RESERVED:
        component = f"_{component}"[:SAFE_COMPONENT_MAX_LENGTH]
    return component


def ensure_within(root: Path, path: Path) -> Path:
    """`path` を resolve() し、`root` の中にあることを確かめて返す。外なら止める."""
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved != resolved_root and not resolved.is_relative_to(resolved_root):
        raise FileWriteError(
            str(path),
            f"path is outside of the output root: {resolved_root}",
        )
    return resolved
