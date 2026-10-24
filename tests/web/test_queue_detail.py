"""送信ジョブの詳細を表の外の枠に出す（docs/spec/12a の 10.6）."""

from __future__ import annotations

import re

from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest


def _queue_with_jobs(client, count: int) -> str:
    service = client.app.state.service
    for index in range(count):
        exam = service.exam(
            ExamRequest(
                emergency_patient=ScheduledPatient(patient_id=f"E000{index}", patient_name="A^B"),
                pixel_mode="simple_text",
            )
        )
        service.send(exam.output_dir)
    return client.get("/pacs/queue").text


def test_each_row_opens_its_own_detail_popover(client) -> None:
    html = _queue_with_jobs(client, 2)

    assert "<details" not in html
    buttons = re.findall(r'popovertarget="(job-detail-\d+)"', html)
    popovers = re.findall(r'<div id="(job-detail-\d+)" popover', html)
    assert sorted(buttons) == sorted(popovers) == ["job-detail-1", "job-detail-2"]


def test_detail_popover_keeps_the_three_items(client) -> None:
    html = _queue_with_jobs(client, 1)

    detail = html.split('<div id="job-detail-1" popover', 1)[1].split("</div>", 1)[0]
    for label in ("元のファイル", "試行回数", "名乗る AEタイトル"):
        assert f"<dt>{label}</dt>" in detail


def test_detail_popover_is_a_named_popover(client) -> None:
    html = _queue_with_jobs(client, 1)

    # 表の形が変わらないことは画面（Playwright）で確かめる。ここでは枠が popover で、
    # 枠の見た目のクラスと読み上げの名前を持つことだけを見る
    tag = re.search(r'<div id="job-detail-1"[^>]*>', html).group(0)
    assert " popover" in tag
    assert 'class="job-detail"' in tag
    assert 'role="group"' in tag and 'aria-label="ジョブ 1 の詳細"' in tag
