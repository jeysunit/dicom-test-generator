"""通信と送信の失敗を画面で知らせる（spec/12a 10.6・10.8）."""

from html import escape

import pytest
from web_helpers import csrf_token, make_client, post_headers

from app.core.exceptions import FileReadError
from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest, SendResult
from app.web.display import send_error_label


@pytest.fixture
def client(tmp_path):
    # この試験は表示だけを確認する。DICOM の通信は行わない。
    return make_client(tmp_path, 18201, 18200)


@pytest.mark.parametrize(("reason", "expected"), [
    ("Association failed: could not connect (refused, aborted or timed out) "
     "(peer=PACS_TEST, host=127.0.0.1, port=18200)",
     "接続できませんでした（PACS_TEST・127.0.0.1:18200）。送信先の電源とポートを確かめてください"),
    ("Association failed: association rejected by the peer (peer=PACS_TEST, host=x, port=1)",
     "送信先に断られました（PACS_TEST）。AEタイトルの登録を確かめてください"),
    ("association lost", "送信の途中で接続が切れました。送信先の接続を確かめてください"),
    ("no response (timed out or aborted)",
     "送信先から応答がありませんでした。送信先の稼働状況を確かめてください"),
    ("status 0xA700", "送信先が画像を受け付けませんでした（状態 0xA700）。送信先の記録を確かめてください"),
    ("unreadable file: <broken>", "送信する画像のファイルを読めませんでした。元のファイルを確かめてください"),
    ("unreadable file: /output/山田/1.dcm",
     "送信する画像のファイルを読めませんでした。元のファイルを確かめてください"),
    ("Association failed: could not connect (refused, aborted or timed out) "
     "(peer=中央_PACS, host=pacs.example.org, port=104)",
     "接続できませんでした（中央_PACS・pacs.example.org:104）。送信先の電源とポートを確かめてください"),
    ("相手が AEタイトル DTG_CT01 を受け付けませんでした。登録してください",
     "相手が AEタイトル DTG_CT01 を受け付けませんでした。登録してください"),
    ("unexpected <error> " * 100, "送信に失敗しました"),
])
def test_send_error_label_and_detail(client, reason, expected) -> None:
    assert send_error_label(reason) == expected
    service = client.app.state.service
    exam = service.exam(ExamRequest(
        emergency_patient=ScheduledPatient(patient_id="E0001", patient_name="A^B"),
        pixel_mode="simple_text",
    ))
    job_id = service.queue.add_job(exam.output_dir, "PACS_TEST", exam.files)
    service.queue.record_job_failure(job_id, reason)
    html = client.get("/pacs/queue").text
    outside, detail = html.split(f'<div id="job-detail-{job_id}" popover', 1)
    assert f'class="job-error-summary text-xs text-danger">{escape(expected)}<' in outside
    assert "<dt>失敗の理由</dt>" in detail
    assert escape(expected) in detail
    assert f'class="font-mono">{escape(reason)}<' in detail
    if reason != expected:
        assert escape(reason) not in outside


def test_queue_read_error_does_not_claim_empty(client, monkeypatch) -> None:
    def fail():
        raise FileReadError("queue", "unreadable")
    monkeypatch.setattr(client.app.state.service, "list_queue", fail)
    html = client.get("/pacs/queue").text
    assert 'role="alert"' in html
    assert "送信した検査はまだありません" not in html
    assert "<table" not in html


@pytest.mark.parametrize("path,job_id", [("/pacs/retry/1", 1), ("/pacs/retry-failed", 1),
                                         ("/pacs/retry/1", 2)])
def test_retry_remaining_failure_is_an_alert(client, monkeypatch, path, job_id) -> None:
    monkeypatch.setattr(client.app.state.service, "retry", lambda **kwargs: [
        SendResult(job_id=job_id, status="failed", destination="PACS_TEST")
    ])
    token = csrf_token(client, "/pacs")
    html = client.post(path, headers=post_headers(token)).text
    notice = html.split('<div id="queue-notice" hx-swap-oob="true">', 1)[1].split("</div>")[0]
    assert 'role="alert"' in notice and "notice-error" in notice
    if job_id == 1:
        assert "1 件を再送信しましたが、まだ送信できていません（送信完了 0 件・送信失敗 1 件）" in notice
    else:
        assert "ジョブ 2 として再送信しました（送信失敗）" in notice
