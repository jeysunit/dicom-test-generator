"""バージョン情報の画面（docs/spec/12a_web_screens_and_cli.md 10.7a）."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.version import app_version

from ..build_info import build_commit
from ..rendering import render

router = APIRouter()


@router.get("/version", response_class=HTMLResponse)
def version_page(request: Request) -> HTMLResponse:
    return render(request, "version.html", page="version", version=app_version(), build_commit=build_commit())
