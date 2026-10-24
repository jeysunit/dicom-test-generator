"""再送の応答を待つ間は、どの [再送] も [失敗をすべて再送] も押せない（docs/spec/12a の 10.6）."""

from __future__ import annotations

import re

from web_helpers import csrf_token, post_headers

from app.core.exceptions import DICOMGeneratorError
from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest

LOCK = 'hx-disabled-elt="#queue [data-resend], #retry-failed"'


def _failed_jobs(client, count: int) -> None:
    service = client.app.state.service
    for index in range(count):
        exam = service.exam(
            ExamRequest(
                emergency_patient=ScheduledPatient(patient_id=f"E000{index}", patient_name="A^B"),
                pixel_mode="simple_text",
            )
        )
        job_id = service.queue.add_job(exam.output_dir, "PACS_TEST", exam.files)
        service.queue.record_job_failure(job_id, "association lost")


def test_every_resend_button_locks_all_resend_buttons(client) -> None:
    _failed_jobs(client, 2)

    page = client.get("/pacs").text
    queue = client.get("/pacs/queue").text

    row_buttons = re.findall(r"<button[^>]*data-resend[^>]*>", queue)
    assert len(row_buttons) == 2
    assert all(LOCK in button for button in row_buttons)
    retry_all = re.search(r'<button[^>]*id="retry-failed"[^>]*>', page).group(0)
    assert LOCK in retry_all and 'hx-post="/pacs/retry-failed"' in retry_all


def test_refused_retry_all_keeps_the_table_and_shows_the_reason_above_it(client, monkeypatch) -> None:
    _failed_jobs(client, 1)

    def refuse(**kwargs):
        raise DICOMGeneratorError("送信中の件があるため、再送できません")

    monkeypatch.setattr(client.app.state.service, "retry", refuse)
    token = csrf_token(client, "/pacs")

    refused = client.post("/pacs/retry-failed", headers=post_headers(token)).text

    notice = refused.split('<div id="queue-notice" hx-swap-oob="true">', 1)[1].split("</div>", 1)[0]
    assert 'role="alert"' in notice and "送信中の件があるため、再送できません" in notice
    assert "<table" in refused
