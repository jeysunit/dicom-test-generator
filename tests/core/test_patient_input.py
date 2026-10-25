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
    PHONETIC_MESSAGE,
    FieldValidationError,
    build_emergency_patient,
    check_name_group,
    check_phonetic_group,
    normalize_phonetic_in_name,
    to_katakana,
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


UTF8 = ["ISO_IR 192"]
JIS = ["", "ISO 2022 IR 87"]
JIS_KANA = ["ISO 2022 IR 13", "ISO 2022 IR 87"]


@pytest.mark.parametrize("value", ["山田^太郎", "山田^太郎ABC", "高橋^あ", "ヤマダ", "山田　太郎", "すゞき"])
def test_ideographic_group_accepts_jis_x_0208_in_every_character_set(value) -> None:
    for character_set in (UTF8, JIS, JIS_KANA, None):
        assert check_name_group("漢字", value, character_set) == ""


@pytest.mark.parametrize("value", ["髙橋^太郎", "山﨑^太郎", "𠮷田", "山田😀"])
def test_ideographic_group_utf8_accepts_characters_outside_jis(value) -> None:
    """文字コードが UTF-8 なら、JIS X 0208 に無い字も受ける."""
    assert check_name_group("漢字", value, UTF8) == ""
    assert check_name_group("漢字", value) == ""


@pytest.mark.parametrize("value", ["髙橋^太郎", "山﨑^太郎", "𠮷田", "山田😀"])
@pytest.mark.parametrize("character_set", [JIS, JIS_KANA])
def test_ideographic_group_jis_refuses_unrepresentable_characters(value, character_set) -> None:
    message = check_name_group("漢字", value, character_set)
    assert message == IDEOGRAPHIC_MESSAGE
    assert "この文字コードでは表せない字" in message
    # 誤りの文に、入れた字を出さない
    assert not any(char in message for char in "髙橋太郎😀𠮷﨑山")


@pytest.mark.parametrize("value", ["キンキュウ^タロウ", "キンキュウ", "ア ー", "ガッコウ・ヴ", "ゝ".replace("ゝ", "ヽ")])
def test_phonetic_group_accepts_full_width_katakana(value) -> None:
    assert check_phonetic_group(value) == ""
    assert check_name_group("かな", value) == ""


@pytest.mark.parametrize("value", ["ﾔﾏﾀﾞ", "ｷﾝｷｭｳ^ﾀﾛｳ", "きんきゅう", "ヤマダ山", "Yamada", "ヤマダ1", "ｱ"])
def test_phonetic_group_refuses_everything_else(value) -> None:
    assert check_phonetic_group(value) == PHONETIC_MESSAGE
    assert PHONETIC_MESSAGE == "氏名（かな）は全角のカタカナで入力してください。"


def test_phonetic_group_test_mode_passes_anything_through() -> None:
    """試験の形：半角カナ・ひらがな・混ざった値をそのまま通す（長さと禁止の字は見る）."""
    for value in ("ﾔﾏﾀﾞ^ﾀﾛｳ", "やまだ^たろう", "ヤマダ^たろう", "ｱあア", "Yamada"):
        assert check_phonetic_group(value, test_mode=True) == ""
        assert check_name_group("かな", value, test_mode=True) == ""
    assert check_name_group("かな", "あ" * 65, test_mode=True)
    assert check_name_group("かな", "あ\\い", test_mode=True)
    assert check_name_group("かな", "ｱ", test_mode=False) == PHONETIC_MESSAGE


def test_hiragana_becomes_katakana_and_other_characters_stay() -> None:
    assert to_katakana("きんきゅう たろう") == "キンキュウ タロウ"
    assert to_katakana("ゔゝゞ") == "ヴヽヾ"
    assert to_katakana("ﾔﾏﾀﾞ山A") == "ﾔﾏﾀﾞ山A"


