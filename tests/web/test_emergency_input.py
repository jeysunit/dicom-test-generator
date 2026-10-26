"""緊急の患者の入力の確かめ：画面（POST /exam）の誤りの文と、欄の印（docs/spec/12a の 10.5）."""

from __future__ import annotations

import html as html_lib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from web_helpers import BASE_URL, csrf_token, modality_config, post_headers

from app.core.patient_input import (
    ALPHABETIC_MESSAGE,
    BIRTH_DATE_FUTURE_MESSAGE,
    IDEOGRAPHIC_MESSAGE,
    PATIENT_ID_MESSAGE,
    PHONETIC_MESSAGE,
    check_ideographic_group,
)
from app.modality.config import ModalityConfig
from app.web.app import STATIC_DIR, create_app
from app.web.settings import WebConfig

JIS = ["", "ISO 2022 IR 87"]


def _post(client, **fields: str) -> str:
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        # 画面の必須の欄（患者ID・漢字の氏名・性別。10.5）
        "name_ideographic": "緊急 太郎",
        "sex": "M",
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
        ({"name_ideographic": "髙橋 太郎", "charset": "jis"}, IDEOGRAPHIC_MESSAGE),
        ({"name_ideographic": "山﨑 太郎", "charset": "jis_kana"}, IDEOGRAPHIC_MESSAGE),
        ({"name_ideographic": "ﾔﾏﾀﾞ", "charset": "jis"}, IDEOGRAPHIC_MESSAGE),
        ({"name_phonetic": "ﾔﾏﾀﾞ"}, PHONETIC_MESSAGE),
        ({"name_phonetic": "ヤマダ 山田"}, PHONETIC_MESSAGE),
        ({"name_phonetic": "Yamada"}, PHONETIC_MESSAGE),
        ({"patient_id": "患者01"}, PATIENT_ID_MESSAGE),
        ({"patient_id": "E\\1"}, PATIENT_ID_MESSAGE),
        ({"patient_id": "A" * 65}, "64 字以内"),
        ({"name_alphabetic": "A" * 65}, "64 字以内"),
        ({"name_phonetic": "ア" * 65}, "氏名（かな）は 64 字以内"),
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
    page = _post(client, name_ideographic="髙橋 太郎", charset="jis")
    assert "髙" not in page
    page = _post(client, patient_id="患者01")
    assert "患者01" not in page


@pytest.mark.parametrize("charset", ["", "auto", "utf8"])
@pytest.mark.parametrize("name", ["髙橋 太郎", "山﨑 太郎"])
def test_utf8_accepts_characters_outside_jis_x_0208(client, tmp_path, charset, name) -> None:
    """文字コードが UTF-8（auto の既定も UTF-8）なら、漢字の氏名を JIS X 0208 で断らない."""
    page = _post(client, name_ideographic=name, charset=charset)
    assert 'role="alert"' not in page
    assert list((tmp_path / "output").rglob("*.dcm"))


def test_hiragana_in_the_phonetic_name_is_written_as_katakana(client, tmp_path) -> None:
    from pydicom import dcmread

    page = _post(client, name_phonetic="きんきゅう たろう")
    assert 'role="alert"' not in page
    file = next((tmp_path / "output").rglob("*.dcm"))
    assert dcmread(file).PatientName.phonetic == "キンキュウ^タロウ"


def test_server_error_names_the_field_for_the_script(client) -> None:
    """サーバーで断った誤りは、欄の名前を持たせて返す（スクリプトが同じ欄の下に結ぶ）."""
    page = _post(client, name_phonetic="ﾔﾏﾀﾞ")
    assert 'data-error-field="name_phonetic"' in page
    page = _post(client, name_ideographic="髙", charset="jis")
    assert 'data-error-field="name_ideographic"' in page
    page = _post(client, patient_id="患者")
    assert 'data-error-field="patient_id"' in page
    # 欄に結べない誤りは、欄の名前を付けない
    assert "data-error-field" not in _post(client, series="0")


def _test_mode_client(tmp_path, worklist_scp, storage_scp):
    data = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_dump()
    data["patient_input_test_mode"] = True
    app = create_app(
        ModalityConfig.model_validate(data),
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(),
        password=None,
    )
    return TestClient(app, base_url=BASE_URL)


