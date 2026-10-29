"""年齢を数える日の試験（docs/spec/12a の 10.3）：予約は予定日の時点、予定日が読めないときは今日."""

from __future__ import annotations

from datetime import date

from app.core.models import WorklistItem
from app.web.display import age_day, birth_cell_label, birth_label, birth_parts

OPENED = date(2027, 1, 1)  # 画面を開いた日。予定日（2026/10/21）より後


def _item(scheduled: str, birth: str = "19751022") -> WorklistItem:
    return WorklistItem(key="k", birth_date=birth, sex="M", scheduled_start_date=scheduled)


def test_age_day_is_the_scheduled_day_and_falls_back_to_today() -> None:
    assert age_day(_item("20261021"), OPENED) == date(2026, 10, 21)
    assert age_day(_item(""), OPENED) == OPENED
    assert age_day(_item("20261399"), OPENED) == OPENED


def test_every_form_counts_the_age_on_the_scheduled_day() -> None:
    # 1975/10/22 生まれ。予定日 2026/10/21 は誕生日の前日で 50 歳、開いた日 2027/01/01 では 51 歳
    item = _item("20261021")
    assert birth_label(item, OPENED) == "1975/10/22（昭50・50歳）男"
    assert birth_parts(item, OPENED) == ("1975/10/22", "（昭50・50歳）男")
    assert birth_cell_label(item, OPENED) == "1975/10/22 (S50・50歳)"


def test_a_row_without_a_readable_scheduled_day_counts_on_today() -> None:
    item = _item("")
    assert birth_label(item, OPENED) == "1975/10/22（昭50・51歳）男"
    assert birth_cell_label(item, OPENED) == "1975/10/22 (S50・51歳)"


def test_the_age_follows_the_row_not_the_screen() -> None:
    # 同じ患者でも、予定日の違う 2 件は行ごとに自分の予定日で数える
    before, after = _item("20261021"), _item("20261022")
    assert birth_cell_label(before, OPENED) == "1975/10/22 (S50・50歳)"
    assert birth_cell_label(after, OPENED) == "1975/10/22 (S50・51歳)"
