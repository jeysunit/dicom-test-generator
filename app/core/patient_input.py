"""手で入れた緊急の患者の値の確かめ（docs/spec/12a_web_screens_and_cli.md 10.5）.

画面と CLI の両方が使う Pure な処理。誤りは日本語の文で `ValidationError` にする。文は
入れた値を含めない（docs/spec/12 の 12 章）。規則の原典：

- 氏名（PN）：DICOM PS3.5 6.2。1つの成分グループは 64 字まで、成分は 5 つまで。`=`（群の
  区切り）・`\\`（値の区切り）・制御文字は使えない。英字の群は基本の文字集合（ISO 646）に
  収める
- 患者 ID：PS3.5 6.2 の LO。64 字まで、`\\` と制御文字は使えない。HL7 v2 の PID-3 に
  そのまま入れるため、基本の文字集合の表示できる字に限り、前後の空白も断る
- 生年月日：PS3.5 6.2 の DA（YYYYMMDD）。暦にある日で、今日より後は断る
- 性別：PS3.3 C.7.1.1 の Patient's Sex（M・F・O。空は許す）
"""

from __future__ import annotations

import re
from datetime import date, datetime

from .exceptions import ValidationError
from .models import PATIENT_ID_MAX_LENGTH, ScheduledPatient
from .person_name import COMPONENT_SEPARATOR, GROUP_SEPARATOR
from .text_safety import is_unsafe_char

PN_GROUP_MAX_LENGTH = 64
PN_COMPONENT_MAX_COUNT = 5
LO_MAX_LENGTH = 64
SEX_VALUES = ("M", "F", "O")
_ASCII_PRINTABLE_MIN = 0x20
_ASCII_PRINTABLE_MAX = 0x7E
_ASCII_MAX = 0x7F
_ALPHABETIC_COMPONENT = re.compile(r"[A-Za-z' -]*")
_DATE = re.compile(r"[0-9]{8}")
_HL7_V2_DELIMITERS = frozenset("^~&|")

# 画面のスクリプトも同じ文を出す（入力した時に分かるように。app/web/static/app.js）
ALPHABETIC_MESSAGE = "氏名（英字）は半角の英字・空白・ハイフン・アポストロフィで入力してください。"
IDEOGRAPHIC_MESSAGE = "氏名（漢字）に使えない字があります。日本語の漢字・ひらがな・カタカナで入力し直してください。"
PATIENT_ID_MESSAGE = "患者ID は半角の英数字と記号で入力してください（\\ ^ ~ & | は使えません）。"
BIRTH_DATE_FUTURE_MESSAGE = "生年月日は今日以前の日付を入力してください。"
_JIS_X_0208_ESCAPES = (b"\x1b$B", b"\x1b$@")
GROUP_LABELS = ("英字", "漢字", "かな")


def validate_emergency_patient(patient: ScheduledPatient, study_description: str = "") -> None:
    """緊急の患者の値を確かめる。誤りは `ValidationError`（最初の1件）.

    画面・CLI・サービスの全部がここを通る。
    """
    validate_patient_id(patient.patient_id)
    validate_person_name(patient.patient_name)
    validate_birth_date(patient.birth_date)
    validate_sex(patient.sex)
    validate_study_description(study_description)


def build_emergency_patient(
    patient_id: str, patient_name: str, birth_date: str = "", sex: str = ""
) -> ScheduledPatient:
    """値を確かめてから `ScheduledPatient` にする。pydantic の英語の文より先に日本語の文で断る."""
    validate_patient_id(patient_id)
    validate_person_name(patient_name)
    validate_birth_date(birth_date)
    validate_sex(sex)
    return ScheduledPatient(
        patient_id=patient_id, patient_name=patient_name, birth_date=birth_date, sex=sex
    )


def validate_patient_id(value: str) -> None:
    """患者 ID：1〜16 字（この製品の上限。LO は 64 字）、表示できる ASCII、`\\` 無し、前後の空白無し."""
    if not value.strip():
        raise ValidationError("患者ID を入力してください。")
    if len(value) > PATIENT_ID_MAX_LENGTH:
        raise ValidationError(f"患者ID は {PATIENT_ID_MAX_LENGTH} 字以内で入力してください。")
    if value != value.strip():
        raise ValidationError("患者ID の前後の空白を消してください。")
    if (
        any(not _ASCII_PRINTABLE_MIN <= ord(char) <= _ASCII_PRINTABLE_MAX for char in value)
        or "\\" in value
        or any(char in _HL7_V2_DELIMITERS for char in value)
    ):
        raise ValidationError(PATIENT_ID_MESSAGE)


