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
    listing = query_worklist(client)
    # 印は氏名のセルの下に出す（狭い幅でも見える。10.4）
    name_cell = listing.split('<td class="name-cell">', 1)[1].split("</td>", 1)[0]
    assert '<span class="badge">撮影済み</span>' in name_cell


def test_append_from_the_screen(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    client.post("/exam", data=_form(key), headers=post_headers(token))

    again = client.post("/exam", data=_form(key), headers=post_headers(token)).text
    assert "撮影済みです" in again  # 通常の撮影は断る
    assert "worklist_key" not in again and key not in again.split('id="result"', 1)[-1]

    page = client.get(f"/exam?key={key}").text
    title = "撮影済みの予約は押せません。続けて撮るときは「追加撮影」"
    assert f'disabled title="{title}" aria-describedby="taken-note"' in page
    assert 'id="taken-note"' in page
    assert "撮影済み" in client.get(f"/worklist/item/{key}").text  # 詳細にも出す

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


def test_append_on_emergency_is_refused(tmp_path, worklist_scp, storage_scp) -> None:
    """緊急の患者に追加撮影を付けても、黙って普通に撮らない（CLI と同じ文言）."""
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        "template": "ct_generic",
        "series": "1",
        "images": "1",
        "action": "exam",
        "append": "1",
    }

    html = client.post("/exam", data=form, headers=post_headers(token)).text

    assert "緊急の患者（予約なし）では追加撮影はできません" in html
    assert "撮影完了" not in html
