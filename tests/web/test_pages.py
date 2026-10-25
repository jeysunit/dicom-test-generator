"""ページと HTMX の部分の応答（docs/spec/12a の 10.3〜10.8）."""

from __future__ import annotations

import re

import pytest
from web_helpers import OWN_AE, csrf_token, post_headers
from web_helpers import key_for as _key_for
from web_helpers import query_worklist as _query


def test_root_redirects_to_worklist(client) -> None:
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/worklist")


@pytest.mark.parametrize(
    ("path", "text"),
    [
        ("/worklist", "ワークリスト検索"),
        ("/exam", "緊急の患者"),
        ("/pacs", "接続確認"),
        ("/settings", OWN_AE),
    ],
)
def test_pages_open_with_header_and_band(client, path, text) -> None:
    response = client.get(path)
    assert response.status_code == 200
    html = response.text
    assert text in html
    assert "dicom-test-generator" in html
    for name in ("ワークリスト", "撮影", "PACS", "設定"):
        assert name in html
    assert f"自分: {OWN_AE}" in html
    assert 'id="theme-toggle"' in html
    assert "Not for Diagnostic Use" not in html
    assert "非医療機器" not in html
    assert '<html lang="ja"' in html


_NAV = re.compile(r'<nav class="sidenav" aria-label="ページ">(.*?)</nav>', re.DOTALL)
_NAV_ITEM = re.compile(r'<a href="([^"]+)" class="nav-item"( aria-current="page")?>([^<]+)</a>')


@pytest.mark.parametrize(
    ("path", "current"),
    [("/worklist", "ワークリスト"), ("/exam", "撮影"), ("/pacs", "PACS"), ("/settings", "設定")],
)
def test_left_nav_groups_items_and_current_page(client, path, current) -> None:
    html = client.get(path).text
    match = _NAV.search(html)
    assert match, "左のナビがある"
    nav = match.group(1)

    # 群は 業務・接続・管理 の順。項目は各ページの題と同じ名前で、群の中の順に並ぶ
    assert re.findall(r'<p class="nav-group">([^<]+)</p>', nav) == ["業務", "接続", "管理"]
    items = _NAV_ITEM.findall(nav)
    assert [(href, label) for href, _, label in items] == [
        ("/worklist", "ワークリスト"),
        ("/exam", "撮影"),
        ("/pacs", "PACS"),
        ("/settings", "設定"),
    ]
    # 現在のページだけに aria-current が付く
    assert [label for _, flag, label in items if flag] == [current]

    # ページへの入り口は左のナビだけ。上の帯（ヘッダー）にタブを置かない
    header = html[html.index("<header") : html.index("</header>")]
    assert 'href="/exam"' not in header and 'href="/pacs"' not in header
    assert 'href="/settings"' not in header
    # ナビは、ヘッダー（帯と情報バー）の後、本文の前
    assert html.index("</header>") < html.index('class="sidenav"') < html.index("<main")


def test_worklist_query_partial_lists_items_and_marks(client) -> None:
    html = _query(client, station="any", modality="")

    assert "<html" not in html  # HTMX の部分の応答
    assert "P000001" in html and "A0001" in html
    assert "山田 太郎" in html
    assert "1980/01/15" in html
    assert "別の装置" in html  # A0003 は DTG_MR01 の予定
    assert "選んで撮影へ" in html
    assert 'id="band"' in html and 'hx-swap-oob="true"' in html
    assert "ISO_IR 192 → ISO_IR 192" in html


def test_worklist_zero_items_offers_emergency(client) -> None:
    html = _query(client, patient_id="NOBODY")
    assert "予約はありません。条件を広げるか、緊急の患者で撮ってください" in html
    assert 'href="/exam"' in html


def test_worklist_non_ascii_zero_items_hint(client) -> None:
    html = _query(client, patient_name="存在しない")
    assert "日本語の条件は相手の文字コードの扱いに左右されます" in html


def test_worklist_bad_date_is_shown_as_error(client) -> None:
    html = _query(client, day="date", date="")
    assert "日付" in html
    assert 'role="alert"' in html


