"""PACS の画面（docs/spec/12a_web_screens_and_cli.md 10.6、docs/spec/12_modality_emulator.md 8 章）."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import DICOMGeneratorError
from app.modality.service import SendResult

from ..rendering import error_text, render, render_error, service_of

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
        return render_error(request, exc)
    return render(request, "_queue.html", **_queue_context(request, _retry_notice(results)))


@router.post("/pacs/retry-failed", response_class=HTMLResponse)
def pacs_retry_failed(request: Request) -> HTMLResponse:
    try:
        results = service_of(request).retry(all_failed=True)
    except DICOMGeneratorError as exc:
        return render_error(request, exc)
    return render(request, "_queue.html", **_queue_context(request, _retry_notice(results)))


def _queue_context(request: Request, notice: str = "") -> dict[str, object]:
    try:
        jobs = service_of(request).list_queue()
    except DICOMGeneratorError as exc:
        return {"jobs": [], "queue_error": str(exc), "notice": notice}
    return {"jobs": list(reversed(jobs)), "queue_error": "", "notice": notice}


def _retry_notice(results: list[SendResult]) -> str:
    if not results:
        return "失敗の件はありません"
    sent = sum(1 for result in results if result.status == "sent")
    return f"{len(results)} 件を再送しました（送信完了 {sent} 件）"
