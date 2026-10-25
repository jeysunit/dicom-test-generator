"""選んだ送信ジョブの詳細を、表の下に出す（docs/spec/12a の 10.6）."""

from __future__ import annotations

import re

from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest


def _queue_with_jobs(client, count: int) -> None:
    service = client.app.state.service
    for index in range(count):
        exam = service.exam(
            ExamRequest(
                emergency_patient=ScheduledPatient(patient_id=f"E000{index}", patient_name="A^B"),
                pixel_mode="simple_text",
            )
        )
        service.send(exam.output_dir)


def test_each_row_has_a_button_that_selects_it(client) -> None:
    _queue_with_jobs(client, 2)

    html = client.get("/pacs/queue").text

    assert "popover" not in html and "<details" not in html
    assert sorted(re.findall(r'data-focus-key="(detail-\d+)"', html)) == ["detail-1", "detail-2"]
    # 選ぶまでは、詳細の区画を出さない
    assert 'id="job-detail"' not in html
    assert html.count('aria-selected="false"') == 2


def test_selected_row_shows_its_detail_below_the_table(client) -> None:
    _queue_with_jobs(client, 2)

    html = client.get("/pacs/queue?selected=2").text

    assert html.index("</table>") < html.index('<section id="job-detail"')
    assert 'aria-label="ジョブ 2 の詳細"' in html
    assert html.count('aria-selected="true"') == 1
    assert re.search(r'<tr aria-selected="true">\s*<td>2</td>', html)
    detail = html.split('<section id="job-detail"', 1)[1]
    for label in ("元のファイル", "試行回数", "名乗る AEタイトル"):
        assert f"<dt>{label}</dt>" in detail
    # 選んだ行は、読み直しでも保つ（隠した欄で送り返す）
    assert '<input type="hidden" form="queue-filter" name="selected" value="2">' in html


def test_detail_can_be_closed(client) -> None:
    _queue_with_jobs(client, 1)

    html = client.get("/pacs/queue?selected=").text

    assert 'id="job-detail"' not in html
    assert 'name="selected" value=""' in html


def test_selected_job_outside_the_conditions_is_not_shown(client) -> None:
    _queue_with_jobs(client, 2)

    html = client.get("/pacs/queue?selected=1&patient_id=E0001").text

    assert 'id="job-detail"' not in html
    assert 'name="selected" value=""' in html
