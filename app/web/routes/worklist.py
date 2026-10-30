"""ワークリストの画面（docs/spec/12a_web_screens_and_cli.md 10.4、docs/spec/12_modality_emulator.md 5 章）."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import DICOMGeneratorError, ModalityError, ValidationError
from app.core.models import WorklistItem
from app.core.patient_input import current_date
from app.modality.service import WorklistState
from app.modality.worklist_scu import WorklistQuery, parse_date_option

from ..display import datetime_label, item_marks
from ..rendering import render, render_error, service_of, worklist_error_text

router = APIRouter()

DAY_CHOICES = (
    ("today", "今日"),
    ("tomorrow", "明日"),
    ("date", "日付を指定"),
    ("any", "絞らない"),
)
STATION_OWN = "own"
STATION_ANY = "any"
ZERO_ITEMS_FACT = "予約はありません。"
ZERO_ITEMS_NEXT = "条件を広げるか、緊急の患者で撮ってください"
ZERO_ITEMS_MESSAGE = ZERO_ITEMS_FACT + ZERO_ITEMS_NEXT
NON_ASCII_HINT = (
    "日本語の条件は相手の文字コードの扱いに左右されます。患者ID か受付番号でも取得してください"
)
PARTIAL_MESSAGE = "途中まで（相手が返し続けたため C-CANCEL を送った）"
NO_SELECTION_MESSAGE = "予約を選んでから「再検索」を押してください"
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
            date_range=_date_range(day, date_value, service.config.timezone),
            modality=modality.strip(),
            station_ae_title=(
                service.current_station().ae_title if station == STATION_OWN else ""
            ),
            patient_id=patient_id.strip(),
            patient_name=patient_name.strip(),
            accession_number=accession.strip(),
        )
    except DICOMGeneratorError as exc:
        # 入力の誤りは、相手に問い合わせていないので、接続の状態を変えない
        return render_error(request, exc)
    link = request.app.state.link_status
    try:
        result = service.query_worklist(query)
    except ModalityError as exc:
        link.record_worklist(False)
        # 上の帯の接続の状態も、同じ応答で差し替える
        return render_error(request, exc, oob_band=True)
    except DICOMGeneratorError as exc:
        return render_error(request, exc)
    link.record_worklist(True)
    try:
        state = service.last_worklist_state()
    except DICOMGeneratorError as exc:
        return render_error(request, exc, oob_band=True)
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
    key = key.strip()
    if not key:
        # 行を選ばずに届いた要求は、問い合わせずに知らせる（10.4）
        error = NO_SELECTION_MESSAGE
    else:
        try:
            service.refresh_item(key)
        except DICOMGeneratorError as exc:
            # 再検索できなくても一覧は消さず、上に理由を出す（10.3 の知らせ）
            error = worklist_error_text(exc)
    try:
        state = service.last_worklist_state()
    except DICOMGeneratorError as exc:
        return render_error(request, exc)
    results = _results(
        request, state, state.partial, selected=key, notice="" if error else "再検索しました"
    )
    results["error"] = error
    # 開いている詳細も、再検索した一覧の値に差し替える
    results["detail_item"] = next((item for item in state.items if item.key == key), None)
    results["detail_taken"] = service.is_taken(key) if key else False
    return render(request, "_worklist_results.html", oob_band=True, results=results)


@router.get("/worklist/item/{key}", response_class=HTMLResponse)
def worklist_item(request: Request, key: str) -> HTMLResponse:
    service = service_of(request)
    try:
        item = service.find_item(key)
    except DICOMGeneratorError as exc:
        return render(request, "_notice.html", error=worklist_error_text(exc))
    # 患者バナーは操作の行の真上へ、予約の詳細は一覧の下へ（同じ応答で差し替える。10.4）
    return render(request, "_worklist_pick.html", item=item, item_taken=service.is_taken(key))


def _results(
    request: Request,
    state: WorklistState,
    partial: bool,
    non_ascii: bool = False,
    selected: str = "",
    notice: str = "",
) -> dict[str, object]:
    service = service_of(request)
    own_ae = service.current_station().ae_title
    taken = service.taken_keys()
    rows: list[tuple[WorklistItem, list[str]]] = [
        (item, item_marks(item, own_ae, item.key in taken)) for item in state.items
    ]
    return {
        "queried": bool(state.queried_at),
        "queried_at": datetime_label(state.queried_at),
        "rows": rows,
        "partial_message": PARTIAL_MESSAGE if partial else "",
        "zero_fact": ZERO_ITEMS_FACT,
        "zero_next": ZERO_ITEMS_NEXT,
        "non_ascii_hint": NON_ASCII_HINT if non_ascii and not rows else "",
        "selected": selected,
        # 「再検索」は、選んだ行が一覧にあるときだけ押せる（10.4）
        "has_selection": any(item.key == selected for item, _marks in rows),
        "detail_item": None,
        "detail_taken": False,
        "notice": notice,
        "error": "",
    }


def _date_range(day: str, date_value: str, timezone: str) -> str:
    """「今日」「明日」は検査日と同じ時計（設定のタイムゾーン）で決める."""
    today = current_date(timezone)
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
