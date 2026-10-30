"""生年月日の和暦と年齢（変換 12 行と年齢の境目 7 行）と、入力の読み取り（受ける形と誤りの組）."""

from __future__ import annotations

from datetime import date

import pytest
from birth_input_cases import ACCEPTED, FORMAT, FUTURE, MORE_REFUSED, OPENED, REFUSED

from app.core.patient_input import BIRTH_DATE_FORMAT_MESSAGE, BIRTH_DATE_FUTURE_MESSAGE, FieldValidationError
from app.core.wareki import age_on, birth_cell, birth_text, era_label, parse_birth_input, parse_date

TODAY = date(2026, 10, 29)

# （生年月日, 漢字 1 字の形, 英字 1 字の形）。空は元号なし
CONVERSIONS = [
    ("18681022", "", ""),
    ("18681023", "明1", "M1"),
    ("19120729", "明45", "M45"),
    ("19120730", "大1", "T1"),
    ("19261224", "大15", "T15"),
    ("19261225", "昭1", "S1"),
    ("19750514", "昭50", "S50"),
    ("19890107", "昭64", "S64"),
    ("19890108", "平1", "H1"),
    ("20190430", "平31", "H31"),
    ("20190501", "令1", "R1"),
    ("20261029", "令8", "R8"),
]

AGES = [
    ("19750514", "20260513", 50),
    ("19750514", "20260514", 51),
    ("20261029", "20261029", 0),
    ("20000229", "20260228", 25),
    ("20000229", "20260301", 26),
    ("20000229", "20280228", 27),
    ("20000229", "20280229", 28),
]


def _date(value: str) -> date:
    parsed = parse_date(value)
    assert parsed is not None
    return parsed


@pytest.mark.parametrize(("value", "kanji", "letter"), CONVERSIONS)
def test_era_conversion(value: str, kanji: str, letter: str) -> None:
    born = _date(value)
    assert era_label(born) == kanji
    assert era_label(born, letter=True) == letter


@pytest.mark.parametrize(("value", "kanji", "letter"), CONVERSIONS)
def test_banner_and_list_forms(value: str, kanji: str, letter: str) -> None:
    day = f"{value[:4]}/{value[4:6]}/{value[6:]}"
    age = age_on(_date(value), TODAY)
    assert birth_text(value, TODAY) == (day, f"（{kanji + '・' if kanji else ''}{age}歳）")
    assert birth_cell(value, TODAY) == f"{day} ({letter + '・' if letter else ''}{age}歳)"


def test_before_meiji_shows_age_only() -> None:
    assert birth_text("18681022", TODAY) == ("1868/10/22", "（158歳）")
    assert birth_cell("18681022", TODAY) == "1868/10/22 (158歳)"


@pytest.mark.parametrize(("value", "today", "age"), AGES)
def test_age_boundaries(value: str, today: str, age: int) -> None:
    assert age_on(_date(value), _date(today)) == age


def test_birthday_today_is_age_zero_in_the_form() -> None:
    assert birth_text("20261029", TODAY) == ("2026/10/29", "（令8・0歳）")


def test_unreadable_value_is_kept_as_is() -> None:
    assert parse_date("19701399") is None
    assert birth_text("19701399", TODAY) == ("1970/13/99", "")
    assert birth_cell("", TODAY) == ""


def _hint(born: date, on: date) -> str:
    """欄の下の読み取り結果（.hint）：西暦と括弧。性別は付けない."""
    return "".join(birth_text(born.strftime("%Y%m%d"), on))


@pytest.mark.parametrize(("value", "western", "hint"), ACCEPTED)
def test_birth_input_accepted_forms(value: str, western: str, hint: str) -> None:
    born = parse_birth_input(value, OPENED)
    assert born.strftime("%Y%m%d") == western
    assert _hint(born, OPENED) == hint


@pytest.mark.parametrize(("value", "message"), REFUSED + MORE_REFUSED)
def test_birth_input_refused_forms(value: str, message: str) -> None:
    with pytest.raises(FieldValidationError) as caught:
        parse_birth_input(value, OPENED)
    assert caught.value.message == message
    assert caught.value.field == "birth_date"


def test_birth_input_messages_are_the_shared_constants() -> None:
    assert FORMAT == BIRTH_DATE_FORMAT_MESSAGE
    assert FUTURE == BIRTH_DATE_FUTURE_MESSAGE


def test_birth_input_checks_the_future_only_with_today() -> None:
    assert parse_birth_input("R8/10/30") == date(2026, 10, 30)
    with pytest.raises(FieldValidationError, match="読み取れません"):
        parse_birth_input("")


def test_birth_input_checks_form_then_era_then_today() -> None:
    """確かめる順は形・元号の範囲・今日より後。範囲の外で今日より後の値は、範囲の誤り."""
    with pytest.raises(FieldValidationError) as caught:
        parse_birth_input("H40/01/01", OPENED)
    assert "平成の範囲にありません" in caught.value.message


def test_birth_input_before_meiji_in_western_is_not_an_error() -> None:
    born = parse_birth_input("1860/03/03", OPENED)
    assert _hint(born, OPENED) == "1860/03/03（166歳）"


def test_birth_input_hint_without_age_after_the_counting_day() -> None:
    assert _hint(parse_birth_input("2026/12/01"), OPENED) == "2026/12/01（令8）"


# 年齢を数える日の組（生年月日 1975/05/10。検査日で数える画面と開いた日で数える画面）
@pytest.mark.parametrize(
    ("on", "age"),
    [(date(2026, 4, 10), 50), (date(2026, 5, 10), 51), (date(2025, 5, 9), 49), (OPENED, 51)],
)
def test_birth_input_hint_counts_the_age_on_the_given_day(on: date, age: int) -> None:
    assert _hint(parse_birth_input("S50/05/10"), on) == f"1975/05/10（昭50・{age}歳）"
