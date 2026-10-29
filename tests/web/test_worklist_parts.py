"""ワークリストの画面の部品：見出しの行・検索の帯・件数の行・状態の札・空の状態（docs/spec/12a の 10.4）."""

from __future__ import annotations

import re

from web_helpers import key_for, query_worklist


def test_worklist_has_heading_search_band_and_count_row(client) -> None:
    page = client.get("/worklist").text
    assert '<div class="pagehead"><h1>ワークリスト</h1></div>' in page
    assert '<form id="query-form"' in page and 'class="searchband"' in page
    # 項目名は欄の上に小さく出す（欄の中の薄い文字に頼らない）
    assert "placeholder" not in page.split('id="query-form"', 1)[1].split("</form>", 1)[0]

    html = query_worklist(client)
    count_row = html.split('<div class="listhead">', 1)[1].split("</div>", 1)[0]
    assert re.search(r'<span class="cnt"><b>\d+</b> 件（\d{4}-\d{2}-\d{2} ', count_row)
    # 件数の行は一覧の上にある
    assert html.index('<div class="listhead">') < html.index("<table")


def test_worklist_marks_are_state_marks(client) -> None:
    html = query_worklist(client, station="any", modality="")
    assert '<span class="st" data-k="note">別の装置</span>' in html
    # 応答に同梱する上の帯の接続の状態（送信先の「標準」の札）を除いた、一覧と詳細の部分
    results = re.sub(r'<div id="band".*?</dl>', "", html, flags=re.DOTALL)
    assert 'class="badge"' not in results


def test_worklist_birth_date_uses_the_era_form_for_each_place(client) -> None:
    html = query_worklist(client)
    results = re.sub(r'<div id="band".*?</dl>', "", html, flags=re.DOTALL)
    table = results.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    # 一覧の列：英字 1 字・半角の括弧・括弧の前に半角の空白。性別は下の行
    cells = re.findall(r'<div class="whitespace-nowrap">([^<]*)</div>', table)
    assert cells
    assert "1980/01/15 (S55・" in cells[0]
    dated = [cell for cell in cells if cell != "生年月日なし"]
    assert all(re.fullmatch(r"\d{4}/\d{2}/\d{2} \(([MTSHR]\d+・)?\d+歳\)", cell) for cell in dated), cells
    # 詳細・患者バナー：漢字 1 字・全角の括弧で、性別が続く
    detail = client.get(f"/worklist/item/{key_for(html, 'A0001')}").text
    # 西暦の後ろ（括弧から後ろ）は .unit で包み、全文は title に出す
    assert re.search(
        r'<dt>生年月日・性別</dt><dd title="1980/01/15（昭55・\d+歳）(男|女|その他)">'
        r'1980/01/15<span class="unit">（昭55・\d+歳）(男|女|その他)</span></dd>',
        detail,
    )
    assert re.search(
        r'<div class="v" title="1980/01/15（昭55・\d+歳）(男|女|その他)">'
        r'1980/01/15<span class="unit">（昭55・\d+歳）(男|女|その他)</span></div>',
        detail,
    )