def validate_person_name(value: str) -> None:
    """氏名（PN）：群ごとの確かめ。英字の群は必須."""
    groups = value.split(GROUP_SEPARATOR)
    if len(groups) > len(GROUP_LABELS):
        raise ValidationError("氏名の群は、英字・漢字・かなの3つまでです。")
    if not groups[0].strip():
        raise ValidationError("氏名（英字）を入力してください。")
    for label, group in zip(GROUP_LABELS, groups, strict=False):
        group_error = check_name_group(label, group)
        if group_error:
            raise ValidationError(group_error)


def check_name_group(label: str, group: str) -> str:
    """氏名の1つの群の誤りの文。誤りが無ければ空.

    `label` は「英字」「漢字」「かな」。群は `^` で成分に区切った後の形。
    """
    if len(group) > PN_GROUP_MAX_LENGTH:
        return f"氏名（{label}）は {PN_GROUP_MAX_LENGTH} 字以内で入力してください。"
    if any(is_unsafe_char(char) for char in group) or "\\" in group:
        return f"氏名（{label}）に使えない字があります。\\ と制御文字を消してください。"
    if len(group.split(COMPONENT_SEPARATOR)) > PN_COMPONENT_MAX_COUNT:
        return f"氏名（{label}）の姓と名の区切りは {PN_COMPONENT_MAX_COUNT} つまでです。空白を減らしてください。"
    if label == GROUP_LABELS[0]:
        return check_alphabetic_group(group)
    if label == GROUP_LABELS[1]:
        return check_ideographic_group(group)
    return check_phonetic_group(group)


def check_alphabetic_group(group: str) -> str:
    """英字の氏名：半角の英字・空白・ハイフン・アポストロフィだけ（`^` は成分の区切り）."""
    if all(_ALPHABETIC_COMPONENT.fullmatch(part) for part in group.split(COMPONENT_SEPARATOR)):
        return ""
    return ALPHABETIC_MESSAGE


def check_ideographic_group(group: str) -> str:
    """漢字の氏名：JIS X 0208 で表せる字（と ASCII）。半角カナや JIS に無い字は断る."""
    return "" if all(_is_ideographic_char(char) for char in group) else IDEOGRAPHIC_MESSAGE


def check_phonetic_group(group: str) -> str:
    """かなの氏名。ひらがな・カタカナ・半角カナのどれを許すかは未決のため、今は文字の種類を見ない.

    決まったら、ここに規則を足す（群の長さと禁止の字は `check_name_group` で確かめ済み）。
    """
    return ""


def validate_birth_date(value: str, today: date | None = None) -> None:
    """生年月日：空か、暦にある YYYYMMDD で今日より前（今日を含む）."""
    if not value:
        return
    parsed = None
    if _DATE.fullmatch(value):
        try:
            parsed = datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            parsed = None
    if parsed is None:
        raise ValidationError("生年月日は、暦にある日付を入力してください。")
    if parsed > (today or date.today()):
        raise ValidationError(BIRTH_DATE_FUTURE_MESSAGE)


def validate_sex(value: str) -> None:
    if value and value not in SEX_VALUES:
        raise ValidationError("性別は、男・女・その他から選んでください。")


def validate_study_description(value: str) -> None:
    """検査名（LO）：64 字まで、制御文字と `\\` は使えない."""
    if len(value) > LO_MAX_LENGTH:
        raise ValidationError(f"検査名は {LO_MAX_LENGTH} 字以内で入力してください。")
    if any(is_unsafe_char(char) for char in value) or "\\" in value:
        raise ValidationError("検査名に使えない字があります。\\ と制御文字を消してください。")


def _is_ideographic_char(char: str) -> bool:
    if ord(char) <= _ASCII_MAX:
        return True
    try:
        encoded = char.encode("iso2022_jp")
    except UnicodeEncodeError:
        return False
    return any(escape in encoded for escape in _JIS_X_0208_ESCAPES)