def test_station_filter_is_labeled_as_the_device_ae_title(client, worklist_scp) -> None:
    """(0040,0001) の絞り込みだと分かる言葉で示す（docs/spec/12a の 10.4）."""
    page = client.get("/worklist").text
    assert "装置の AEタイトル" in page
    assert f"この装置で絞る（{OWN_AE}）" in page
    assert ">予定の AE<" not in page

    _query(client)  # 初期設定は「この装置で絞る」
    sps = worklist_scp.queries[-1].ScheduledProcedureStepSequence[0]
    assert sps.ScheduledStationAETitle == OWN_AE

    _query(client, station="any")
    sps = worklist_scp.queries[-1].ScheduledProcedureStepSequence[0]
    assert sps.ScheduledStationAETitle == ""


def test_detail_shows_the_scheduled_station_ae_title_on_its_own_row(client) -> None:
    key = _key_for(_query(client, station="any", modality=""), "A0003")

    detail = client.get(f"/worklist/item/{key}").text

    row = detail.split("<dt>予定の装置の AEタイトル</dt>", 1)[1].split("</dd>", 1)[0]
    assert "DTG_MR01" in row
    schedule = detail.split("<dt>予定</dt>", 1)[1].split("</dd>", 1)[0]
    assert "DTG_MR01" not in schedule


def _detail_row(html: str, label: str) -> str:
    return html.split(f"<dt>{label}</dt><dd>", 1)[1].split("</dd>", 1)[0]


def test_detail_shows_names_in_the_list_order_without_raw_pn(client, worklist_scp) -> None:
    """氏名・依頼医・紹介医は、`^` と `=` を出さず、一覧と同じ漢字・かな・英字の順にする（10.4）."""
    item = dict(worklist_scp.items[0])
    item["patient_name"] = "YAMADA^TARO=山田^太郎=やまだ^たろう"
    item["requesting_physician"] = "SATO^ICHIRO=佐藤^一郎=さとう^いちろう"
    item["referring_physician_name"] = "SUZUKI^HANAKO"
    worklist_scp.items = [item, *worklist_scp.items[1:]]
    html = _query(client)

    detail = client.get(f"/worklist/item/{_key_for(html, 'A0001')}").text
    assert _detail_row(detail, "氏名") == "山田 太郎 / やまだ たろう / YAMADA TARO"
    assert _detail_row(detail, "依頼医") == "佐藤 一郎 / さとう いちろう / SATO ICHIRO"
    assert _detail_row(detail, "紹介医") == "SUZUKI HANAKO"


def test_detail_shows_requesting_and_referring_physicians(client, worklist_scp) -> None:
    """依頼医 (0032,1032) と紹介医 (0008,0090) を別の行に出す（docs/spec/12a の 10.4）."""
    item = dict(worklist_scp.items[0])
    item["requesting_physician"] = "SATO^ICHIRO"
    item["referring_physician_name"] = "SUZUKI^HANAKO"
    worklist_scp.items = [item, *worklist_scp.items[1:]]
    html = _query(client)

    detail = client.get(f"/worklist/item/{_key_for(html, 'A0001')}").text
    assert _detail_row(detail, "依頼医") == "SATO ICHIRO"
    assert _detail_row(detail, "紹介医") == "SUZUKI HANAKO"

    other = client.get(f"/worklist/item/{_key_for(html, 'A0002')}").text
    assert _detail_row(other, "依頼医") == "—"  # 応答に無い


def test_worklist_detail_and_refresh(client, worklist_scp) -> None:
    html = _query(client)
    key = _key_for(html, "A0001")

    detail = client.get(f"/worklist/item/{key}")
    assert detail.status_code == 200
    assert "2.25.100000000000000000000000000000000001" in detail.text
    assert "SPS0001" in detail.text

    worklist_scp.items[0]["requested_procedure_description"] = "胸部 CT（直した）"
    token = csrf_token(client)
    refreshed = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token))
    assert refreshed.status_code == 200
    assert "胸部 CT（直した）" in refreshed.text
    assert "再検索しました" in refreshed.text


def test_exam_page_is_read_only_and_lists_profiles(client) -> None:
    key = _key_for(_query(client), "A0001")

    html = client.get(f"/exam?key={key}").text

    assert "P000001" in html
    assert 'name="patient_id"' not in html  # 予約の値は入力の欄にしない
    assert "dtg_synthetic_ct" in html
    assert "ct_generic" in html
    assert "撮影して送信" in html
    # 確かめ直しの GET は、CSRF の token を URL に載せない（要る欄だけを送る）
    assert 'hx-include="#exam-form"' not in html
    assert "disabled" not in html.split('id="actions"', 1)[1].split("</div>", 1)[0]


