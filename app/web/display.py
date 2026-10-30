"""画面に出す値の形（docs/spec/12a_web_screens_and_cli.md 10.3）.

値は文字列のまま返し、エスケープは Jinja2 に任せる（ここで HTML を作らない）。
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.core.models import WorklistItem
from app.core.patient_input import current_date
from app.core.wareki import birth_cell, birth_text

DATE_LENGTH = 8
ISO_DATE_LENGTH = 10
TIME_MIN_LENGTH = 4
PN_GROUPS = 3
SEX_LABELS = {"M": "男", "F": "女", "O": "その他"}
SEX_UNKNOWN_LABEL = "不明"
GENERIC_SEND_ERROR = "送信に失敗しました"
# モダリティの印（`.mod`）の色の名前：ui-kit の tokens.css の `--color-mod-*` の後ろの部分
MODALITY_COLORS = {
    "CT": "ct",
    "MR": "mr",
    "CR": "crdx",
    "DX": "crdx",
    "US": "us",
    "ES": "es",
    "MG": "mg",
    "SR": "sr",
}
STATUS_LABELS = {"pending": "送信待ち", "sending": "送信中", "sent": "送信完了", "failed": "送信失敗"}
# 状態の札の種類（`.st` の `data-k`。枠と印は画面の決まりの状態の札と同じ）
STATUS_KINDS = {"pending": "plan", "sending": "wait", "sent": "ok", "failed": "ng"}
# 保管の確認の状態（10.6・10.8）と、出すときの札の種類（送信ジョブの状態と同じ札を使う）
COMMITMENT_LABELS = {
    "waiting": "確認待ち",
    "confirmed": "確認済",
    "failed": "確認の失敗",
    "timed_out": "確認の時間切れ",
}
COMMITMENT_KINDS = {
    "waiting": "wait",
    "confirmed": "ok",
    "failed": "ng",
    "timed_out": "ng",
}
DEFAULT_CHARSET_LABEL = "初期設定"
# 撮影の画面の「文字コード（画像）」の選択肢の表示名（値は docs/spec/12 の 7.1 の表。10.5）
CHARSET_CHOICE_LABELS = {
    "auto": "自動（予約に合わせる）",
    "utf8": "UTF-8（ISO_IR 192）",
    "jis": "JIS（漢字。ISO 2022 IR 87）",
    "jis_kana": "JIS（半角カナと漢字。ISO 2022 IR 13\\IR 87）",
}
# 画像が ISO 2022 IR 13\ISO 2022 IR 87 になるときに選択の下に出す注意（docs/spec/12 の 14.4）
JIS_KANA_WARNING = (
    "Orthanc 1.13.0 は、この組み合わせの漢字・かなを読み崩します。"
    "Orthanc へ送るときは、UTF-8 か JIS（漢字）を選んでください。"
)
JIS_KANA_CHARACTER_SET = ("ISO 2022 IR 13", "ISO 2022 IR 87")


def auto_is_jis_kana(item: WorklistItem | None, fallback: str) -> bool:
    """「自動」で画像が ISO 2022 IR 13\\ISO 2022 IR 87 になるか（14.4 の崩れる組）."""
    response = tuple(term.strip() for term in item.specific_character_set) if item else ()
    if any(response):
        return response == JIS_KANA_CHARACTER_SET
    return fallback == "jis_kana"


def utc_offset_label() -> str:
    """画面を動かすマシンの時刻の UTC からの差を `UTC+09:00` の形で返す.

    画面に出す取得・受付・完了・検査の時刻は、このマシンの時刻（タイムゾーンの表記が無い）。
    どの時刻かが読めるように、時刻の見出しと取得の時刻に添える（10.4・10.6）。
    """
    offset = datetime.now().astimezone().strftime("%z")
    return f"UTC{offset[:3]}:{offset[3:]}"


def send_error_label(reason: str) -> str:
    """送信失敗の理由を日本語にする。原文は詳細の枠に残す（10.6）."""
    details = dict(re.findall(r"(?:\(|, )(peer|host|port)=([^,()]+)", reason))
    peer = details.get("peer", "")
    address = ":".join(details[key] for key in ("host", "port") if key in details)
    endpoint = "・".join(value for value in (peer, address) if value)
    if reason.startswith("Association failed: could not connect"):
        suffix = f"（{endpoint}）" if endpoint else ""
        return f"接続できませんでした{suffix}。送信先の電源とポートを確かめてください"
    if reason.startswith("Association failed: association rejected by the peer"):
        suffix = f"（{peer}）" if peer else ""
        return f"送信先に断られました{suffix}。AEタイトルの登録を確かめてください"
    if reason == "association lost":
        return "送信の途中で接続が切れました。送信先の接続を確かめてください"
    if reason == "no response (timed out or aborted)":
        return "送信先から応答がありませんでした。送信先の稼働状況を確かめてください"
    status = re.fullmatch(r"status (0x[0-9A-Fa-f]{4})", reason)
    if status:
        return f"送信先が画像を受け付けませんでした（状態 {status[1]}）。送信先の記録を確かめてください"
    if reason.startswith("unreadable file:"):
        return "送信する画像のファイルを読めませんでした。元のファイルを確かめてください"
    mpps = _mpps_error_label(reason)
    if mpps:
        return mpps
    if re.search(r"[ぁ-んァ-ヶ一-龯]", reason):
        # 相手の AEタイトルを受け付けなかった知らせなど、すでに日本語の文
        return reason
    return GENERIC_SEND_ERROR


def _mpps_error_label(reason: str) -> str:
    """MPPS の送信失敗の原文（`app/modality/mpps_scu.py`・`mpps_queue.py`）を日本語にする。当たらなければ空."""
    failed = re.match(r"N-(?:CREATE|SET) failed with status (0x[0-9A-Fa-f]{4})", reason)
    if failed:
        return f"送信先が MPPS を受け付けませんでした（状態 {failed[1]}）。送信先の記録を確かめてください"
    if re.match(r"N-(?:CREATE|SET) timed out or the association was aborted", reason):
        return "MPPS の送信先から応答がありませんでした。届いていたかもしれません。送信先の稼働状況を確かめてください"
    if re.match(r"N-(?:CREATE|SET) could not be sent:", reason):
        return "MPPS を送れませんでした。送信先が MPPS に対応しているか確かめてください"
    if reason.startswith("N-CREATE has not been sent yet"):
        return "先に送る MPPS（N-CREATE）がまだ送れていません。再送信してください"
    if reason.startswith("being sent by another process"):
        return "別のプロセスが MPPS を送信中です。少し待って、再送信の結果を確かめてください"
    return ""


def mpps_error_label(reason: str) -> str:
    """MPPS の注意に出す理由。どの形にも当たらないときは、次にすることを示す."""
    label = send_error_label(reason)
    if label == GENERIC_SEND_ERROR:
        return f"{GENERIC_SEND_ERROR}。python -m app.cli mpps list で記録を確かめてください"
    return label


def name_parts(patient_name: str) -> tuple[str, str, str]:
    """PN を（英字・漢字・かな）に分け、成分の `^` を空白にする."""
    groups = (patient_name.split("=") + [""] * PN_GROUPS)[:PN_GROUPS]
    alphabetic, ideographic, phonetic = (
        " ".join(part for part in group.split("^") if part) for group in groups
    )
    return alphabetic, ideographic, phonetic


def name_display(person_name: str) -> str:
    """PN を、一覧の氏名と同じ順（漢字・かな・英字）に ` / ` で区切って出す。空なら空の文字列."""
    alphabetic, ideographic, phonetic = name_parts(person_name)
    return " / ".join(part for part in (ideographic, phonetic, alphabetic) if part)


def date_label(value: str) -> str:
    """`YYYYMMDD` を `YYYY/MM/DD` にする。形が違えばそのまま."""
    if len(value) == DATE_LENGTH and value.isdigit():
        return f"{value[:4]}/{value[4:6]}/{value[6:]}"
    return value


def sex_label(value: str) -> str:
    """性別を 男・女・その他・不明 にする（DICOM の値 M・F・O 以外は、空も不明）."""
    return SEX_LABELS.get(value, SEX_UNKNOWN_LABEL)


def modality_key(modality: str) -> str:
    """モダリティの印（`.mod`）の色の名前：`ct`・`crdx` など。表に無いモダリティは `doc`.

    CSP が style 属性を許さないので、色は `data-m` の値で選ぶ（app.css の `.mod[data-m=…]`）。
    """
    return MODALITY_COLORS.get(modality.upper(), "doc")


def birth_label(item: WorklistItem, today: date | None = None) -> str:
    """患者バナー・詳細の生年月日と性別を `1980/01/15（昭55・45歳）男` の形にする."""
    sex = sex_label(item.sex)
    if not item.birth_date:
        return f"生年月日なし（{sex}）"
    day, inside = birth_text(item.birth_date, age_day(item, today))
    return f"{day}{inside}{sex}" if inside else f"{day} {sex}".rstrip()


def age_day(item: WorklistItem, today: date | None = None) -> date:
    """年齢を数える日：予約の予定日（検査日）。読めない・無いときは今日（`today`、無ければ設定の今日）."""
    try:
        return datetime.strptime(item.scheduled_start_date, "%Y%m%d").date()
    except (TypeError, ValueError):
        return today or current_date()


def birth_parts(item: WorklistItem, today: date | None = None) -> tuple[str, str]:
    """`birth_label` を 西暦 と 括弧から後ろ に分ける（後ろは `.unit` で包んで折れ方を決める）.

    括弧が無い値（生年月日なし・元号も年齢も出せない値）は後ろが空で、全文が前に入る。
    """
    label = birth_label(item, today)
    if not item.birth_date:
        return label, ""
    day, inside = birth_text(item.birth_date, age_day(item, today))
    return (day, label[len(day) :]) if inside else (label, "")


def birth_cell_label(item: WorklistItem, today: date | None = None) -> str:
    """一覧の表の生年月日の列を `1980/01/15 (S55・45歳)` の形にする（性別は別の行に出す）."""
    if not item.birth_date:
        return "生年月日なし"
    return birth_cell(item.birth_date, age_day(item, today))


def auto_charset_note(item: WorklistItem | None, fallback: str) -> str:
    """「自動」が何になるか（10.5）。予約なしと、文字コードの無い予約は設定の fallback."""
    response = [term.strip() for term in item.specific_character_set] if item else []
    if item is not None and any(response):
        return f"自動は予約の文字コード（{charset_label(response)}）に合わせます。"
    target = CHARSET_CHOICE_LABELS.get(fallback, fallback)
    if item is None:
        return f"予約なしの撮影では、自動は {target}になります。"
    return f"予約に文字コードが無いため、自動は {target}になります。"


def patient_label(patient_name: str, patient_id: str) -> str:
    """知らせに入れる患者：`緊急 太郎（E0002）`。氏名は漢字、無ければ英字・かな."""
    alphabetic, ideographic, phonetic = name_parts(patient_name)
    name = ideographic or alphabetic or phonetic or "氏名なし"
    return f"{name}（{patient_id}）" if patient_id else name


def datetime_label(value: str) -> str:
    """記録の時刻（`2026-10-25T10:00:00`）を `2026/10/25 10:00` にする（画面の日時は yyyy/MM/dd HH:mm）.

    時刻の無い値（`2026-10-25`）は日付だけ（`2026/10/25`）にする。読めない値と空の値は、そのまま返す。
    """
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return value
    if len(value) <= ISO_DATE_LENGTH:
        return parsed.strftime("%Y/%m/%d")
    return parsed.strftime("%Y/%m/%d %H:%M")


def time_label(value: str) -> str:
    return f"{value[:2]}:{value[2:4]}" if len(value) >= TIME_MIN_LENGTH else value


def charset_label(character_set: list[str]) -> str:
    return "\\".join(character_set) if any(character_set) else DEFAULT_CHARSET_LABEL


def item_marks(item: WorklistItem, own_ae_title: str, taken: bool = False) -> list[str]:
    """一覧の行の印（10.4・16.1）。CLI の `worklist query` と同じ4つ."""
    marks = []
    if taken:
        marks.append("撮影済み")  # 撮影を終えた予約（docs/spec/12 の 6.3・ADR-0024）
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
        notices.append("予約に Study Instance UID が無いため、このツールが生成します")
    if not item.birth_date:
        notices.append("生年月日が空です")
    if not item.sex:
        notices.append("性別が空です")
    if "漢字・かなが空" in item_marks(item, own_ae_title):
        notices.append("氏名の漢字・かなが空です")
    return notices