def test_name_normalization_converts_only_the_phonetic_group() -> None:
    assert normalize_phonetic_in_name("KINKYU^TARO=緊急^太郎=きんきゅう^たろう") == (
        "KINKYU^TARO=緊急^太郎=キンキュウ^タロウ"
    )
    # かなの群が無い名前や、ひらがなを含む漢字の群は変えない
    assert normalize_phonetic_in_name("KINKYU=たろう") == "KINKYU=たろう"
    # 試験の形は直さない
    assert normalize_phonetic_in_name("A==きん", test_mode=True) == "A==きん"


def test_phonetic_group_still_gets_common_checks() -> None:
    assert check_name_group("かな", "ア" * 65)
    assert check_name_group("かな", "ア\\イ")
    assert check_name_group("かな", "ア\x1bイ")


def test_group_limits() -> None:
    assert check_name_group("英字", "A" * 64) == ""
    assert "64 字以内" in check_name_group("英字", "A" * 65)
    assert "5 つ" in check_name_group("英字", "A^B^C^D^E^F")
    assert check_name_group("英字", "A^B^C^D^E") == ""
    assert check_name_group("英字", "A\\B")
    assert check_name_group("英字", "A\x00B")


def test_person_name_needs_alphabetic_group_and_at_most_three_groups() -> None:
    validate_person_name("KINKYU^TARO=緊急^太郎=キンキュウ^タロウ")
    validate_person_name("KINKYU^TARO==キンキュウ^タロウ")
    with pytest.raises(ValidationError, match="氏名（かな）は全角のカタカナ"):
        validate_person_name("KINKYU^TARO==きんきゅう^たろう")
    with pytest.raises(ValidationError, match="氏名（英字）を入力"):
        validate_person_name("=緊急^太郎")
    with pytest.raises(ValidationError, match="3つまで"):
        validate_person_name("A=B=C=D")
    with pytest.raises(ValidationError, match="氏名（英字）は半角"):
        validate_person_name("緊急^太郎")
    with pytest.raises(ValidationError, match="氏名（漢字）"):
        validate_person_name("KINKYU=髙橋", JIS)
    validate_person_name("KINKYU=髙橋", UTF8)
    validate_person_name("KINKYU==ｷﾝｷｭｳ", test_mode=True)


def test_errors_carry_the_field_name() -> None:
    cases = [
        (lambda: validate_patient_id(""), "patient_id"),
        (lambda: validate_person_name("山田"), "name_alphabetic"),
        (lambda: validate_person_name("A=髙", JIS), "name_ideographic"),
        (lambda: validate_person_name("A==ｱ"), "name_phonetic"),
        (lambda: validate_birth_date("20991231"), "birth_date"),
        (lambda: validate_sex("X"), "sex"),
        (lambda: validate_study_description("あ" * 65), "study_description"),
    ]
    for call, field in cases:
        with pytest.raises(FieldValidationError) as caught:
            call()
        assert caught.value.field == field
        # 欄の名前は誤りの文に出さない（str にも入らない）
        assert field not in str(caught.value)


@pytest.mark.parametrize("value", ["E0001", "P000101", "ID-1.2_3/4", "A" * 16, "A" * 64])
def test_patient_id_accepts(value) -> None:
    validate_patient_id(value)


@pytest.mark.parametrize(
    "value",
    ["", "  ", " E1", "E1 ", "患者01", "ＥＯＯ１", "E\\1", "E^1", "E~1", "E&1", "E|1", "E\x001", "A" * 65],
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
    # かなのひらがなはカタカナに直して作る。試験の形はそのまま
    converted = build_emergency_patient("E0001", "A==きんきゅう")
    assert converted.patient_name == "A==キンキュウ"
    raw = build_emergency_patient("E0001", "A==ｷﾝ^きん", test_mode=True)
    assert raw.patient_name == "A==ｷﾝ^きん"
    # 漢字は画像の文字コードで決まる
    assert build_emergency_patient("E0001", "A=髙橋", character_set=UTF8).patient_name == "A=髙橋"
    for kwargs in (
        {"patient_id": "E0001", "patient_name": "A=髙橋", "character_set": JIS},
        {"patient_id": "E0001", "patient_name": "A==ｷﾝ"},
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
