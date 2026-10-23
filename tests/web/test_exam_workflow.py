"""撮影の画面の撮影済み・追加撮影・撮り直しの予約（docs/spec/12a の 10.4・10.5・ADR-0024）."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient
from web_helpers import BASE_URL, csrf_token, key_for, modality_config, post_headers, query_worklist

from app.modality.config import ModalityConfig
from app.web.app import create_app
from app.web.settings import WebConfig


def _client(tmp_path, worklist_port: int, storage_port: int, retake_mode: str = "append"):
    data = modality_config(tmp_path, worklist_port, storage_port).model_dump()
    data["retake_mode"] = retake_mode
    app = create_app(
        ModalityConfig.model_validate(data),
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(),
        password=None,
    )
    return TestClient(app, base_url=BASE_URL)


def _form(key: str, action: str = "exam", **extra: str) -> dict[str, str]:
    return {
        "mode": "scheduled",
        "key": key,
        "template": "ct_generic",
        "series": "1",
        "images": "1",
        "action": action,
        **extra,
    }


def _actions(html: str) -> str:
    return html.split('id="actions"', 1)[1].split("</div>", 1)[0]


def _enabled_buttons(actions: str) -> list[str]:
    pattern = r"<button([^>]*)>\s*(?:<span[^>]*></span>)?\s*([^<]+?)\s*</button>"
    return [label for attrs, label in re.findall(pattern, actions) if " disabled" not in attrs]


def test_exam_then_buttons_change_to_append(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    assert _enabled_buttons(_actions(client.get(f"/exam?key={key}").text)) == [
        "撮影",
        "撮影して送る",
    ]

    result = client.post("/exam", data=_form(key, "exam_send"), headers=post_headers(token)).text

    # 撮影の結果と一緒に、撮影のボタンを描き直す（撮影済み）
    assert '<div id="actions" hx-swap-oob="true">' in result
    assert _enabled_buttons(_actions(result)) == ["追加撮影"]
    assert _enabled_buttons(_actions(client.get(f"/exam?key={key}").text)) == ["追加撮影"]
    assert "撮影済み" in query_worklist(client)


def test_append_from_the_screen(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    client.post("/exam", data=_form(key), headers=post_headers(token))

    again = client.post("/exam", data=_form(key), headers=post_headers(token)).text
    assert "撮影済みです" in again  # 通常の撮影は断る

    appended = client.post("/exam", data=_form(key, append="1"), headers=post_headers(token)).text
    assert "撮影完了：1 画像" in appended


def test_new_order_mode_shows_the_retake_notice(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port, retake_mode="new_order")
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    client.post("/exam", data=_form(key), headers=post_headers(token))

    actions = _actions(client.get(f"/exam?key={key}").text)

    assert _enabled_buttons(actions) == []
    assert "撮り直しの予約が要ります（RIS で新しい予約を作ってください）" in actions
    assert "追加撮影" not in actions
    refused = client.post("/exam", data=_form(key, append="1"), headers=post_headers(token)).text
    assert "撮り直しの予約が要ります" in refused


def test_template_check_keeps_the_taken_state(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    client.post("/exam", data=_form(key), headers=post_headers(token))

    checked = client.get("/exam/check", params={"key": key, "template": "ct_generic"}).text

    assert _enabled_buttons(checked) == ["追加撮影"]
