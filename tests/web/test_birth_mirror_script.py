"""緊急の患者の入力の写し：生年月日の和暦と年齢（変換 12 行と年齢の境目 7 行は tests/core/test_wareki.py と同じ組）.

node で app.js を読み込み、最小の偽の DOM に入力を送って、写しの生年月日の文字列を読む。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "web" / "static"

PROGRAM = r"""
const fs = require("fs");
const listeners = {};
class Element {
  constructor(props) {
    Object.assign(this, { value: "", children: [] }, props);
    this.attrs = props.attrs || {};
    let text = "";
    // textContent に代入すると子の要素は捨てられる（実際の DOM と同じ）
    Object.defineProperty(this, "textContent", {
      get: () => text,
      set: (value) => { text = value; this.children = []; },
    });
  }
  hasAttribute(name) { return name in this.attrs; }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  closest(selector) { return selector === "#emergency-patient" ? this : null; }
  appendChild(child) { this.children.push(child); }
}
class HTMLInputElement extends Element {}
class HTMLSelectElement extends Element {}
class HTMLFormElement extends Element {}
global.Element = Element;
global.HTMLInputElement = HTMLInputElement;
global.HTMLSelectElement = HTMLSelectElement;
global.HTMLFormElement = HTMLFormElement;
global.window = { localStorage: { setItem() {} }, setTimeout };
const cell = new Element({});
const target = {
  querySelectorAll() { return []; },
  querySelector(selector) { return selector === "[data-mirror-birth]" ? cell : null; },
};
global.document = {
  documentElement: { getAttribute() { return "light"; }, setAttribute() {} },
  body: {},
  createElement() { return new Element({}); },
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  getElementById(id) { return id === "exam-target" ? target : null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
eval(fs.readFileSync(process.argv[1], "utf8"));

const birth = new HTMLInputElement({ name: "birth_date", attrs: {} });
const sex = new HTMLSelectElement({ name: "sex", value: "M", attrs: {} });
const form = new HTMLFormElement({ attrs: {} });
form.elements = { namedItem(name) { return { birth_date: birth, sex }[name] || null; } };
birth.form = form;
sex.form = form;

function shown(value, today, sexValue) {
  birth.value = value;
  birth.attrs["data-today"] = today;
  sex.value = sexValue;
  (listeners.input || []).forEach((fn) => fn({ target: birth }));
  const unit = cell.children.find((child) => child.className === "unit");
  return {
    text: cell.textContent + cell.children.map((child) => child.textContent).join(""),
    unit: unit ? unit.textContent : null,
    title: cell.getAttribute("title"),
  };
}
const cases = JSON.parse(process.argv[2]);
console.log(JSON.stringify(cases.map(([value, today, sexValue]) => shown(value, today, sexValue))));
"""

# （生年月日, 漢字 1 字の形）。変換の組の 12 行。基準日は 2026-10-29
CONVERSIONS = [
    ("1868-10-22", ""),
    ("1868-10-23", "明1"),
    ("1912-07-29", "明45"),
    ("1912-07-30", "大1"),
    ("1926-12-24", "大15"),
    ("1926-12-25", "昭1"),
    ("1975-05-14", "昭50"),
    ("1989-01-07", "昭64"),
    ("1989-01-08", "平1"),
    ("2019-04-30", "平31"),
    ("2019-05-01", "令1"),
    ("2026-10-29", "令8"),
]
TODAY = "2026-10-29"

# （生年月日, 基準日, 年齢）。年齢の境目の組の 7 行
AGES = [
    ("1975-05-14", "2026-05-13", 50),
    ("1975-05-14", "2026-05-14", 51),
    ("2026-10-29", "2026-10-29", 0),
    ("2000-02-29", "2026-02-28", 25),
    ("2000-02-29", "2026-03-01", 26),
    ("2000-02-29", "2028-02-28", 27),
    ("2000-02-29", "2028-02-29", 28),
]


def _run(cases: list[list[str]]) -> list[str]:
    return [shown["text"] for shown in _run_detail(cases)]


def _run_detail(cases: list[list[str]]) -> list[dict[str, str | None]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無いので、画面のスクリプトを動かせない")
    # 欄は文字の欄で、西暦は 1975/05/14 の形で入れる（組の生年月日は 1975-05-14 の形で書いてある）。
    # 基準日（data-today）はサーバーが渡す ISO 8601 の形のまま
    typed = [[born.replace("-", "/"), today, sex] for born, today, sex in cases]
    result = subprocess.run(
        [node, "-e", PROGRAM, str(STATIC_DIR / "app.js"), json.dumps(typed)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _age(born: str, today: str) -> int:
    by, bm, bd = (int(part) for part in born.split("-"))
    ty, tm, td = (int(part) for part in today.split("-"))
    return ty - by - ((tm, td) < (bm, bd))


def test_mirrored_birth_date_has_era_and_age_for_every_conversion_row() -> None:
    shown = _run([[born, TODAY, "M"] for born, _ in CONVERSIONS])
    for (born, era), text in zip(CONVERSIONS, shown, strict=True):
        day = born.replace("-", "/")
        inside = (f"{era}・" if era else "") + f"{_age(born, TODAY)}歳"
        assert text == f"{day}（{inside}）男", born


def test_mirrored_birth_date_wraps_the_part_after_the_date_in_unit_with_the_full_text_in_title() -> None:
    [with_paren, without_date] = _run_detail([["1975-05-14", TODAY, "M"], ["", TODAY, "M"]])
    assert with_paren["unit"] == "（昭50・51歳）男"
    assert with_paren["title"] == "1975/05/14（昭50・51歳）男"
    assert without_date["unit"] is None
    assert without_date["title"] is None


def test_mirrored_age_follows_the_birthday_boundaries() -> None:
    shown = _run([[born, today, "F"] for born, today, _ in AGES])
    for (born, today, age), text in zip(AGES, shown, strict=True):
        assert f"・{age}歳）女" in text, (born, today)


def test_mirrored_birth_date_without_a_date_or_a_sex() -> None:
    assert _run([["", TODAY, "M"], ["", TODAY, ""], ["1975-05-14", TODAY, ""]]) == [
        "生年月日なし（男）",
        "生年月日なし",
        "1975/05/14（昭50・51歳）",
    ]


def test_mirrored_birth_date_after_the_count_day_shows_the_era_without_an_age() -> None:
    # 生年月日が数える日より後（年齢が負）：年齢は出さず、元号の括弧だけにする
    [later_year, later_day] = _run_detail([["2027-06-15", TODAY, "M"], ["2026-10-30", TODAY, "F"]])
    assert later_year["text"] == "2027/06/15（令9）男"
    assert later_year["unit"] == "（令9）男"
    assert later_day["text"] == "2026/10/30（令8）女"
    assert "歳" not in later_year["text"] + later_day["text"]


def test_mirrored_birth_date_reads_the_era_forms_and_keeps_an_unreadable_value_as_typed() -> None:
    # 元号で入れても西暦にして写す。読めない値は入れたまま写し、括弧を付けない（誤りは欄の下）
    [era, formal, unreadable] = _run_detail(
        [["S50/05/14", TODAY, "M"], ["平成元年1月8日", TODAY, "F"], ["S50.5.14", TODAY, "M"]]
    )
    assert era["text"] == "1975/05/14（昭50・51歳）男"
    assert formal["text"] == "1989/01/08（平1・37歳）女"
    assert unreadable == {"text": "S50.5.14 男", "unit": None, "title": "S50.5.14 男"}


def test_mirrored_sex_shows_all_four_words() -> None:
    shown = _run([["1975-05-14", TODAY, sex] for sex in ("M", "F", "O", "U")])
    assert [text.rsplit("）", 1)[1] for text in shown] == ["男", "女", "その他", "不明"]
    assert _run([["", TODAY, "U"]]) == ["生年月日なし（不明）"]
