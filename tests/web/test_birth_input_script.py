"""緊急の患者の生年月日の欄：画面のスクリプトの読み取り結果（.hint）と誤りの文（.msg）.

受ける形と誤りの組は、変換の試験（tests/core/test_wareki.py）と同じ（tests/birth_input_cases.py）。
誤りの文はサーバー（app/core/wareki.py）と同じ字面であることを、同じ組で確かめる。
node で app.js を読み込み、最小の偽の DOM で欄に入力を送る。時計は 2026/10/29 に止める。
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from birth_input_cases import ACCEPTED, MORE_REFUSED, REFUSED

from app.core.patient_input import BIRTH_DATE_FORMAT_MESSAGE, BIRTH_DATE_FUTURE_MESSAGE

STATIC_DIR = Path(__file__).resolve().parents[2] / "app" / "web" / "static"

PROGRAM = r"""
const fs = require("fs");
const RealDate = Date;
// ブラウザの今日も 2026/10/29（サーバーの今日 data-today と同じ日）にする
global.Date = class extends RealDate {
  constructor(...args) { if (args.length) { super(...args); } else { super(2026, 9, 29, 12, 0, 0); } }
};
const listeners = {};
const nodes = {};
class Element {
  constructor(props) { Object.assign(this, { value: "", attrs: {} }, props); }
  hasAttribute(name) { return name in this.attrs; }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  closest() { return null; }
}
class HTMLInputElement extends Element {}
class HTMLSelectElement extends Element {}
class HTMLFormElement extends Element {}
global.Element = Element;
global.HTMLInputElement = HTMLInputElement;
global.HTMLSelectElement = HTMLSelectElement;
global.HTMLFormElement = HTMLFormElement;
global.window = { localStorage: { setItem() {} }, setTimeout };
global.document = {
  documentElement: { getAttribute() { return "light"; }, setAttribute() {} },
  body: {},
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  getElementById(id) { return nodes[id] || null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
eval(fs.readFileSync(process.argv[1], "utf8"));

const messages = JSON.parse(process.argv[3]);
const birth = new HTMLInputElement({
  name: "birth_date",
  attrs: {
    "data-check": "birth-date", "data-today": "2026-10-29",
    "data-message": messages.future, "data-format-message": messages.format,
  },
});
const hint = { textContent: "", hidden: true };
const msgText = { textContent: "" };
const msg = { hidden: true, querySelector: (selector) => (selector === ".t" ? msgText : null) };
nodes["hint-birth_date"] = hint;
nodes["error-birth_date"] = msg;

const out = JSON.parse(process.argv[2]).map((value) => {
  birth.value = value;
  (listeners.input || []).forEach((fn) => fn({ target: birth }));
  return {
    hint: hint.hidden ? null : hint.textContent,
    msg: msg.hidden ? null : msgText.textContent,
    invalid: birth.getAttribute("aria-invalid"),
  };
});
console.log(JSON.stringify(out));
"""


def _typed(values: list[str]) -> list[dict[str, str | None]]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無いので、画面のスクリプトを動かせない")
    messages = {"format": BIRTH_DATE_FORMAT_MESSAGE, "future": BIRTH_DATE_FUTURE_MESSAGE}
    result = subprocess.run(
        [node, "-e", PROGRAM, str(STATIC_DIR / "app.js"), json.dumps(values), json.dumps(messages)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def test_accepted_forms_show_the_reading_in_the_hint() -> None:
    shown = _typed([value for value, _, _ in ACCEPTED])
    for (value, _, hint), result in zip(ACCEPTED, shown, strict=True):
        assert result == {"hint": hint, "msg": None, "invalid": None}, value


def test_refused_forms_clear_the_hint_and_show_the_server_message() -> None:
    cases = REFUSED + MORE_REFUSED
    shown = _typed([value for value, _ in cases])
    for (value, message), result in zip(cases, shown, strict=True):
        assert result == {"hint": None, "msg": message, "invalid": "true"}, value


def test_empty_field_shows_neither_hint_nor_message() -> None:
    # 読めない値の後に消すと、.hint も .msg も消える
    [_, empty, spaces] = _typed(["S50.5.14", "", "  "])
    assert empty == spaces == {"hint": None, "msg": None, "invalid": None}


def test_reading_follows_each_keystroke() -> None:
    """入力のたびに替える。打ちかけ（S5・S50/5）は誤り、打ち終えたら読み取り結果."""
    shown = _typed(["S5", "S50/5", "S50/5/14"])
    assert [result["hint"] for result in shown] == [None, None, "1975/05/14（昭50・51歳）"]
    assert shown[0]["msg"] == BIRTH_DATE_FORMAT_MESSAGE
