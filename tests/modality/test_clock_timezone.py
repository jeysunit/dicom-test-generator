"""時計の決め方：検査日と同じ時計（設定のタイムゾーン）にそろえる所の試験（docs/spec/12a の 10.5）.

OS の時計の地域に関わらず、UTC の 2030-01-01 20:00 を 1 つの時刻に固定する。
日本（Asia/Tokyo）では 2030-01-02 05:00、UTC の設定では 2030-01-01 20:00 になる。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.cli.modality_commands import _build_query
from app.core.models import WorklistItem
from app.web.routes.worklist import _date_range
from app.web.templating import create_environment

from .test_exam_workflow import _exam, _key, _service

INSTANT = datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc)


@pytest.fixture
def frozen_clock(monkeypatch) -> None:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return INSTANT.astimezone(tz)

    monkeypatch.setattr("app.core.patient_input.datetime", FrozenDatetime)


def test_mpps_end_uses_the_configured_timezone_like_the_start(
    tmp_path, worklist_scp, mpps_scp, frozen_clock
) -> None:
    """終了だけ OS の時計だと、UTC のコンテナと Asia/Tokyo で終了が開始より前になる."""
    service = _service(tmp_path, worklist_scp.port, mpps_port=mpps_scp.port)
    result = _exam(service, _key(service))

    created = mpps_scp.created[result.mpps.sop_instance_uid]
    modification = mpps_scp.sets[-1][1]
    assert created.PerformedProcedureStepStartDate == "20300102"
    assert modification.PerformedProcedureStepEndDate == "20300102"
    start = (created.PerformedProcedureStepStartDate, created.PerformedProcedureStepStartTime)
    end = (modification.PerformedProcedureStepEndDate, modification.PerformedProcedureStepEndTime)
    assert end >= start


@pytest.mark.parametrize(
    ("zone", "today", "tomorrow"),
    [("Asia/Tokyo", "20300102", "20300103"), ("UTC", "20300101", "20300102")],
)
def test_worklist_today_and_tomorrow_follow_the_timezone_setting(
    frozen_clock, zone, today, tomorrow
) -> None:
    assert _date_range("today", "", zone) == f"{today}-{today}"
    assert _date_range("tomorrow", "", zone) == f"{tomorrow}-{tomorrow}"


@pytest.mark.parametrize(("zone", "today"), [("Asia/Tokyo", "20300102"), ("UTC", "20300101")])
def test_cli_worklist_default_date_follows_the_timezone_setting(frozen_clock, zone, today) -> None:
    service = SimpleNamespace(
        config=SimpleNamespace(timezone=zone, default_template="ct_generic"),
        template_modality=lambda _name: "CT",
        current_station=lambda: SimpleNamespace(ae_title="DTG_CT01"),
    )
    args = SimpleNamespace(
        date="today",
        modality=None,
        station_aet=None,
        patient_id=None,
        patient_name=None,
        accession=None,
    )

    assert _build_query(service, args).date_range == f"{today}-{today}"


@pytest.mark.parametrize(("zone", "age"), [("Asia/Tokyo", "30歳"), ("UTC", "29歳")])
def test_age_is_counted_on_the_configured_timezone_today(frozen_clock, zone, age) -> None:
    item = WorklistItem(key="k", birth_date="20000102", sex="M")
    template = create_environment().from_string("{{ item|birth_label }}")

    assert age in template.render(item=item, config=SimpleNamespace(timezone=zone))
