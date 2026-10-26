"""上の帯の「接続の状態」：全体の状態の札と、押すと出る中身（docs/spec/12a の 10.3）."""

from __future__ import annotations

import re

from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers, query_worklist

from app.web.link_status import LinkStatus
from app.web.routes.pacs import CHECK_ALL_LOCK

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
    # 中身の下に「接続確認」と、接続先の画面（PACS）への道を置く。説明の文は置かない
    footer = band.split('<div class="ft">', 1)[1].split("</div>", 1)[0]
    assert 'hx-post="/link/check"' in footer and "接続確認" in footer
    assert '<a class="btn btn-sm" href="/pacs">PACS を開く</a>' in footer
    assert "PACS の画面で行う" not in band
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


def test_link_check_probes_every_peer_and_replaces_the_popover(
    tmp_path, worklist_scp, storage_scp
) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/worklist")

    checked = client.post("/link/check", headers=post_headers(token)).text

    # 中身（#band）は差し替えの本体で、全体の状態の札は同梱して差し替える
    assert '<div id="band" popover' in checked and 'id="band" popover hx-swap-oob' not in checked
    assert re.search(
        r'<span id="conn-state" hx-swap-oob="true" class="st" data-k="ok">接続中</span>', checked
    )
    # ワークリストの取得先と送信先の両方が「成功」になる
    assert checked.count('data-k="ok">成功</span>') == 2


def test_link_check_marks_a_peer_that_does_not_answer(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/worklist")

    checked = client.post("/link/check", headers=post_headers(token)).text

    assert 'data-k="ok">成功</span>' in checked
    assert 'data-k="ng">失敗</span>' in checked
    assert re.search(r'<span id="conn-state" hx-swap-oob="true" class="st" data-k="ng">', checked)


def test_link_check_does_not_overlap_a_running_check(tmp_path, worklist_scp, storage_scp) -> None:
    # 確かめている最中に、差し替わった中身の新しいボタンから重ねて届いても、C-ECHO を重ねない
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/worklist")

    with CHECK_ALL_LOCK:
        overlapped = client.post("/link/check", headers=post_headers(token))

    assert overlapped.status_code == 204
    assert overlapped.text == ""
    assert client.app.state.link_status.worklist is None
    # 前の確認が終われば、また確かめられる
    assert client.post("/link/check", headers=post_headers(token)).status_code == 200
