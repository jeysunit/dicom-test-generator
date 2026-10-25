"""PACS の送信先の表の「最後の接続確認」の列（docs/spec/12a の 10.6）."""

from __future__ import annotations

import re

from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers

_CELL = re.compile(r'<td id="echo-1" class="text-xs text-label">(.*?)</td>', re.DOTALL)


def _cell(html: str) -> str:
    found = _CELL.search(html)
    assert found, "最後の接続確認の列がない"
    return found.group(1)


def test_column_is_named_and_empty_before_any_check(client) -> None:
    html = client.get("/pacs").text

    assert '<th scope="col">最後の接続確認</th>' in html
    assert _cell(html) == "—"


def test_column_shows_the_last_result_and_time(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/pacs")

    client.post("/pacs/echo/PACS_TEST", headers=post_headers(token))

    cell = _cell(client.get("/pacs").text)
    assert '<span class="st" data-k="ok">成功</span>' in cell
    assert re.search(r"\d{2}/\d{2} \d{2}:\d{2}", cell)


def test_column_shows_a_failure(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/pacs")

    client.post("/pacs/echo/PACS_TEST", headers=post_headers(token))

    assert '<span class="st" data-k="ng">失敗</span>' in _cell(client.get("/pacs").text)
