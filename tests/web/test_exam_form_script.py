"""撮影の画面のスクリプト：form は novalidate なので、数の欄の確かめと、サーバーで断った誤りの消去を自分で行う.

node で app.js を読み込み、最小の偽の DOM に対して送る前の確かめと欄の変更を動かす。
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
class FakeControl {
  constructor(props) {
    Object.assign(this, { attrs: {}, custom: "", reported: 0 }, props);
    this.attrs = props.attrs || {};
  }
  hasAttribute(name) { return name in this.attrs; }
  getAttribute(name) { return name in this.attrs ? this.attrs[name] : null; }
  setAttribute(name, value) { this.attrs[name] = value; }
  removeAttribute(name) { delete this.attrs[name]; }
  setCustomValidity(message) { this.custom = message; }
  checkValidity() {
    const ok = this.validate(this) && !this.custom;
    if (!ok) { dispatch("invalid", { target: this }); }
    return ok && !this.custom;
  }
  get validationMessage() { return this.custom; }
  focus() { focused.push(this.name); }
}
class HTMLInputElement extends FakeControl {}
class HTMLSelectElement extends FakeControl {}
class HTMLFormElement extends FakeControl {}
function dispatch(type, event) {
  (listeners[type] || []).forEach((fn) => fn(event));
}
global.HTMLInputElement = HTMLInputElement;
global.HTMLSelectElement = HTMLSelectElement;
global.HTMLFormElement = HTMLFormElement;
global.window = { localStorage: { setItem() {} }, setTimeout };
global.document = {
  documentElement: { getAttribute() { return "light"; }, setAttribute() {} },
  body: {},
  addEventListener(type, fn) { (listeners[type] = listeners[type] || []).push(fn); },
  getElementById(id) { return lines[id] || null; },
  querySelector() { return null; },
  querySelectorAll() { return []; },
};
function line(name, text) {
  lines["error-" + name] = { textContent: text, hidden: !text };
  return lines["error-" + name];
}
eval(fs.readFileSync(process.argv[1], "utf8"));

const out = {};
// 数の欄（確かめの属性 data-check が無い）：0 は範囲の外
const count = new HTMLInputElement({
  name: "routine_images", value: "0", min: "1", max: "5", willValidate: true,
  validity: { valueMissing: false, badInput: false, rangeUnderflow: true, rangeOverflow: false, stepMismatch: false },
  validate: () => false,
  attrs: { "data-count-label": "Scout の画像数", "data-error-line": "error-routine-count" },
});
const sex = new HTMLSelectElement({ name: "sex", willValidate: true, validate: () => true });
const study = new HTMLInputElement({ name: "study_description", value: "", willValidate: true, validate: () => true });
const countLine = line("routine-count", "");
const sexLine = line("sex", "性別は、男・女・その他から選んでください。");
const studyLine = line("study_description", "検査名は 64 字以内で入力してください。");
const form = new HTMLFormElement({ id: "exam-form", elements: [sex, study, count] });
form.querySelectorAll = () => [];

let prevented = false;
dispatch("htmx:beforeRequest", { detail: { elt: form }, preventDefault() { prevented = true; } });
out.beforeRequest = {
  prevented, focused: focused.slice(), message: count.custom, shown: countLine.hidden ? "" : countLine.textContent,
  staleSexLineCleared: sexLine.hidden, staleStudyLineCleared: studyLine.hidden,
};

// 性別を選び直したら、サーバーで断った誤りが消える
sexLine.hidden = false; sexLine.textContent = "性別は、男・女・その他から選んでください。";
dispatch("change", { target: sex });
out.afterChange = { hidden: sexLine.hidden };

// 検査名を直したら、同じく消える
studyLine.hidden = false; studyLine.textContent = "検査名は 64 字以内で入力してください。";
dispatch("input", { target: study });
out.afterInput = { hidden: studyLine.hidden };

// 数の欄を直せば、日本語の文が消えて通る
count.value = "3"; count.validate = () => true;
dispatch("input", { target: count });
prevented = false;
dispatch("htmx:beforeRequest", { detail: { elt: form }, preventDefault() { prevented = true; } });
out.afterFix = { prevented, message: count.custom, shown: countLine.hidden };
console.log(JSON.stringify(out));
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


def test_count_field_range_is_checked_before_sending_although_the_form_is_novalidate(probe) -> None:
    """数の欄の範囲・必須・整数は、これまでどおり日本語の文で止める（#52）."""
    result = probe["beforeRequest"]
    assert result["prevented"] is True and result["focused"] == ["routine_images"]
    # ブラウザの吹き出しではなく、欄の外の 1 行に日本語の文を出す
    assert result["message"] == result["shown"] == "Scout の画像数は 1〜5 で入れてください"


def test_server_refusal_is_cleared_on_the_next_send(probe) -> None:
    result = probe["beforeRequest"]
    assert result["staleSexLineCleared"] and result["staleStudyLineCleared"]


def test_server_refusal_is_cleared_when_the_unchecked_field_is_fixed(probe) -> None:
    assert probe["afterChange"]["hidden"] is True
    assert probe["afterInput"]["hidden"] is True


def test_fixed_count_field_goes_through(probe) -> None:
    assert probe["afterFix"] == {"prevented": False, "message": "", "shown": True}
