"""ワークリストの画面の部品：見出しの行・検索の帯・件数の行・状態の札・空の状態（docs/spec/12a の 10.4）."""

from __future__ import annotations

import re

from web_helpers import query_worklist


def test_worklist_has_heading_search_band_and_count_row(client) -> None:
    page = client.get("/worklist").text
    assert '<div class="pagehead"><h1>ワークリスト</h1></div>' in page
    assert '<form id="query-form"' in page and 'class="searchband"' in page
    # 項目名は欄の上に小さく出す（欄の中の薄い文字に頼らない）
    assert "placeholder" not in page.split('id="query-form"', 1)[1].split("</form>", 1)[0]

    html = query_worklist(client)
    count_row = html.split('<div class="count-row">', 1)[1].split("</div>", 1)[0]
    assert re.search(r'<b class="count-n">\d+</b> 件（\d{4}-\d{2}-\d{2} ', count_row)
    # 件数の行は一覧の上にある
    assert html.index('<div class="count-row">') < html.index("<table")


def test_worklist_marks_are_state_marks(client) -> None:
    html = query_worklist(client, station="any", modality="")
    assert '<span class="st" data-k="note">別の装置</span>' in html
    assert 'class="badge"' not in html
