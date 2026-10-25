"""緊急の患者の入力の確かめ（docs/spec/12a の 10.5）."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.exceptions import ValidationError
from app.core.models import ScheduledPatient
from app.core.patient_input import (
    ALPHABETIC_MESSAGE,
    BIRTH_DATE_FUTURE_MESSAGE,
    IDEOGRAPHIC_MESSAGE,
    PATIENT_ID_MESSAGE,
    build_emergency_patient,
    check_name_group,
    check_phonetic_group,
    validate_birth_date,
    validate_emergency_patient,
    validate_patient_id,
    validate_person_name,
    validate_sex,
    validate_study_description,
)


@pytest.mark.parametrize("value", ["KINKYU^TARO", "O'BRIEN^MARY-ANN", "SMITH", "Kinkyu Taro"])
def test_alphabetic_group_accepts_letters_space_hyphen_apostrophe(value) -> None:
    assert check_name_group("英字", value) == ""


@pytest.mark.parametrize(
    "value",
    ["山田^太郎", "ＹＡＭＡＤＡ^ＴＡＲＯ", "ﾔﾏﾀﾞ", "TARO1", "A.B", "A_B", "TARO,", "Ünal", "A/B"],
)
def test_alphabetic_group_refuses_other_characters(value) -> None:
    assert check_name_group("英字", value) == ALPHABETIC_MESSAGE


@pytest.mark.parametrize("value", ["山田^太郎", "山田^太郎ABC", "高橋^あ", "ヤマダ", "山田　太郎"])
def test_ideographic_group_accepts_jis_x_0208(value) -> None:
    assert check_name_group("漢字", value) == ""


@pytest.mark.parametrize("value", ["髙橋^太郎", "ﾔﾏﾀﾞ", "山田😀", "𠮷田"])
def test_ideographic_group_refuses_unrepresentable_characters(value) -> None:
    message = check_name_group("漢字", value)
    assert message == IDEOGRAPHIC_MESSAGE
    # 誤りの文に、入れた字を出さない
    assert not any(char in message for char in "髙橋太郎😀𠮷")


def test_phonetic_group_is_not_restricted_yet() -> None:
    """ひらがな・カタカナ・半角カナのどれを許すかは未決。今は種類を見ない."""
    for value in ("やまだ^たろう", "ヤマダ^タロウ", "ﾔﾏﾀﾞ^ﾀﾛｳ", "Yamada"):
        assert check_phonetic_group(value) == ""
        assert check_name_group("かな", value) == ""


def test_phonetic_group_still_gets_common_checks() -> None:
    assert check_name_group("かな", "あ" * 65)
    assert check_name_group("かな", "あ\\い")
    assert check_name_group("かな", "あ\x1bい")


def test_group_limits() -> None:
    assert check_name_group("英字", "A" * 64) == ""
    assert "64 字以内" in check_name_group("英字", "A" * 65)
    assert "5 つ" in check_name_group("英字", "A^B^C^D^E^F")
    assert check_name_group("英字", "A^B^C^D^E") == ""
    assert check_name_group("英字", "A\\B")
    assert check_name_group("英字", "A\x00B")


def test_person_name_needs_alphabetic_group_and_at_most_three_groups() -> None:
    validate_person_name("KINKYU^TARO=緊急^太郎=きんきゅう^たろう")
    validate_person_name("KINKYU^TARO==きんきゅう^たろう")
    with pytest.raises(ValidationError, match="氏名（英字）を入力"):
        validate_person_name("=緊急^太郎")
    with pytest.raises(ValidationError, match="3つまで"):
        validate_person_name("A=B=C=D")
    with pytest.raises(ValidationError, match="氏名（英字）は半角"):
        validate_person_name("緊急^太郎")
    with pytest.raises(ValidationError, match="氏名（漢字）"):
        validate_person_name("KINKYU=髙橋")


@pytest.mark.parametrize("value", ["E0001", "P000101", "ID-1.2_3/4", "A" * 16])
def test_patient_id_accepts(value) -> None:
    validate_patient_id(value)


@pytest.mark.parametrize(
    "value",
    ["", "  ", " E1", "E1 ", "患者01", "ＥＯＯ１", "E\\1", "E^1", "E~1", "E&1", "E|1", "E\x001", "A" * 17],
)
def test_patient_id_refuses(value) -> None:
    with pytest.raises(ValidationError) as caught:
        validate_patient_id(value)
    # 入れた値を誤りの文に出さない
    assert value.strip() == "" or value.strip() not in caught.value.message


def test_patient_id_message_for_characters() -> None:
    with pytest.raises(ValidationError) as caught:
        validate_patient_id("患者01")
    assert caught.value.message == PATIENT_ID_MESSAGE


def test_birth_date() -> None:
    today = date(2026, 10, 25)
    validate_birth_date("", today)
    validate_birth_date("19750510", today)
    validate_birth_date("20261025", today)
    validate_birth_date("20240229", today)
    for value in ("20230229", "19751301", "19750532", "00000000", "1975-05-10", "197505", "１９７５０５１０"):
        with pytest.raises(ValidationError, match="暦にある日付"):
            validate_birth_date(value, today)
    with pytest.raises(ValidationError) as caught:
        validate_birth_date("20261026", today)
    assert caught.value.message == BIRTH_DATE_FUTURE_MESSAGE


def test_sex_and_study_description() -> None:
    for value in ("", "M", "F", "O"):
        validate_sex(value)
    for value in ("X", "m", "男"):
        with pytest.raises(ValidationError, match="性別"):
            validate_sex(value)
    validate_study_description("胸部 単純" + "あ" * 55)
    with pytest.raises(ValidationError, match="64 字以内"):
        validate_study_description("あ" * 65)
    with pytest.raises(ValidationError, match="使えない字"):
        validate_study_description("a\\b")
    with pytest.raises(ValidationError, match="使えない字"):
        validate_study_description("a\x1bb")


def test_build_emergency_patient_refuses_before_pydantic() -> None:
    """pydantic の英語の文より先に、日本語の文で断る."""
    patient = build_emergency_patient("E0001", "KINKYU^TARO=緊急^太郎", "19750510", "M")
    assert isinstance(patient, ScheduledPatient)
    for kwargs in (
        {"patient_id": "E0001", "patient_name": "緊急^太郎"},
        {"patient_id": "", "patient_name": "A"},
        {"patient_id": "E0001", "patient_name": "A", "birth_date": "2100-01-01"},
        {"patient_id": "E0001", "patient_name": "A", "sex": "X"},
    ):
        with pytest.raises(ValidationError):
            build_emergency_patient(**kwargs)


def test_validate_emergency_patient_checks_a_patient_made_directly() -> None:
    """画面・CLI を通らずに作った ScheduledPatient も、サービスの手前の確かめで断る."""
    good = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    validate_emergency_patient(good, "胸部")
    bad = ScheduledPatient(patient_id="E0001", patient_name="山田^太郎")
    with pytest.raises(ValidationError, match="氏名（英字）は半角"):
        validate_emergency_patient(bad)
