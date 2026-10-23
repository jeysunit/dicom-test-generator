"""画面から「取得→選ぶ→撮る→送る→確かめる」の一巡り（docs/development.md の 4 章）.

手元の MWL の SCP と Storage の SCP（tests/modality_peers.py）を相手にする。
"""

from __future__ import annotations

import re

from modality_peers import free_port
from web_helpers import csrf_token, key_for, make_client, post_headers, query_worklist

_OUTPUT_DIR_PATTERN = re.compile(r'name="output_dir" value="([^"]+)"')


def _exam_form(key: str, action: str, **extra: str) -> dict[str, str]:
    return {
        "mode": "scheduled",
        "key": key,
        "template": "ct_generic",
        "profile": "",
        "series": "2",
        "images": "1,2",
        "abnormal_level": "none",
        "charset": "auto",
        "action": action,
        **extra,
    }


def test_pick_exam_send_and_confirm(client, worklist_scp, storage_scp) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")

    response = client.post("/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token))

    assert response.status_code == 200, response.text
    assert "撮影完了：3 画像" in response.text
    assert "送信完了：PACS_TEST へ 3/3 画像（ジョブ 1）" in response.text
    assert "notice-ok" in response.text
    assert len(storage_scp.received) == 3
    first = storage_scp.received[0]
    assert first.PatientID == "P000001"
    assert first.AccessionNumber == "A0001"
    assert first.StudyInstanceUID == "2.25.100000000000000000000000000000000001"

    queue = client.get("/pacs/queue").text
    assert "送信完了" in queue
    assert "3/3" in queue


def test_queue_table_shows_the_accession_number(client, worklist_scp, storage_scp) -> None:
    """送信キューの表の受付番号の欄に、画像の Accession Number を出す（docs/spec/12a の 10.6）."""
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    client.post("/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token))

    queue = client.get("/pacs/queue").text

    assert '<td class="font-mono">A0001</td>' in queue


def test_exam_with_profile_then_send_from_result(client, storage_scp) -> None:
    """予約なしの緊急の患者を、装置を選んで撮り、結果の [送る] で送る.

    氏名は空白で区切って入れる（スクリプトが切れていてもサーバーで ^ にする。10.5）。
    """
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": " KINKYU  TARO ",
        "name_ideographic": "緊急　太郎",
        "name_phonetic": "",
        "birth_date": "1980-01-01",
        "sex": "M",
        "study_description": "緊急 CT",
        "template": "ct_generic",
        "profile": "dtg_synthetic_ct",
        "series": "1",
        "images": "1",
        "abnormal_level": "none",
        "charset": "auto",
        "action": "exam",
    }

    response = client.post("/exam", data=form, headers=post_headers(token))

    assert "予約なし（受付番号は空）" in response.text
    assert storage_scp.received == []
    output_dir = _OUTPUT_DIR_PATTERN.search(response.text).group(1)

    sent = client.post("/exam/send", data={"output_dir": output_dir}, headers=post_headers(token))
    assert "送信完了" in sent.text
    received = storage_scp.received[0]
    assert received.Manufacturer == "DTG Synthetic"
    assert str(received.PatientName) == "KINKYU^TARO=緊急^太郎"
    assert received.PatientBirthDate == "19800101"


def test_send_from_result_refuses_outside_output_root(client, tmp_path) -> None:
    token = csrf_token(client, "/exam")
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "a.dcm").write_bytes(b"")

    html = client.post(
        "/exam/send", data={"output_dir": str(outside)}, headers=post_headers(token)
    ).text

    assert 'role="alert"' in html
    assert client.get("/pacs/queue").text.count("<tr") <= 1


def test_failed_send_is_retried_from_pacs(tmp_path, worklist_scp, storage_scp) -> None:
    """送れなかった件を PACS の画面の [再送] で送り直す（10.6）."""
    unreachable = make_client(tmp_path, worklist_scp.port, free_port())
    key = key_for(query_worklist(unreachable), "A0001")
    token = csrf_token(unreachable, f"/exam?key={key}")
    failed = unreachable.post(
        "/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token)
    )
    assert "失敗" in failed.text
    assert "再送" in unreachable.get("/pacs/queue").text

    reachable = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(reachable, "/pacs")
    retried = reachable.post("/pacs/retry-failed", headers=post_headers(token))

    assert retried.status_code == 200
    assert "送信完了" in retried.text
    assert len(storage_scp.received) == 3
