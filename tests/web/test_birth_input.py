"""緊急の患者の生年月日の入力：西暦と元号を受け、西暦の YYYYMMDD で保存する（docs/spec/12a の 10.5）."""

from __future__ import annotations

import html as html_lib
import re

import pytest
from birth_input_cases import FORMAT, FUTURE, HEISEI_AFTER_END
from pydicom import dcmread
from web_helpers import csrf_token, post_headers

from app.core.patient_input import BIRTH_DATE_FORMAT_MESSAGE, PATIENT_ID_MESSAGE


def _post(client, **fields: str) -> str:
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
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


def _birth_label(page: str) -> str:
    start = page.index('name="birth_date"')
    return page[page.rindex("<label", 0, start) : page.index("</label>", start)]


def test_birth_field_is_one_text_field_with_a_hint_line(client) -> None:
    label = _birth_label(html_lib.unescape(client.get("/exam").text))
    field = re.search(r"<input [^>]*name=\"birth_date\"[^>]*>", label).group(0)
    assert 'type="text"' in field and 'inputmode="text"' in field and 'autocomplete="off"' in field
    assert 'type="date"' not in label
    # 読み取り結果（.hint）と誤り（.msg）を欄に結ぶ。打つたびに読まれないよう aria-live は付けない
    # 誤りの行を先に結ぶのはほかの欄（氏名（かな）の知らせ）と同じ。.hint と .msg は同時には出ない
    assert 'aria-describedby="error-birth_date hint-birth_date"' in field
    assert '<span class="hint" id="hint-birth_date" hidden></span>' in label
    assert label.index('id="hint-birth_date"') < label.index('id="error-birth_date"')
    assert "aria-live" not in label
    assert f'data-format-message="{BIRTH_DATE_FORMAT_MESSAGE}"' in field
    assert f'data-message="{FUTURE}"' in field


@pytest.mark.parametrize("value", ["S50/05/14", "昭和50年5月14日", "s50/5/14", "Ｓ50/05/14", " 1975/5/14 "])
def test_era_and_western_forms_are_saved_as_yyyymmdd(client, tmp_path, value) -> None:
    page = _post(client, birth_date=value)
    assert 'role="alert"' not in page
    file = next((tmp_path / "output").rglob("*.dcm"))
    assert dcmread(file).PatientBirthDate == "19750514"


@pytest.mark.parametrize(
    ("value", "message"),
    [("1975-05-14", FORMAT), ("19750514", FORMAT), ("H31/05/01", HEISEI_AFTER_END), ("R99/01/01", FUTURE)],
)
def test_unreadable_birth_date_is_refused_with_the_same_message(client, tmp_path, value, message) -> None:
    page = _post(client, birth_date=value)
    assert 'role="alert"' in page
    assert message in page
    # 誤りは生年月日の欄の下に結ぶ（スクリプトが error_field を読む）
    assert 'data-error-field="birth_date"' in page
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_fields_above_the_birth_date_are_reported_first(client) -> None:
    """誤りは上の欄から順に 1 件。患者ID と生年月日の両方が誤りなら、患者ID を返す."""
    page = _post(client, patient_id="患者01", birth_date="S50.5.14")
    assert PATIENT_ID_MESSAGE in page
    assert FORMAT not in page


def test_empty_birth_date_is_still_allowed(client, tmp_path) -> None:
    page = _post(client, birth_date="  ")
    assert 'role="alert"' not in page
    file = next((tmp_path / "output").rglob("*.dcm"))
    assert dcmread(file).PatientBirthDate == ""
