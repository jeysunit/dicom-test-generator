"""ワークリストの選んだ予約の患者バナーは、部品集の患者バナー（.fb.r1）の項目と順で出す（docs/spec/12a の 10.4）."""

from __future__ import annotations

import re

import pytest
from web_helpers import key_for, query_worklist

from app.web.display import datetime_label, modality_key, sex_label

SLOTS = ["nm", "f pid", "f birth", "f acc", "f dt", "f md"]


def _slots(banner: str) -> list[str]:
    """`.fb` の直下の項目のクラスを、出てくる順に返す（項目の中の入れ子は数えない）."""
    return re.findall(r'<div class="(nm|f (?:pid|birth|acc|dt|md|end))">', banner)


@pytest.mark.parametrize(
    ("value", "label"),
    [("M", "男"), ("F", "女"), ("O", "その他"), ("", "不明"), ("U", "不明")],
)
def test_sex_label_uses_the_four_words(value: str, label: str) -> None:
    assert sex_label(value) == label


@pytest.mark.parametrize(
    ("modality", "key"),
    [("CT", "ct"), ("mr", "mr"), ("CR", "crdx"), ("DX", "crdx"), ("US", "us"), ("PT", "doc"), ("", "doc")],
)
def test_modality_key_picks_the_token_name(modality: str, key: str) -> None:
    assert modality_key(modality) == key


def test_datetime_label_is_year_slash_month_slash_day_and_hour_minute() -> None:
    assert datetime_label("2026-10-25T10:00:03") == "2026/10/25 10:00"
    assert datetime_label("") == ""
    assert datetime_label("読めない値") == "読めない値"


def test_datetime_label_keeps_a_date_only_value_without_a_made_up_time() -> None:
    assert datetime_label("2026-10-25") == "2026/10/25"


def test_worklist_banner_has_the_fixed_slots_and_the_modality_mark(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    html = client.get(f"/worklist/item/{key}").text

    banner = html.split('<section id="detail"', 1)[0]
    assert _slots(banner) == SLOTS
    assert re.search(r'<span class="mod" data-m="ct">CT</span> 胸部 CT', banner)
    assert '<div class="l">予定日時</div>' in banner
    assert re.search(r'<div class="v">\d{4}/\d{2}/\d{2} 09:00</div>', banner)
    assert "style=" not in banner  # CSP が style 属性を許さない。モダリティの色は data-m で選ぶ


def test_banner_keeps_every_slot_when_a_value_is_missing(client) -> None:
    key = key_for(query_worklist(client), "A0002")

    banner = client.get(f"/worklist/item/{key}").text.split('<section id="detail"', 1)[0]

    assert _slots(banner) == SLOTS
    assert '<div class="l">受付番号</div><div class="v mono keep">A0002</div>' in banner
    # 生年月日が空の予約は「生年月日なし」に、性別は不明を添える
    assert "生年月日なし（不明）" in banner


def test_app_css_selects_the_modality_color_without_a_style_attribute(client) -> None:
    css = client.get("/static/app.css").text

    for name in ("ct", "mr", "crdx", "us", "es", "mg", "sr"):
        assert f".mod[data-m={name}]{{--m:var(--color-mod-{name})}}" in css
