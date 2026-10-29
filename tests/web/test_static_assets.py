"""画面の静的な物：版を固定した htmx・Lucide のアイコン・作った CSS が揃っている（docs/spec/12a の 10.1）."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "app" / "web" / "static"
FETCH_SCRIPT = ROOT / "scripts" / "fetch_web_assets.sh"
INPUT_CSS = ROOT / "app" / "web" / "styles" / "input.css"


def _script_value(name: str) -> str:
    match = re.search(rf'^{name}="([^"]+)"', FETCH_SCRIPT.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, name
    return match.group(1)


def test_htmx_is_the_pinned_file() -> None:
    data = (STATIC / "htmx.min.js").read_bytes()
    assert hashlib.sha256(data).hexdigest() == _script_value("HTMX_SHA256")


def test_every_icon_used_by_the_css_is_present_with_license() -> None:
    used = set(re.findall(r"/static/icons/([a-z-]+)\.svg", INPUT_CSS.read_text(encoding="utf-8")))
    icons_line = re.search(
        r"^ICONS=\(([^)]*)\)", FETCH_SCRIPT.read_text(encoding="utf-8"), re.MULTILINE
    )
    assert icons_line
    assert used == set(icons_line.group(1).split())
    for name in used:
        assert (
            (STATIC / "icons" / f"{name}.svg")
            .read_text(encoding="utf-8")
            .lstrip()
            .startswith("<svg")
        ), name
    assert "ISC" in (STATIC / "icons" / "LICENSE").read_text(encoding="utf-8")


def test_built_css_is_committed_and_uses_the_kit_tokens() -> None:
    # 値と部品は ui-kit の写し、作った CSS は Tailwind の色の名前を ui-kit の変数で使う
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert ".text-label{color:var(--color-label)!important}" in css.replace(" ", "")
    kit = STATIC / "ui-kit"
    assert (kit / "VERSION").read_text(encoding="utf-8").strip() == "1.2.0"
    assert "--color-primary: #4B4FBF;" in (kit / "tokens.css").read_text(encoding="utf-8")
    assert ".btn-primary{" in (kit / "components.css").read_text(encoding="utf-8")


def test_kit_copy_matches_its_fingerprints() -> None:
    """ui-kit の写しは直さない：5 つのファイルが SHA256SUMS の指紋と合う（ADR-0028）."""
    kit = STATIC / "ui-kit"
    sums = {}
    for line in (kit / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        sums[name.strip()] = digest
    assert set(sums) == {"tokens.css", "components.css", "icons.svg", "VERSION"}
    for name, digest in sums.items():
        assert hashlib.sha256((kit / name).read_bytes()).hexdigest() == digest, name


def test_pages_read_the_kit_before_the_product_css() -> None:
    base = (ROOT / "app" / "web" / "templates" / "base.html").read_text(encoding="utf-8")
    order = [
        base.index('href="/static/ui-kit/tokens.css"'),
        base.index('href="/static/ui-kit/components.css"'),
        base.index('href="/static/app.css"'),
    ]
    assert order == sorted(order)


def test_request_failures_share_the_result_place() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    place = js.split("function failurePlace(event)", 1)[1].split("function showFailure", 1)[0]
    for name in ("query-form", "results", "detail", "exam-form", "result", "send-result", "queue-notice", "echo-"):
        assert name in place
    assert "requestConfig" in place and "detail.target" in place
    assert "var place = failurePlace(event)" in js
    assert '"htmx:sendError"' in js
    assert "xhr.status === 401" in js and "shouldSwap = false" in js
    assert "ログインが切れました。ページを読み込み直して、ログインし直してください" in js
    assert "routineFailure(xhr.status === 401 ? LOGIN_EXPIRED_MESSAGE" in js
    assert "xhr.status === 401 ? LOGIN_EXPIRED_MESSAGE" in js


def test_queue_error_summary_has_a_width_limit() -> None:
    css = INPUT_CSS.read_text(encoding="utf-8")
    rule = css.split(".job-error-summary {", 1)[1].split("}", 1)[0]
    for declaration in ("max-width:", "overflow: hidden", "white-space: nowrap", "text-overflow: ellipsis"):
        assert declaration in rule
