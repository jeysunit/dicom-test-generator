"""画面に出す値の形（spec/12_modality_emulator.md 10.3）.

値は文字列のまま返し、エスケープは Jinja2 に任せる（ここで HTML を作らない）。
"""

from __future__ import annotations

from datetime import date

from app.core.models import WorklistItem

DATE_LENGTH = 8
TIME_MIN_LENGTH = 4
PN_GROUPS = 3
SEX_LABELS = {"M": "男", "F": "女", "O": "その他"}
STATUS_LABELS = {"pending": "待ち", "sending": "送信中", "sent": "送れた", "failed": "失敗"}
DEFAULT_CHARSET_LABEL = "既定"


def name_parts(patient_name: str) -> tuple[str, str, str]:
    """PN を（英字・漢字・かな）に分け、成分の `^` を空白にする."""
    groups = (patient_name.split("=") + [""] * PN_GROUPS)[:PN_GROUPS]
    alphabetic, ideographic, phonetic = (
        " ".join(part for part in group.split("^") if part) for group in groups
    )
    return alphabetic, ideographic, phonetic


def date_label(value: str) -> str:
    """`YYYYMMDD` を `YYYY/MM/DD` にする。形が違えばそのまま."""
    if len(value) == DATE_LENGTH and value.isdigit():
        return f"{value[:4]}/{value[4:6]}/{value[6:]}"
    return value


def birth_label(item: WorklistItem, today: date | None = None) -> str:
    """生年月日を `1980/01/15（45歳・男）` の形にする（和暦は出さない）."""
    sex = SEX_LABELS.get(item.sex, item.sex)
    if not item.birth_date:
        return f"生年月日なし（{sex}）" if sex else "生年月日なし"
    parts = []
    age = _age(item.birth_date, today or date.today())
    if age is not None:
        parts.append(f"{age}歳")
    if sex:
        parts.append(sex)
    suffix = f"（{'・'.join(parts)}）" if parts else ""
    return f"{date_label(item.birth_date)}{suffix}"


def time_label(value: str) -> str:
    return f"{value[:2]}:{value[2:4]}" if len(value) >= TIME_MIN_LENGTH else value


def charset_label(character_set: list[str]) -> str:
    return "\\".join(character_set) if any(character_set) else DEFAULT_CHARSET_LABEL


def item_marks(item: WorklistItem, own_ae_title: str) -> list[str]:
    """一覧の行の印（10.4・16.1）。CLI の `worklist query` と同じ3つ."""
    marks = []
    if item.scheduled_station_ae_title and item.scheduled_station_ae_title != own_ae_title:
        marks.append("別の装置")
    if item.unreadable_attributes:
        marks.append("読めない値")
    groups = item.patient_name.split("=")
    if len(groups) < 2 or not any(group for group in groups[1:]):
        marks.append("漢字・かなが空")
    return marks


def exam_notices(item: WorklistItem, own_ae_title: str) -> list[str]:
    """撮影の画面で、撮る前に確かめてほしいこと（10.5・6.3）。撮影は止めない."""
    notices = []
    if item.scheduled_station_ae_title and item.scheduled_station_ae_title != own_ae_title:
        notices.append("この予約は別の装置の予定です")
    if not item.study_instance_uid:
        notices.append("予約に Study Instance UID が無いため、この道具が作ります")
    if not item.birth_date:
        notices.append("生年月日が空です")
    if not item.sex:
        notices.append("性別が空です")
    if "漢字・かなが空" in item_marks(item, own_ae_title):
        notices.append("氏名の漢字・かなが空です")
    return notices


def _age(birth_date: str, today: date) -> int | None:
    try:
        born = date(int(birth_date[:4]), int(birth_date[4:6]), int(birth_date[6:8]))
    except ValueError:
        return None
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))
