"""相手から来る悪い値（`<script>`・制御文字）が画面でエスケープされる（docs/spec/12a の 10.8）."""

from __future__ import annotations

from web_helpers import csrf_token, post_headers
from web_helpers import key_for as _key_for
from web_helpers import query_worklist as _query

EVIL_NAME = "<script>alert(1)</script>^X=\x1b]0;pwn\x07漢字"
EVIL_DESCRIPTION = '"><img src=x onerror=alert(2)>\u202eCT'


def _evil_items(worklist_scp) -> None:
    evil = dict(worklist_scp.items[0])
    evil["patient_name"] = EVIL_NAME
    evil["requested_procedure_description"] = EVIL_DESCRIPTION
    evil["accession_number"] = "A<b>9"
    worklist_scp.items = [evil]


def _assert_safe(html: str) -> None:
    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "<b>9" not in html
    assert "\x1b" not in html and "\x07" not in html and "\u202e" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "\\x1b" in html


def test_worklist_list_and_detail_escape_peer_values(client, worklist_scp) -> None:
    _evil_items(worklist_scp)

    html = _query(client)
    _assert_safe(html)
    assert "&lt;img src=x onerror=alert(2)&gt;" in html
    assert "\\u202e" in html

    key = _key_for(html, "A&lt;b&gt;9")
    _assert_safe(client.get(f"/worklist/item/{key}").text)
    _assert_safe(client.get(f"/exam?key={key}").text)
    _assert_safe(client.get("/worklist").text)


def test_peer_status_text_in_errors_is_escaped(client) -> None:
    token = csrf_token(client, "/pacs")
    html = client.post("/pacs/echo/<script>x</script>", headers=post_headers(token)).text
    assert "<script>x" not in html
