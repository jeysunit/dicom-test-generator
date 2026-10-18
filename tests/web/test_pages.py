"""頁と HTMX の部分の応答（spec/12 の 10.3〜10.8）."""

from __future__ import annotations

import pytest
from web_helpers import OWN_AE, csrf_token, post_headers
from web_helpers import key_for as _key_for
from web_helpers import query_worklist as _query


def test_root_redirects_to_worklist(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/worklist")


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("/worklist", "引く"),
        ("/exam", "緊急の患者"),
        ("/pacs", "C-ECHO"),
        ("/settings", OWN_AE),
    ],
)
def test_pages_open_with_header_and_band(client, path, text) -> None:
    response = client.get(path)
    assert response.status_code == 200
    html = response.text
    assert text in html
    assert "dicom-test-generator" in html
    for name in ("ワークリスト", "撮影", "PACS", "設定"):
        assert name in html
    assert f"自分: {OWN_AE}" in html
    assert 'id="theme-toggle"' in html
    assert "Not for Diagnostic Use" not in html
    assert "非医療機器" not in html
    assert '<html lang="ja"' in html


def test_worklist_query_partial_lists_items_and_marks(client) -> None:
    html = _query(client, station="any", modality="")

    assert "<html" not in html  # HTMX の部分の応答
    assert "P000001" in html and "A0001" in html
    assert "山田 太郎" in html
    assert "1980/01/15" in html
    assert "別の装置" in html  # A0003 は DTG_MR01 の予定
    assert "選んで撮影へ" in html
    assert 'id="band"' in html and 'hx-swap-oob="true"' in html
    assert "ISO_IR 192 → ISO_IR 192" in html


def test_worklist_zero_items_offers_emergency(client) -> None:
    html = _query(client, patient_id="NOBODY")
    assert "予約はありません。条件を広げるか、緊急の患者で撮ってください" in html
    assert 'href="/exam"' in html


def test_worklist_non_ascii_zero_items_hint(client) -> None:
    html = _query(client, patient_name="存在しない")
    assert "日本語の条件は相手の文字コードの扱いに左右されます" in html


def test_worklist_bad_date_is_shown_as_error(client) -> None:
    html = _query(client, day="date", date="")
    assert "日付" in html
    assert 'role="alert"' in html


def test_worklist_detail_and_refresh(client, worklist_scp) -> None:
    html = _query(client)
    key = _key_for(html, "A0001")

    detail = client.get(f"/worklist/item/{key}")
    assert detail.status_code == 200
    assert "2.25.100000000000000000000000000000000001" in detail.text
    assert "SPS0001" in detail.text

    worklist_scp.items[0]["requested_procedure_description"] = "胸部 CT（直した）"
    token = csrf_token(client)
    refreshed = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token))
    assert refreshed.status_code == 200
    assert "胸部 CT（直した）" in refreshed.text
    assert "引き直しました" in refreshed.text


def test_exam_page_is_read_only_and_lists_profiles(client) -> None:
    key = _key_for(_query(client), "A0001")

    html = client.get(f"/exam?key={key}").text

    assert "P000001" in html
    assert 'name="patient_id"' not in html  # 予約の値は入力の欄にしない
    assert "dtg_synthetic_ct" in html
    assert "ct_generic" in html
    assert "撮影して送る" in html
    # 確かめ直しの GET は、CSRF の token を URL に載せない（要る欄だけを送る）
    assert 'hx-include="#exam-form"' not in html
    assert "disabled" not in html.split('id="actions"', 1)[1].split("</div>", 1)[0]


def test_exam_page_blocks_modality_mismatch(client) -> None:
    key = _key_for(_query(client, station="any", modality=""), "A0003")

    html = client.get(f"/exam?key={key}").text

    assert "予約は MR、テンプレートは CT です" in html
    assert "この予約は別の装置の予定です" in html
    actions = html.split('id="actions"', 1)[1]
    assert "disabled" in actions.split("</div>", 1)[0]


def test_exam_check_partial_follows_profile_choice(client) -> None:
    key = _key_for(_query(client), "A0001")
    ok = client.get("/exam/check", params={"key": key, "template": "ct_generic"})
    assert ok.status_code == 200
    assert "disabled" not in ok.text

    missing = client.get(
        "/exam/check", params={"key": key, "template": "ct_generic", "profile": "no_such"}
    )
    assert "disabled" in missing.text
    assert "no_such" in missing.text


def test_unknown_worklist_key_on_exam_page(client) -> None:
    html = client.get("/exam?key=0000000000").text
    assert 'role="alert"' in html
    assert "0000000000" in html


def test_emergency_form_validation_error_is_shown(client) -> None:
    token = csrf_token(client, "/exam")
    response = client.post(
        "/exam",
        data={"mode": "emergency", "patient_id": "", "name_alphabetic": "", "action": "exam"},
        headers=post_headers(token),
    )
    assert response.status_code == 200
    assert 'role="alert"' in response.text


@pytest.mark.parametrize(("series", "images"), [("100", "1"), ("1", "1001"), ("2", "1,0")])
def test_exam_size_is_bounded_on_the_server(client, tmp_path, series, images) -> None:
    """シリーズ数・枚数の上限は画面の欄だけでなくサーバーで確かめる（10.5）."""
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E1",
        "name_alphabetic": "A^B",
        "series": series,
        "images": images,
        "action": "exam",
    }
    html = client.post("/exam", data=form, headers=post_headers(token)).text
    assert 'role="alert"' in html
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_template_name_from_the_form_is_not_a_path(client) -> None:
    html = client.get("/exam/check", params={"template": "../../config/app_config"}).text
    assert "disabled" in html
    assert "app_config.yaml" not in html


def test_failed_refresh_keeps_the_list(client) -> None:
    html = _query(client)
    token = csrf_token(client)
    failed = client.post("/worklist/refresh", data={"key": ""}, headers=post_headers(token)).text
    assert 'role="alert"' in failed
    assert "A0001" in failed and "選んで撮影へ" in failed
    assert "A0001" in html


def test_htmx_swaps_error_responses() -> None:
    """403 などの失敗の応答も画面に出す（htmx 2 の既定は 4xx・5xx を出さない）."""
    from app.web.templating import TEMPLATES_DIR

    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert '"responseHandling"' in base and '"[45]..", "swap": true' in base


def test_pacs_queue_partial_polls(client) -> None:
    page = client.get("/pacs").text
    assert 'hx-get="/pacs/queue"' in page
    assert "every 2s" in page

    partial = client.get("/pacs/queue")
    assert partial.status_code == 200
    assert "<html" not in partial.text
    assert "まだ送った検査はありません" in partial.text


def test_pacs_echo(client) -> None:
    token = csrf_token(client, "/pacs")
    ok = client.post("/pacs/echo/PACS_TEST", headers=post_headers(token))
    assert "つながった" in ok.text

    unknown = client.post("/pacs/echo/NOPE", headers=post_headers(token))
    assert 'role="alert"' in unknown.text


def test_settings_page_is_read_only(client) -> None:
    html = client.get("/settings").text
    assert "RIS_TEST" in html and "PACS_TEST" in html
    assert "<form" not in html
    assert "app_config.yaml" in html
