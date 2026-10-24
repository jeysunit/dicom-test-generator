"""PACS の画面（docs/spec/12a_web_screens_and_cli.md 10.6、docs/spec/12_modality_emulator.md 8 章）."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import DICOMGeneratorError
from app.modality.service import SendResult

from ..display import STATUS_LABELS
from ..rendering import error_text, render, service_of

router = APIRouter()

QUEUE_POLL_TRIGGER = "every 2s"


@router.get("/pacs", response_class=HTMLResponse)
def pacs_page(request: Request) -> HTMLResponse:
    service = service_of(request)
    return render(
        request,
        "pacs.html",
        page="pacs",
        destinations=service.config.destinations,
        poll_trigger=QUEUE_POLL_TRIGGER,
        **_queue_context(request),
    )


@router.get("/pacs/queue", response_class=HTMLResponse)
def pacs_queue(request: Request) -> HTMLResponse:
    return render(request, "_queue.html", **_queue_context(request))


@router.post("/pacs/echo/{name}", response_class=HTMLResponse)
def pacs_echo(request: Request, name: str) -> HTMLResponse:
    try:
        result = service_of(request).echo(destination=name)
    except DICOMGeneratorError as exc:
        return render(request, "_echo_result.html", result=None, error=error_text(exc))
    return render(request, "_echo_result.html", result=result, error="")


@router.post("/pacs/retry/{job_id}", response_class=HTMLResponse)
def pacs_retry(request: Request, job_id: int) -> HTMLResponse:
    try:
        results = service_of(request).retry(job_id=job_id)
    except DICOMGeneratorError as exc:
        # 失敗しても表は消さず、表の上の知らせの場所に理由を出す
        return render(request, "_queue.html", **_queue_context(request, error=error_text(exc)))
    notice, failed = _retry_notice(results, job_id)
    return render(request, "_queue.html", **_queue_context(
        request, notice="" if failed else notice, error=notice if failed else ""
    ))


@router.post("/pacs/retry-failed", response_class=HTMLResponse)
def pacs_retry_failed(request: Request) -> HTMLResponse:
    try:
        results = service_of(request).retry(all_failed=True)
    except DICOMGeneratorError as exc:
        return render(request, "_queue.html", **_queue_context(request, error=error_text(exc)))
    notice, failed = _retry_notice(results)
    return render(request, "_queue.html", **_queue_context(
        request, notice="" if failed else notice, error=notice if failed else ""
    ))


def _queue_context(request: Request, notice: str = "", error: str = "") -> dict[str, object]:
    context: dict[str, object] = {"notice": notice, "retry_error": error}
    try:
        jobs = service_of(request).list_queue()
    except DICOMGeneratorError as exc:
        return {**context, "jobs": [], "queue_error": str(exc)}
    return {**context, "jobs": list(reversed(jobs)), "queue_error": ""}


def _retry_notice(results: list[SendResult], job_id: int | None = None) -> tuple[str, bool]:
    if not results:
        return "失敗の件はありません", False
    failed = sum(1 for result in results if result.status == "failed")
    if job_id is not None and len(results) == 1 and results[0].job_id != job_id:
        # 送信完了の件の再送は新しい件になる。どの件になったかを出す（10.6）
        result = results[0]
        return f"ジョブ {result.job_id} として再送しました（{STATUS_LABELS.get(result.status)}）", bool(failed)
    sent = sum(1 for result in results if result.status == "sent")
    if failed:
        return (
            f"{len(results)} 件を再送しましたが、まだ送信できていません"
            f"（送信完了 {sent} 件・送信失敗 {failed} 件）", True
        )
    return f"{len(results)} 件を再送しました（送信完了 {sent} 件）", False
