"""撮影・送信の結果の言い方と色分け（docs/spec/12a の 10.2・10.5。現場の PACS の用語にそろえる）."""

from __future__ import annotations

import re

import pytest
from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers

# 画面に出さない言い方（PACS の現場で使わない言葉。結果の表示に出ないことを確認する）
AVOIDED = ("送れた", "待ち行列", "住所", "この道具", "ダミー", "模擬")


def _emergency_form(**extra: str) -> dict[str, str]:
    return {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        "name_ideographic": "緊急 太郎",
        "sex": "M",
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

    # 誰を撮ったか（氏名と患者ID）を知らせに入れる（10.5）
    assert "撮影完了：緊急 太郎（E0001）の 2 画像" in html
    assert re.search(r'class="notice[^"]*" data-k="ok"', html)
    assert "出力先フォルダ" in html
    # 予約なしと空の値は注意として、結果の見出しとは別の枠で出す
    assert re.search(r'class="notice[^"]*" data-k="warn"', html)
    assert "注意：予約なし（受付番号は空）" in html
    assert "撮影しました" not in html


def test_send_completion_names_state_destination_count_and_job(client) -> None:
    token = csrf_token(client, "/exam")

    html = client.post(
        "/exam", data=_emergency_form(action="exam_send"), headers=post_headers(token)
    ).text

    assert (
        "送信完了：緊急 太郎（E0001）の 2/2 画像を PACS_TEST へ送信しました（ジョブ 1）" in html
    )
    # 送信先の AEタイトルとホストも添える
    assert "送信先：PACS_TEST（" in html
    assert 'data-k="err"' not in html


def test_send_failure_is_a_red_notice(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/exam")

    html = client.post(
        "/exam", data=_emergency_form(action="exam_send"), headers=post_headers(token)
    ).text

    assert "撮影完了：緊急 太郎（E0001）の 2 画像" in html
    # つながらなかった送信も、送信ジョブの枚数（2 画像のうち 0）で知らせる
    assert (
        "送信失敗：緊急 太郎（E0001）の画像を PACS_TEST へ送信できませんでした"
        "（2 画像のうち 0 画像を送信。ジョブ 1）" in html
    )
    assert 'class="notice" role="alert" data-k="err"' in html


def test_pacs_job_table_shows_patient_not_folder(client) -> None:
    token = csrf_token(client, "/exam")
    form = _emergency_form(action="exam_send", name_ideographic="緊急 太郎")
    client.post("/exam", data=form, headers=post_headers(token))
    queue = client.get("/pacs/queue").text

    head = queue.split("</thead>", 1)[0]
    # 列は 7 つに絞る（1024 の幅で氏名が縦に並ばず、操作が見える。10.6）
    columns = re.findall(r'<th scope="col">([^<]+)', head)
    assert columns == ["受付日時", "患者ID", "氏名", "送信先", "画像数", "状態", "操作"]
    # 検査日時・完了・受付番号・ジョブの番号・保管の確認は、選んだ行の詳細に出す
    picked = client.get("/pacs/queue?selected=1").text.split('<section id="job-detail"', 1)[1]
    for label in ("検査日時", "完了", "受付番号", "ジョブ", "保管の確認"):
        assert f"<dt>{label}" in picked
    assert "出力先フォルダ" not in queue
    body = queue.split("<tbody>", 1)[1]
    assert "E0001" in body
    assert "緊急^太郎" not in body
    assert "緊急 太郎" in body
    # フォルダは、行の「詳細」で選んだ行の詳細の「元のファイル」に残す
    assert 'data-focus-key="detail-1"' in body and "元のファイル" not in body
    detail = client.get("/pacs/queue?selected=1").text.split('<section id="job-detail"', 1)[1]
    assert "元のファイル" in detail and "emergency_" in detail


@pytest.mark.parametrize("path",["/worklist", "/exam", "/pacs", "/settings"])
def test_pages_do_not_use_avoided_words(client, path) -> None:
    html = client.get(path).text

    for word in AVOIDED:
        assert word not in html, (path, word)