def test_test_mode_passes_kana_values_through_to_dicom(tmp_path, worklist_scp, storage_scp) -> None:
    from pydicom import dcmread

    client = _test_mode_client(tmp_path, worklist_scp, storage_scp)
    page = _post(client, name_phonetic="ﾔﾏﾀﾞ^きん^キン")
    assert 'role="alert"' not in page
    file = next((tmp_path / "output").rglob("*.dcm"))
    assert dcmread(file).PatientName.phonetic == "ﾔﾏﾀﾞ^きん^キン"
    # 試験の形でも、長さと禁止の字は見る
    assert 'role="alert"' in _post(client, name_phonetic="ﾔ" * 65)
    # 画面は今の形を示す
    assert "かなの確かめ：試験の形" in html_lib.unescape(client.get("/exam").text)
    assert "data-test-mode" in client.get("/exam").text


def test_page_shows_the_normal_form_by_default(client) -> None:
    page = html_lib.unescape(client.get("/exam").text)
    assert "かなの確かめ：全角カタカナ" in page
    assert "data-test-mode" not in page


def test_exam_page_marks_each_field_for_the_script(client) -> None:
    """入力した時に分かるよう、欄に確かめの種類・文・誤りの行を結ぶ。誤りの行は label の中の下（.msg）."""
    page = html_lib.unescape(client.get("/exam").text)
    assert re.search(r'<form id="exam-form"[^>]* novalidate', page)
    for name, kind, message in (
        ("patient_id", "patient-id", PATIENT_ID_MESSAGE),
        ("name_alphabetic", "alphabetic", ALPHABETIC_MESSAGE),
        ("name_ideographic", "ideographic", IDEOGRAPHIC_MESSAGE),
        ("name_phonetic", "phonetic", PHONETIC_MESSAGE),
        ("birth_date", "birth-date", BIRTH_DATE_FUTURE_MESSAGE),
    ):
        end = page.index(f'name="{name}"')
        label_end = page.index("</label>", end)
        label = page[page.rindex("<label", 0, end) : label_end]
        assert f'data-check="{kind}"' in label, name
        assert f'data-message="{message}"' in label, name
        assert f'aria-describedby="error-{name}' in label, name
        # 誤りの行は label の中の下で、印と文（.msg）。読み上げない（画面の上の知らせだけが role="alert"）
        line = re.search(rf'<span class="msg" id="error-{name}" hidden>(.*?)</span></span>', label, re.S)
        assert line, name
        assert 'class="icon icon-triangle-alert ic" aria-hidden="true"' in line.group(1), name
        assert '<span class="t"></span>' in line.group(0), name
        assert 'role="alert"' not in line.group(0), name
    for name in ("sex", "study_description"):
        assert f'id="error-{name}"' in page
    # 送るのを止めたときの件数の知らせ（読み上げる唯一の場所）。form の外の上に置く
    assert page.index('<div id="error-summary" role="alert">') < page.index('<form id="exam-form"')
    # 患者ID は先頭の欄で、上限は 64 字（VR LO）
    patient_id = page[page.index('name="patient_id"') : page.index(">", page.index('name="patient_id"'))]
    assert "autofocus" in patient_id and 'maxlength="64"' in patient_id


def _freeze_clock_at_utc(monkeypatch, instant: datetime) -> None:
    """OS の時計の地域に関わらず、`datetime.now(tz)` が同じ 1 つの時刻を返すようにする."""

    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz)

    monkeypatch.setattr("app.core.patient_input.datetime", FrozenDatetime)


def test_birth_date_today_is_decided_in_the_configured_timezone(client, monkeypatch) -> None:
    """UTC の 2030-01-01 20:00 は日本（既定の Asia/Tokyo）では 01-02 の朝。今日生まれを断らない."""
    _freeze_clock_at_utc(monkeypatch, datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc))

    # 画面は、サーバーの今日を欄に持たせる（ブラウザの現地の日付が先に行かなくても通すため）
    assert 'data-today="2030-01-02"' in client.get("/exam").text
    page = _post(client, birth_date="2030-01-02")
    assert 'role="alert"' not in page
    # 日本の明日は、断る
    assert BIRTH_DATE_FUTURE_MESSAGE in _post(client, birth_date="2030-01-03")


