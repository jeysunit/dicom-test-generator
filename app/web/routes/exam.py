"""撮影の画面（docs/spec/12a_web_screens_and_cli.md 10.5・docs/spec/13 の 8）."""

from __future__ import annotations

import secrets
import threading
from collections import deque
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
    require_screen_fields,
)
from app.core.routine import DEFAULT_DOSE_REPORT_MODE
from app.modality.service import ExamRequest, ExamResult, ModalityService, SendResult

from ..display import (
    CHARSET_CHOICE_LABELS,
    JIS_KANA_WARNING,
    auto_charset_note,
    auto_is_jis_kana,
    exam_notices,
    patient_label,
)
from ..rendering import error_text, render, service_of, worklist_error_text

router = APIRouter()

CHARSET_CHOICES = ("auto", "utf8", "jis", "jis_kana")
ABNORMAL_CHOICES = (
    ("none", "なし"),
    ("mild", "軽い"),
    ("moderate", "中くらい"),
    ("severe", "強い"),
)
DOSE_REPORT_CHOICES = (
    ("screen", "画面（画像）"),
    ("sr", "SR"),
    ("both", "画面（画像）と SR"),
)
SEX_CHOICES = (("", "選んでください"), ("M", "男"), ("F", "女"), ("O", "その他"))
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
    "dose_sr": "線量の報告（SR）",
    # MR のルーチン（位置決めは CT と同じ "localizer"）
    "acquisition": "撮像",
    "derived": "計算画像",
    # PET/CT のルーチンの PT のシリーズ
    "pet_ac": "PET（減弱補正あり）",
    "pet_nac": "PET（補正なし）",
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
    template = service.config.default_template
    profile = service.config.default_profile or ""
    try:
        templates = service.available_templates()
        profiles, profile_errors = service.available_profiles()
        if item is not None and item.modality:
            # 予約のモダリティに合うテンプレートと、それに合う装置を先に選んでおく（ADR-0030）
            template = service.template_for_modality(item.modality)
            profile = service.profile_for_template(profile, template) or ""
    except DICOMGeneratorError as exc:
        templates, profiles, profile_errors = [service.config.default_template], [], [exc]
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
        # 撮る前に「誰を・どこへ」を操作の行の真上に出す（10.5）
        destination=service.config.destination(),
        charset_labels=CHARSET_CHOICE_LABELS,
        jis_kana_warning=JIS_KANA_WARNING,
        auto_charset_note=auto_charset_note(item, service.config.character_set_fallback),
        # 注意を出す選択肢（JIS（半角カナと漢字）と、「自動」でそれになるときの自動）
        jis_kana_choices=(
            "jis_kana auto"
            if auto_is_jis_kana(item, service.config.character_set_fallback)
            else "jis_kana"
        ),
        charset_choices=CHARSET_CHOICES,
        abnormal_choices=ABNORMAL_CHOICES,
        dose_report_choices=DOSE_REPORT_CHOICES,
        sex_choices=SEX_CHOICES,
        input_messages=INPUT_MESSAGES,
        required_messages=REQUIRED_MESSAGES,
        phonetic_converted_note=PHONETIC_CONVERTED_NOTE,
        server_today=service.today().isoformat(),
        unknown_name_ideographic=service.unknown_name()[0],
        unknown_name_phonetic=service.unknown_name()[1],
        blocker=_blocker(service, item, template, profile),
        exam_token=ExamTokens.issue(),
        **_retake_context(service, item),
        **_routine_context(service, item, template),
    )


