"""送信一覧と接続先の画面（docs/spec/12a_web_screens_and_cli.md 10.6、docs/spec/12_modality_emulator.md 8 章）."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from app.core.exceptions import DICOMGeneratorError
from app.modality.queue import QueueJob
from app.modality.service import SendResult

from ..display import STATUS_LABELS
from ..link_status import Probe, check_summary, echo_reason
from ..rendering import error_text, render, service_of

logger = logging.getLogger(__name__)
router = APIRouter()

QUEUE_POLL_TRIGGER = "every 2s"
HTTP_NO_CONTENT = 204
HTTP_PERMANENT_REDIRECT = 308
# 接続先の表の行を選ぶ値（接続先の詳細。送信先は名称、ワークリストの相手は固定の値）
DEST_KEY_PREFIX = "dest:"
WORKLIST_KEY = "worklist"
# 接続先の詳細の「今日の送信」：新しい 5 件と、状態ごとの件数に並べる状態の順
TODAY_ROWS = 5
TODAY_STATUS_ORDER = ("sending", "sent", "failed", "pending")
# すべての相手への接続確認は、同時に 1 つだけ（重ねて押されても C-ECHO を重ねて送らない）
CHECK_ALL_LOCK = threading.Lock()

# 検索の帯の「期間」。値は画面と要求の取り決め。部品集の送受信の一覧の 4 つ（初期は今日）
PERIOD_TODAY = "today"
PERIOD_CUSTOM = "custom"
PERIOD_CHOICES = (
    (PERIOD_TODAY, "今日"),
    ("yesterday", "昨日"),
    ("week", "過去7日"),
    (PERIOD_CUSTOM, "期間を指定"),
)
WEEK_BACK_DAYS = 6
# 状態の要約に並べる状態（送信待ちは画面から作った件には残らないので並べない。10.6）
SUMMARY_STATUSES = ("sending", "sent", "failed")
# 一覧は 1 ページ 50 件。条件に合う件が 1,000 件を超えたら、新しい 1,000 件だけを出す（部品集の送受信の一覧）
PAGE_SIZE = 50
LIST_LIMIT = 1000


@dataclass(frozen=True)
class QueueFilter:
    """送信ジョブの一覧の条件。画面の検索の帯・状態の要約・選んだ行から来る."""

    period: str = PERIOD_TODAY
    # 「期間を指定」のときの開始日・終了日（YYYY-MM-DD。空は片側を決めない）
    date_from: str = ""
    date_to: str = ""
    destination: str = ""
    patient_id: str = ""
    status: str = "all"
    selected: int | None = None
    page: int = 1


def _iso_day(value: str) -> str:
    """`YYYY-MM-DD` の日付なら、その形にして返す。読めなければ空."""
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return ""


def _make_filter(
    period: str,
    date_from: str,
    date_to: str,
    destination: str,
    patient_id: str,
    status: str,
    selected: str,
    page: str,
) -> QueueFilter:
    """知らない値は初期値に戻す（要求を書き換えられても、一覧が壊れないように）."""
    return QueueFilter(
        period=period if period in dict(PERIOD_CHOICES) else PERIOD_TODAY,
        date_from=_iso_day(date_from),
        date_to=_iso_day(date_to),
        destination=destination.strip(),
        patient_id=patient_id.strip(),
        status=status if status in SUMMARY_STATUSES else "all",
        selected=int(selected) if selected.isascii() and selected.isdigit() else None,
        page=int(page) if page.isascii() and page.isdigit() and int(page) > 0 else 1,
    )


def filter_from_query(
    period: Annotated[str, Query()] = PERIOD_TODAY,
    date_from: Annotated[str, Query()] = "",
    date_to: Annotated[str, Query()] = "",
    destination: Annotated[str, Query()] = "",
    patient_id: Annotated[str, Query()] = "",
    status: Annotated[str, Query()] = "all",
    selected: Annotated[str, Query()] = "",
    page: Annotated[str, Query()] = "1",
) -> QueueFilter:
    return _make_filter(period, date_from, date_to, destination, patient_id, status, selected, page)


def filter_from_form(
    period: Annotated[str, Form()] = PERIOD_TODAY,
    date_from: Annotated[str, Form()] = "",
    date_to: Annotated[str, Form()] = "",
    destination: Annotated[str, Form()] = "",
    patient_id: Annotated[str, Form()] = "",
    status: Annotated[str, Form()] = "all",
    selected: Annotated[str, Form()] = "",
    page: Annotated[str, Form()] = "1",
) -> QueueFilter:
    return _make_filter(period, date_from, date_to, destination, patient_id, status, selected, page)


FromQuery = Annotated[QueueFilter, Depends(filter_from_query)]
FromForm = Annotated[QueueFilter, Depends(filter_from_form)]


@router.get("/pacs")
def pacs_page() -> RedirectResponse:
    """前の「PACS」の画面の道。接続先と送信一覧に分けたので、接続先へ移す."""
    return RedirectResponse("/connections", status_code=HTTP_PERMANENT_REDIRECT)


@router.get("/sent", response_class=HTMLResponse)
def sent_page(request: Request, aet: Annotated[str, Query()] = "") -> HTMLResponse:
    """送信一覧。`aet` は接続先の詳細の「送信一覧で全部見る」から来る相手の AEタイトル."""
    filters = QueueFilter(destination=_destination_of_aet(request, aet))
    # 状態の要約と再送信の件数は、画面を開くときは画面の側に置く（再読み込みでは同梱して差し替える）
    context = {**_queue_context(request, filters), "first_render": True}
    return render(
        request,
        "sent.html",
        page="sent",
        destinations=service_of(request).config.destinations,
        period_choices=PERIOD_CHOICES,
        poll_trigger=QUEUE_POLL_TRIGGER,
        **context,
    )


def _destination_of_aet(request: Request, aet: str) -> str:
    """AEタイトルで結んだ送信先の名称。登録に無い値は絞らない（空）."""
    wanted = aet.strip()
    for destination in service_of(request).config.destinations:
        if wanted and destination.ae_title == wanted:
            return destination.name
    return ""


@router.get("/connections", response_class=HTMLResponse)
def connections_page(request: Request, peer: Annotated[str, Query()] = "") -> HTMLResponse:
    return render(
        request,
        "connections.html",
        page="connections",
        **_conn_context(request, peer),
    )


@router.get("/connections/region", response_class=HTMLResponse)
def connections_region(request: Request, peer: Annotated[str, Query()] = "") -> HTMLResponse:
    """接続先の表の行を選んだとき：表と、選んだ相手の詳細を差し替える."""
    return render(request, "_conn_table.html", **_conn_context(request, peer))


@router.get("/pacs/queue", response_class=HTMLResponse)
def pacs_queue(request: Request, filters: FromQuery) -> HTMLResponse:
    return render(request, "_queue.html", **_queue_context(request, filters))


@dataclass(frozen=True)
class EchoNotice:
    """接続確認を押した直後に区画の上に出す通知（何が起きたか・なぜか・次にすること）."""

    ok: bool
    text: str


def _probe(request: Request, name: str | None) -> EchoNotice:
    """1 つの相手（name が None ならワークリストの取得先）に C-ECHO を送り、最後の結果を覚える."""
    link = request.app.state.link_status
    service = service_of(request)
    node = service.config.worklist if name is None else None
    try:
        if node is None:
            node = service.config.destination(name)
        result = service.echo(worklist=True) if name is None else service.echo(destination=name)
    except DICOMGeneratorError as exc:
        reason, next_step = echo_reason(str(exc))
        # 英語の原文は画面に出さず、記録に残す（10.6）
        logger.warning("C-ECHO failed: peer=%s reason=%s", name or "worklist", exc)
        if name is None:
            link.record_worklist(False, reason)
        else:
            link.record_destination(name, False, reason)
        where = f"{name or 'ワークリストの取得先'}（{node.host}:{node.port}）" if node else str(name)
        return EchoNotice(False, f"{where}に接続できませんでした。{reason}。{next_step}")
    if name is None:
        link.record_worklist(True)
    else:
        link.record_destination(name, True)
    label = name or "ワークリストの取得先"
    return EchoNotice(True, f"{label}（{node.host}:{node.port}）に接続できました（{result.elapsed_ms} ms）。")


@router.post("/pacs/echo/{name}", response_class=HTMLResponse)
def pacs_echo(
    request: Request, name: str, selected: Annotated[str, Form()] = ""
) -> HTMLResponse:
    notice = _probe(request, name)
    probe = request.app.state.link_status.destinations.get(name)
    return _echo_response(request, notice, probe, selected, _peer_key(name))


@router.post("/pacs/echo-worklist", response_class=HTMLResponse)
def pacs_echo_worklist(
    request: Request, selected: Annotated[str, Form()] = ""
) -> HTMLResponse:
    notice = _probe(request, None)
    probe = request.app.state.link_status.worklist
    return _echo_response(request, notice, probe, selected, WORKLIST_KEY)


def _echo_response(
    request: Request, notice: EchoNotice, probe: Probe | None, selected: str, key: str
) -> HTMLResponse:
    """押した行の結果の列と、上の帯の接続の状態を差し替える。詳細がその相手なら、詳細の接続確認も同じ応答で替える."""
    context: dict[str, Any] = {}
    if selected == key:
        context = {**_conn_context(request, selected), "detail_oob": True}
    return render(
        request, "_echo_result.html", oob_band=True, probe=probe, notice=notice, **context
    )


@router.post("/pacs/check-all", response_class=HTMLResponse)
def pacs_check_all(request: Request, selected: Annotated[str, Form()] = "") -> Response:
    """接続先の区画の「すべて接続確認」：区画を結果で差し替え、前の通知は消す.

    上の帯の「接続確認」（/link/check）と同じ錠を取る。確認している最中にもう一度届いたら、
    重ねて送らず 204 で何も差し替えない。
    """
    if not CHECK_ALL_LOCK.acquire(blocking=False):
        return Response(status_code=HTTP_NO_CONTENT)
    try:
        _check_all(request)
    finally:
        CHECK_ALL_LOCK.release()
    return render(
        request, "_check_all_result.html", oob_band=True, **_conn_context(request, selected)
    )


def _check_all(request: Request) -> list[EchoNotice]:
    notices = [_probe(request, None)]
    for destination in service_of(request).config.destinations:
        notices.append(_probe(request, destination.name))
    return notices


def _peer_key(name: str) -> str:
    """接続先の表の行を選ぶ値。送信先は `dest:` を付けた名称、ワークリストの相手は `worklist`."""
    return f"{DEST_KEY_PREFIX}{name}"


def _conn_context(request: Request, selected: str = "") -> dict[str, Any]:
    """接続先の表の行（送信先 → ワークリストの相手の順）と、選んだ相手の詳細の値.

    選んだ相手が無い・知らない値のときは、先頭の行を選ぶ。
    """
    link = request.app.state.link_status
    config = service_of(request).config
    peers: list[dict[str, Any]] = [
        {
            "key": _peer_key(destination.name),
            "name": destination.name,
            "kind": "destination",
            "node": destination,
            "probe": link.destinations.get(destination.name),
            "cell_id": f"echo-{index}",
            "echo_url": f"/pacs/echo/{quote(destination.name, safe='')}",
        }
        for index, destination in enumerate(config.destinations, start=1)
    ]
    peers.append(
        {
            "key": WORKLIST_KEY,
            "name": "ワークリスト",
            "kind": "worklist",
            "node": config.worklist,
            "probe": link.worklist,
            "cell_id": "echo-worklist",
            "echo_url": "/pacs/echo-worklist",
        }
    )
    chosen = next((peer for peer in peers if peer["key"] == selected), peers[0])
    today = _today_sent(request, chosen["name"]) if chosen["kind"] == "destination" else None
    return {"peers": peers, "chosen": chosen, "today_sent": today}


def _today_sent(request: Request, name: str) -> dict[str, Any]:
    """送信先 1 件の「今日の送信」：今日の件数・状態ごとの件数・新しい 5 件（部品集の接続先の詳細）."""
    try:
        jobs = list(reversed(service_of(request).list_queue()))
    except DICOMGeneratorError as exc:
        return {"error": str(exc), "total": 0, "counts": [], "jobs": []}
    today = date.today().isoformat()
    todays = [job for job in jobs if job.destination == name and job.created_at[:10] == today]
    counts = [
        (STATUS_LABELS[status], sum(1 for job in todays if job.status == status))
        for status in TODAY_STATUS_ORDER
    ]
    return {
        "error": "",
        "total": len(todays),
        "counts": [(label, count) for label, count in counts if count],
        "jobs": todays[:TODAY_ROWS],
    }


@router.post("/link/check", response_class=HTMLResponse)
def link_check(request: Request) -> Response:
    """上の帯の接続の状態の「接続確認」：ワークリストの取得先とすべての送信先に C-ECHO を送る（10.3）.

    確認している最中にもう一度届いたら（別の応答で中身が差し替わり、押せるボタンが戻ったとき）、
    重ねて送らず 204 で何も差し替えない。
    """
    if not CHECK_ALL_LOCK.acquire(blocking=False):
        return Response(status_code=HTTP_NO_CONTENT)
    try:
        notices = _check_all(request)
    finally:
        CHECK_ALL_LOCK.release()
    # 中身（#band）を結果で差し替え、全体の状態バッジも同じ応答で差し替える。
    # 結果の 1 文は、中身の中の読み上げの欄（app.js が差し替えの後に入れる）に渡す
    return render(
        request,
        "_link_check.html",
        oob_band=True,
        check_result=check_summary([notice.ok for notice in notices]),
    )


@router.post("/pacs/retry/{job_id}", response_class=HTMLResponse)
def pacs_retry(request: Request, job_id: int, filters: FromForm) -> HTMLResponse:
    try:
        results = service_of(request).retry(job_id=job_id)
    except DICOMGeneratorError as exc:
        # 失敗しても表は消さず、表の上の通知の場所に理由を出す
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
            "list_page": 1,
            "list_pages": 1,
            "listed": 0,
            "range_first": 0,
            "range_last": 0,
            "limited": False,
        }
    # 条件に合う件が 1,000 件を超えたら、新しい 1,000 件だけを出す（キューの読みは全件。上限は表示の上限）。
    # 状態の件数も、その 1,000 件の中で数える
    narrowed = [job for job in all_jobs if _matches(job, filters)]
    limited = len(narrowed) > LIST_LIMIT
    narrowed = narrowed[:LIST_LIMIT]
    # 状態の件数は、期間・送信先・患者IDで絞った件の中で数える（状態は件数の中から選ぶ）
    jobs = [job for job in narrowed if filters.status == "all" or job.status == filters.status]
    counts = {status: sum(1 for job in narrowed if job.status == status) for status in SUMMARY_STATUSES}
    selected_job = next((job for job in jobs if job.id == filters.selected), None)
    pages = max(1, -(-len(jobs) // PAGE_SIZE))
    page = min(filters.page, pages)
    first = (page - 1) * PAGE_SIZE
    return {
        **context,
        "jobs": jobs[first : first + PAGE_SIZE],
        "queue_error": "",
        # 期間の初期が今日なので、送信ジョブがあるのに 0 件のときは「条件に合う…」と示す
        "any_jobs": bool(all_jobs),
        "total": len(narrowed),
        "counts": counts,
        "list_page": page,
        "list_pages": pages,
        "listed": len(jobs),
        "range_first": first + 1 if jobs else 0,
        "range_last": min(first + PAGE_SIZE, len(jobs)),
        "limited": limited,
        # [失敗をすべて再送信] は条件で絞らず、失敗のすべてに効く（12 の 8.2）
        "failed_total": sum(1 for job in all_jobs if job.status == "failed"),
        "selected_job": selected_job,
    }


def _matches(job: QueueJob, filters: QueueFilter) -> bool:
    if filters.destination and job.destination != filters.destination:
        return False
    if filters.patient_id and filters.patient_id.casefold() not in job.patient_id.casefold():
        return False
    # created_at は「2026-10-25T10:00:00」の形（このマシンの時刻）。日付の部分だけを比べる
    day = job.created_at[:10]
    first, last = _period_days(filters)
    return (not first or day >= first) and (not last or day <= last)


def _period_days(filters: QueueFilter) -> tuple[str, str]:
    """期間の最初の日と最後の日（YYYY-MM-DD。空は決めない）."""
    today = date.today()
    if filters.period == "yesterday":
        yesterday = (today - timedelta(days=1)).isoformat()
        return yesterday, yesterday
    if filters.period == "week":
        return (today - timedelta(days=WEEK_BACK_DAYS)).isoformat(), today.isoformat()
    if filters.period == PERIOD_CUSTOM:
        return filters.date_from, filters.date_to
    return today.isoformat(), today.isoformat()


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