def test_exam_page_blocks_modality_mismatch(client) -> None:
    key = _key_for(_query(client, station="any", modality=""), "A0003")

    html = client.get(f"/exam?key={key}").text

    assert "予約は MR、テンプレートは CT です" in html
    assert "この予約は別の装置の予定です" in html
    actions = html.split('id="actions"', 1)[1]
    assert "disabled" in actions.split("</div>", 1)[0]


def test_exam_check_partial_follows_profile_choice(client) -> None:
    key = _key_for(_query(client), "A0001")
    ok = client.get("/exam/check", params={"key": key, "template": "ct_generic"})
    assert ok.status_code == 200
    assert "disabled" not in ok.text

    missing = client.get(
        "/exam/check", params={"key": key, "template": "ct_generic", "profile": "no_such"}
    )
    assert "disabled" in missing.text
    assert "no_such" in missing.text


def test_unknown_worklist_key_on_exam_page(client) -> None:
    html = client.get("/exam?key=0000000000").text
    assert 'role="alert"' in html
    # 内部の予約の鍵は出さず、次の操作を日本語で知らせる（docs/spec/12a の 10.4）
    assert "0000000000" not in html
    assert "「ワークリスト検索」からやり直してください" in html


def test_emergency_form_validation_error_is_shown(client) -> None:
    token = csrf_token(client, "/exam")
    response = client.post(
        "/exam",
        data={"mode": "emergency", "patient_id": "", "name_alphabetic": "", "action": "exam"},
        headers=post_headers(token),
    )
    assert response.status_code == 200
    assert 'role="alert"' in response.text


@pytest.mark.parametrize(("series", "images"), [("100", "1"), ("1", "1001"), ("2", "1,0")])
def test_exam_size_is_bounded_on_the_server(client, tmp_path, series, images) -> None:
    """シリーズ数・枚数の上限は画面の欄だけでなくサーバーで確かめる（10.5）."""
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E1",
        "name_alphabetic": "A^B",
        "series": series,
        "images": images,
        "action": "exam",
    }
    html = client.post("/exam", data=form, headers=post_headers(token)).text
    assert 'role="alert"' in html
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_template_name_from_the_form_is_not_a_path(client) -> None:
    html = client.get("/exam/check", params={"template": "../../config/app_config"}).text
    assert "disabled" in html
    assert "app_config.yaml" not in html


REFRESH_BUTTON = 'hx-post="/worklist/refresh"'


def _refresh_button(html: str) -> str:
    start = html.rfind("<button", 0, html.index(REFRESH_BUTTON))
    return html[start : html.index(">", html.index(REFRESH_BUTTON)) + 1]


def _is_disabled(button: str) -> bool:
    return re.search(r'\sdisabled[\s>]', button) is not None


def test_refresh_button_waits_for_a_selected_row(client, worklist_scp) -> None:
    """行を選ぶまで「再検索」は押せない（docs/spec/12a の 10.4）."""
    html = _query(client)
    button = _refresh_button(html)
    assert _is_disabled(button)
    assert 'title="行を選ぶと押せます"' in button
    assert 'hx-disabled-elt="this"' in button  # 通信の間も押せない

    key = _key_for(html, "A0001")
    token = csrf_token(client)
    refreshed = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token))
    # 再検索した後は、選んだ行に印があるので押せる
    assert not _is_disabled(_refresh_button(refreshed.text))

    unknown = client.post(
        "/worklist/refresh", data={"key": "0000000000"}, headers=post_headers(token)
    )
    # 一覧に無い鍵では、どの行にも印が無いので押せない
    assert _is_disabled(_refresh_button(unknown.text))


def test_refresh_also_replaces_the_open_detail(client, worklist_scp) -> None:
    """再検索したら、開いている詳細も新しい値にする（docs/spec/12a の 10.4）."""
    html = _query(client)
    assert '<section id="detail" hx-swap-oob="true"></section>' in html  # 再検索で閉じる

    key = _key_for(html, "A0001")
    worklist_scp.items[0]["requested_procedure_description"] = "胸部 CT（直した）"
    token = csrf_token(client)
    refreshed = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token))

    detail = refreshed.text.split('<section id="detail" hx-swap-oob="true">', 1)[1]
    detail = detail.split("</section>", 1)[0]
    assert "予約の詳細" in detail and "胸部 CT（直した）" in detail


