"""上の帯の「接続の状態」：全体の状態の札と、押すと出る中身（docs/spec/12a の 10.3）."""

from __future__ import annotations

import re

from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers, query_worklist

from app.web.link_status import LinkStatus

_BADGE = re.compile(r'<span id="conn-state" class="st" data-k="(\w+)">([^<]+)</span>')


def _badge(html: str) -> tuple[str, str]:
    found = _BADGE.search(html)
    assert found, "全体の状態の札がない"
    return found.group(1), found.group(2)


def test_closed_state_is_one_badge_in_the_top_band(client) -> None:
    html = client.get("/worklist").text
    header = html[html.index("<header") : html.index("</header>")]

    # 上の帯に、標準の popover を開くボタンと全体の状態の札がある。別の帯（情報バー）は無い
    assert 'popovertarget="band"' in header
    assert _badge(header) == ("plan", "未確認")
    assert '<div id="band" popover' in header
    assert "border-t border-border" not in header
    assert html.index("</header>") < html.index('class="sidenav"')


def test_popover_lists_the_connections(client) -> None:
    html = client.get("/pacs").text
    band = html[html.index('<div id="band"') : html.index("</header>")]

    assert "<dt>自分</dt>" in band and "DTG_CT01" in band
    assert "RIS_TEST" in band
    assert "PACS_TEST" in band and '<span class="badge">標準</span>' in band
    assert "文字コード" in band
    assert 'href="/pacs"' not in band  # ページへの入り口は左のナビだけ
    # まだ試していないものは「未確認」
    assert band.count('data-k="plan">未確認</span>') == 2


def test_badge_follows_the_last_probe(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/pacs")

    echoed = client.post("/pacs/echo/PACS_TEST", headers=post_headers(token))
    # 接続確認の応答が、上の帯の札と中身を同じ応答で差し替える
    assert 'hx-swap-oob="true"' in echoed.text
    assert re.search(
        r'<span id="conn-state" hx-swap-oob="true" class="st" data-k="ok">接続中</span>', echoed.text
    )
    assert _badge(client.get("/pacs").text) == ("ok", "接続中")

    query_worklist(client)
    page = client.get("/worklist").text
    assert _badge(page) == ("ok", "接続中")
    assert page.count('data-k="ok">成功</span>') == 2


def test_badge_changes_when_a_destination_is_unreachable(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/pacs")

    echoed = client.post("/pacs/echo/PACS_TEST", headers=post_headers(token))

    assert 'role="alert"' in echoed.text
    assert re.search(r'<span id="conn-state"[^>]*data-k="ng">一部が接続不可</span>', echoed.text)
    page = client.get("/worklist").text
    assert _badge(page) == ("ng", "一部が接続不可")
    assert 'data-k="ng">失敗</span>' in page


def test_failed_worklist_query_changes_the_badge(tmp_path, storage_scp) -> None:
    client = make_client(tmp_path, free_port(), storage_scp.port)

    failed = query_worklist(client)

    # 失敗の応答も、上の帯の札を同じ応答で差し替える
    assert re.search(r'<span id="conn-state" hx-swap-oob="true" class="st" data-k="ng">', failed)
    assert _badge(client.get("/worklist").text) == ("ng", "一部が接続不可")


def test_input_error_does_not_change_the_badge(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    query_worklist(client)
    assert _badge(client.get("/worklist").text) == ("ok", "接続中")

    # 日付を指定して日付を空にすると、相手に問い合わせる前に入力の誤りで断る
    refused = query_worklist(client, day="date", date="")

    assert "日付を入れてください" in refused
    assert 'id="conn-state"' not in refused
    assert _badge(client.get("/worklist").text) == ("ok", "接続中")


def test_overall_counts_only_configured_destinations() -> None:
    status = LinkStatus()
    assert status.overall(["A"]) == ("plan", "未確認")

    status.record_destination("A", True)
    status.record_destination("GONE", False)
    assert status.overall(["A"]) == ("ok", "接続中")

    status.record_worklist(False)
    assert status.overall(["A"]) == ("ng", "一部が接続不可")