@router.post("/exam/temporary-id")
def exam_temporary_id(request: Request) -> JSONResponse:
    """「仮の ID を作る」：身元不明の患者の仮の患者ID（頭 + 日時。同じ秒に2回押しても重ならない）."""
    return JSONResponse({"patient_id": service_of(request).new_temporary_patient_id()})


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
    request: Request, key: str = "", template: str = "", profile: str = "", done: str = ""
) -> HTMLResponse:
    """テンプレート・装置を選び直したときに、撮れるかを確かめ直す（10.5）.

    緊急の患者を撮った後（`done`）は、撮った後の操作の行のままにする（前の患者で撮らない）。
    """
    service = service_of(request)
    if done and not key:
        return render(request, "_exam_actions.html", exam_done=True, blocker="", taken=False)
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
    dose_report: FormStr = DEFAULT_DOSE_REPORT_MODE,
    charset: FormStr = "",
    action: FormStr = ACTION_EXAM,
    patient_id: FormStr = "",
    name_alphabetic: FormStr = "",
    name_ideographic: FormStr = "",
    name_phonetic: FormStr = "",
    name_unknown: FormStr = "",
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
            if name_unknown:
                # 氏名が分からない：設定の漢字・かなの氏名にし、英字は空にする（10.5）
                name_alphabetic = ""
                name_ideographic, name_phonetic = service.unknown_name()
            if not append:
                require_screen_fields(patient_id.strip(), name_ideographic, sex)
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
                today=service.today(),
            )
        exam_request = ExamRequest(
            worklist_key=None if emergency_patient else key,
            emergency_patient=emergency_patient,
            study_description=study_description.strip() if emergency_patient else "",
            template=template or None,
            profile=profile or None,
            **_series_request(routine, routine_series, routine_images, series, images),
            abnormal_level=abnormal_level,
            dose_report=dose_report if routine != MANUAL_ROUTINE else DEFAULT_DOSE_REPORT_MODE,
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
    return _exam_result(
        request,
        result,
        send_result,
        send_error,
        next_token,
        patient=(
            patient_label(emergency_patient.patient_name, emergency_patient.patient_id)
            if emergency_patient is not None
            else _scheduled_patient(service, result)
        ),
        emergency=mode == MODE_EMERGENCY,
    )


@router.post("/exam/send", response_class=HTMLResponse)
def exam_send(request: Request, output_dir: FormStr = "") -> HTMLResponse:
    """撮った後の [送信]・[もう一度送る]。フォルダは出力の根の中だけを受ける（6.5）."""
    service = service_of(request)
    send_result, send_error = _send(service, output_dir)
    if send_result is None:
        return render(request, "_notice.html", error=send_error)
    # 結果の下に [もう一度送る] を出す。送るたびに新しい件になる（docs/spec/12 の 8.2）
    return render(
        request,
        "_send_outcome.html",
        send=send_result,
        output_dir=output_dir,
        **_send_context(service, send_result),
    )


def _exam_result(
    request: Request,
    result: ExamResult,
    send: SendResult | None,
    send_error: str,
    next_token: str,
    *,
    patient: str,
    emergency: bool,
) -> HTMLResponse:
    service = service_of(request)
    return render(
        request,
        "_exam_result.html",
        result=result,
        exam_patient=patient,
        send=send,
        send_error=send_error,
        next_token=next_token,
        # 予約で撮ったら撮影済みになるので、撮影のボタンを描き直す（10.5・ADR-0024）。
        # 緊急の患者は、撮った患者のまま次を撮らないように、撮影のボタンを「次の緊急の患者」
        # と「同じ患者でもう一度」に替える（10.5）
        refresh_actions=result.worklist_key is not None or emergency,
        exam_done=emergency,
        blocker="",
        taken=result.worklist_key is not None and service.is_taken(result.worklist_key),
        retake_mode=service.config.retake_mode,
        **(_send_context(service, send) if send else {}),
    )


def _scheduled_patient(service: ModalityService, result: ExamResult) -> str:
    """予約で撮った結果の知らせに入れる患者（氏名と患者ID）."""
    try:
        item = service.find_item(result.worklist_key or "")
    except DICOMGeneratorError:
        return ""
    return patient_label(item.patient_name, item.patient_id)


def _send_context(service: ModalityService, send: SendResult) -> dict[str, object]:
    """送信の結果の知らせに入れる患者と送信先（AEタイトル・ホスト）."""
    # 枚数は送信ジョブの数（つながらなかった送信は、画像ごとの結果を持たない）
    sent = sum(1 for result in send.results if result.sent)
    total = len(send.results)
    try:
        job = service.queue_job(send.job_id)
        patient = patient_label(job.patient_name, job.patient_id)
        sent, total = job.num_sent, job.num_files
    except DICOMGeneratorError:
        patient = ""
    try:
        node = service.config.destination(send.destination)
        address = f"{node.ae_title}・{node.host}:{node.port}"
    except DICOMGeneratorError:
        address = ""
    return {
        "send_patient": patient,
        "send_address": address,
        "send_sent": sent,
        "send_total": total,
    }


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
