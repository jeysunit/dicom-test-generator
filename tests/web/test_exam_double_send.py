"""撮影の画面の二度押しの対策と、枚数の自動入力の部品（docs/spec/12a の 10.5）."""

from __future__ import annotations

import re
from pathlib import Path

from web_helpers import csrf_token, post_headers

STATIC = Path(__file__).resolve().parents[2] / "app" / "web" / "static"
_TOKEN_PATTERN = re.compile(r'name="exam_token" value="([^"]+)"')


def _form(token: str, **extra: str) -> dict[str, str]:
    return {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        "template": "ct_generic",
        "profile": "",
        "series": "1",
        "images": "1",
        "abnormal_level": "none",
        "charset": "auto",
        "action": "exam",
        "exam_token": token,
        **extra,
    }


def _page_token(client) -> str:
    match = _TOKEN_PATTERN.search(client.get("/exam").text)
    assert match, "the exam page must carry a token"
    return match.group(1)


def test_exam_page_has_busy_indicators_and_form_guards(client) -> None:
    html = client.get("/exam").text

    # find は最初の1つだけを押せなくするので、全部のボタンを選ぶ書き方にする
    assert 'hx-disabled-elt="#actions button"' in html
    assert 'hx-sync="this:drop"' in html
    assert "撮影して送信しています" in html
    # 既定はルーチンの行（ADR-0025）。「手で入れる」にすると今のシリーズ数・画像数の欄
    assert 'name="routine_images"' in html
    manual = client.get("/exam/routine?routine=manual").text
    assert "data-series-count" in manual
    assert "data-images-list" in manual


def test_each_exam_page_gets_its_own_token(client) -> None:
    assert _page_token(client) != _page_token(client)


def test_same_token_is_accepted_once(client, tmp_path) -> None:
    csrf = csrf_token(client, "/exam")
    token = _page_token(client)

    first = client.post("/exam", data=_form(token), headers=post_headers(csrf))
    second = client.post("/exam", data=_form(token), headers=post_headers(csrf))

    assert "撮影完了" in first.text
    assert "受け付け済み" in second.text
    assert "撮影完了" not in second.text
    assert len(list((tmp_path / "output").rglob("*.dcm"))) == 1


def test_result_hands_over_a_fresh_token(client, tmp_path) -> None:
    csrf = csrf_token(client, "/exam")
    token = _page_token(client)

    first = client.post("/exam", data=_form(token), headers=post_headers(csrf))
    next_token = _TOKEN_PATTERN.search(first.text).group(1)
    assert 'hx-swap-oob="true"' in first.text
    assert next_token != token

    second = client.post("/exam", data=_form(next_token), headers=post_headers(csrf))

    assert "撮影完了" in second.text
    assert len(list((tmp_path / "output").rglob("*.dcm"))) == 2


def test_failed_exam_gives_the_token_back(client) -> None:
    csrf = csrf_token(client, "/exam")
    token = _page_token(client)

    failed = client.post("/exam", data=_form(token, images="1,2"), headers=post_headers(csrf))
    retried = client.post("/exam", data=_form(token), headers=post_headers(csrf))

    assert 'role="alert"' in failed.text
    assert "受け付け済み" not in retried.text
    assert "撮影完了" in retried.text


def test_request_without_token_is_still_accepted(client) -> None:
    csrf = csrf_token(client, "/exam")

    response = client.post("/exam", data=_form(""), headers=post_headers(csrf))

    assert "撮影完了" in response.text
    assert "exam_token" not in response.text


def test_busy_styles_and_script_are_shipped() -> None:
    css = (STATIC / "app.css").read_text(encoding="utf-8")
    script = (STATIC / "app.js").read_text(encoding="utf-8")

    assert "htmx-request" in css
    assert "data-series-count" in script
    assert "data-edited" in script
