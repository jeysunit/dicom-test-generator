"""身元不明の患者の画面のスクリプト：仮の ID のボタン、「氏名が分からない」、性別の必須（docs/spec/12a の 10.5）.

node で app.js を読み込み、最小の偽の DOM に対して動かす。
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
const lines = {};
const focused = [];
class Element {
  constructor(props) {
    Object.assign(this, { value: "", readOnly: false }, props);
    this.attrs = props.attrs || {};
  }
  hasAttribute(name) { return name in this.attrs; }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  focus() { focused.push(this.name); }
  closest(selector) {
    if (selector === "[data-temporary-id]") { return this.hasAttribute("data-temporary-id") ? this : null; }
    if (selector === "form") { return this.form; }
    return null;
  }
}
class HTMLInputElement extends Element {}
class HTMLSelectElement extends Element {}
class HTMLFormElement extends Element {}
function dispatch(type, event) { (listeners[type] || []).forEach((fn) => fn(event)); }
global.Element = Element;
global.HTMLInputElement = HTMLInputElement;
global.HTMLSelectElement = HTMLSelectElement;
global.HTMLFormElement = HTMLFormElement;
global.window = { localStorage: { setItem() {} }, setTimeout };
global.document = {
  documentElement: { getAttribute() { return "light"; }, setAttribute() {} },
  body: {},
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  getElementById(id) { return lines[id] || null; },
  querySelector(selector) {
    return selector === 'meta[name="csrf-token"]' ? new Element({ attrs: { content: "TOKEN" } }) : null;
  },
  querySelectorAll() { return []; },
};
function line(name) {
  lines["error-" + name] = { textContent: "", hidden: true };
  return lines["error-" + name];
}
let fetched = null;
global.fetch = (url, options) => {
  fetched = { url, method: options.method, token: options.headers["X-CSRF-Token"] };
  return Promise.resolve({ ok: true, json: () => Promise.resolve({ patient_id: "TMP20300102030405" }) });
};
eval(fs.readFileSync(process.argv[1], "utf8"));

const out = {};
const field = (name, attrs, props) => new HTMLInputElement(Object.assign({ name, attrs: attrs || {} }, props));
const alphabetic = field("name_alphabetic", { "data-person-name": "", "data-check": "alphabetic", "data-message": "x" });
const ideographic = field("name_ideographic", {
  "data-person-name": "", "data-check": "ideographic", "data-message": "x", "data-required-message": "漢字を入れてください",
}, { required: true });
const phonetic = field("name_phonetic", { "data-person-name": "", "data-check": "phonetic", "data-message": "x" });
const patientId = field("patient_id", { "data-check": "patient-id", "data-message": "x" }, { required: true });
const sex = new HTMLSelectElement({
  name: "sex", required: true, value: "",
  attrs: { "data-check": "required", "data-required-message": "性別を選んでください。" },
});
const box = field("name_unknown", { "data-unknown-name": "", "data-ideographic": "不明^不明", "data-phonetic": "フメイ^フメイ" });
const button = new HTMLInputElement({ name: "", attrs: { "data-temporary-id": "" } });
const form = new HTMLFormElement({ id: "exam-form" });
form.elements = Object.assign([alphabetic, ideographic, phonetic, patientId, sex, box], {
  namedItem(name) { return this.find((control) => control.name === name) || null; },
});
[alphabetic, ideographic, phonetic, patientId, sex, box, button].forEach((control) => { control.form = form; });
["name_alphabetic", "name_ideographic", "name_phonetic", "patient_id", "sex"].forEach(line);
const summaryText = { textContent: "" };
const summaryNotice = { hidden: true, querySelector: (selector) => (selector === ".t" ? summaryText : null) };
lines["error-summary"] = { querySelector: (selector) => (selector === ".notice" ? summaryNotice : null) };
form.querySelectorAll = () => [patientId, ideographic, phonetic, alphabetic, sex];
form.querySelector = () => null;

// 性別が空なら送らない（必須）。メッセージは欄の下に出す
let prevented = false;
patientId.value = "E1"; ideographic.value = "山田 太郎";
dispatch("htmx:beforeRequest", { detail: { elt: form }, preventDefault() { prevented = true; } });
out.sexRequired = { prevented, text: lines["error-sex"].textContent, hidden: lines["error-sex"].hidden, focus: focused.slice(-1)[0] };
sex.value = "M"; prevented = false;
dispatch("change", { target: sex });
dispatch("htmx:beforeRequest", { detail: { elt: form }, preventDefault() { prevented = true; } });
out.sexChosen = { prevented, hidden: lines["error-sex"].hidden };

// 「氏名が分からない」：設定の値を入れて読むだけにし、英字は空。外すと消えて戻る
alphabetic.value = "TYPED"; ideographic.value = "";
box.checked = true;
dispatch("change", { target: box });
out.unknownOn = {
  alphabetic: alphabetic.value, ideographic: ideographic.value, phonetic: phonetic.value,
  readOnly: [alphabetic, ideographic, phonetic].map((control) => control.readOnly),
  ideographicError: lines["error-name_ideographic"].hidden,
};
box.checked = false;
dispatch("change", { target: box });
out.unknownOff = {
  values: [alphabetic.value, ideographic.value, phonetic.value],
  readOnly: [alphabetic, ideographic, phonetic].map((control) => control.readOnly),
  ideographicError: lines["error-name_ideographic"].hidden,
};

// 仮の ID：サーバーに作らせた値を患者ID の欄に入れる
patientId.value = "";
dispatch("click", { target: button });
setTimeout(() => {
  out.temporaryId = { value: patientId.value, fetched, disabled: !!button.disabled };
  console.log(JSON.stringify(out));
}, 50);
"""


@pytest.fixture(scope="module")
def probe() -> dict:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無いので、画面のスクリプトを動かせない")
    result = subprocess.run(
        [node, "-e", PROGRAM, str(STATIC_DIR / "app.js")], capture_output=True, text=True, check=True
    )
    return json.loads(result.stdout)


def test_sex_is_required_before_sending(probe) -> None:
    assert probe["sexRequired"] == {
        "prevented": True,
        "text": "性別を選んでください。",
        "hidden": False,
        "focus": "sex",
    }
    assert probe["sexChosen"] == {"prevented": False, "hidden": True}


def test_unknown_name_fills_the_configured_values_and_locks_the_fields(probe) -> None:
    assert probe["unknownOn"] == {
        "alphabetic": "",
        "ideographic": "不明^不明",
        "phonetic": "フメイ^フメイ",
        "readOnly": [True, True, True],
        "ideographicError": True,
    }


def test_unchecking_unknown_name_clears_the_values_without_an_error(probe) -> None:
    assert probe["unknownOff"] == {
        "values": ["", "", ""],
        "readOnly": [False, False, False],
        "ideographicError": True,
    }


def test_temporary_id_button_asks_the_server_with_the_csrf_token(probe) -> None:
    assert probe["temporaryId"]["value"] == "TMP20300102030405"
    assert probe["temporaryId"]["fetched"] == {
        "url": "/exam/temporary-id",
        "method": "POST",
        "token": "TOKEN",
    }
    assert probe["temporaryId"]["disabled"] is False
