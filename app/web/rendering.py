"""頁と HTMX の部分を描く（spec/12a_web_screens_and_cli.md 10.3）."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse
from pydantic import ValidationError

from app.core.exceptions import DICOMGeneratorError
from app.core.validation_text import describe_validation_error
from app.modality.service import ModalityService

logger = logging.getLogger(__name__)

PAGES = (
    ("worklist", "/worklist", "ワークリスト"),
    ("exam", "/exam", "撮影"),
    ("pacs", "/pacs", "PACS"),
    ("settings", "/settings", "設定"),
)


def service_of(request: Request) -> ModalityService:
    service: ModalityService = request.app.state.service
    return service


def render(
    request: Request, template: str, page: str | None = None, **context: Any
) -> HTMLResponse:
    """テンプレートを描く。頁（`page` あり）と帯の差し替えには、見出しと帯の値も渡す."""
    env = request.app.state.templates
    values: dict[str, Any] = {
        "csrf_token": request.app.state.csrf_token,
        "config": service_of(request).config,
        "oob_band": False,
        **context,
    }
    if page is not None or values["oob_band"]:
        values.update(band_context(request))
        values["pages"] = PAGES
        values["page"] = page
    return HTMLResponse(env.get_template(template).render(**values))


def render_error(request: Request, exc: DICOMGeneratorError | ValidationError) -> HTMLResponse:
    """操作の失敗を、その操作の結果の場所に出す（10.3 の知らせ）."""
    return render(request, "_notice.html", error=error_text(exc))


def error_text(exc: DICOMGeneratorError | ValidationError) -> str:
    if isinstance(exc, ValidationError):
        # 項目の名前と原因だけ。入っていた値は出さない（spec/12 の 12 章）
        return "入力の値が正しくありません：" + describe_validation_error(exc)
    return str(exc)


def band_context(request: Request) -> dict[str, Any]:
    """自分の帯：自分の AE・ワークリストの相手・既定の送り先・文字コード（10.3・7.1）."""
    service = service_of(request)
    config = service.config
    band: dict[str, Any] = {
        "own_ae": config.ae_title,
        "worklist_ae": config.worklist.ae_title,
        "destination": config.default_destination,
        "worklist_charset": None,
        "image_charset": [],
        "error": "",
    }
    try:
        state = service.last_worklist_state()
        band["image_charset"] = service.image_character_set(state.response_character_set)
        if state.queried_at:
            band["worklist_charset"] = state.response_character_set
    except DICOMGeneratorError as exc:
        logger.warning("Could not read the worklist state for the band: %s", type(exc).__name__)
        band["error"] = str(exc)
    return {"band": band}
