"""年齢を数える日の試験（docs/spec/12a の 10.3）：予約は予定日の時点、予定日が読めないときは今日."""

from __future__ import annotations

from datetime import date

from modality_peers import WorklistSCP, start_server
from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityWorklistInformationFind
from web_helpers import key_for, make_client, query_worklist

from app.core.models import WorklistItem
from app.core.wareki import age_on
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


def _scp_with_scheduled_days(worklist_items, days: dict[str, str]):
    """受付番号ごとに予定日を差し替えた MWL の SCP（日付は YYYYMMDD）."""
    items = [
        {**item, "sps": {**item["sps"], "start_date": days[item["accession_number"]]}}
        for item in worklist_items
        if item["accession_number"] in days
    ]
    scp = WorklistSCP(items=items)
    ae = AE(ae_title=scp.ae_title)
    ae.add_supported_context(ModalityWorklistInformationFind)
    server, scp.port = start_server(ae, [(evt.EVT_C_FIND, scp.handle_find)])
    return scp, server


def test_every_screen_counts_the_age_on_a_past_or_future_scheduled_day(
    tmp_path, worklist_items, storage_scp
) -> None:
    # A0001 は 1980/01/15 生まれ。予定日が過去（2020/03/15）なら 40 歳、未来（2099/06/01）なら 119 歳。
    # どちらも、開いた日の満年齢とは違う。
    past, future = "20200315", "20990601"
    born = date(1980, 1, 15)
    for scheduled, expected in ((past, 40), (future, 119)):
        scp, server = _scp_with_scheduled_days(worklist_items, {"A0001": scheduled})
        try:
            client = make_client(tmp_path, scp.port, storage_scp.port)
            listing = query_worklist(client, day="any")
            key = key_for(listing, "A0001")
            detail = client.get(f"/worklist/item/{key}").text
            exam = client.get(f"/exam?key={key}").text
        finally:
            server.shutdown()
        assert age_on(born, date.today()) != expected
        # 一覧の列・バナー・詳細・撮影（予約から）の患者の帯
        assert f"1980/01/15 (S55・{expected}歳)" in listing
        assert detail.count(f"（昭55・{expected}歳）") >= 2
        assert f"（昭55・{expected}歳）" in exam
        assert f"・{age_on(born, date.today())}歳" not in listing + detail + exam
