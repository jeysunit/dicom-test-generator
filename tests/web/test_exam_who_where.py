"""撮る前と撮った後に「誰を・どこへ」を示す。文字コードの選び方・
ワークリストの選び方（docs/spec/12a の 10.4・10.5）."""

from __future__ import annotations

import re

from modality_peers import WorklistSCP, start_server
from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityWorklistInformationFind
from web_helpers import csrf_token, key_for, make_client, post_headers, query_worklist


def _emergency_form(**extra: str) -> dict[str, str]:
    return {
        "mode": "emergency",
        "patient_id": "E0002",
        "name_alphabetic": "KINKYU TARO",
        "name_ideographic": "緊急 太郎",
        "sex": "O",
        "template": "ct_generic",
        "profile": "",
        "series": "1",
        "images": "1",
        "abnormal_level": "none",
        "charset": "auto",
        "action": "exam",
        **extra,
    }


def _target(html: str) -> str:
    return html.split('id="exam-target"', 1)[1].split("</section>", 1)[0]


def test_target_banner_sits_right_above_the_action_row(client) -> None:
    html = client.get("/exam").text

    # 「撮る患者と送信先」の直後に操作の行（間に区画を挟まない）
    after = html.split('id="exam-target"', 1)[1].split("</section>", 1)[1]
    assert after.lstrip().startswith('<div id="actions">')


def test_emergency_target_mirrors_the_inputs_and_names_the_destination(client) -> None:
    target = _target(client.get("/exam").text)

    for name in ("name_ideographic", "name_phonetic", "name_alphabetic", "patient_id"):
        assert f'data-mirror="{name}"' in target
    assert "data-mirror-birth" in target
    assert "—（予約なし）" in target
    # 送信先は名前・AEタイトル・ホストとポート
    assert re.search(r"PACS_TEST <span[^>]*>PACS_TEST・127\.0\.0\.1:\d+</span>", target)