def test_birth_date_follows_the_timezone_setting(tmp_path, worklist_scp, storage_scp, monkeypatch) -> None:
    _freeze_clock_at_utc(monkeypatch, datetime(2030, 1, 1, 20, 0, tzinfo=timezone.utc))
    data = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_dump()
    data["timezone"] = "UTC"
    app = create_app(
        ModalityConfig.model_validate(data),
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(),
        password=None,
    )
    utc_client = TestClient(app, base_url=BASE_URL)

    # UTC の今日は 2030-01-01。日本の今日（01-02）は、UTC の設定では明日
    assert BIRTH_DATE_FUTURE_MESSAGE in _post(utc_client, birth_date="2030-01-02")
    assert 'role="alert"' not in _post(utc_client, birth_date="2030-01-01")


def test_unknown_timezone_is_refused_by_the_config(tmp_path, worklist_scp, storage_scp) -> None:
    data = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_dump()
    data["timezone"] = "Mars/Olympus"
    with pytest.raises(ValueError, match="タイムゾーン"):
        ModalityConfig.model_validate(data)


def test_script_range_covers_every_jis_x_0208_character() -> None:
    """画面の漢字の確かめは、サーバーが許す字（JIS X 0208）を 1 字も止めない（含みすぎはよい）."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無いので、画面のスクリプトを動かせない")
    jis = [
        chr(code)
        for code in range(0x80, 0x10000)
        if not check_ideographic_group(chr(code), JIS) and not 0xD800 <= code <= 0xDFFF
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
    assert check_ideographic_group("すゞき^スヾキ", JIS) == ""


def test_script_uses_inline_errors_not_browser_bubbles() -> None:
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    for marker in ("data-check", "data-message", "aria-invalid", "patient-id", "htmx:beforeRequest",
                   "data-error-field", "convertPhonetic", "data-test-mode"):
        assert marker in script, marker
    # form は novalidate。ブラウザの吹き出し（二重になる）は使わない
    assert "setCustomValidity(message" not in script.split("数の欄の検証の文言", 1)[0]
    assert "reportValidity" not in script


def test_script_rechecks_a_field_after_the_blur_correction() -> None:
    """空白を ^ に補正した後（値の代入では input が起きない）に、欄の確かめを直す."""
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    focusout = script.split('addEventListener("focusout"', 1)[1].split("});", 1)[0]
    assert focusout.index('replace(/\\s+/g, "^")') < focusout.index("checkField(input)")


def test_script_phonetic_rules_match_the_server(tmp_path) -> None:
    """画面のかなの確かめと、ひらがなの直しは、サーバーと同じ字を通し、同じ字に直す."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node が無いので、画面のスクリプトを動かせない")
    from app.core.patient_input import check_phonetic_group, to_katakana

    chars = [chr(code) for code in range(0x20, 0x10000) if not 0xD800 <= code <= 0xDFFF]
    chars_file = tmp_path / "chars.json"
    chars_file.write_text(json.dumps(chars), encoding="utf-8")
    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    pieces = [
        re.search(pattern, script).group(0)
        for pattern in (
            r"var PHONETIC_CHARS = .*?;\n",
            r"var HIRAGANA = .*?;\n",
            r"var HIRAGANA_TO_KATAKANA = .*?;\n",
        )
    ]
    program = "".join(pieces) + (
        "var chars = JSON.parse(require('fs').readFileSync(process.argv[1], 'utf8'));\n"
        "console.log(JSON.stringify({"
        "accepted: chars.filter(function (c) { return PHONETIC_CHARS.test(c); }),"
        "converted: chars.map(function (c) {"
        "  return c.replace(HIRAGANA, function (h) {"
        "    return String.fromCharCode(h.charCodeAt(0) + HIRAGANA_TO_KATAKANA); }); })}));"
    )
    result = subprocess.run(
        [node, "-e", program, str(chars_file)], capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    # 画面は成分の区切り ^ も通す。サーバーは群を ^ で分けてから確かめる
    assert sorted(data["accepted"]) == sorted(
        c for c in chars if c == "^" or not check_phonetic_group(c)
    )
    assert data["converted"] == [to_katakana(c) for c in chars]
