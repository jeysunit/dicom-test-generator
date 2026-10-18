"""撮影の画面（spec/12_modality_emulator.md 10.5・spec/13 の 8）."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.core.exceptions import ConfigurationError, DICOMGeneratorError
from app.core.models import ScheduledPatient, WorklistItem
from app.modality.service import ExamRequest, ExamResult, ModalityService, SendResult

from ..display import exam_notices
from ..rendering import error_text, render, render_error, service_of

router = APIRouter()

CHARSET_CHOICES = ("auto", "utf8", "jis", "jis_kana")
ABNORMAL_CHOICES = (
    ("none", "なし"),
    ("mild", "軽い"),
    ("moderate", "中くらい"),
    ("severe", "強い"),
)
SEX_CHOICES = (("", "空"), ("M", "男"), ("F", "女"), ("O", "その他"))
ACTION_EXAM = "exam"
ACTION_EXAM_SEND = "exam_send"
MODE_EMERGENCY = "emergency"
# 画面から1回で作る量の上限（1つの要求でディスクを埋めない。spec/12 の 10.5）
MAX_SERIES = 99
MAX_IMAGES_PER_SERIES = 1000
FormStr = Annotated[str, Form()]


@router.get("/exam", response_class=HTMLResponse)
def exam_page(request: Request, key: str = "") -> HTMLResponse:
    service = service_of(request)
    item: WorklistItem | None = None
    load_error = ""
    if key:
        try:
            item = service.find_item(key)
        except DICOMGeneratorError as exc:
            load_error = str(exc)
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
        notices=exam_notices(item, service.config.ae_title) if item else [],
        templates=templates,
        profiles=profiles,
        profile_errors=[str(error) for error in profile_errors],
        selected_template=template,
        selected_profile=profile,
        charset_choices=CHARSET_CHOICES,
        abnormal_choices=ABNORMAL_CHOICES,
        sex_choices=SEX_CHOICES,
        blocker=_blocker(service, item, template, profile),
    )


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
            return render(request, "_exam_actions.html", blocker=str(exc))
    blocker = _blocker(service, item, template or service.config.default_template, profile)
    return render(request, "_exam_actions.html", blocker=blocker)


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
) -> HTMLResponse:
    service = service_of(request)
    try:
        emergency_patient = None
        if mode == MODE_EMERGENCY:
            emergency_patient = ScheduledPatient(
                patient_id=patient_id.strip(),
                # 空白を ^ にする置き換えはサーバーの側で必ず行う（スクリプトは補助。10.5）
                patient_name=service.emergency_person_name(
                    name_alphabetic, name_ideographic, name_phonetic
                ),
                birth_date=birth_date.replace("-", "").strip(),
                sex=sex,
            )
        exam_request = ExamRequest(
            worklist_key=None if emergency_patient else key,
            emergency_patient=emergency_patient,
            study_description=study_description.strip() if emergency_patient else "",
            template=template or None,
            profile=profile or None,
            images_per_series=_parse_images(images, series),
            abnormal_level=abnormal_level,
            charset=charset or None,
        )
        result = service.exam(exam_request)
    except (DICOMGeneratorError, ValidationError) as exc:
        return render_error(request, exc)
    send_result, send_error = None, ""
    if action == ACTION_EXAM_SEND:
        send_result, send_error = _send(service, result.output_dir)
    return _exam_result(request, result, send_result, send_error)


@router.post("/exam/send", response_class=HTMLResponse)
def exam_send(request: Request, output_dir: FormStr = "") -> HTMLResponse:
    """撮った後の [送る]。フォルダは出力の根の中だけを受ける（6.5）."""
    send_result, send_error = _send(service_of(request), output_dir)
    if send_result is None:
        return render(request, "_notice.html", error=send_error)
    return render(request, "_send_result.html", send=send_result)


def _exam_result(
    request: Request, result: ExamResult, send: SendResult | None, send_error: str
) -> HTMLResponse:
    return render(request, "_exam_result.html", result=result, send=send, send_error=send_error)


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


def _parse_images(images: str, series: str) -> list[int]:
    """CLI の `-s`・`-i` と同じ決まり（数はシリーズ数と同じ・1以上）."""
    try:
        count = int(series)
        values = [int(value.strip()) for value in images.split(",")]
    except ValueError as exc:
        raise ConfigurationError(
            "シリーズ数と枚数は整数で入れてください（枚数はカンマ区切り）",
            {"series": series, "images": images},
        ) from exc
    if not 1 <= count <= MAX_SERIES:
        raise ConfigurationError(f"シリーズ数は 1〜{MAX_SERIES} にしてください", {"series": series})
    if any(not 1 <= value <= MAX_IMAGES_PER_SERIES for value in values):
        raise ConfigurationError(
            f"枚数は 1〜{MAX_IMAGES_PER_SERIES} にしてください", {"images": images}
        )
    if len(values) != count:
        raise ConfigurationError(
            "枚数の数をシリーズ数と同じにしてください", {"series": count, "images": images}
        )
    return values
