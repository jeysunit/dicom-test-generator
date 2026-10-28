"""身元不明の患者：欄の順と必須、仮の ID、氏名が分からない（docs/spec/12a の 10.5）."""

from __future__ import annotations

import html as html_lib
import re
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from pydicom import dcmread
from web_helpers import BASE_URL, csrf_token, modality_config, post_headers

from app.core.patient_input import REQUIRED_MESSAGES, validate_patient_id
from app.modality.config import ModalityConfig
from app.web.app import create_app
from app.web.settings import WebConfig

TEMPORARY_ID = re.compile(r"TMP[0-9]{14}(-[0-9]+)?")


def _post(client, **fields: str) -> str:
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "TMP20261026083000",
        "sex": "O",
        "template": "ct_generic",
        "series": "1",
        "images": "1",
        "action": "exam",
        **fields,
    }
    response = client.post("/exam", data=form, headers=post_headers(token))
    return html_lib.unescape(response.text)


def _client_with(tmp_path, worklist_scp, storage_scp, **settings) -> TestClient:
    data = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_dump()
    data.update(settings)
    app = create_app(
        ModalityConfig.model_validate(data),
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(),
        password=None,
    )
    return TestClient(app, base_url=BASE_URL)


def _patient_name(tmp_path) -> str:
    return str(dcmread(next((tmp_path / "output").rglob("*.dcm"))).PatientName)


def test_fields_are_in_the_order_id_ideographic_phonetic_alphabetic_birth_sex(client) -> None:
    page = client.get("/exam").text
    order = [
        page.index(f'name="{name}"')
        for name in (
            "patient_id",
            "name_ideographic",
            "name_phonetic",
            "name_alphabetic",
            "birth_date",
            "sex",
        )
    ]
    assert order == sorted(order)


def test_screen_offers_temporary_id_and_unknown_name(client) -> None:
    page = client.get("/exam").text
    assert "data-temporary-id" in page
    assert "仮の ID を作る" in page
    assert "氏名が分からない" in page
    assert 'data-ideographic="不明^不明"' in page
    assert 'data-phonetic="フメイ^フメイ"' in page
    assert "TMP と日時の番号" in page


@pytest.mark.parametrize(
    ("fields", "message", "field"),
    [
        ({"patient_id": ""}, REQUIRED_MESSAGES["patient_id"], "patient_id"),
        ({"name_ideographic": ""}, REQUIRED_MESSAGES["name_ideographic"], "name_ideographic"),
        (
            {"name_ideographic": "", "name_alphabetic": "KINKYU TARO"},
            REQUIRED_MESSAGES["name_ideographic"],
            "name_ideographic",
        ),
        ({"name_ideographic": "山田 太郎", "sex": ""}, REQUIRED_MESSAGES["sex"], "sex"),
    ],
)
def test_required_fields_are_refused_with_the_field_name(client, tmp_path, fields, message, field) -> None:
    page = _post(client, **fields)
    assert message in page
    assert f'data-error-field="{field}"' in page
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_the_first_missing_field_in_screen_order_is_reported(client) -> None:
    page = _post(client, patient_id="", name_ideographic="", sex="")
    assert 'data-error-field="patient_id"' in page


@pytest.mark.parametrize("charset", ["utf8", "jis", "jis_kana"])
def test_ideographic_only_name_has_an_empty_alphabetic_group(client, tmp_path, charset) -> None:
    page = _post(client, name_ideographic="山田 太郎", charset=charset)
    assert 'role="alert"' not in page
    assert _patient_name(tmp_path) == "=山田^太郎"


def test_ideographic_and_phonetic_without_alphabetic(client, tmp_path) -> None:
    page = _post(client, name_ideographic="山田 太郎", name_phonetic="やまだ たろう")
    assert 'role="alert"' not in page
    assert _patient_name(tmp_path) == "=山田^太郎=ヤマダ^タロウ"


def test_alphabetic_name_is_still_accepted_when_typed(client, tmp_path) -> None:
    _post(client, name_ideographic="山田 太郎", name_alphabetic="YAMADA TARO")
    assert _patient_name(tmp_path) == "YAMADA^TARO=山田^太郎"


def test_unknown_name_uses_the_configured_values_and_drops_typed_ones(client, tmp_path) -> None:
    page = _post(
        client,
        name_unknown="1",
        name_ideographic="",
        name_alphabetic="IGNORED NAME",
        name_phonetic="むし",
    )
    assert 'role="alert"' not in page
    assert _patient_name(tmp_path) == "=不明^不明=フメイ^フメイ"


