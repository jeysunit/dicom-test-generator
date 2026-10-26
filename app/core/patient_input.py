"""手で入れた緊急の患者の値の確かめ（docs/spec/12a_web_screens_and_cli.md 10.5）.

画面と CLI の両方が使う Pure な処理。誤りは日本語の文で `FieldValidationError` にする（どの欄
の誤りかを `field` に持つ）。文は入れた値を含めない（docs/spec/12 の 12 章）。規則の原典：

- 氏名（PN）：DICOM PS3.5 6.2。1つの成分グループは 64 字まで、成分は 5 つまで。`=`（群の
  区切り）・`\\`（値の区切り）・制御文字は使えない。英字の群は基本の文字集合（ISO 646）に
  収める
- 患者 ID：PS3.5 6.2 の LO。64 字まで、`\\` と制御文字は使えない。HL7 v2 の PID-3 に
  そのまま入れるため、基本の文字集合の表示できる字に限り、前後の空白も断る
- 生年月日：PS3.5 6.2 の DA（YYYYMMDD）。暦にある日で、今日より後は断る
- 性別：PS3.3 C.7.1.1 の Patient's Sex（M・F・O。空は許す）

漢字の氏名は、画像の文字コードで表せる字だけを受ける。UTF-8 なら制限しない。かなの氏名は
全角カタカナだけを受け、ひらがなはカタカナに直す。半角カナは断る。試験の形（設定の
`patient_input_test_mode`）では、かなの確かめと直しをせず、そのまま通す。
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date, datetime
from zoneinfo import ZoneInfo

from .exceptions import ValidationError
from .models import PATIENT_ID_MAX_LENGTH, ScheduledPatient
from .person_name import COMPONENT_SEPARATOR, GROUP_SEPARATOR
from .text_safety import is_unsafe_char
from .worklist_charset import find_unrepresentable_chars

PN_GROUP_MAX_LENGTH = 64
PN_COMPONENT_MAX_COUNT = 5
LO_MAX_LENGTH = 64
# 生年月日の「今日」を決めるタイムゾーンの既定（サーバーの OS の時計の地域に頼らない。
# UTC のコンテナでも日本の日付で確かめる。docs/spec/12a の 10.5）
DEFAULT_TIMEZONE = "Asia/Tokyo"
SEX_VALUES = ("M", "F", "O")
_ASCII_PRINTABLE_MIN = 0x20
_ASCII_PRINTABLE_MAX = 0x7E
_ALPHABETIC_COMPONENT = re.compile(r"[A-Za-z' -]*")
_DATE = re.compile(r"[0-9]{8}")
# 全角カタカナ（ァ〜ヺ）・中点・長音・繰り返し記号。成分の区切り `^` は群の中で許す
_KATAKANA = re.compile(r"[ァ-ヺ・-ヾ ]*")
_HIRAGANA_TO_KATAKANA_OFFSET = 0x60
_HIRAGANA_RANGES = ((0x3041, 0x3096), (0x309D, 0x309E))
_HL7_V2_DELIMITERS = frozenset("^~&|")
# 半角カナ。jis_kana の ISO 2022 IR 13 は表せるが、この画面の漢字の氏名には半角カナを入れない
# （画面は jis・jis_kana のどちらでも断る。docs/spec/12a の 10.5）
_HALFWIDTH_KANA = re.compile("[｡-ﾟ]")
_UTF8_TERM = "ISO_IR 192"

# 画面のスクリプトも同じ文を出す（入力した時に分かるように。app/web/static/app.js）
ALPHABETIC_MESSAGE = "氏名（英字）は半角の英字・空白・ハイフン・アポストロフィで入力してください。"
IDEOGRAPHIC_MESSAGE = (
    "氏名（漢字）に、この文字コードでは表せない字があります。"
    "文字コードを UTF-8 にするか、表せる字に入れ替えてください。"
)
PHONETIC_MESSAGE = "氏名（かな）は全角のカタカナで入力してください。"
PHONETIC_CONVERTED_NOTE = "ひらがなをカタカナに直しました。"
PATIENT_ID_MESSAGE = "患者ID は半角の英数字と記号で入力してください（\\ ^ ~ & | は使えません）。"
BIRTH_DATE_FUTURE_MESSAGE = "生年月日は今日以前の日付を入力してください。"
REQUIRED_MESSAGES = {
    "patient_id": "患者ID を入力してください。",
    "name_alphabetic": "氏名（英字）を入力してください。",
}
GROUP_LABELS = ("英字", "漢字", "かな")
NAME_FIELDS = ("name_alphabetic", "name_ideographic", "name_phonetic")


class FieldValidationError(ValidationError):
    """欄の誤り。`field` は画面の欄の name（誤りの文をその欄の下に結ぶ）."""

    def __init__(self, message: str, field: str = "") -> None:
        super().__init__(message)
        self.field = field


def validate_emergency_patient(
    patient: ScheduledPatient,
    study_description: str = "",
    character_set: Sequence[str] | None = None,
    *,
    test_mode: bool = False,
    today: date | None = None,
) -> None:
    """緊急の患者の値を確かめる。誤りは `FieldValidationError`（最初の1件）.

    `character_set` は画像の Specific Character Set の値（漢字の氏名が表せるか）。
    `today` は生年月日の上限（設定のタイムゾーンの今日）。
    画面・CLI・サービスの全部がここを通る。
    """
    validate_patient_id(patient.patient_id)
    validate_person_name(patient.patient_name, character_set, test_mode=test_mode)
    validate_birth_date(patient.birth_date, today)
    validate_sex(patient.sex)
    validate_study_description(study_description)


def build_emergency_patient(
    patient_id: str,
    patient_name: str,
    birth_date: str = "",
    sex: str = "",
    *,
    strict: bool = True,
    character_set: Sequence[str] | None = None,
    test_mode: bool = False,
    today: date | None = None,
) -> ScheduledPatient:
    """値を確かめてから `ScheduledPatient` にする。pydantic の英語の文より先に日本語の文で断る.

    かなの氏名のひらがなはカタカナに直してから確かめる。追加撮影（`strict=False`）は
    確かめも直しもしない。前の撮影と患者ID・氏名が一致するかをサービスが確かめるので、
    以前に受け付けた値の患者にも追加撮影できる。
    """
    if strict:
        patient_name = normalize_phonetic_in_name(patient_name, test_mode=test_mode)
        validate_patient_id(patient_id)
        validate_person_name(patient_name, character_set, test_mode=test_mode)
        validate_birth_date(birth_date, today)
        validate_sex(sex)
    return ScheduledPatient(
        patient_id=patient_id, patient_name=patient_name, birth_date=birth_date, sex=sex
    )


def validate_patient_id(value: str) -> None:
    """患者 ID：1〜64 字、表示できる ASCII、`\\` と HL7 v2 の区切り無し、前後の空白無し."""
    field = "patient_id"
    if not value.strip():
        raise FieldValidationError(REQUIRED_MESSAGES[field], field)
    if len(value) > PATIENT_ID_MAX_LENGTH:
        raise FieldValidationError(
            f"患者ID は {PATIENT_ID_MAX_LENGTH} 字以内で入力してください。", field
        )
    if value != value.strip():
        raise FieldValidationError("患者ID の前後の空白を消してください。", field)
    if (
        any(not _ASCII_PRINTABLE_MIN <= ord(char) <= _ASCII_PRINTABLE_MAX for char in value)
        or "\\" in value
        or any(char in _HL7_V2_DELIMITERS for char in value)
    ):
        raise FieldValidationError(PATIENT_ID_MESSAGE, field)


def validate_person_name(
    value: str, character_set: Sequence[str] | None = None, *, test_mode: bool = False
) -> None:
    """氏名（PN）：群ごとの確かめ。英字の群は必須."""
    groups = value.split(GROUP_SEPARATOR)
    if len(groups) > len(GROUP_LABELS):
        raise FieldValidationError("氏名の群は、英字・漢字・かなの3つまでです。", NAME_FIELDS[0])
    if not groups[0].strip():
        raise FieldValidationError(REQUIRED_MESSAGES["name_alphabetic"], NAME_FIELDS[0])
    for label, field, group in zip(GROUP_LABELS, NAME_FIELDS, groups, strict=False):
        group_error = check_name_group(label, group, character_set, test_mode=test_mode)
        if group_error:
            raise FieldValidationError(group_error, field)


def check_name_group(
    label: str,
    group: str,
    character_set: Sequence[str] | None = None,
    *,
    test_mode: bool = False,
) -> str:
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
        return check_ideographic_group(group, character_set)
    return check_phonetic_group(group, test_mode=test_mode)


def check_alphabetic_group(group: str) -> str:
    """英字の氏名：半角の英字・空白・ハイフン・アポストロフィだけ（`^` は成分の区切り）."""
    if all(_ALPHABETIC_COMPONENT.fullmatch(part) for part in group.split(COMPONENT_SEPARATOR)):
        return ""
    return ALPHABETIC_MESSAGE


def check_ideographic_group(group: str, character_set: Sequence[str] | None = None) -> str:
    """漢字の氏名：画像の文字コードで表せる字だけ。`character_set` が無ければ UTF-8 として制限しない."""
    if character_set is None or list(character_set) == [_UTF8_TERM]:
        return ""
    if _HALFWIDTH_KANA.search(group) or find_unrepresentable_chars(group, character_set):
        return IDEOGRAPHIC_MESSAGE
    return ""


def check_phonetic_group(group: str, *, test_mode: bool = False) -> str:
    """かなの氏名：全角カタカナ（長音・中点・`^` 区切りを含む）だけ。半角カナは断る.

    ひらがなは `normalize_phonetic_in_name` がカタカナに直してから確かめる。試験の形では
    何も見ずに通す。
    """
    if test_mode:
        return ""
    if all(_KATAKANA.fullmatch(part) for part in group.split(COMPONENT_SEPARATOR)):
        return ""
    return PHONETIC_MESSAGE


def to_katakana(text: str) -> str:
    """ひらがな（ゝゞを含む）を全角カタカナにする。ほかの字は変えない."""
    return "".join(
        chr(ord(char) + _HIRAGANA_TO_KATAKANA_OFFSET)
        if any(low <= ord(char) <= high for low, high in _HIRAGANA_RANGES)
        else char
        for char in text
    )


def normalize_phonetic_in_name(patient_name: str, *, test_mode: bool = False) -> str:
    """PN のかなの群のひらがなをカタカナに直す。試験の形では直さない."""
    if test_mode:
        return patient_name
    groups = patient_name.split(GROUP_SEPARATOR)
    if len(groups) > len(GROUP_LABELS):
        return patient_name
    if len(groups) == len(GROUP_LABELS):
        groups[2] = to_katakana(groups[2])
    return GROUP_SEPARATOR.join(groups)


def current_datetime(timezone: str = DEFAULT_TIMEZONE) -> datetime:
    """指定したタイムゾーンでの今の日時（DICOM の日付・時刻と同じく、タイムゾーンの情報は持たない）."""
    return datetime.now(ZoneInfo(timezone)).replace(tzinfo=None)


def current_date(timezone: str = DEFAULT_TIMEZONE) -> date:
    """指定したタイムゾーンでの今日."""
    return current_datetime(timezone).date()


def validate_birth_date(value: str, today: date | None = None) -> None:
    """生年月日：空か、暦にある YYYYMMDD で今日以前。`today` が無ければ既定のタイムゾーンの今日."""
    if not value:
        return
    parsed = None
    if _DATE.fullmatch(value):
        try:
            parsed = datetime.strptime(value, "%Y%m%d").date()
        except ValueError:
            parsed = None
    if parsed is None:
        raise FieldValidationError("生年月日は、暦にある日付を入力してください。", "birth_date")
    if parsed > (today or current_date()):
        raise FieldValidationError(BIRTH_DATE_FUTURE_MESSAGE, "birth_date")


def validate_sex(value: str) -> None:
    if value and value not in SEX_VALUES:
        raise FieldValidationError("性別は、男・女・その他から選んでください。", "sex")


def validate_study_description(value: str) -> None:
    """検査名（LO）：64 字まで、制御文字と `\\` は使えない."""
    field = "study_description"
    if len(value) > LO_MAX_LENGTH:
        raise FieldValidationError(f"検査名は {LO_MAX_LENGTH} 字以内で入力してください。", field)
    if any(is_unsafe_char(char) for char in value) or "\\" in value:
        raise FieldValidationError("検査名に使えない字があります。\\ と制御文字を消してください。", field)
