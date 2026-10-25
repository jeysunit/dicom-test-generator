"""撮影の画面は、3 製品の画面の型 C（入力）の形で出す（docs/spec/12a の 10.5）."""

from __future__ import annotations

import re

from web_helpers import key_for, query_worklist


def test_scheduled_exam_has_crumbs_banner_sections_and_action_row(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    html = client.get(f"/exam?key={key}").text

    # パンくず（患者の下の画面）→ 見出しの行 → 患者バナー → 区画 → 操作の行の順
    order = [
        html.index('<ol class="crumbs">'),
        html.index('<div class="pagehead"><h1>撮影</h1></div>'),
        html.index('<section class="banner" aria-label="患者">'),
        html.index('<h2 class="sec-title">撮影の設定</h2>'),
        html.index('<div class="formbar">'),
    ]
    assert order == sorted(order)
    banner = html.split('<section class="banner"', 1)[1].split("</section>", 1)[0]
    for label in ("患者ID", "生年月日・性別", "受付番号", "検査名"):
        assert f'<div class="l">{label}</div>' in banner
    assert "P000001" in banner and "予約の値（読むだけ）" in banner
    # 予約の値の項目の表は、バナーに入らない値（UID・文字コード）だけを持つ
    assert 'class="panel"' not in html
    assert html.count('class="sec"') >= 2


def test_emergency_exam_has_no_crumbs_or_banner(client) -> None:
    html = client.get("/exam").text

    assert '<ol class="crumbs">' not in html
    assert 'class="banner"' not in html
    assert '<h2 class="sec-title">緊急の患者（予約なし）</h2>' in html
    # 必須は項目名の横の文字で示す（バッジの色に頼らない）
    required = re.findall(r'<span class="field-label">([^<]+)<span class="req">必須</span>', html)
    assert required == ["患者ID", "氏名（英字。例 KINKYU TARO）"]


def test_action_row_puts_secondary_before_primary(client) -> None:
    html = client.get("/exam").text
    actions = html.split('id="actions"', 1)[1].split("</form>", 1)[0]

    buttons = re.findall(r'<button[^>]*class="(btn [^"]+)"', actions)
    assert buttons == ["btn btn-outline", "btn btn-primary"]


def test_settings_follows_screen_type_d_read_only(client) -> None:
    """設定（読むだけ）：見出しの行、区画の見出しと項目名・値の対、1 列で最大 560px の幅."""
    html = client.get("/settings").text

    assert '<div class="pagehead"><h1>設定 <small>読むだけ</small></h1></div>' in html
    assert '<div class="settings-col">' in html
    titles = re.findall(r'<h2 class="sec-title">([^<]+)</h2>', html)
    assert titles == ["自分", "ワークリストの相手", "送信先", "文字コードと撮影"]
    assert 'class="panel' not in html and "<form" not in html
