"""設定の画面（spec/12_modality_emulator.md 10.7）。読むだけ."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from ..rendering import render

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
