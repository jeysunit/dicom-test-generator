"""PACS の画面の形：区画＋下に一覧（画面の型 F。docs/spec/12a の 10.6）."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from web_helpers import csrf_token, post_headers

from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest


def _job(client, patient_id: str, failed: bool = False) -> int:
    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id=patient_id, patient_name="A^B"),
            pixel_mode="simple_text",
        )
    )
    if not failed:
        # 送信先（テストの SCP）へ実際に送り、送信完了の件を作る
        return service.send(exam.output_dir).job_id
    job_id = service.queue.add_job(exam.output_dir, "PACS_TEST", exam.files)
    service.queue.record_job_failure(job_id, "association lost")
    return job_id


def _counts(html: str) -> dict[str, str]:
    """状態の要約の（ボタンの名前 → 件数）."""
    return dict(re.findall(r'data-focus-key="sum-(\w+)"[^>]*>\s*<span[^>]*>[^<]*</span><span class="nbr">(\d+)</span>', html))


def test_page_puts_the_destination_section_above_the_job_list(client) -> None:
    html = client.get("/pacs").text

    destinations = html.index('<h2 class="sec-title">送信先</h2>')
    jobs = html.index("<h2>送信ジョブ</h2>")
    assert destinations < jobs
    # 下段は、状態の要約 → 検索の帯 → 件数の行 → 一覧の順
    order = [
        html.index('id="queue-sum"'),
        html.index('id="queue-filter"'),
        html.index('<div class="count-row">'),
        html.index("<table", html.index('<div class="count-row">')),
    ]
    assert order == sorted(order)
    # 送信先の表のポートは、ホストと別の列
    head = html.split("</thead>", 1)[0]
    assert ">ホスト<" in head and ">ポート<" in head


def test_search_band_has_the_three_conditions(client) -> None:
    html = client.get("/pacs").text
    band = html.split('id="queue-filter"', 1)[1].split("</form>", 1)[0]

    for name in ("period", "destination", "patient_id"):
        assert f'name="{name}"' in band
    assert "検索" in band and "条件をクリア" in band
    assert 'role="search"' in html


def test_summary_counts_states_and_failed_total_ignores_conditions(client) -> None:
    _job(client, "E0001", failed=True)
    _job(client, "E0002", failed=True)
    _job(client, "E0003")

    html = client.get("/pacs/queue").text
    assert _counts(html)["all"] == "3"
    assert _counts(html)["failed"] == "2"
    # 状態の要約と再送信の件数は、読み直しの応答に同梱して差し替える
    assert 'id="queue-sum"' in html and 'hx-swap-oob="true"' in html
    assert "失敗 2 件を再送信" in html

    narrowed = client.get("/pacs/queue?patient_id=E0001").text
    assert _counts(narrowed)["all"] == "1"
    assert "失敗 2 件を再送信" in narrowed  # まとめての再送信は、絞らず失敗のすべてに効く


def test_status_filter_selects_and_toggles(client) -> None:
    _job(client, "E0001", failed=True)
    _job(client, "E0002", failed=True)
    _job(client, "E0003")

    failed = client.get("/pacs/queue?status=failed").text

    assert '<b class="count-n">2</b>' in failed
    assert 'aria-pressed="true" data-focus-key="sum-failed"' in failed
    # 押している状態をもう一度押すと、絞りを外す
    assert re.search(r'data-focus-key="sum-failed"[^>]*hx-vals=\'\{"status": "all"\}\'', failed)
    assert '<input type="hidden" form="queue-filter" name="status" value="failed">' in failed


def test_destination_and_patient_id_conditions(client) -> None:
    _job(client, "E0001", failed=True)
    _job(client, "E0002", failed=True)

    assert '<b class="count-n">1</b>' in client.get("/pacs/queue?patient_id=e0002").text
    assert '<b class="count-n">2</b>' in client.get("/pacs/queue?destination=PACS_TEST").text
    other = client.get("/pacs/queue?destination=OTHER").text
    assert '<b class="count-n">0</b>' in other
    assert "条件に合う送信ジョブはありません" in other
    assert "送信ジョブはまだありません" not in other


def test_period_condition_uses_the_created_date(client) -> None:
    job_id = _job(client, "E0001", failed=True)
    old = (datetime.now() - timedelta(days=10)).isoformat(timespec="seconds")
    with client.app.state.service.queue._connect() as conn:
        conn.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (old, job_id))
    _job(client, "E0002", failed=True)

    assert '<b class="count-n">2</b>' in client.get("/pacs/queue?period=all").text
    assert '<b class="count-n">1</b>' in client.get("/pacs/queue?period=today").text
    assert '<b class="count-n">1</b>' in client.get("/pacs/queue?period=week").text


def test_unknown_condition_values_fall_back(client) -> None:
    _job(client, "E0001", failed=True)

    html = client.get("/pacs/queue?period=bogus&status=bogus&selected=abc").text

    assert '<b class="count-n">1</b>' in html
    assert 'name="status" value="all"' in html and 'name="selected" value=""' in html


def test_empty_list_keeps_the_first_run_message(client) -> None:
    html = client.get("/pacs/queue").text

    assert "送信ジョブはまだありません" in html
    assert "<table" in html


def test_retry_all_is_confirmed_by_a_dialog(client) -> None:
    _job(client, "E0001", failed=True)

    page = client.get("/pacs").text

    assert '<dialog id="dlg-resend"' in page
    assert 'data-dialog-open="dlg-resend"' in page
    # 押すまで送らない：見出しの右のボタンは窓を開くだけで、送信の要求は窓の中の 1 つだけ
    opener = re.search(r'<button[^>]*data-dialog-open="dlg-resend"[^>]*>', page).group(0)
    assert "hx-post" not in opener
    assert page.count('hx-post="/pacs/retry-failed"') == 1
    dialog = page.split('<dialog id="dlg-resend"', 1)[1].split("</dialog>", 1)[0]
    assert 'hx-post="/pacs/retry-failed"' in dialog and "キャンセル" in dialog


def test_interactions_replace_the_polling_request(client) -> None:
    """条件・状態・行の選択の要求は、先に出ていた再取得を取り消し、古い応答で上書きされない."""
    _job(client, "E0001", failed=True)
    page = client.get("/pacs").text
    queue = client.get("/pacs/queue?selected=1").text

    form = re.search(r'<form id="queue-filter"[^>]*>', page).group(0)
    buttons = re.findall(r"<button[^>]*data-queue-action[^>]*>", queue)
    assert 'hx-sync="#queue:replace"' in form and "data-queue-action" in form
    # 状態の要約 4 つ、行の [詳細]、詳細の [閉じる]
    assert len(buttons) == 6
    assert all('hx-sync="#queue:replace"' in button for button in buttons)
    assert "hx-sync" not in re.search(r'<div id="queue"[^>]*>', page).group(0)


def test_retry_button_is_disabled_without_failed_jobs(client) -> None:
    page = client.get("/pacs").text
    slot = page.split('id="retry-slot"', 1)[1].split("</span>\n", 1)[0]

    assert "disabled" in slot and "失敗をすべて再送信" in slot


def test_retry_keeps_the_conditions_and_selected_row(client) -> None:
    job_id = _job(client, "E0001", failed=True)
    token = csrf_token(client, "/pacs")

    response = client.post(
        f"/pacs/retry/{job_id}",
        data={"period": "all", "destination": "PACS_TEST", "patient_id": "E0001",
              "status": "failed", "selected": str(job_id)},
        headers=post_headers(token),
    )

    assert response.status_code == 200
    # 再送信の応答も、条件（状態の絞り）を保ち、状態の要約を同じ応答で差し替える
    assert 'name="status" value="failed"' in response.text
    assert 'id="queue-sum"' in response.text and "再送信しました" in response.text
