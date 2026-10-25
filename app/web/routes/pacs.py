"""PACS の画面（docs/spec/12a_web_screens_and_cli.md 10.6、docs/spec/12_modality_emulator.md 8 章）."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import DICOMGeneratorError
from app.modality.queue import QueueJob
from app.modality.service import SendResult

from ..display import STATUS_LABELS
from ..rendering import error_text, render, service_of

router = APIRouter()

QUEUE_POLL_TRIGGER = "every 2s"

# 検索の帯の「期間」。値は画面と要求の取り決め
PERIOD_CHOICES = (("all", "すべて"), ("today", "今日"), ("week", "1 週間"))
# 状態の要約に並べる状態（送信待ちは画面から作った件には残らないので並べない。10.6）
SUMMARY_STATUSES = ("sending", "sent", "failed")


@dataclass(frozen=True)
class QueueFilter:
    """送信ジョブの一覧の条件。画面の検索の帯・状態の要約・選んだ行から来る."""

    period: str = "all"
    destination: str = ""
    patient_id: str = ""
    status: str = "all"
    selected: int | None = None


def _make_filter(
    period: str, destination: str, patient_id: str, status: str, selected: str
) -> QueueFilter:
    """知らない値は初期値に戻す（要求を書き換えられても、一覧が壊れないように）."""
    return QueueFilter(
        period=period if period in dict(PERIOD_CHOICES) else "all",
        destination=destination.strip(),
        patient_id=patient_id.strip(),
        status=status if status in SUMMARY_STATUSES else "all",
        selected=int(selected) if selected.isascii() and selected.isdigit() else None,
    )


def filter_from_query(
    period: Annotated[str, Query()] = "all",
    destination: Annotated[str, Query()] = "",
    patient_id: Annotated[str, Query()] = "",
    status: Annotated[str, Query()] = "all",
    selected: Annotated[str, Query()] = "",
) -> QueueFilter:
    return _make_filter(period, destination, patient_id, status, selected)


def filter_from_form(
    period: Annotated[str, Form()] = "all",
    destination: Annotated[str, Form()] = "",
    patient_id: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "all",
    selected: Annotated[str, Form()] = "",
) -> QueueFilter:
    return _make_filter(period, destination, patient_id, status, selected)


FromQuery = Annotated[QueueFilter, Depends(filter_from_query)]
FromForm = Annotated[QueueFilter, Depends(filter_from_form)]


@router.get("/pacs", response_class=HTMLResponse)
def pacs_page(request: Request) -> HTMLResponse:
    service = service_of(request)
    # 状態の要約と再送信の件数は、画面を開くときは画面の側に置く（読み直しでは同梱して差し替える）
    context = {**_queue_context(request, QueueFilter()), "first_render": True}
    return render(
        request,
        "pacs.html",
        page="pacs",
        destinations=service.config.destinations,
        link_probes=dict(request.app.state.link_status.destinations),
        period_choices=PERIOD_CHOICES,
        poll_trigger=QUEUE_POLL_TRIGGER,
        **context,
    )


@router.get("/pacs/queue", response_class=HTMLResponse)
def pacs_queue(request: Request, filters: FromQuery) -> HTMLResponse:
    return render(request, "_queue.html", **_queue_context(request, filters))


@router.post("/pacs/echo/{name}", response_class=HTMLResponse)
def pacs_echo(request: Request, name: str) -> HTMLResponse:
    link = request.app.state.link_status
    try:
        result = service_of(request).echo(destination=name)
    except DICOMGeneratorError as exc:
        link.record_destination(name, False)
        # 上の帯の接続の状態も、同じ応答で差し替える（oob_band）
        return render(request, "_echo_result.html", oob_band=True, result=None, error=error_text(exc))
    link.record_destination(name, True)
    return render(request, "_echo_result.html", oob_band=True, result=result, error="")


@router.post("/link/check", response_class=HTMLResponse)
def link_check(request: Request) -> HTMLResponse:
    """上の帯の接続の状態の「接続確認」：ワークリストの取得先とすべての送信先に C-ECHO を送る（10.3）."""
    link = request.app.state.link_status
    service = service_of(request)
    try:
        service.echo(worklist=True)
        link.record_worklist(True)
    except DICOMGeneratorError:
        link.record_worklist(False)
    for destination in service.config.destinations:
        try:
            service.echo(destination=destination.name)
            link.record_destination(destination.name, True)
        except DICOMGeneratorError:
            link.record_destination(destination.name, False)
    # 中身（#band）を結果で差し替え、全体の状態の札も同じ応答で差し替える
    return render(request, "_link_check.html", oob_band=True)


@router.post("/pacs/retry/{job_id}", response_class=HTMLResponse)
def pacs_retry(request: Request, job_id: int, filters: FromForm) -> HTMLResponse:
    try:
        results = service_of(request).retry(job_id=job_id)
    except DICOMGeneratorError as exc:
        # 失敗しても表は消さず、表の上の知らせの場所に理由を出す
        return render(
            request, "_queue.html", **_queue_context(request, filters, error=error_text(exc))
        )
    notice, failed = _retry_notice(results, job_id)
    return render(request, "_queue.html", **_queue_context(
        request, filters, notice="" if failed else notice, error=notice if failed else ""
    ))


@router.post("/pacs/retry-failed", response_class=HTMLResponse)
def pacs_retry_failed(request: Request, filters: FromForm) -> HTMLResponse:
    try:
        results = service_of(request).retry(all_failed=True)
    except DICOMGeneratorError as exc:
        return render(
            request, "_queue.html", **_queue_context(request, filters, error=error_text(exc))
        )
    notice, failed = _retry_notice(results)
    return render(request, "_queue.html", **_queue_context(
        request, filters, notice="" if failed else notice, error=notice if failed else ""
    ))


def _queue_context(
    request: Request, filters: QueueFilter, notice: str = "", error: str = ""
) -> dict[str, object]:
    context: dict[str, object] = {
        "notice": notice,
        "retry_error": error,
        "filters": filters,
        "oob_parts": False,
        "first_render": False,
    }
    try:
        all_jobs = list(reversed(service_of(request).list_queue()))
    except DICOMGeneratorError as exc:
        return {
            **context,
            "jobs": [],
            "queue_error": str(exc),
            "total": 0,
            "counts": {},
            "failed_total": 0,
            "selected_job": None,
        }
    # 状態の件数は、期間・送信先・患者IDで絞った件の中で数える（状態は件数の中から選ぶ）
    narrowed = [job for job in all_jobs if _matches(job, filters)]
    jobs = [job for job in narrowed if filters.status == "all" or job.status == filters.status]
    counts = {status: sum(1 for job in narrowed if job.status == status) for status in SUMMARY_STATUSES}
    selected_job = next((job for job in jobs if job.id == filters.selected), None)
    return {
        **context,
        "jobs": jobs,
        "queue_error": "",
        "total": len(narrowed),
        "counts": counts,
        # [失敗をすべて再送信] は条件で絞らず、失敗のすべてに効く（12 の 8.2）
        "failed_total": sum(1 for job in all_jobs if job.status == "failed"),
        "selected_job": selected_job,
    }


def _matches(job: QueueJob, filters: QueueFilter) -> bool:
    if filters.destination and job.destination != filters.destination:
        return False
    if filters.patient_id and filters.patient_id.casefold() not in job.patient_id.casefold():
        return False
    if filters.period != "all":
        days = 0 if filters.period == "today" else 6
        # created_at は「2026-10-25T10:00:00」の形（この機械の時刻）。日付の部分だけを比べる
        if job.created_at[:10] < (date.today() - timedelta(days=days)).isoformat():
            return False
    return True


def _retry_notice(results: list[SendResult], job_id: int | None = None) -> tuple[str, bool]:
    if not results:
        return "失敗の件はありません", False
    failed = sum(1 for result in results if result.status == "failed")
    if job_id is not None and len(results) == 1 and results[0].job_id != job_id:
        # 送信完了の件の再送信は新しい件になる。どの件になったかを出す（10.6）
        result = results[0]
        return f"ジョブ {result.job_id} として再送信しました（{STATUS_LABELS.get(result.status)}）", bool(failed)
    sent = sum(1 for result in results if result.status == "sent")
    if failed:
        return (
            f"{len(results)} 件を再送信しましたが、まだ送信できていません"
            f"（送信完了 {sent} 件・送信失敗 {failed} 件）", True
        )
    return f"{len(results)} 件を再送信しました（送信完了 {sent} 件）", False
