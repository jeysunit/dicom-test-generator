"""FastAPI のアプリ（docs/spec/12a_web_screens_and_cli.md 10 章）."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.modality.config import ModalityConfig
from app.modality.service import ModalityService

from .auth import basic_auth_ok, csrf_guard, host_header_is_loopback, is_loopback, new_csrf_token
from .rendering import render
from .routes import exam, pacs, settings, worklist
from .settings import WebConfig
from .templating import create_environment

STATIC_DIR = Path(__file__).resolve().parent / "static"
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHORIZED = 401
CONTENT_SECURITY_POLICY = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    )
)
SECURITY_HEADERS = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
}
BASIC_CHALLENGE = 'Basic realm="dicom-test-generator", charset="UTF-8"'


def create_app(
    config: ModalityConfig,
    *,
    config_path: Path,
    web: WebConfig,
    password: str | None,
    service: ModalityService | None = None,
) -> FastAPI:
    """画面のアプリを作る。`password` があれば HTTP Basic を付ける（10.9）.

    起動のときに保管の確認の待ち受けを立て、止めるときに止める（使う送信先が
    あるときだけ。docs/spec/12 の 8.3.3）。画面のプロセスは「送れた」で自動に求める。
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        listener = app.state.service.start_commitment_listener()
        try:
            yield
        finally:
            if listener is not None:
                listener.shutdown()

    app = FastAPI(
        title="dicom-test-generator",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(csrf_guard)],
        lifespan=lifespan,
    )
    app.state.service = service or ModalityService(config, auto_commitment=True)
    app.state.config_path = config_path
    app.state.web = web
    app.state.csrf_token = new_csrf_token()
    app.state.exam_tokens = exam.ExamTokens()
    app.state.templates = create_environment()
    check_host = is_loopback(web.bind_address)

    @app.middleware("http")
    async def guard(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if check_host and not host_header_is_loopback(request.headers.get("host", "")):
            # 手元で待ち受けるときの DNS rebinding よけ（10.9）
            response: Response = PlainTextResponse("Invalid Host header", HTTP_BAD_REQUEST)
        elif password is not None and not basic_auth_ok(
            request.headers.get("authorization"), password
        ):
            response = PlainTextResponse(
                "Authentication required",
                HTTP_UNAUTHORIZED,
                headers={"WWW-Authenticate": BASIC_CHALLENGE},
            )
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        # 断った理由を、HTMX が差し込める短い HTML で返す（10.3 の知らせ）
        response = render(request, "_notice.html", error=f"{exc.status_code}: {exc.detail}")
        response.status_code = exc.status_code
        return response

    @app.get("/")
    def root() -> RedirectResponse:
        return RedirectResponse("/worklist")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    for module in (worklist, exam, pacs, settings):
        app.include_router(module.router)
    return app
