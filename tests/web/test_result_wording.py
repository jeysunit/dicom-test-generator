"""撮影・送信の結果の言い方と色分け（spec/12a の 10.2・10.5。現場の PACS の用語にそろえる）."""

from __future__ import annotations

import pytest
from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers

# 画面に出さない言い方（承認者が避けると指摘した。2026-10-21）
AVOIDED = ("送れた", "待ち行列", "住所", "この道具", "ダミー", "模擬")


def _emergency_form(**extra: str) -> dict[str, str]:
    return {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        "template": "ct_generic",
        "profile": "",
        "series": "1",
        "images": "2",
        "abnormal_level": "none",
        "charset": "auto",
        "action": "exam",
        **extra,
    }


def test_exam_result_is_a_green_completion_with_separate_warnings(client) -> None:
    token = csrf_token(client, "/exam")

    html = client.post("/exam", data=_emergency_form(), headers=post_headers(token)).text

    assert "撮影完了：2 画像" in html
    assert 'class="notice notice-ok' in html
    assert "出力先フォルダ" in html
    # 予約なしと空の値は注意として、結果の見出しとは別の枠で出す
    assert 'class="notice notice-warn' in html
    assert "注意：予約なし（受付番号は空）" in html
    assert "撮影しました" not in html


def test_send_completion_names_state_destination_count_and_job(client) -> None:
    token = csrf_token(client, "/exam")

    html = client.post(
        "/exam", data=_emergency_form(action="exam_send"), headers=post_headers(token)
    ).text

    assert "送信完了：PACS_TEST へ 2/2 画像（ジョブ 1）" in html
    assert "notice-error" not in html


def test_send_failure_is_a_red_notice(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/exam")

    html = client.post(
        "/exam", data=_emergency_form(action="exam_send"), headers=post_headers(token)
    ).text

    assert "撮影完了：2 画像" in html
    assert "送信失敗：PACS_TEST へ 0/0 画像（ジョブ 1）" in html
    assert 'class="notice notice-error"' in html


@pytest.mark.parametrize("path", ["/worklist", "/exam", "/pacs", "/settings"])
def test_pages_do_not_use_avoided_words(client, path) -> None:
    html = client.get(path).text

    for word in AVOIDED:
        assert word not in html, (path, word)
