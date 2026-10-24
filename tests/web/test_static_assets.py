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


def test_built_css_is_committed_and_has_the_tokens() -> None:
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    assert "--color-primary:#4b4fbf" in css.replace(" ", "")
    assert ".btn-primary" in css


def test_request_failures_share_the_result_place() -> None:
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    place = js.split("function failurePlace(event)", 1)[1].split("function showFailure", 1)[0]
    for name in ("query-form", "results", "exam-form", "result", "send-result", "queue-notice", "echo-"):
        assert name in place
    assert "requestConfig" in place and "detail.target" in place
    assert "var place = failurePlace(event)" in js
    assert '"htmx:sendError"' in js
    assert "xhr.status === 401" in js and "shouldSwap = false" in js
    assert "ログインが切れました。頁を読み込み直して、ログインし直してください" in js
    assert "routineFailure(xhr.status === 401 ? LOGIN_EXPIRED_MESSAGE" in js
    assert "xhr.status === 401 ? LOGIN_EXPIRED_MESSAGE" in js


def test_queue_error_summary_has_a_width_limit() -> None:
    css = INPUT_CSS.read_text(encoding="utf-8")
    rule = css.split(".job-error-summary {", 1)[1].split("}", 1)[0]
    for declaration in ("max-width:", "overflow: hidden", "white-space: nowrap", "text-overflow: ellipsis"):
        assert declaration in rule
