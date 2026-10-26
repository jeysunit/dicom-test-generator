"""PACS の接続先の表の「最後の接続確認」の列と、押した直後の知らせ（docs/spec/12a の 10.6）."""

from __future__ import annotations

import re

from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers

from app.web.link_status import (
    REASON_AE_TITLE,
    REASON_NO_ANSWER,
    REASON_PEER_FAILED,
    REASON_REFUSED,
    echo_reason,
)
from app.web.routes.pacs import CHECK_ALL_LOCK

_CELL = re.compile(r'<td id="echo-1" class="res">(.*?)</td>', re.DOTALL)
_WAIT = '<span class="st wait-mark" data-k="check">確認中</span>'


def _cell(html: str) -> str:
    found = _CELL.search(html)
    assert found, "最後の接続確認の列がない"
    return found.group(1)


def _notice(html: str) -> str:
    return html.split('<div id="echo-notice" hx-swap-oob="true">', 1)[1].split('<div id="band"', 1)[0]


def test_columns_follow_the_connection_table(client) -> None:
    html = client.get("/pacs").text
    head = html.split('<table class="tbl conn">', 1)[1].split("</thead>", 1)[0]

    labels = re.findall(r'<th scope="col">([^<]+)</th>', head)
    assert labels == ["名称", "種類", "AEタイトル", "ホスト名:ポート番号", "最後の接続確認"]
    # ワークリストの取得先も同じ表の 1 行
    assert '<td id="echo-worklist" class="res">' in html
    assert 'hx-post="/pacs/check-all"' in html


def test_column_is_empty_before_any_check(client) -> None:
    cell = _cell(client.get("/pacs").text)

    assert '<span class="none">—</span>' in cell
    # 確認中の札は、押している間だけ CSS で出す
    assert _WAIT in cell
    assert 'data-k="ok"' not in cell and 'data-k="ng"' not in cell


def test_column_shows_the_last_result_and_time(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/pacs")

    echoed = client.post("/pacs/echo/PACS_TEST", headers=post_headers(token)).text

    cell = _cell(client.get("/pacs").text)
    assert '<span class="st" data-k="ok">成功</span>' in cell
    assert re.search(r'<span class="when">\d{2}/\d{2} \d{2}:\d{2}</span>', cell)
    notice = _notice(echoed)
    assert 'role="status" class="notice" data-k="ok"' in notice
    assert re.search(r"PACS_TEST（127\.0\.0\.1:\d+）に接続できました（\d+ ms）。", notice)


def test_failure_shows_a_reason_in_the_cell_and_the_next_step_above(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/pacs")

    echoed = client.post("/pacs/echo/PACS_TEST", headers=post_headers(token)).text

    cell = _cell(client.get("/pacs").text)
    assert '<span class="st" data-k="ng">失敗</span>' in cell
    assert f'<span class="why">{REASON_NO_ANSWER}</span>' in cell
    notice = _notice(echoed)
    assert 'role="alert" class="notice" data-k="err"' in notice
    assert "に接続できませんでした。応答がありません。相手が動いているかと" in notice
    # 英語の原文は画面に出さない
    assert "Association" not in echoed


def test_worklist_row_and_check_all(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/pacs")

    echoed = client.post("/pacs/echo-worklist", headers=post_headers(token)).text
    assert "ワークリストの取得先（127.0.0.1:" in _notice(echoed)

    section = client.post("/pacs/check-all", headers=post_headers(token)).text
    assert '<section id="conn-sec" class="sec">' in section
    table = section.split('<div id="band"', 1)[0]
    assert table.count('data-k="ok">成功</span>') == 2
    # 上の帯も同じ応答で差し替える
    assert '<div id="band" popover hx-swap-oob="true"' in section
    # 前の接続確認の知らせは、同じ応答で消す
    assert '<div id="echo-notice" hx-swap-oob="true"></div>' in section


def test_check_all_is_skipped_while_another_check_runs(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/pacs")

    assert CHECK_ALL_LOCK.acquire(blocking=False)
    try:
        response = client.post("/pacs/check-all", headers=post_headers(token))
    finally:
        CHECK_ALL_LOCK.release()

    assert response.status_code == 204
    assert response.text == ""


def test_echo_reason_phrases() -> None:
    assert echo_reason("Association failed: could not connect (refused, aborted or timed out)")[0] == (
        REASON_NO_ANSWER
    )
    assert echo_reason("Association failed: association rejected by the peer")[0] == REASON_REFUSED
    assert echo_reason("相手が AEタイトル DTG を受け付けませんでした。")[0] == REASON_AE_TITLE
    assert echo_reason("C-ECHO failed with status 0x0110")[0] == REASON_PEER_FAILED