def test_unknown_name_still_needs_the_other_required_fields(client, tmp_path) -> None:
    page = _post(client, name_unknown="1", sex="")
    assert 'data-error-field="sex"' in page
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_unknown_name_and_temporary_id_follow_the_settings(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client_with(
        tmp_path,
        worklist_scp,
        storage_scp,
        temporary_patient_id_prefix="ER",
        unknown_name_ideographic="身元不明",
        unknown_name_phonetic="ミモトフメイ",
    )
    page = client.get("/exam").text
    assert 'data-ideographic="身元不明"' in page
    assert 'data-phonetic="ミモトフメイ"' in page
    assert "ER と日時の番号" in page
    token = csrf_token(client, "/exam")
    created = client.post("/exam/temporary-id", headers=post_headers(token)).json()["patient_id"]
    assert re.fullmatch(r"ER[0-9]{14}(-[0-9]+)?", created)
    _post(client, name_unknown="1", patient_id=created)
    assert _patient_name(tmp_path) == "=身元不明=ミモトフメイ"


@pytest.mark.parametrize(
    "settings",
    [
        {"temporary_patient_id_prefix": ""},
        {"temporary_patient_id_prefix": "T M"},
        {"temporary_patient_id_prefix": "T^P"},
        {"temporary_patient_id_prefix": "A" * 21},
        {"unknown_name_ideographic": ""},
        {"unknown_name_ideographic": "A=B"},
        {"unknown_name_phonetic": "ふめい"},
        {"unknown_name_phonetic": ""},
    ],
)
def test_bad_unknown_settings_are_refused_by_the_config(tmp_path, worklist_scp, storage_scp, settings) -> None:
    data = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_dump()
    data.update(settings)
    with pytest.raises(Exception, match="仮の患者ID|氏名|漢字|かな"):
        ModalityConfig.model_validate(data)


@pytest.mark.parametrize(
    ("settings", "accepted"),
    [
        ({"character_set": "jis"}, False),
        ({"character_set": "jis_kana"}, False),
        ({"character_set": "auto", "character_set_fallback": "jis"}, False),
        ({"character_set": "utf8"}, True),
        ({"character_set": "auto", "character_set_fallback": "utf8"}, True),
    ],
)
def test_unknown_name_must_fit_the_configured_image_charset(
    tmp_path, worklist_scp, storage_scp, settings, accepted
) -> None:
    """「氏名が分からない」の漢字は、設定の画像の文字コードで表せる字に限る（10.5）."""
    data = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_dump()
    data.update(settings, unknown_name_ideographic="髙橋^不明")
    if accepted:
        ModalityConfig.model_validate(data)
    else:
        with pytest.raises(Exception, match="unknown_name_ideographic.*文字コード"):
            ModalityConfig.model_validate(data)


def test_temporary_id_has_prefix_and_time_and_passes_the_id_rules(client) -> None:
    token = csrf_token(client, "/exam")
    response = client.post("/exam/temporary-id", headers=post_headers(token))
    assert response.status_code == 200
    created = response.json()["patient_id"]
    assert TEMPORARY_ID.fullmatch(created)
    validate_patient_id(created)


def test_temporary_id_is_refused_without_the_csrf_token(client) -> None:
    csrf_token(client, "/exam")
    response = client.post("/exam/temporary-id", headers={"Origin": BASE_URL})
    assert response.status_code == 403


def test_temporary_id_does_not_repeat_within_the_same_second(client, monkeypatch) -> None:
    frozen = datetime(2030, 1, 2, 3, 4, 5, 678901)
    monkeypatch.setattr("app.modality.service.current_datetime", lambda timezone="": frozen)
    token = csrf_token(client, "/exam")
    created = [
        client.post("/exam/temporary-id", headers=post_headers(token)).json()["patient_id"]
        for _ in range(3)
    ]
    assert created == ["TMP20300102030405", "TMP20300102030405-2", "TMP20300102030405-3"]
    for value in created:
        validate_patient_id(value)


def test_temporary_id_does_not_repeat_when_the_clock_goes_back(client, monkeypatch) -> None:
    """時計が戻って同じ秒を通り直しても、渡した ID とは重ならない（ADR-0029）."""
    seconds = iter([datetime(2030, 1, 2, 3, 4, 6), datetime(2030, 1, 2, 3, 4, 5)] * 2)
    monkeypatch.setattr("app.modality.service.current_datetime", lambda timezone="": next(seconds))
    token = csrf_token(client, "/exam")
    created = [
        client.post("/exam/temporary-id", headers=post_headers(token)).json()["patient_id"]
        for _ in range(4)
    ]
    assert created == [
        "TMP20300102030406",
        "TMP20300102030405",
        "TMP20300102030406-2",
        "TMP20300102030405-2",
    ]


def test_temporary_id_is_made_in_the_configured_timezone(tmp_path, worklist_scp, storage_scp, monkeypatch) -> None:
    from datetime import timezone as tz

    instant = datetime(2030, 1, 1, 20, 0, tzinfo=tz.utc)

    class _Clock(datetime):
        @classmethod
        def now(cls, zone=None):
            return instant.astimezone(zone) if zone else instant

    monkeypatch.setattr("app.core.patient_input.datetime", _Clock)
    client = _client_with(tmp_path, worklist_scp, storage_scp)
    token = csrf_token(client, "/exam")
    created = client.post("/exam/temporary-id", headers=post_headers(token)).json()["patient_id"]
    assert created == "TMP20300102050000"


def test_temporary_id_goes_into_the_image_unchanged(client, tmp_path) -> None:
    """仮の ID の患者を撮った後に、RIS が同じ ID で照合できるよう、ID は画像にそのまま入る."""
    token = csrf_token(client, "/exam")
    created = client.post("/exam/temporary-id", headers=post_headers(token)).json()["patient_id"]
    _post(client, patient_id=created, name_unknown="1")
    image = dcmread(next((tmp_path / "output").rglob("*.dcm")))
    assert image.PatientID == created
    assert str(image.PatientName) == "=不明^不明=フメイ^フメイ"
