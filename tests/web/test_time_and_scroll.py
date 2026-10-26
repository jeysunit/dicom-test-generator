"""時刻の UTC の差の表記と、PACS の表の横スクロールの保持（docs/spec/12a の 10.4・10.6）."""

from __future__ import annotations

import re

from web_helpers import query_worklist

from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest
from app.web.display import utc_offset_label

OFFSET = re.compile(r"UTC[+-]\d{2}:\d{2}")


def test_utc_offset_label_has_the_sign_hours_and_minutes() -> None:
    assert OFFSET.fullmatch(utc_offset_label())


def test_worklist_fetch_time_carries_the_utc_offset(client) -> None:
    html = query_worklist(client)

    assert re.search(r"件（\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC[+-]\d{2}:\d{2} に取得）", html)


def test_queue_time_headers_carry_the_utc_offset(client) -> None:
    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E0001", patient_name="A^B"),
            pixel_mode="simple_text",
        )
    )
    service.send(exam.output_dir)

    html = client.get("/pacs/queue").text

    # 一覧の時刻の列は受付日時だけ（10.6）。検査日時・完了は選んだ行の詳細に、UTC からの差を添えて出す
    assert re.search(r'<th scope="col">受付日時<span class="block text-xs">UTC[+-]\d{2}:\d{2}</span></th>', html)
    detail = client.get("/pacs/queue?selected=1").text
    for label in ("検査日時", "受付", "完了"):
        assert re.search(rf'<dt>{label}<span class="text-xs">（UTC[+-]\d{{2}}:\d{{2}}）</span></dt>', detail)


def test_queue_scroll_position_is_kept_across_swaps(client) -> None:
    script = client.get("/static/app.js").text

    assert "wrap.scrollLeft = queueScroll" in script
    assert "queueScroll = wrap ? wrap.scrollLeft : 0" in script
