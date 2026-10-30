"""送信ジョブの一覧：モダリティ・検査名の列、Study UID の行、50 件のページ送り、1,000 件の上限（docs/spec/12a の 10.6）."""

from __future__ import annotations

import re

import pytest

from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest


def _send_one(client, patient_id: str = "E0001") -> None:
    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id=patient_id, patient_name="A^B"),
            study_description="胸部 単純",
            pixel_mode="simple_text",
        )
    )
    service.send(exam.output_dir)


def _add_jobs(client, count: int) -> None:
    """画像の無い件を直接足す（ページ送りと上限の試験用。元のファイルが無くても一覧は出る）."""
    queue = client.app.state.service.queue
    for index in range(count):
        queue.add_job(f"/nonexistent/job-{index}", "PACS_TEST", [f"/nonexistent/job-{index}/a.dcm"])


def test_row_shows_modality_mark_and_study_description(client) -> None:
    _send_one(client)

    html = client.get("/pacs/queue").text

    body = html.split("<tbody>", 1)[1]
    assert re.search(r'<span class="mod" data-m="[a-z]+">[A-Z]{2}</span> 胸部 単純', body)
    assert "style=" not in body  # CSP が style 属性を許さない。モダリティの色は data-m で選ぶ


def test_detail_has_a_study_uid_row_with_a_copy_button(client) -> None:
    _send_one(client)

    detail = client.get("/pacs/queue?selected=1").text.split('<section id="job-detail"', 1)[1]

    match = re.search(
        r'<div class="uidrow">\s*<span class="l">Study UID</span><span class="uid">(2\.25\.[0-9.]+)</span>'
        r'\s*<button type="button" class="btn btn-ghost btn-sm" data-copy="\1">コピー</button>',
        detail,
    )
    assert match, detail


def test_a_job_without_its_files_still_lists_with_dashes(client) -> None:
    _add_jobs(client, 1)

    html = client.get("/pacs/queue").text

    row = html.split("<tbody>", 1)[1].split("</tr>", 1)[0]
    assert row.count("—") >= 4  # 患者ID・氏名・モダリティと検査名・保管の確認
    detail = client.get("/pacs/queue?selected=1").text.split('<section id="job-detail"', 1)[1]
    uid_row = detail.split('<div class="uidrow">', 1)[1].split("</div>", 1)[0]
    assert '<span class="uid">—</span>' in uid_row
    assert "data-copy" not in uid_row


def test_fifty_rows_a_page_with_a_pager(client) -> None:
    _add_jobs(client, 120)

    first = client.get("/pacs/queue").text

    assert first.count('data-focus-key="detail-') == 50
    assert "<b>120</b> 件" in first
    assert "1〜50 件目／全 120 件" in first
    assert "1 / 3" in first
    # 最初のページは「前のページ」を押せない。新しい順なので、最初の行は新しい件（120）
    assert re.search(r'<button type="button" class="btn btn-sm" disabled>前のページ</button>', first)
    assert 'data-focus-key="detail-120"' in first and 'data-focus-key="detail-71"' in first
    assert 'data-focus-key="detail-70"' not in first
    assert 'hx-vals=\'{"page": "2"}\'' in first
    assert '<input type="hidden" form="queue-filter" name="page" value="1">' in first

    last = client.get("/pacs/queue?page=3").text

    assert last.count('data-focus-key="detail-') == 20
    assert "101〜120 件目／全 120 件" in last
    assert re.search(r'<button type="button" class="btn btn-sm" disabled>次のページ</button>', last)
    assert '<input type="hidden" form="queue-filter" name="page" value="3">' in last


def test_a_page_past_the_end_falls_back_to_the_last_page(client) -> None:
    _add_jobs(client, 60)

    html = client.get("/pacs/queue?page=99").text

    assert "51〜60 件目／全 60 件" in html
    assert 'name="page" value="2"' in html


def test_a_list_that_fits_one_page_has_no_pager(client) -> None:
    _add_jobs(client, 5)

    html = client.get("/pacs/queue").text

    assert 'class="pager"' not in html
    assert "1,000 件を超えた" not in html


def test_the_filter_and_the_summary_buttons_go_back_to_the_first_page(client) -> None:
    page = client.get("/pacs").text

    form_tag = page.split('id="queue-filter"', 1)[1].split(">", 1)[0]
    assert 'hx-vals=\'{"page": "1"}\'' in form_tag
    summary = page.split('id="queue-sum"', 1)[1].split("</div>", 1)[0]
    assert summary.count('"page": "1"') == 4  # すべて・送信中・送信完了・送信失敗


@pytest.mark.parametrize(
    ("count", "listed", "pages", "notice"),
    [
        (0, 0, None, False),  # 0 件は 1 ページ（ページ送りなし）
        (50, 50, None, False),  # ちょうど 50 件は送りなし
        (51, 51, 2, False),  # 51 件で 2 ページ
        (1000, 1000, 20, False),  # ちょうど 1,000 件は上限の知らせなし
        (1001, 1000, 20, True),  # 1,001 件で上限の知らせあり（表示だけが 1,000 件）
    ],
)
def test_page_and_display_limit_boundaries(client, count, listed, pages, notice) -> None:
    _add_jobs(client, count)

    html = client.get("/pacs/queue").text

    assert f"<b>{listed}</b> 件" in html
    assert ("class=\"pager\"" in html) == (pages is not None)
    if pages is not None:
        assert f"1 / {pages}" in html
    assert ("送信ジョブが 1,000 件を超えたため" in html) == notice


def test_over_a_thousand_jobs_shows_only_the_newest_thousand_with_a_notice(client) -> None:
    _add_jobs(client, 1005)

    html = client.get("/pacs/queue").text

    assert "送信ジョブが 1,000 件を超えたため、新しい 1,000 件だけを出しています。期間を狭めてください。" in html
    assert "<b>1000</b> 件" in html
    assert "1〜50 件目／全 1000 件" in html
    assert "1 / 20" in html
    # 新しい 1,000 件：古い 5 件（1〜5）は出ない
    last = client.get("/pacs/queue?page=20").text
    assert "951〜1000 件目／全 1000 件" in last
    assert 'data-focus-key="detail-6"' in last and 'data-focus-key="detail-5"' not in last
