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
    """予約なしの緊急の患者を、装置を選んで撮り、結果の [送信] で送る.

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
    """送れなかった件を PACS の画面の [もう一度送る] で送り直す（10.6）."""
    unreachable = make_client(tmp_path, worklist_scp.port, free_port())
    key = key_for(query_worklist(unreachable), "A0001")
    token = csrf_token(unreachable, f"/exam?key={key}")
    failed = unreachable.post(
        "/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token)
    )
    assert "失敗" in failed.text
    assert "もう一度送る" in unreachable.get("/pacs/queue").text

    reachable = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(reachable, "/pacs")
    retried = reachable.post("/pacs/retry-failed", headers=post_headers(token))

    assert retried.status_code == 200
    assert "送信完了" in retried.text
    assert len(storage_scp.received) == 3


def _resend_buttons(html: str) -> list[str]:
    return re.findall(r'hx-post="/pacs/retry/(\d+)"', html)


def test_sent_job_is_resent_from_pacs_as_a_new_job(client, worklist_scp, storage_scp) -> None:
    """送信完了の件にも [もう一度送る] を出し、押すと新しい件として送る（10.6）."""
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    client.post("/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token))
    assert _resend_buttons(client.get("/pacs/queue").text) == ["1"]

    token = csrf_token(client, "/pacs")
    resent = client.post("/pacs/retry/1", headers=post_headers(token)).text

    # どの件になったかを、表の外（2 秒ごとの再取得で消えない場所）に出す
    notice = resent.split('<div id="queue-notice" hx-swap-oob="true">', 1)[1].split("</div>", 1)[0]
    assert "ジョブ 2 として再送信しました（送信完了）" in notice
    assert sorted(_resend_buttons(resent)) == ["1", "2"]
    assert "queue-notice" not in client.get("/pacs/queue").text  # 再取得では知らせを消さない
    assert len(storage_scp.received) == 6
    uids = [ds.SOPInstanceUID for ds in storage_scp.received]
    assert sorted(uids[:3]) == sorted(uids[3:])  # 同じ画像を送り直す


def test_sending_job_has_no_resend_button(client) -> None:
    from app.core.models import ScheduledPatient
    from app.modality.service import ExamRequest

    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E0001", patient_name="A^B"),
            pixel_mode="simple_text",
        )
    )
    job_id = service.queue.add_job(exam.output_dir, "PACS_TEST", exam.files)
    service.queue.mark_sending(job_id)

    assert _resend_buttons(client.get("/pacs/queue").text) == []

    # 送信中の件の再送信の要求は断り、表を残して理由を表の上に出す
    token = csrf_token(client, "/pacs")
    refused = client.post(f"/pacs/retry/{job_id}", headers=post_headers(token)).text
    notice = refused.split('<div id="queue-notice" hx-swap-oob="true">', 1)[1]
    assert 'role="alert"' in notice.split("</div>", 1)[0]
    assert "<table" in refused


def test_exam_result_offers_send_again(client, worklist_scp, storage_scp) -> None:
    """撮影の画面で、送信の結果の後も [もう一度送る] で何回でも送り直せる（10.5）."""
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    result = client.post(
        "/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token)
    ).text
    assert "もう一度送る" in result
    output_dir = _OUTPUT_DIR_PATTERN.search(result).group(1)

    for job in (2, 3):
        again = client.post(
            "/exam/send", data={"output_dir": output_dir}, headers=post_headers(token)
        ).text
        assert f"送信完了：PACS_TEST へ 3/3 画像（ジョブ {job}）" in again
        assert "もう一度送る" in again and 'hx-disabled-elt="find button"' in again
    assert len(storage_scp.received) == 9
