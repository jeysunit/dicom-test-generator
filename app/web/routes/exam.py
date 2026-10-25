"""撮影の画面（docs/spec/12a_web_screens_and_cli.md 10.5・docs/spec/13 の 8）."""

from __future__ import annotations

import secrets
import threading
from collections import deque
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.core.exceptions import ConfigurationError, DICOMGeneratorError
from app.core.models import WorklistItem
from app.core.patient_input import (
    ALPHABETIC_MESSAGE,
    BIRTH_DATE_FUTURE_MESSAGE,
    IDEOGRAPHIC_MESSAGE,
    PATIENT_ID_MESSAGE,
    PHONETIC_CONVERTED_NOTE,
    PHONETIC_MESSAGE,
    REQUIRED_MESSAGES,
    build_emergency_patient,
)
from app.modality.service import ExamRequest, ExamResult, ModalityService, SendResult

from ..display import exam_notices
from ..rendering import error_text, render, service_of, worklist_error_text

router = APIRouter()

CHARSET_CHOICES = ("auto", "utf8", "jis", "jis_kana")
ABNORMAL_CHOICES = (
    ("none", "なし"),
    ("mild", "軽い"),
    ("moderate", "中くらい"),
    ("severe", "強い"),
)
SEX_CHOICES = (("", "空"), ("M", "男"), ("F", "女"), ("O", "その他"))
# 緊急の患者の欄の下に出す誤りの文（スクリプトが入力のたびに確かめる。サーバーも同じ文で断る）
INPUT_MESSAGES = {
    "patient-id": PATIENT_ID_MESSAGE,
    "alphabetic": ALPHABETIC_MESSAGE,
    "ideographic": IDEOGRAPHIC_MESSAGE,
    "birth-date": BIRTH_DATE_FUTURE_MESSAGE,
    "phonetic": PHONETIC_MESSAGE,
}
ACTION_EXAM = "exam"
ACTION_EXAM_SEND = "exam_send"
MODE_EMERGENCY = "emergency"
# 画面から1回で作る量の上限（1つの要求でディスクを埋めない。docs/spec/12a の 10.5）
MAX_SERIES = 99
MAX_IMAGES_PER_SERIES = 1000
FormStr = Annotated[str, Form()]
FormList = Annotated[list[str], Form()]
# ルーチンの選択の「手で入れる」（今のシリーズ数・画像数の欄。ADR-0025）
MANUAL_ROUTINE = "manual"
SERIES_KIND_LABELS = {
    "localizer": "位置決め",
    "axial": "軸位",
    "coronal": "冠状断",
    "sagittal": "矢状断",
    "dose_report": "線量の画面",
    # MR のルーチン（位置決めは CT と同じ "localizer"）
    "acquisition": "撮像",
    "derived": "計算画像",
}
# 受け付け済みの撮影のトークンを覚える数（二重の受付を止める。古いものから忘れる）
TOKEN_MEMORY = 512
DUPLICATE_MESSAGE = (
    "この撮影は受け付け済みです（ボタンが続けて押された可能性があります）。"
    "結果は PACS の画面の送信の履歴で確かめてください"
)


