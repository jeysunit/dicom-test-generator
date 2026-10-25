"""見た目の値：入力の CSS の値が docs/spec/12a の 10.2 の表と同じ（docs/development.md の 4 章）."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "spec" / "12a_web_screens_and_cli.md"
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
        "--color-border-input",
        "--color-muted",
        "--color-muted-strong",
        "--color-selected",
        "--color-chrome",
        "--color-primary",
        "--color-primary-foreground",
        "--color-link",
        "--color-danger",
        "--color-success",
        "--color-warning",
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


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


# 文字の色と、その文字が乗る地（WCAG 2.2 の AA：4.5:1 以上）
_TEXT_PAIRS = [
    ("--color-foreground", "--color-background"),
    ("--color-foreground", "--color-surface"),
    ("--color-foreground", "--color-muted"),
    ("--color-foreground", "--color-muted-strong"),
    ("--color-label", "--color-background"),
    ("--color-label", "--color-surface"),
    ("--color-label", "--color-muted"),
    ("--color-label", "--color-muted-strong"),
    ("--color-value", "--color-background"),
    ("--color-value", "--color-surface"),
    ("--color-value", "--color-muted"),
    # 現在のナビの項目（値の色・太字）と、選んだ行
    ("--color-value", "--color-selected"),
    ("--color-foreground", "--color-selected"),
    ("--color-link", "--color-background"),
    ("--color-link", "--color-surface"),
    ("--color-link", "--color-muted"),
    ("--color-danger", "--color-background"),
    ("--color-danger", "--color-surface"),
    ("--color-primary-foreground", "--color-primary"),
]


def _themes() -> dict[str, dict[str, str]]:
    css = INPUT_CSS.read_text(encoding="utf-8")
    light = dict(_DECLARATION.findall(_block(css, "@theme")))
    dark = {**light, **dict(_DECLARATION.findall(_block(css, ':root[data-theme="dark"]')))}
    return {"light": light, "dark": dark}


def test_text_contrast_is_at_least_aa() -> None:
    for theme, tokens in _themes().items():
        for foreground, background in _TEXT_PAIRS:
            ratio = _contrast(tokens[foreground], tokens[background])
            assert ratio >= 4.5, (theme, foreground, background, round(ratio, 2))


def test_input_border_contrast_is_at_least_3_to_1() -> None:
    for theme, tokens in _themes().items():
        for background in ("--color-background", "--color-surface"):
            ratio = _contrast(tokens["--color-border-input"], tokens[background])
            assert ratio >= 3, (theme, background, round(ratio, 2))


def test_greys_are_neutral() -> None:
    names = (
        "--color-background",
        "--color-surface",
        "--color-foreground",
        "--color-label",
        "--color-value",
        "--color-border",
        "--color-border-input",
        "--color-muted",
        "--color-muted-strong",
        "--color-chrome",
    )
    for theme, tokens in _themes().items():
        for name in names:
            value = tokens[name]
            assert value[1:3] == value[3:5] == value[5:7], (theme, name, value)
