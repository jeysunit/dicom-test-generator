"""緊急の患者の入力の確かめ：画面（POST /exam）の誤りの文と、欄の印（docs/spec/12a の 10.5）."""

from __future__ import annotations

import html as html_lib
import json
import re
import shutil
import subprocess

import pytest
from web_helpers import csrf_token, post_headers

from app.core.patient_input import (
    ALPHABETIC_MESSAGE,
    BIRTH_DATE_FUTURE_MESSAGE,
    IDEOGRAPHIC_MESSAGE,
    PATIENT_ID_MESSAGE,
    check_ideographic_group,
)
from app.web.app import STATIC_DIR


def _post(client, **fields: str) -> str:
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        "template": "ct_generic",
        "series": "1",
        "images": "1",
        "action": "exam",
        **fields,
    }
    response = client.post("/exam", data=form, headers=post_headers(token))
    return html_lib.unescape(response.text)


def test_valid_emergency_patient_is_accepted(client) -> None:
    page = _post(
        client,
        name_ideographic="緊急 太郎",
        name_phonetic="きんきゅう たろう",
        birth_date="1975-05-10",
        sex="M",
    )
    assert 'role="alert"' not in page


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"name_alphabetic": "山田 太郎"}, ALPHABETIC_MESSAGE),
        ({"name_alphabetic": "ＹＡＭＡＤＡ ＴＡＲＯ"}, ALPHABETIC_MESSAGE),
        ({"name_alphabetic": "TARO 1"}, ALPHABETIC_MESSAGE),
        ({"name_ideographic": "髙橋 太郎"}, IDEOGRAPHIC_MESSAGE),
        ({"name_ideographic": "ﾔﾏﾀﾞ"}, IDEOGRAPHIC_MESSAGE),
        ({"patient_id": "患者01"}, PATIENT_ID_MESSAGE),
        ({"patient_id": "E\\1"}, PATIENT_ID_MESSAGE),
        ({"patient_id": "A" * 17}, "16 字以内"),
        ({"name_alphabetic": "A" * 65}, "64 字以内"),
        ({"name_phonetic": "あ" * 65}, "氏名（かな）は 64 字以内"),
        ({"birth_date": "2999-01-01"}, BIRTH_DATE_FUTURE_MESSAGE),
        ({"birth_date": "2023-02-29"}, "暦にある日付"),
        ({"sex": "X"}, "性別"),
        ({"study_description": "あ" * 65}, "検査名は 64 字以内"),
    ],
)
def test_bad_values_are_refused_with_a_japanese_message(client, tmp_path, fields, message) -> None:
    page = _post(client, **fields)
    assert 'role="alert"' in page
    assert message in page
    assert "撮影完了" not in page
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_refusal_message_does_not_echo_the_value(client) -> None:
    page = _post(client, name_ideographic="髙橋 太郎")
    assert "髙" not in page
    page = _post(client, patient_id="患者01")
    assert "患者01" not in page


def test_exam_page_marks_each_field_for_the_script(client) -> None:
    """入力した時に分かるよう、欄に確かめの種類・文・誤りの置き場を持たせる."""
    page = html_lib.unescape(client.get("/exam").text)
    for name, kind, message in (
        ("patient_id", "patient-id", PATIENT_ID_MESSAGE),
        ("name_alphabetic", "alphabetic", ALPHABETIC_MESSAGE),
        ("name_ideographic", "ideographic", IDEOGRAPHIC_MESSAGE),
        ("birth_date", "birth-date", BIRTH_DATE_FUTURE_MESSAGE),
    ):
        end = page.index(f'name="{name}"')
        label = page[page.rindex("<label", 0, end) : page.index("</label>", end)]
        assert f'data-check="{kind}"' in label, name
        assert f'data-message="{message}"' in label, name
        note_id = f"error-{kind}"
        assert f'aria-describedby="{note_id}"' in label, name
        # 欄の下の誤りは読み上げない（画面の上の知らせだけが role="alert"）
        assert f'id="{note_id}"' in label and "hidden" in label, name
        assert 'role="alert"' not in label, name


def test_script_range_covers_every_jis_x_0208_character() -> None:
    """画面の漢字の確かめは、サーバーが許す字（JIS X 0208）を 1 字も止めない（含みすぎはよい）."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無いので、画面のスクリプトを動かせない")
    jis = [
        chr(code)
        for code in range(0x80, 0x10000)
        if not check_ideographic_group(chr(code)) and not 0xD800 <= code <= 0xDFFF
    ]
    assert "ゞ" in jis and "ヾ" in jis and "髙" not in jis and len(jis) > 6000
    source = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    match = re.search(r"var IDEOGRAPHIC_RANGES = .*?\n  }\n", source, re.S)
    assert match
    program = match.group(0) + "\nvar chars = JSON.parse(process.argv[1]);\n"
    program += "console.log(JSON.stringify(chars.filter(function (c) { return !isIdeographic(c); })));"
    result = subprocess.run(
        [node, "-e", program, json.dumps(jis)], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout) == []
    # 半角カナと JIS に無い字は止める
    probe = subprocess.run(
        [node, "-e", match.group(0) + "console.log(isIdeographic('ﾔ'), isIdeographic('😀'), isIdeographic('すゞき'));"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert probe.stdout.split() == ["false", "false", "true"]


def test_server_accepts_iteration_marks() -> None:
    assert check_ideographic_group("すゞき^スヾキ") == ""


def test_script_checks_on_input_and_blocks_submit_while_invalid() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for marker in ("data-check", "data-message", "setCustomValidity", "aria-invalid", "patient-id"):
        assert marker in script, marker
