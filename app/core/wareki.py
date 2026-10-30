"""生年月日の和暦と年齢の表示と、入力の読み取り（画面だけで使う。DICOM・HL7 の値は西暦の YYYYMMDD のまま）.

規則は 1 つ：生年月日が元号の表のどの期間に入るかを日付で決め、年 ＝ 西暦の年 − 元号の始まりの年 ＋ 1。
明治より前（1868/10/22 以前）は元号を出さず、年齢だけを出す。元年は短い表示では数字の 1。
入力は西暦（`1975/05/14`）と元号（`S50/05/14`・`昭50/05/14`・`昭和50年5月14日`）を受ける
（docs/spec/12a の 10.5）。画面のスクリプト（app/web/static/app.js）も同じ形を同じ文で断る。
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from .patient_input import BIRTH_DATE_FORMAT_MESSAGE, BIRTH_DATE_FUTURE_MESSAGE, FieldValidationError

# （始まりの日, 漢字 1 字, 英字 1 字, 正式名）。新しい元号から先に並べる
_ERAS = (
    (date(2019, 5, 1), "令", "R", "令和"),
    (date(1989, 1, 8), "平", "H", "平成"),
    (date(1926, 12, 25), "昭", "S", "昭和"),
    (date(1912, 7, 30), "大", "T", "大正"),
    (date(1868, 10, 23), "明", "M", "明治"),
)
# 入力の形。区切りは `/` だけで、数字は半角だけ（[0-9]。\d は全角の数字にも当たる）。
# 英字は全角も受ける（読む前に半角の大文字に直す）
_WESTERN_INPUT = re.compile(r"([0-9]{4})/([0-9]{1,2})/([0-9]{1,2})")
_SHORT_ERA_INPUT = re.compile(r"([MTSHR明大昭平令])([0-9]{1,2}|元)/([0-9]{1,2})/([0-9]{1,2})")
_FULL_ERA_INPUT = re.compile(r"(明治|大正|昭和|平成|令和)([0-9]{1,2}|元)年([0-9]{1,2})月([0-9]{1,2})日")
_LETTERS = str.maketrans("mtshrＭＴＳＨＲｍｔｓｈｒ", "MTSHRMTSHRMTSHR")


def parse_date(value: str) -> date | None:
    """DICOM の DA（YYYYMMDD）を日付にする。読めなければ None."""
    try:
        return datetime.strptime(value, "%Y%m%d").date() if len(value) == 8 and value.isdigit() else None
    except ValueError:
        return None


def age_on(born: date, on: date) -> int:
    """on（年齢を数える日）の時点の満年齢（誕生日の当日に上がる。2/29 生まれは平年は 3/1）."""
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def era_label(born: date, letter: bool = False) -> str:
    """元号と年：昭50（letter なら S50）。明治より前は空の文字列."""
    for start, kanji, alpha, _name in _ERAS:
        if born >= start:
            return f"{alpha if letter else kanji}{born.year - start.year + 1}"
    return ""


def _parts(value: str, on: date, letter: bool) -> tuple[str, str]:
    """（西暦の日付, 括弧の中身）。日付として読めなければ（そのままの値, 空）."""
    born = parse_date(value)
    if born is None:
        return (f"{value[:4]}/{value[4:6]}/{value[6:]}" if len(value) == 8 and value.isdigit() else value, "")
    items = [era_label(born, letter)]
    age = age_on(born, on)
    if age >= 0:
        items.append(f"{age}歳")
    inside = "・".join(item for item in items if item)
    return born.strftime("%Y/%m/%d"), inside


def birth_text(value: str, on: date) -> tuple[str, str]:
    """患者バナーの生年月日（漢字 1 字）：（1975/05/14, （昭50・51歳））。括弧は全角."""
    day, inside = _parts(value, on, letter=False)
    return day, f"（{inside}）" if inside else ""


def birth_cell(value: str, on: date) -> str:
    """一覧の表の生年月日の列（英字 1 字）：1975/05/14 (S50・51歳)。括弧は半角で前に半角の空白."""
    day, inside = _parts(value, on, letter=True)
    return f"{day} ({inside})" if inside else day


def _slash(day: date) -> str:
    return day.strftime("%Y/%m/%d")


def era_range_message(index: int, after_end: bool) -> str:
    """元号の範囲の外の誤りの文。`index` は `_ERAS` の位置、`after_end` は終わりより後か.

    終わりより後は、その元号の終わりの日と次の元号の 1 年の始まりの日を、始まりより前は、
    その元号の始まりの日と前の元号の末年とその終わりの日を入れる（明治の前は無いので 2 文）。
    """
    start, _kanji, _alpha, name = _ERAS[index]
    head = f"生年月日が{name}の範囲にありません。"
    if after_end:
        next_start, _, _, next_name = _ERAS[index - 1]
        return f"{head}{name}は {_slash(next_start - timedelta(days=1))} までです。{next_name}1年は {_slash(next_start)} からです。"
    if index + 1 == len(_ERAS):
        return f"{head}{name}は {_slash(start)} からです。"
    prev_start, _, _, prev_name = _ERAS[index + 1]
    prev_end = start - timedelta(days=1)
    prev_last = prev_end.year - prev_start.year + 1
    return f"{head}{name}は {_slash(start)} からです。{prev_name}{prev_last}年は {_slash(prev_end)} までです。"


def _calendar_date(year: int, month: int, day: int) -> date:
    try:
        return date(year, month, day)
    except ValueError:
        raise FieldValidationError(BIRTH_DATE_FORMAT_MESSAGE, "birth_date") from None


def parse_birth_input(value: str, today: date | None = None) -> date:
    """画面で入れた生年月日を読む。誤りは `FieldValidationError`（欄は birth_date）.

    確かめる順は、形（暦に無い日を含む）・元号の範囲・今日より後（`today` があるときだけ）。
    受ける形は西暦 `1975/5/14`、英字か漢字 1 字と年 `S50/05/14`・`昭50/05/14`、正式名
    `昭和50年5月14日`。年の 1 は `元` でもよい。英字は大文字・小文字・全角を受ける。前後の
    空白は捨てる。
    """
    text = value.strip()
    western = _WESTERN_INPUT.fullmatch(text)
    if western:
        born = _calendar_date(*(int(part) for part in western.groups()))
    else:
        era = _SHORT_ERA_INPUT.fullmatch(text[:1].translate(_LETTERS) + text[1:])
        era = era or _FULL_ERA_INPUT.fullmatch(text)
        if not era:
            raise FieldValidationError(BIRTH_DATE_FORMAT_MESSAGE, "birth_date")
        mark, year_text, month, day = era.groups()
        index = next(i for i, row in enumerate(_ERAS) if mark in (row[1], row[2], row[3]))
        year = 1 if year_text == "元" else int(year_text)
        if year == 0:
            raise FieldValidationError(BIRTH_DATE_FORMAT_MESSAGE, "birth_date")
        start = _ERAS[index][0]
        born = _calendar_date(start.year + year - 1, int(month), int(day))
        if born < start:
            raise FieldValidationError(era_range_message(index, after_end=False), "birth_date")
        if index > 0 and born >= _ERAS[index - 1][0]:
            raise FieldValidationError(era_range_message(index, after_end=True), "birth_date")
    if today is not None and born > today:
        raise FieldValidationError(BIRTH_DATE_FUTURE_MESSAGE, "birth_date")
    return born
