"""緊急の患者を撮った後の固定：仮の ID のボタンと「氏名が分からない」でも患者を変えない（docs/spec/12a の 10.5）.

node で app.js を読み込み、最小の偽の DOM に対して、撮った後の固定と「同じ患者でもう一度」を動かす。
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
class Element {
  constructor(props) {
    Object.assign(this, { value: "", readOnly: false, disabled: false, checked: false, type: "text" }, props);
    this.attrs = props.attrs || {};
  }
  hasAttribute(name) { return name in this.attrs; }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  toggleAttribute(name, force) {
    if (force) { this.attrs[name] = ""; } else { delete this.attrs[name]; }
    return !!force;
  }
  focus() {}
  closest(selector) {
    if (selector === "[data-temporary-id]") { return this.hasAttribute("data-temporary-id") ? this : null; }
    if (selector === "form") { return this.form; }
    if (selector === "#emergency-patient") { return this.section || null; }
    return null;
  }
}
class HTMLInputElement extends Element {}
class HTMLSelectElement extends Element {}
class HTMLButtonElement extends Element {}
class HTMLFormElement extends Element {}
function dispatch(type, event) { (listeners[type] || []).forEach((fn) => fn(event)); }
global.Element = Element;
global.HTMLInputElement = HTMLInputElement;
global.HTMLSelectElement = HTMLSelectElement;
global.HTMLButtonElement = HTMLButtonElement;
global.HTMLFormElement = HTMLFormElement;
global.window = { localStorage: { setItem() {} }, setTimeout };
// 撮った後の操作の行（[同じ患者でもう一度]）が出ているか
let done = false;
let section = null;
global.document = {
  documentElement: { getAttribute() { return "light"; }, setAttribute() {} },
  body: {},
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  getElementById(id) { return id === "emergency-patient" ? section : lines[id] || null; },
  querySelector(selector) {
    if (selector === 'meta[name="csrf-token"]') { return new Element({ attrs: { content: "TOKEN" } }); }
    if (selector === "#actions [data-same-patient]") { return done ? new Element({}) : null; }
    return null;
  },
  querySelectorAll() { return []; },
};
// 仮の ID の応答は、試験が決めたときに返す（撮った後に届く応答を作るため）
const pending = [];
let fetchCount = 0;
global.fetch = () => {
  fetchCount += 1;
  return new Promise((resolve) => pending.push(resolve));
};
function answer(patientId) {
  pending.shift()({ ok: true, json: () => Promise.resolve({ patient_id: patientId }) });
}
const tick = () => new Promise((resolve) => setTimeout(resolve, 20));
eval(fs.readFileSync(process.argv[1], "utf8"));

const field = (name, props) => new HTMLInputElement(Object.assign({ name, attrs: {} }, props));
const alphabetic = field("name_alphabetic", { attrs: { "data-person-name": "" } });
const ideographic = field("name_ideographic", { attrs: { "data-person-name": "" } });
const phonetic = field("name_phonetic", { attrs: { "data-person-name": "" } });
const patientId = field("patient_id");
const sex = new HTMLSelectElement({ name: "sex", value: "M", attrs: {} });
const box = field("name_unknown", {
  type: "checkbox", attrs: { "data-unknown-name": "", "data-ideographic": "不明^不明", "data-phonetic": "フメイ^フメイ" },
});
const button = new HTMLButtonElement({ name: "", type: "button", attrs: { "data-temporary-id": "" } });
const controls = [patientId, ideographic, phonetic, alphabetic, sex, box, button];
const form = new HTMLFormElement({ id: "exam-form", attrs: {} });
form.elements = Object.assign(controls.slice(), {
  namedItem(name) { return this.find((control) => control.name === name) || null; },
});
form.querySelectorAll = () => [];
form.querySelector = () => null;
const TAGS = { input: HTMLInputElement, select: HTMLSelectElement, button: HTMLButtonElement };
section = new Element({ attrs: {} });
section.querySelectorAll = (selector) => {
  const kinds = selector.split(",").map((part) => TAGS[part.trim()]).filter(Boolean);
  return controls.filter((control) => kinds.some((kind) => control instanceof kind));
};
section.querySelector = () => null;
controls.forEach((control) => { control.form = form; control.section = section; });
["name_alphabetic", "name_ideographic", "name_phonetic", "patient_id", "sex"].forEach((name) => {
  lines["error-" + name] = { textContent: "", hidden: true };
});

// 操作の行（#actions）を入れ替えた後の htmx:afterSettle
const actions = new Element({ attrs: {} });
function settle(isDone) {
  done = isDone;
  dispatch("htmx:afterSettle", { target: actions, detail: { requestConfig: { path: "/exam/check" } } });
}
function names() { return [alphabetic.value, ideographic.value, phonetic.value]; }
function nameReadOnly() { return [alphabetic, ideographic, phonetic].map((control) => control.readOnly); }

(async () => {
  const out = {};
  // E1001・緊急 一郎 を撮った後
  patientId.value = "E1001"; ideographic.value = "緊急^一郎"; phonetic.value = "キンキュウ^イチロウ";
  settle(true);
  out.locked = {
    buttonDisabled: button.disabled, boxDisabled: box.disabled,
    patientReadOnly: patientId.readOnly, nameReadOnly: nameReadOnly(), sexDisabled: sex.disabled,
  };

  // (a) 撮った後に仮の ID のボタンを押し、「氏名が分からない」を入れて外しても、患者は変わらない
  dispatch("click", { target: button });
  await tick();
  box.checked = true;
  dispatch("change", { target: box });
  const afterCheck = { box: box.checked, names: names(), nameReadOnly: nameReadOnly() };
  box.checked = false;
  dispatch("change", { target: box });
  out.pressedWhileLocked = {
    fetchCount, patientId: patientId.value, afterCheck,
    afterUncheck: { names: names(), nameReadOnly: nameReadOnly() },
  };

  // (b) 撮る前に押した仮の ID の応答が、撮った後に届いても書かない
  settle(false);
  dispatch("click", { target: button });
  settle(true);
  answer("TMP20300102030405");
  await tick();
  out.lateAnswer = { patientId: patientId.value, buttonDisabled: button.disabled, patientReadOnly: patientId.readOnly };
  // 応答の前に撮って「同じ患者でもう一度」で戻っても、撮る前に押した応答は書かない
  settle(false);
  dispatch("click", { target: button });
  settle(true);
  settle(false);
  answer("TMP20300102030406");
  await tick();
  out.answerAcrossShot = { patientId: patientId.value, buttonDisabled: button.disabled };
  // 固定していない間の応答は、これまでどおり書く
  dispatch("click", { target: button });
  answer("TMP20300102030407");
  await tick();
  out.unlockedAnswer = { patientId: patientId.value, buttonDisabled: button.disabled };

  // (c) 氏名不明のまま撮って「同じ患者でもう一度」を押しても、氏名の欄は読むだけのまま
  box.checked = true;
  dispatch("change", { target: box });
  settle(true);
  settle(false);
  out.unknownSamePatient = {
    names: names(), nameReadOnly: nameReadOnly(), box: box.checked, boxDisabled: box.disabled,
    buttonDisabled: button.disabled, patientReadOnly: patientId.readOnly, sexDisabled: sex.disabled,
  };
  // 氏名の分かる患者なら、「同じ患者でもう一度」で氏名の欄を戻す
  box.checked = false;
  dispatch("change", { target: box });
  settle(true);
  settle(false);
  out.knownSamePatient = { nameReadOnly: nameReadOnly(), boxDisabled: box.disabled };
  console.log(JSON.stringify(out));
})();
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


def test_locking_disables_the_temporary_id_button_and_the_unknown_name_box(probe) -> None:
    assert probe["locked"] == {
        "buttonDisabled": True,
        "boxDisabled": True,
        "patientReadOnly": True,
        "nameReadOnly": [True, True, True],
        "sexDisabled": True,
    }


def test_pressing_the_buttons_after_the_shot_keeps_the_patient(probe) -> None:
    result = probe["pressedWhileLocked"]
    assert result["fetchCount"] == 0
    assert result["patientId"] == "E1001"
    # チェックは戻り、氏名は撮ったときの値で読むだけのまま
    assert result["afterCheck"] == {
        "box": False,
        "names": ["", "緊急^一郎", "キンキュウ^イチロウ"],
        "nameReadOnly": [True, True, True],
    }
    assert result["afterUncheck"] == {
        "names": ["", "緊急^一郎", "キンキュウ^イチロウ"],
        "nameReadOnly": [True, True, True],
    }


def test_temporary_id_answer_arriving_after_the_shot_is_not_written(probe) -> None:
    assert probe["lateAnswer"] == {"patientId": "E1001", "buttonDisabled": True, "patientReadOnly": True}
    assert probe["answerAcrossShot"] == {"patientId": "E1001", "buttonDisabled": False}


def test_temporary_id_answer_is_written_while_not_locked(probe) -> None:
    assert probe["unlockedAnswer"] == {"patientId": "TMP20300102030407", "buttonDisabled": False}


def test_same_patient_keeps_the_unknown_name_fields_read_only(probe) -> None:
    assert probe["unknownSamePatient"] == {
        "names": ["", "不明^不明", "フメイ^フメイ"],
        "nameReadOnly": [True, True, True],
        "box": True,
        "boxDisabled": False,
        "buttonDisabled": False,
        "patientReadOnly": False,
        "sexDisabled": False,
    }


def test_same_patient_unlocks_the_name_fields_for_a_known_name(probe) -> None:
    assert probe["knownSamePatient"] == {"nameReadOnly": [False, False, False], "boxDisabled": False}