def test_scheduled_target_shows_the_patient_and_the_destination(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    target = _target(client.get(f"/exam?key={key}").text)

    for value in ("山田 太郎", "やまだ たろう", "YAMADA TARO", "P000001", "A0001", "1980/01/15"):
        assert value in target, value
    assert "PACS_TEST" in target
    assert "data-mirror" not in target


# 患者の帯の生年月日は、西暦と、括弧から後ろ（.unit）の 2 つに分け、全文を title に出す
_BIRTH_VALUE = re.compile(
    r'<(?:div class="v"|dd) title="1980/01/15（昭55・\d+歳）(?P<sex>[^"]+)">1980/01/15'
    r'<span class="unit">（昭55・\d+歳）(?P=sex)</span></(?:div|dd)>'
)


def test_scheduled_target_wraps_the_birth_date_tail_in_unit(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    target = _target(client.get(f"/exam?key={key}").text)

    assert _BIRTH_VALUE.search(target)


def test_worklist_item_banner_and_detail_wrap_the_birth_date_tail_in_unit(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    html = client.get(f"/worklist/item/{key}").text

    banner, detail = html.split('<section id="detail"', 1)
    assert _BIRTH_VALUE.search(banner)
    assert _BIRTH_VALUE.search(detail)


def test_emergency_exam_replaces_the_buttons_with_next_patient(client) -> None:
    token = csrf_token(client, "/exam")

    html = client.post("/exam", data=_emergency_form(), headers=post_headers(token)).text

    assert "撮影完了：緊急 太郎（E0002）の 1 画像" in html
    actions = html.split('<div id="actions" hx-swap-oob="true">', 1)[1].split("</div>\n</div>", 1)[0]
    # 撮った患者のまま次を撮らない：撮影のボタンは無く、次の患者は空の欄の画面で入れる
    assert 'name="action"' not in actions
    assert '<a class="btn btn-primary" href="/exam" data-next-patient>次の緊急の患者</a>' in actions
    assert "data-same-patient" in actions and "同じ患者でもう一度" in actions


def test_check_keeps_the_done_row_until_same_patient_is_chosen(client) -> None:
    done = client.get("/exam/check", params={"template": "ct_generic", "done": "1"}).text
    again = client.get("/exam/check", params={"template": "ct_generic"}).text

    assert "data-same-patient" in done and 'name="action"' not in done
    assert 'value="exam_send"' in again and "data-same-patient" not in again


def test_scheduled_exam_keeps_the_taken_row(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    form = {**_emergency_form(), "mode": "scheduled", "key": key}

    html = client.post("/exam", data=form, headers=post_headers(token)).text

    assert "撮影完了：山田 太郎（P000001）の" in html
    assert "data-same-patient" not in html


def test_charset_choices_have_names_and_the_jis_kana_warning(client) -> None:
    html = client.get("/exam").text
    select = html.split('id="exam-charset"', 1)[1].split("</select>", 1)[0]

    options = re.findall(r'<option value="([^"]+)"[^>]*>([^<]+)</option>', select)
    assert options == [
        ("auto", "自動（予約に合わせる）"),
        ("utf8", "UTF-8（ISO_IR 192）"),
        ("jis", "JIS（漢字。ISO 2022 IR 87）"),
        ("jis_kana", "JIS（半角カナと漢字。ISO 2022 IR 13\\IR 87）"),
    ]
    # 予約なしでは「自動」が何になるか
    assert "予約なしの撮影では、自動は UTF-8（ISO_IR 192）になります。" in html
    # JIS（半角カナと漢字）の注意は、選んだときだけ出す（初期設定は自動なので隠す）
    warning = re.search(r'<p id="charset-warning"[^>]*>', html).group(0)
    assert 'data-charset-warning="jis_kana"' in warning and " hidden" in warning
    assert "Orthanc 1.13.0 は、この組み合わせの漢字・かなを読み崩します。" in html
    assert "UTF-8 か JIS（漢字）を選んでください。" in html
    assert 'aria-describedby="charset-auto-note charset-warning"' in select


def test_scheduled_auto_note_names_the_worklist_charset(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    html = client.get(f"/exam?key={key}").text

    assert "自動は予約の文字コード（ISO_IR 192）に合わせます。" in html


def test_auto_that_becomes_jis_kana_also_warns(tmp_path, worklist_items, storage_scp) -> None:
    """予約の文字コードが ISO 2022 IR 13\\IR 87 なら、「自動」でも注意を出す（12 の 14.4）."""
    scp = WorklistSCP(items=worklist_items, character_set=["ISO 2022 IR 13", "ISO 2022 IR 87"])
    ae = AE(ae_title=scp.ae_title)
    ae.add_supported_context(ModalityWorklistInformationFind)
    server, scp.port = start_server(ae, [(evt.EVT_C_FIND, scp.handle_find)])
    try:
        client = make_client(tmp_path, scp.port, storage_scp.port)
        key = key_for(query_worklist(client), "A0001")
        html = client.get(f"/exam?key={key}").text
    finally:
        server.shutdown()

    warning = re.search(r'<p id="charset-warning"[^>]*>', html).group(0)
    assert 'data-charset-warning="jis_kana auto"' in warning
    # 初期設定は自動なので、開いたときから出す
    assert " hidden" not in warning
    assert "自動は予約の文字コード（ISO 2022 IR 13\\ISO 2022 IR 87）に合わせます。" in html


def test_form_does_not_restore_the_previous_patient(client) -> None:
    html = client.get("/exam").text

    # 読み込み直したときに、ブラウザーが前の患者の値を欄に戻さない
    form = re.search(r'<form id="exam-form"[^>]*>', html).group(0)
    assert 'autocomplete="off"' in form


def test_worklist_primary_waits_for_a_row(client) -> None:
    html = query_worklist(client)

    primary = re.search(r'<button type="submit" class="btn btn-primary"[^>]*>選んで撮影へ', html).group(0)
    assert "data-needs-selection" in primary and " disabled" in primary
    # 行を選ぶと、患者バナーを操作の行の真上（#pick-banner）に出す
    assert 'hx-target="#pick-banner"' in html
    pickbar = html.split('<div class="pickbar">', 1)[1]
    assert pickbar.index('id="pick-banner"') < pickbar.index("選んで撮影へ")


def test_worklist_item_returns_banner_and_detail(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    html = client.get(f"/worklist/item/{key}").text

    banner = html.split('<section id="detail"', 1)[0]
    assert 'class="fb r1" aria-label="選んだ予約の患者"' in banner
    for value in ("山田 太郎", "P000001", "A0001"):
        assert value in banner
    assert '<section id="detail" hx-swap-oob="true">' in html
    assert "予約の詳細" in html


def test_worklist_refresh_keeps_the_selection_and_the_banner(client) -> None:
    listing = query_worklist(client)
    key = key_for(listing, "A0001")
    token = csrf_token(client)

    html = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token)).text

    primary = re.search(r'<button type="submit" class="btn btn-primary"[^>]*>選んで撮影へ', html).group(0)
    assert " disabled" not in primary
    assert 'aria-label="選んだ予約の患者"' in html.split('<div class="pickbar">', 1)[1]
