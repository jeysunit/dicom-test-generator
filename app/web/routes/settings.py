"""設定の画面（docs/spec/12a_web_screens_and_cli.md 10.7）と、装置の切り替え（10.3）."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse

from app.core.exceptions import DICOMGeneratorError

from ..rendering import band_context, error_text, render, service_of

router = APIRouter()


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request) -> HTMLResponse:
    return render(
        request,
        "settings.html",
        page="settings",
        config_path=str(request.app.state.config_path),
        web=request.app.state.web,
    )


@router.post("/station", response_class=HTMLResponse)
def select_station(request: Request, station: Annotated[str, Form()] = "") -> HTMLResponse:
    """情報バーで装置を切り替える。切り替えたら頁を読み込み直す（ADR-0023）."""
    try:
        service_of(request).select_station(station)
    except DICOMGeneratorError as exc:
        # 切り替えられなければ、帯に理由を出し、選択を元の装置に戻して描く
        context = band_context(request)
        context["band"]["error"] = error_text(exc)
        return render(request, "_band.html", **context)
    response = render(request, "_band.html", **band_context(request))
    response.headers["HX-Refresh"] = "true"
    return response
