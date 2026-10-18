"""見た目の値：入力の CSS の値が spec/12 の 10.2 の表と同じ（spec/12 の 14 章）."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "spec" / "12_modality_emulator.md"
INPUT_CSS = ROOT / "app" / "web" / "styles" / "input.css"
_TABLE_ROW = re.compile(
    r"^\| `(--color-[a-z-]+)` \| `(#[0-9a-f]{6})`[^|]*\| `(#[0-9a-f]{6})`", re.MULTILINE
)
_DECLARATION = re.compile(r"(--color-[a-z-]+):\s*(#[0-9a-f]{6});")


def _block(css: str, selector: str) -> str:
    start = css.index(selector)
    return css[css.index("{", start) + 1 : css.index("}", start)]


def _spec_tokens() -> dict[str, tuple[str, str]]:
    rows = _TABLE_ROW.findall(SPEC.read_text(encoding="utf-8"))
    return {name: (light, dark) for name, light, dark in rows}


def test_spec_table_has_all_color_tokens() -> None:
    tokens = _spec_tokens()
    assert set(tokens) == {
        "--color-background",
        "--color-surface",
        "--color-foreground",
        "--color-label",
        "--color-value",
        "--color-border",
        "--color-muted",
        "--color-primary",
        "--color-primary-foreground",
        "--color-danger",
    }


def test_input_css_matches_spec_light_and_dark() -> None:
    css = INPUT_CSS.read_text(encoding="utf-8")
    light = dict(_DECLARATION.findall(_block(css, "@theme")))
    dark = dict(_DECLARATION.findall(_block(css, ':root[data-theme="dark"]')))

    for name, (light_value, dark_value) in _spec_tokens().items():
        assert light[name] == light_value, name
        assert dark[name] == dark_value, name


def test_base_font_size_and_line_height() -> None:
    css = INPUT_CSS.read_text(encoding="utf-8")
    body = _block(css, "body")
    assert "font-size: 0.875rem" in body
    assert "line-height: 1.5" in body