class ExamTokens:
    """撮影の画面が出すトークン。同じトークンの撮影を2回は受けない（二度押しの対策）.

    撮っている間と、撮り終えた後のトークンを断る。失敗した撮影のトークンは戻すので、
    入力を直して同じ画面から押し直せる。撮り終えたら、結果の応答が新しいトークンを渡す。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._done: deque[str] = deque(maxlen=TOKEN_MEMORY)

    @staticmethod
    def issue() -> str:
        return secrets.token_urlsafe(12)

    def begin(self, token: str) -> bool:
        with self._lock:
            if token in self._active or token in self._done:
                return False
            self._active.add(token)
            return True

    def finish(self, token: str, *, accepted: bool) -> None:
        with self._lock:
            self._active.discard(token)
            if accepted:
                self._done.append(token)


def tokens_of(request: Request) -> ExamTokens:
    tokens: ExamTokens = request.app.state.exam_tokens
    return tokens


@router.get("/exam", response_class=HTMLResponse)
def exam_page(request: Request, key: str = "") -> HTMLResponse:
    service = service_of(request)
    item: WorklistItem | None = None
    load_error = ""
    if key:
        try:
            item = service.find_item(key)
        except DICOMGeneratorError as exc:
            load_error = worklist_error_text(exc)
    try:
        templates = service.available_templates()
        profiles, profile_errors = service.available_profiles()
    except DICOMGeneratorError as exc:
        templates, profiles, profile_errors = [service.config.default_template], [], [exc]
    template = service.config.default_template
    profile = service.config.default_profile or ""
    return render(
        request,
        "exam.html",
        page="exam",
        item=item,
        key=key if item else "",
        load_error=load_error,
        notices=exam_notices(item, service.current_station().ae_title) if item else [],
        templates=templates,
        profiles=profiles,
        profile_errors=[str(error) for error in profile_errors],
        selected_template=template,
        selected_profile=profile,
        charset_choices=CHARSET_CHOICES,
        abnormal_choices=ABNORMAL_CHOICES,
        sex_choices=SEX_CHOICES,
        input_messages=INPUT_MESSAGES,
        required_messages=REQUIRED_MESSAGES,
        phonetic_converted_note=PHONETIC_CONVERTED_NOTE,
        blocker=_blocker(service, item, template, profile),
        exam_token=ExamTokens.issue(),
        **_retake_context(service, item),
        **_routine_context(service, item, template),
    )


@router.get("/exam/routine", response_class=HTMLResponse)
def exam_routine(
    request: Request, key: str = "", template: str = "", routine: str = ""
) -> HTMLResponse:
    """ルーチンを選び直したとき・テンプレートを変えたときに、シリーズの欄を描き直す.

    テンプレートを変えたとき（`routine` が無い）は、予約に当て直す。
    """
    service = service_of(request)
    item: WorklistItem | None = None
    if key:
        try:
            item = service.find_item(key)
        except DICOMGeneratorError:
            item = None
    context = _routine_context(
        service, item, template or service.config.default_template, routine or None
    )
    return render(request, "_routine_fields.html", **context)


def _routine_context(
    service: ModalityService,
    item: WorklistItem | None,
    template: str,
    routine_name: str | None = None,
) -> dict[str, object]:
    """ルーチンの選択肢と、選んだルーチン（無ければ予約に当てたルーチン。ADR-0025）.

    そのモダリティのルーチンが無ければ「手で入れる」にする。ルーチンが読めなければ、
    「手で入れる」にしたうえで、読めない理由を出す（黙って手入力に切り替えない）。
    """
    context: dict[str, object] = {
        "routine_choices": [],
        "selected_routine": MANUAL_ROUTINE,
        "routine": None,
        "routine_error": "",
        "manual_routine": MANUAL_ROUTINE,
        "series_kind_labels": SERIES_KIND_LABELS,
        "max_images_per_series": MAX_IMAGES_PER_SERIES,
    }
    try:
        template_modality = service.template_modality(template)
        choices = service.routines((item.modality if item else "") or template_modality)
        if routine_name == MANUAL_ROUTINE or not choices:
            return {**context, "routine_choices": choices}
        selected = next((r for r in choices if r.name == routine_name), None)
        if selected is None:
            selected = service.matched_routine(item, template_modality)
    except DICOMGeneratorError as exc:
        return {**context, "routine_error": "ルーチンを読めません：" + error_text(exc)}
    return {
        **context,
        "routine_choices": choices,
        "selected_routine": selected.name,
        "routine": selected,
    }


def _retake_context(service: ModalityService, item: WorklistItem | None) -> dict[str, object]:
    """撮影済みの予約か、と撮り直しの形（ボタンの出し分け。10.5・ADR-0024）."""
    return {
        "taken": item is not None and service.is_taken(item.key),
        "retake_mode": service.config.retake_mode,
    }


@router.get("/exam/check", response_class=HTMLResponse)
def exam_check(
    request: Request, key: str = "", template: str = "", profile: str = ""
) -> HTMLResponse:
    """テンプレート・装置を選び直したときに、撮れるかを確かめ直す（10.5）."""
    service = service_of(request)
    item: WorklistItem | None = None
    if key:
        try:
            item = service.find_item(key)
        except DICOMGeneratorError as exc:
            return render(
                request,
                "_exam_actions.html",
                blocker=worklist_error_text(exc),
                **_retake_context(service, None),
            )
    blocker = _blocker(service, item, template or service.config.default_template, profile)
    return render(
        request, "_exam_actions.html", blocker=blocker, **_retake_context(service, item)
    )


@router.post("/exam", response_class=HTMLResponse)
def exam_run(
    request: Request,
    mode: FormStr = "scheduled",
    key: FormStr = "",
    template: FormStr = "",
    profile: FormStr = "",
    series: FormStr = "1",
    images: FormStr = "1",
    abnormal_level: FormStr = "none",
    charset: FormStr = "",
    action: FormStr = ACTION_EXAM,
    patient_id: FormStr = "",
    name_alphabetic: FormStr = "",
    name_ideographic: FormStr = "",
    name_phonetic: FormStr = "",
    birth_date: FormStr = "",
    sex: FormStr = "",
    study_description: FormStr = "",
    exam_token: FormStr = "",
    append: FormStr = "",
    # 画面の既定はルーチン（ADR-0025）。欄の無い要求（スクリプトなど）は今のまま手で入れた値
    routine: FormStr = MANUAL_ROUTINE,
    routine_series: FormList = [],  # noqa: B006（FastAPI の Form の既定）
    routine_images: FormList = [],  # noqa: B006
) -> HTMLResponse:
    service = service_of(request)
    tokens = tokens_of(request)
    # トークンの無い要求（スクリプトなど）は、これまでどおり受ける
    if exam_token and not tokens.begin(exam_token):
        return render(request, "_notice.html", error=DUPLICATE_MESSAGE)
    accepted = False
    try:
        emergency_patient = None
        if mode == MODE_EMERGENCY:
            emergency_patient = build_emergency_patient(
                patient_id=patient_id.strip(),
                # 空白を ^ にする置き換えはサーバーの側で必ず行う（スクリプトは補助。10.5）
                patient_name=service.emergency_person_name(
                    name_alphabetic, name_ideographic, name_phonetic
                ),
                birth_date=birth_date.replace("-", "").strip(),
                sex=sex,
                strict=not append,
                character_set=service.image_character_set(None, charset or None),
                test_mode=service.config.patient_input_test_mode,
            )
        exam_request = ExamRequest(
            worklist_key=None if emergency_patient else key,
            emergency_patient=emergency_patient,
            study_description=study_description.strip() if emergency_patient else "",
            template=template or None,
            profile=profile or None,
            **_series_request(routine, routine_series, routine_images, series, images),
            abnormal_level=abnormal_level,
            charset=charset or None,
            # 撮影済みの予約の「追加撮影」（10.5・ADR-0024）。緊急の患者に付いていれば、
            # 黙って普通に撮らずに断る（CLI と同じ文言）
            append=bool(append),
        )
        result = service.exam(exam_request)
        accepted = True
    except (DICOMGeneratorError, ValidationError) as exc:
        # 欄の誤りは、その欄の下にも結ぶ（スクリプトが error_field を読む）
        return render(
            request,
            "_notice.html",
            error=worklist_error_text(exc),
            error_field=getattr(exc, "field", ""),
        )
    finally:
        if exam_token:
            tokens.finish(exam_token, accepted=accepted)
    send_result, send_error = None, ""
    if action == ACTION_EXAM_SEND:
        send_result, send_error = _send(service, result.output_dir)
    next_token = ExamTokens.issue() if exam_token else ""
    return _exam_result(request, result, send_result, send_error, next_token)


@router.post("/exam/send", response_class=HTMLResponse)
def exam_send(request: Request, output_dir: FormStr = "") -> HTMLResponse:
    """撮った後の [送信]・[もう一度送る]。フォルダは出力の根の中だけを受ける（6.5）."""
    send_result, send_error = _send(service_of(request), output_dir)
    if send_result is None:
        return render(request, "_notice.html", error=send_error)
    # 結果の下に [もう一度送る] を出す。送るたびに新しい件になる（docs/spec/12 の 8.2）
    return render(request, "_send_outcome.html", send=send_result, output_dir=output_dir)


def _exam_result(
    request: Request,
    result: ExamResult,
    send: SendResult | None,
    send_error: str,
    next_token: str,
) -> HTMLResponse:
    service = service_of(request)
    return render(
        request,
        "_exam_result.html",
        result=result,
        send=send,
        send_error=send_error,
        next_token=next_token,
        # 予約で撮ったら撮影済みになるので、撮影のボタンを描き直す（10.5・ADR-0024）
        refresh_actions=result.worklist_key is not None,
        blocker="",
        taken=result.worklist_key is not None and service.is_taken(result.worklist_key),
        retake_mode=service.config.retake_mode,
    )


def _send(service: ModalityService, output_dir: str) -> tuple[SendResult | None, str]:
    try:
        return service.send_exam_output(output_dir), ""
    except DICOMGeneratorError as exc:
        return None, error_text(exc)


def _blocker(
    service: ModalityService, item: WorklistItem | None, template: str, profile: str
) -> str:
    """撮れない理由（モダリティの違い・読めない値・装置の違い）。撮れるなら空."""
    try:
        template_modality = service.template_modality(template)
        if item is not None:
            if item.unreadable_attributes:
                return "読めない値があるため撮れません：" + ", ".join(item.unreadable_attributes)
            if item.modality and item.modality != template_modality:
                return f"予約は {item.modality}、テンプレートは {template_modality} です"
        service.check_profile_modality(profile or None, template_modality)
    except DICOMGeneratorError as exc:
        return str(exc)
    return ""


def _series_request(
    routine: str,
    routine_series: list[str],
    routine_images: list[str],
    series: str,
    images: str,
) -> dict[str, object]:
    """撮るシリーズの指定を ExamRequest の値にする（ルーチンか、手で入れた値）."""
    if routine == MANUAL_ROUTINE:
        return {"images_per_series": _parse_images(images, series)}
    try:
        keep = [int(value) for value in routine_series]
        counts = [int(value) for value in routine_images]
    except ValueError as exc:
        raise ConfigurationError("画像数は整数で入れてください") from exc
    # 行の欄が無い要求（スクリプトの routine=auto など）は、ルーチンの全部を標準の数で撮る。
    # 画面は最後の1行を外せない
    return {"routine": routine, "routine_series": keep or None, "routine_images": counts or None}


def _parse_images(images: str, series: str) -> list[int]:
    """CLI の `-s`・`-i` と同じ決まり（数はシリーズ数と同じ・1以上）."""
    try:
        count = int(series)
        values = [int(value.strip()) for value in images.split(",")]
    except ValueError as exc:
        raise ConfigurationError(
            "シリーズ数と画像数は整数で入れてください（画像数はカンマ区切り）",
            {"series": series, "images": images},
        ) from exc
    if not 1 <= count <= MAX_SERIES:
        raise ConfigurationError(f"シリーズ数は 1〜{MAX_SERIES} にしてください", {"series": series})
    if any(not 1 <= value <= MAX_IMAGES_PER_SERIES for value in values):
        raise ConfigurationError(
            f"画像数は 1〜{MAX_IMAGES_PER_SERIES} にしてください", {"images": images}
        )
    if len(values) != count:
        raise ConfigurationError(
            "画像数の項目の数をシリーズ数と同じにしてください", {"series": count, "images": images}
        )
    return values