def test_refresh_without_a_key_does_not_query(client, worklist_scp) -> None:
    _query(client)
    queries = len(worklist_scp.queries)
    token = csrf_token(client)

    html = client.post("/worklist/refresh", data={}, headers=post_headers(token)).text

    assert len(worklist_scp.queries) == queries
    assert "予約を選んでから「再検索」を押してください" in html
    assert "worklist_key" not in html and "worklist query" not in html
    assert "A0001" in html  # 一覧は残す


def test_refresh_of_an_unknown_key_is_told_in_japanese(client) -> None:
    _query(client)
    token = csrf_token(client)

    html = client.post(
        "/worklist/refresh", data={"key": "0000000000"}, headers=post_headers(token)
    ).text

    assert (
        "この予約は最後に取得した一覧にありません。「ワークリスト検索」からやり直してください"
        in html
    )
    assert "worklist_key" not in html and "worklist query" not in html


def test_refresh_of_a_removed_item_keeps_the_row(client, worklist_scp) -> None:
    key = _key_for(_query(client), "A0001")
    worklist_scp.items = []
    token = csrf_token(client)

    html = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token)).text

    assert (
        "この予約はワークリストにもうありません（受付番号 A0001）。"
        "RIS で取り消されたか、変更された可能性があります"
    ) in html
    assert html.count("A0001") >= 2  # 知らせと、残した一覧の行
    assert "worklist_key" not in html


def test_refresh_time_limit_is_told_in_japanese(client, monkeypatch) -> None:
    from app.core.exceptions import WorklistRefreshTimeoutError

    key = _key_for(_query(client), "A0001")
    service = client.app.state.service

    def time_out(worklist_key: str):
        raise WorklistRefreshTimeoutError(
            "Worklist refresh was cut off by the time limit: x",
            {"worklist_key": worklist_key, "timeout_seconds": 30.0},
        )

    monkeypatch.setattr(service, "refresh_item", time_out)
    token = csrf_token(client)

    html = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token)).text

    assert "再検索の途中で時間切れになりました（30 秒）。もう一度押してください" in html
    assert "worklist_key" not in html


def test_removed_item_without_accession_has_no_empty_label(client, monkeypatch) -> None:
    from app.core.exceptions import WorklistItemGoneError

    key = _key_for(_query(client), "A0001")

    def gone(worklist_key: str):
        raise WorklistItemGoneError("gone", {"worklist_key": worklist_key, "accession_number": ""})

    monkeypatch.setattr(client.app.state.service, "refresh_item", gone)
    token = csrf_token(client)

    html = client.post("/worklist/refresh", data={"key": key}, headers=post_headers(token)).text

    assert "この予約はワークリストにもうありません。RIS で取り消されたか" in html
    assert "受付番号 なし" not in html


def test_exam_page_with_an_unknown_key_is_told_in_japanese(client) -> None:
    _query(client)

    html = client.get("/exam", params={"key": "0000000000"}).text

    assert "この予約は最後に取得した一覧にありません" in html
    assert "worklist_key" not in html and "worklist query" not in html

    check = client.get("/exam/check", params={"key": "0000000000"}).text
    assert "この予約は最後に取得した一覧にありません" in check


def test_failed_refresh_keeps_the_list(client) -> None:
    html = _query(client)
    token = csrf_token(client)
    failed = client.post("/worklist/refresh", data={"key": ""}, headers=post_headers(token)).text
    assert 'role="alert"' in failed
    assert "A0001" in failed and "選んで撮影へ" in failed
    assert "A0001" in html


def test_htmx_swaps_error_responses() -> None:
    """403 などの失敗の応答も画面に出す（htmx 2 の既定は 4xx・5xx を出さない）."""
    from app.web.templating import TEMPLATES_DIR

    base = (TEMPLATES_DIR / "base.html").read_text(encoding="utf-8")
    assert '"responseHandling"' in base and '"[45]..", "swap": true' in base


