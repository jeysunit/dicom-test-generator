"""選んだ送信ジョブの詳細の知らせ：保管の確認の結果で言い方を替える（デザインシステム ui-kit 1.2.9。2026-11-16 承認者が決定）."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.web.templating import create_environment


def _render(status: str, commitment: str | None) -> str:
    job = SimpleNamespace(
        id=7,
        patient_name="YAMADA^TARO",
        patient_id="P000001",
        status=status,
        destination="TSUNAGI",
        num_sent=412,
        num_files=412,
        last_error="Association rejected",
        study_datetime=None,
        accession_number=None,
        created_at="2026-11-16T09:00:00+09:00",
        updated_at="2026-11-16T09:01:00+09:00",
        commitment=commitment,
        commitment_error=None,
        folder="/data/out",
        study_instance_uid="2.25.1",
        attempts=1,
        calling_ae_title="DTG",
    )
    return create_environment().get_template("_job_detail.html").render(job=job)


def _notice(html: str) -> str:
    start = html.index('<div role="')
    return html[start : html.index("</div>", start)]


@pytest.mark.parametrize(
    ("commitment", "kind", "text"),
    [
        ("confirmed", "ok", "TSUNAGI へ 412 枚を送信しました。保管の確認が取れました。"),
        ("waiting", "ok", "TSUNAGI へ 412 枚を送信しました。保管の確認を待っています。"),
        (
            "failed",
            "warn",
            "TSUNAGI へ 412 枚を送信しました。保管の確認が取れませんでした。"
            "TSUNAGI に届いているかを確認してください。",
        ),
        (
            "timed_out",
            "warn",
            "TSUNAGI へ 412 枚を送信しました。保管の確認が時間内に届きませんでした。"
            "TSUNAGI に届いているかを確認してください。",
        ),
        (None, "ok", "TSUNAGI へ 412 枚を送信しました。</span>"),
    ],
)
def test_sent_notice_follows_the_commitment_result(commitment, kind, text) -> None:
    notice = _notice(_render("sent", commitment))
    assert f'data-k="{kind}"' in notice
    assert text in notice
    assert "済んでいます" not in notice


def test_failed_job_keeps_the_error_notice() -> None:
    notice = _notice(_render("failed", "confirmed"))
    assert 'data-k="err"' in notice
    assert "保管の確認" not in notice
