"""見た目の値：ui-kit の tokens.css の値が docs/spec/12a の 10.2 の表と同じ（docs/development.md の 4 章）."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = ROOT / "docs" / "spec" / "12a_web_screens_and_cli.md"
INPUT_CSS = ROOT / "app" / "web" / "styles" / "input.css"
UI_KIT = ROOT / "app" / "web" / "static" / "ui-kit"
TOKENS_CSS = UI_KIT / "tokens.css"
COMPONENTS_CSS = UI_KIT / "components.css"
_TABLE_ROW = re.compile(
    r"^\| `(--color-[a-z-]+)` \| `(#[0-9a-f]{6})`[^|]*\| `(#[0-9a-f]{6})`", re.MULTILINE
)
_DECLARATION = re.compile(r"(--color-[a-z-]+):\s*(#[0-9a-fA-F]{6});")
_LINKED = re.compile(r"(--color-[a-z-]+):\s*var\((--color-[a-z-]+)\);")


def _block(css: str, selector: str) -> str:
    start = css.index(selector)
    return css[css.index("{", start) + 1 : css.index("}", start)]


def _declarations(block: str) -> dict[str, str]:
    return {name: value.lower() for name, value in _DECLARATION.findall(block)}


def _spec_tokens() -> dict[str, tuple[str, str]]:
    rows = _TABLE_ROW.findall(SPEC.read_text(encoding="utf-8"))
    return {name: (light, dark) for name, light, dark in rows}


def _kit_light() -> dict[str, str]:
    return _declarations(_block(TOKENS_CSS.read_text(encoding="utf-8"), ":root {"))


def _kit_dark() -> dict[str, str]:
    return _declarations(_block(TOKENS_CSS.read_text(encoding="utf-8"), ":root[data-theme=dark]"))


def test_spec_table_has_all_color_tokens_of_the_kit() -> None:
    assert set(_spec_tokens()) == set(_kit_light())


def test_kit_tokens_match_spec_light_and_dark() -> None:
    light = _kit_light()
    dark = _kit_dark()
    for name, (light_value, dark_value) in _spec_tokens().items():
        assert light[name] == light_value, name
        assert dark.get(name, light[name]) == dark_value, name


def test_kit_dark_follows_the_device_when_no_theme_is_chosen() -> None:
    # 端末の設定で暗い地のときの値は、data-theme="dark" のときの値と同じ
    css = TOKENS_CSS.read_text(encoding="utf-8")
    assert _declarations(_block(css, ":root:not([data-theme=light])")) == _kit_dark()


def test_input_css_links_every_kit_color_to_tailwind() -> None:
    # テンプレートの Tailwind の色の名前（bg-surface など）は、tokens.css の変数へつなぐだけ。値は書かない
    css = INPUT_CSS.read_text(encoding="utf-8")
    linked = dict(_LINKED.findall(_block(css, "@theme inline")))
    assert linked == {name: name for name in _kit_light()}
    assert not _DECLARATION.findall(css)


def test_base_font_size_and_line_height() -> None:
    body = _block(COMPONENTS_CSS.read_text(encoding="utf-8"), "body{")
    assert "font-size:14px" in body
    assert "line-height:1.5" in body


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
    ("--color-value", "--color-selected-strong"),
    ("--color-foreground", "--color-selected-strong"),
    ("--color-link", "--color-background"),
    ("--color-link", "--color-surface"),
    ("--color-link", "--color-muted"),
    ("--color-danger", "--color-background"),
    ("--color-danger", "--color-surface"),
    ("--color-primary-foreground", "--color-primary"),
]


def _themes() -> dict[str, dict[str, str]]:
    light = _kit_light()
    dark = {**light, **_kit_dark()}
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
        "--color-hover",
        "--color-pressed",
    )
    for theme, tokens in _themes().items():
        for name in names:
            value = tokens[name]
            assert value[1:3] == value[3:5] == value[5:7], (theme, name, value)
