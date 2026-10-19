"""ワークリストの画面（spec/12a_web_screens_and_cli.md 10.4、spec/12_modality_emulator.md 5 章）."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import DICOMGeneratorError, ValidationError
from app.core.models import WorklistItem
from app.modality.service import WorklistState
from app.modality.worklist_scu import WorklistQuery, parse_date_option

from ..display import item_marks
from ..rendering import error_text, render, render_error, service_of

router = APIRouter()

DAY_CHOICES = (
    ("today", "今日"),
    ("tomorrow", "明日"),
    ("date", "日付を指定"),
    ("any", "絞らない"),
)
STATION_OWN = "own"
STATION_ANY = "any"
ZERO_ITEMS_MESSAGE = "予約はありません。条件を広げるか、緊急の患者で撮ってください"
NON_ASCII_HINT = (
    "日本語の条件は相手の文字コードの扱いに左右されます。患者 ID か受付番号でも取得してください"
)
PARTIAL_MESSAGE = "途中まで（相手が返し続けたため C-CANCEL を送った）"
FormStr = Annotated[str, Form()]


@router.get("/worklist", response_class=HTMLResponse)
def worklist_page(request: Request) -> HTMLResponse:
    service = service_of(request)
    try:
        state = service.last_worklist_state()
        default_modality = service.template_modality(service.config.default_template)
    except DICOMGeneratorError as exc:
        return render(
            request,
            "worklist.html",
            page="worklist",
            load_error=str(exc),
            results=None,
            day_choices=DAY_CHOICES,
            default_modality="",
        )
    return render(
        request,
        "worklist.html",
        page="worklist",
        load_error="",
        results=_results(request, state, state.partial),
        day_choices=DAY_CHOICES,
        default_modality=default_modality,
    )


@router.post("/worklist/query", response_class=HTMLResponse)
def worklist_query(
    request: Request,
    day: FormStr = "today",
    date_value: Annotated[str, Form(alias="date")] = "",
    modality: FormStr = "",
    station: FormStr = STATION_OWN,
    patient_id: FormStr = "",
    patient_name: FormStr = "",
    accession: FormStr = "",
) -> HTMLResponse:
    service = service_of(request)
    try:
        query = WorklistQuery(
            date_range=_date_range(day, date_value),
            modality=modality.strip(),
            station_ae_title=service.config.ae_title if station == STATION_OWN else "",
            patient_id=patient_id.strip(),
            patient_name=patient_name.strip(),
            accession_number=accession.strip(),
        )
        result = service.query_worklist(query)
        state = service.last_worklist_state()
    except DICOMGeneratorError as exc:
        return render_error(request, exc)
    return render(
        request,
        "_worklist_results.html",
        oob_band=True,
        results=_results(request, state, result.partial, non_ascii=result.query_non_ascii),
    )


@router.post("/worklist/refresh", response_class=HTMLResponse)
def worklist_refresh(request: Request, key: FormStr = "") -> HTMLResponse:
    service = service_of(request)
    error = ""
    try:
        service.refresh_item(key)
    except DICOMGeneratorError as exc:
        # 取得し直せなくても一覧は消さず、上に理由を出す（10.3 の知らせ）
        error = error_text(exc)
    try:
        state = service.last_worklist_state()
    except DICOMGeneratorError as exc:
        return render_error(request, exc)
    results = _results(
        request, state, state.partial, selected=key, notice="" if error else "取得し直しました"
    )
    results["error"] = error
    return render(request, "_worklist_results.html", oob_band=True, results=results)


@router.get("/worklist/item/{key}", response_class=HTMLResponse)
def worklist_item(request: Request, key: str) -> HTMLResponse:
    try:
        item = service_of(request).find_item(key)
    except DICOMGeneratorError as exc:
        return render_error(request, exc)
    return render(request, "_worklist_detail.html", item=item)


def _results(
    request: Request,
    state: WorklistState,
    partial: bool,
    non_ascii: bool = False,
    selected: str = "",
    notice: str = "",
) -> dict[str, object]:
    own_ae = service_of(request).config.ae_title
    rows: list[tuple[WorklistItem, list[str]]] = [
        (item, item_marks(item, own_ae)) for item in state.items
    ]
    return {
        "queried": bool(state.queried_at),
        "queried_at": state.queried_at.replace("T", " "),
        "rows": rows,
        "partial_message": PARTIAL_MESSAGE if partial else "",
        "zero_message": ZERO_ITEMS_MESSAGE,
        "non_ascii_hint": NON_ASCII_HINT if non_ascii and not rows else "",
        "selected": selected,
        "notice": notice,
        "error": "",
    }


def _date_range(day: str, date_value: str) -> str:
    today = date.today()
    if day == "any":
        return ""
    if day == "tomorrow":
        return parse_date_option((today + timedelta(days=1)).strftime("%Y%m%d"), today)
    if day == "date":
        compact = date_value.replace("-", "").strip()
        if not compact:
            raise ValidationError("予定の日：日付を入れてください", {"date": date_value})
        return parse_date_option(compact, today)
    return parse_date_option("today", today)
