"""画面と CLI の説明に、用語集で外した言い方が出ないこと（docs/spec/12a の 10.1）."""

from __future__ import annotations

import argparse
import html as html_module
import re
from pathlib import Path

from modality_peers import free_port
from web_helpers import csrf_token, key_for, make_client, post_headers, query_worklist

from app.cli.main import _create_parser

# 外した言い方。正規表現で書く（再送信の中の「再送」は外した言い方ではない）
RETIRED_WORDS = (
    "送り先",
    "待機中",
    r"再送(?![信出])",
    "もう一度送信",
    "つながった",
    "つながらない",
    "検査の記述",
    "頁",
    "患者 ID",
    "AE タイトル",
    "ワークリストを取得",
    "取得し直",
    "既定",
    "C-ECHO の結果",
)


def _visible_text(page: str) -> str:
    """タグを除いた本文に、読み上げの名前と補助の文字（aria-label・title・placeholder）を足す."""
    text = html_module.unescape(re.sub(r"<[^>]+>", " ", page))
    attributes = " ".join(re.findall(r'(?:aria-label|title|placeholder)="([^"]*)"', page))
    return f"{text} {html_module.unescape(attributes)}"


def _assert_no_retired_words(label: str, text: str) -> None:
    for word in RETIRED_WORDS:
        assert not re.search(word, text), f"{label}: {word}"


def _exam_form(key: str, action: str) -> dict[str, str]:
    return {
        "mode": "scheduled",
        "key": key,
        "template": "ct_generic",
        "profile": "",
        "series": "2",
        "images": "1,2",
        "abnormal_level": "none",
        "charset": "auto",
        "action": action,
    }


def test_pages_avoid_retired_words(client) -> None:
    results = query_worklist(client)
    key = key_for(results, "A0001")
    token = csrf_token(client, "/pacs")
    pages = {
        "/worklist": client.get("/worklist").text,
        "worklist results": results,
        "/exam": client.get("/exam").text,
        "/exam?key": client.get(f"/exam?key={key}").text,
        "/pacs": client.get("/pacs").text,
        "/pacs/queue": client.get("/pacs/queue").text,
        "/settings": client.get("/settings").text,
        "echo": client.post("/pacs/echo/PACS_TEST", headers=post_headers(token)).text,
    }
    for label, page in pages.items():
        _assert_no_retired_words(label, _visible_text(page))


def test_pacs_queue_with_rows_avoids_retired_words(tmp_path, worklist_scp, storage_scp) -> None:
    """失敗の行（もう一度送る）と送信完了の行・知らせを含む表と、行の詳細."""
    unreachable = make_client(tmp_path, worklist_scp.port, free_port())
    key = key_for(query_worklist(unreachable), "A0001")
    token = csrf_token(unreachable, f"/exam?key={key}")
    exam = unreachable.post("/exam", data=_exam_form(key, "exam_send"), headers=post_headers(token))
    queue = unreachable.get("/pacs/queue").text
    assert "もう一度送る" in queue

    reachable = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(reachable, "/pacs")
    notice = reachable.post("/pacs/retry-failed", headers=post_headers(token)).text
    sent_queue = reachable.get("/pacs/queue").text
    assert "もう一度送る" in sent_queue

    for label, page in {
        "exam result": exam.text,
        "queue": queue,
        "retry notice": notice,
        "queue after retry": sent_queue,
    }.items():
        _assert_no_retired_words(label, _visible_text(page))


def _help_texts(parser: argparse.ArgumentParser, name: str = "app.cli") -> dict[str, str]:
    texts = {name: parser.format_help()}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub_name, sub in action.choices.items():
                texts.update(_help_texts(sub, f"{name} {sub_name}"))
    return texts


def test_cli_help_avoids_retired_words() -> None:
    texts = _help_texts(_create_parser())
    assert "app.cli queue retry" in texts
    for label, text in texts.items():
        _assert_no_retired_words(label, text)


def test_static_script_avoids_retired_words() -> None:
    script = Path(__file__).resolve().parents[2] / "app" / "web" / "static" / "app.js"
    _assert_no_retired_words("app.js", script.read_text(encoding="utf-8"))