def test_pacs_queue_partial_polls(client) -> None:
    page = client.get("/pacs").text
    assert 'hx-get="/pacs/queue"' in page
    assert "every 2s" in page

    partial = client.get("/pacs/queue")
    assert partial.status_code == 200
    assert "<html" not in partial.text
    assert "送信した検査はまだありません" in partial.text


def test_pacs_echo(client) -> None:
    token = csrf_token(client, "/pacs")
    ok = client.post("/pacs/echo/PACS_TEST", headers=post_headers(token))
    assert "成功" in ok.text

    unknown = client.post("/pacs/echo/NOPE", headers=post_headers(token))
    assert 'role="alert"' in unknown.text


def test_screens_say_get_the_worklist_not_hiku(client) -> None:
    """画面の言葉は「ワークリスト検索」「再検索」（2026-10-19。docs/spec/12a の 10.4）."""
    page = client.get("/worklist").text
    results = _query(client)
    exam = client.get(f"/exam?key={_key_for(results, 'A0001')}").text
    for html in (page, results, exam):
        assert "引" not in html
    assert "ワークリスト検索" in page
    assert "再検索" in results


def _field(html: str, name: str) -> str:
    """欄の name を含む <label> の中身."""
    end = html.index(f'name="{name}"')
    start = html.rindex("<label", 0, end)
    return html[start : html.index("</label>", end)]


def test_required_fields_are_marked(client) -> None:
    """必須の欄に「必須」の印と required（docs/spec/12a の 10.5）."""
    html = client.get("/exam").text
    for name in ("patient_id", "name_alphabetic"):
        field = _field(html, name)
        assert "必須" in field, name
        assert " required" in field, name
    # シリーズ数・画像数は「手で入れる」のときの欄（既定はルーチン。ADR-0025）
    manual = client.get("/exam/routine?routine=manual").text
    for name in ("series", "images"):
        field = _field(manual, name)
        assert "必須" in field, name
        assert " required" in field, name
    for name in ("name_ideographic", "name_phonetic", "birth_date", "study_description"):
        assert "必須" not in _field(html, name), name
    for name in ("name_alphabetic", "name_ideographic", "name_phonetic"):
        assert "data-person-name" in _field(html, name), name


def _emergency(client, **fields: str) -> str:
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU^TARO",
        "series": "1",
        "images": "1",
        "action": "exam",
        **fields,
    }
    return client.post("/exam", data=form, headers=post_headers(token)).text


@pytest.mark.parametrize(
    "fields",
    [
        {"name_alphabetic": ""},
        {"name_alphabetic": "　 "},
        {"patient_id": ""},
        {"name_alphabetic": "A=B"},
        {"name_ideographic": "山田\x1b太郎"},
    ],
)
def test_emergency_required_and_bad_names_are_refused_on_the_server(
    client, tmp_path, fields
) -> None:
    html = _emergency(client, **fields)
    assert 'role="alert"' in html
    assert "撮影完了" not in html
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_person_name_script_replaces_spaces_on_blur() -> None:
    """画面のスクリプトは補助：欄から離れたとき（focusout）に空白を ^ にする."""
    from app.web.app import STATIC_DIR

    script = (STATIC_DIR / "app.js").read_text(encoding="utf-8")
    assert "focusout" in script and "data-person-name" in script
    assert "\\s*\\^\\s*" in script and "\\s+" in script


def test_broken_state_is_reported_without_values(client, tmp_path) -> None:
    """壊れた保存のデータの誤りを、値（氏名）を出さずに見せる（docs/spec/12 の 12 章）."""
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "worklist_last.json").write_text(
        '{"items": [{"patient_name": "SECRET^PATIENTNAME", "birth_date": 19800101}]}',
        encoding="utf-8",
    )
    for path in ("/worklist", "/exam", "/pacs"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "SECRET" not in response.text, path
    assert 'role="alert"' in client.get("/worklist").text


def test_exam_page_shows_the_total_images_limit(client) -> None:
    assert "2000 画像まで" in client.get("/exam").text


def test_exam_over_the_total_limit_is_refused(client, tmp_path) -> None:
    html = _emergency(client, series="3", images="1000,1000,1")
    assert 'role="alert"' in html
    assert "2000" in html
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_settings_page_is_read_only(client) -> None:
    html = client.get("/settings").text
    assert "RIS_TEST" in html and "PACS_TEST" in html
    assert "<form" not in html
    assert "app_config.yaml" in html
