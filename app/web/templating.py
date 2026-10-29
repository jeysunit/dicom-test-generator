"""Jinja2 の環境（docs/spec/12a_web_screens_and_cli.md 10.8）.

- 自動エスケープを必ず有効にする（相手から来る値を HTML として出さない）
- `{{ }}` で出す文字列は、エスケープの前に制御文字・双方向の制御文字を見える形にする
  （端末の 11.7 と同じ置き換え）。テンプレートが作った HTML（マクロの出力）には触れない
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, pass_context
from jinja2.runtime import Context

from app.core.patient_input import DEFAULT_TIMEZONE, current_date
from app.core.text_safety import make_visible

from . import display
from .link_status import CHECK_UNREADABLE

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


def _finalize(value: Any) -> Any:
    if isinstance(value, str) and not hasattr(value, "__html__"):
        return make_visible(value)
    return value


@pass_context
def _birth_label(context: Context, item: Any) -> str:
    """年齢は検査日と同じ時計（設定のタイムゾーン）の今日で数える."""
    config = context.get("config")
    timezone = getattr(config, "timezone", DEFAULT_TIMEZONE)
    return display.birth_label(item, current_date(timezone))


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
    env.filters["name_display"] = display.name_display
    env.filters["birth_label"] = _birth_label
    env.filters["time_label"] = display.time_label
    env.filters["date_label"] = display.date_label
    env.filters["charset_label"] = display.charset_label
    env.filters["send_error_label"] = display.send_error_label
    env.globals["patient_label"] = display.patient_label
    env.globals["utc_offset"] = display.utc_offset_label
    env.globals["STATUS_LABELS"] = display.STATUS_LABELS
    env.globals["CHECK_UNREADABLE"] = CHECK_UNREADABLE
    env.globals["COMMITMENT_LABELS"] = display.COMMITMENT_LABELS
    env.globals["STATUS_KINDS"] = display.STATUS_KINDS
    env.globals["COMMITMENT_KINDS"] = display.COMMITMENT_KINDS
    return env
