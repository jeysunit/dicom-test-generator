"""JST の 0〜9 時（UTC ではまだ前の日）にも、試験とアプリの「今日」がそろう.

CI は UTC で動くので、JST の朝に流すと OS の `date.today()` は前の日になる。予約の
試験の道具（MWL の SCP）とアプリの両方が、設定のタイムゾーン（既定は Asia/Tokyo）の
今日を使うことを、時刻を固定して確かめる。
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port, today

from app.core import patient_input
from app.modality.config import ModalityConfig
from app.modality.service import ModalityService

# UTC では 1 月 5 日の 15:40、JST では 1 月 6 日の 0:40（CI が JST の朝に流れたとき）
FROZEN_UTC = datetime(2026, 1, 5, 15, 40, tzinfo=timezone.utc)
JST_TODAY = date(2026, 1, 6)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[override]
        if tz is None:
            return FROZEN_UTC.replace(tzinfo=None)  # OS が UTC の CI と同じ
        return FROZEN_UTC.astimezone(tz)


@pytest.fixture
def jst_morning(monkeypatch) -> None:
    monkeypatch.setattr(patient_input, "datetime", _FrozenDatetime)


def _service(tmp_path: Path, worklist_port: int) -> ModalityService:
    return ModalityService(
        ModalityConfig.model_validate(
            {
                "ae_title": "DTG_CT01",
                "state_dir": str(tmp_path / "state"),
                "output_dir": str(tmp_path / "output"),
                "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
                "destinations": [
                    {
                        "name": "PACS_TEST",
                        "ae_title": "PACS_TEST",
                        "host": LOCALHOST,
                        "port": free_port(),
                    }
                ],
                "default_destination": "PACS_TEST",
                "default_pixel_mode": "simple_text",
            }
        )
    )


def test_test_today_is_the_app_today_in_the_jst_morning(jst_morning, tmp_path, worklist_scp):
    service = _service(tmp_path, worklist_scp.port)

    assert FROZEN_UTC.date() != JST_TODAY
    assert today() == JST_TODAY
    assert service.today() == JST_TODAY


def test_todays_orders_are_found_in_the_jst_morning(jst_morning, tmp_path, worklist_scp):
    """予約の道具が作る「今日」の予約を、アプリの「今日」の条件で引ける."""
    service = _service(tmp_path, worklist_scp.port)

    result = service.query_worklist(service.default_query(service.today()))

    accessions = {item.accession_number for item in result.items}
    assert {"A0001", "A0002"} <= accessions
    assert {item.scheduled_start_date for item in result.items} == {"20260106"}
