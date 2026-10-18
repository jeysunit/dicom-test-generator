"""Jinja2 の環境（spec/12_modality_emulator.md 10.8）.

- 自動エスケープを必ず有効にする（相手から来る値を HTML として出さない）
- `{{ }}` で出す文字列は、エスケープの前に制御文字・双方向の制御文字を見える形にする
  （端末の 11.7 と同じ置き換え）。テンプレートが作った HTML（マクロの出力）には触れない
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.core.text_safety import make_visible

from . import display

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _finalize(value: Any) -> Any:
    if isinstance(value, str) and not hasattr(value, "__html__"):
        return make_visible(value)
    return value


def create_environment() -> Environment:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=True,
        finalize=_finalize,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["name_parts"] = display.name_parts
    env.filters["birth_label"] = display.birth_label
    env.filters["time_label"] = display.time_label
    env.filters["date_label"] = display.date_label
    env.filters["charset_label"] = display.charset_label
    env.globals["STATUS_LABELS"] = display.STATUS_LABELS
    return env
