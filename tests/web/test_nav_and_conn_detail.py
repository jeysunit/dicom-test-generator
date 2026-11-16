"""左のナビの群（業務・送受信・管理）、接続先の詳細、タブのアイコン（docs/spec/12a の 10.3・10.6）."""

from __future__ import annotations

import re

from modality_peers import free_port
from web_helpers import csrf_token, make_client, post_headers

from app.core.models import ScheduledPatient
from app.modality.config import DestinationConfig
from app.modality.service import ExamRequest


def _failed_job(client, patient_id: str) -> int:
    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id=patient_id, patient_name="A^B"),
            pixel_mode="simple_text",
        )
    )
    job_id = service.queue.add_job(exam.output_dir, "PACS_TEST", exam.files)
    service.queue.record_job_failure(job_id, "association lost")
    return job_id


def _nav(html: str) -> str:
    return html.split('<nav id="sidenav"', 1)[1].split("</nav>", 1)[0]


def test_nav_groups_are_work_transfer_and_admin_in_that_order(client) -> None:
    nav = _nav(client.get("/worklist").text)

    groups = re.findall(r'<p class="nav-g">([^<]+)</p>', nav)
    assert groups == ["業務", "送受信", "管理"]
    labels = re.findall(r'<span class="t">([^<]+)</span>', nav)
    assert labels == ["ワークリスト", "撮影", "送信一覧", "接続先", "設定", "バージョン情報"]
    assert "PACS" not in nav and "接続</p>" not in nav


def test_nav_marks_the_current_page(client) -> None:
    sent = _nav(client.get("/sent").text)
    connections = _nav(client.get("/connections").text)

    assert re.search(r'<a href="/sent" class="nav-i" aria-current="page"', sent)
    assert 'href="/connections" class="nav-i" aria-current' not in sent
    assert re.search(r'<a href="/connections" class="nav-i" aria-current="page"', connections)


def test_the_old_pacs_address_moves_to_connections(client) -> None:
    response = client.get("/pacs", follow_redirects=False)

    assert response.status_code == 308
    assert response.headers["location"] == "/connections"


def test_titles_follow_screen_name_then_system_name(client) -> None:
    assert "<title>送信一覧 - dicom-test-generator</title>" in client.get("/sent").text
    assert "<title>接続先 - dicom-test-generator</title>" in client.get("/connections").text


def test_tab_icon_is_linked_and_served_with_a_dark_variant(client) -> None:
    page = client.get("/connections").text
    assert '<link rel="icon" href="/static/icon.svg" type="image/svg+xml">' in page

    icon = client.get("/static/icon.svg")
    assert icon.status_code == 200
    assert icon.headers["content-type"].startswith("image/svg+xml")
    body = icon.text
    # 形は四隅の枠と中央の点、色は部品集の案の値（明るい地と暗い地）
    assert 'viewBox="0 0 16 16"' in body and 'rx="3"' in body
    assert "M4.5 6.5V4.5h2M9.5 4.5h2v2M11.5 9.5v2h-2M6.5 11.5h-2v-2" in body
    assert "#4b4fbf" in body and "#a5a8ff" in body and "prefers-color-scheme: dark" in body


def test_connections_screen_has_no_section_title_and_selects_the_first_row(client) -> None:
    html = client.get("/connections").text

    assert '<h1>接続先</h1>' in html
    # 区画の題「接続先」と説明の文は置かない。「すべて接続確認」は見出しの行の右
    assert '<h2 class="hd">' not in html
    pagehead = html.split('<div class="pagehead">', 1)[1].split("</div>", 1)[0]
    assert "すべて接続確認" in pagehead
    rows = re.findall(r'<tr data-row tabindex="0" aria-selected="(true|false)"', html)
    assert rows == ["true", "false"]


def test_destination_detail_has_settings_check_and_todays_sends(client) -> None:
    detail = client.get("/connections").text.split('id="conn-detail"', 1)[1]

    assert '<div class="grid2" role="region" aria-label="PACS_TEST の詳細">' in detail
    sections = re.findall(r"<section class=\"sec[^\"]*\"[^>]*>\s*<h2>([^<]+)</h2>", detail)
    assert sections == ["設定", "接続確認", "今日の送信"]
    assert "今日の受信" not in detail
    # 3 つ目の区画は 2 列にまたがる
    assert '<section class="sec span">' in detail
    settings = detail.split("<h2>設定</h2>", 1)[1].split("</section>", 1)[0]
    for label in ("名称", "種類", "AEタイトル", "ホスト名:ポート番号", "保管の確認"):
        assert f"<dt>{label}</dt>" in settings
    assert '<a href="/sent?aet=PACS_TEST">送信一覧で全部見る</a>' in detail
    # 今日の送信は表の枠をやめて区画の端から端まで（デザインシステム ui-kit 1.2.9。リンクは .sec-foot に入れる）
    today = detail.split("<h2>今日の送信</h2>", 1)[1]
    assert '<div class="in flush">' in today
    assert '<div class="sec-foot"><a href="/sent?aet=PACS_TEST">' in today
    # 件数が 0 でも区画を出す
    assert '今日 <b>0</b> 件' in detail and "今日の送信はありません。" in detail


def test_worklist_peer_detail_has_no_receive_or_send_sections(client) -> None:
    html = client.get("/connections/region?peer=worklist").text
    detail = html.split('id="conn-detail"', 1)[1]

    assert "<h2>今日の送信</h2>" not in detail and "今日の受信" not in detail
    assert re.findall(r"<section class=\"sec[^\"]*\"[^>]*>\s*<h2>([^<]+)</h2>", detail) == ["設定", "接続確認"]
    assert "<dt>MPPS</dt><dd>使わない</dd>" in detail
    assert "<dt>保管の確認</dt>" not in detail
    # 選んだ行は、押した相手に替わる
    assert re.findall(r'<tr data-row tabindex="0" aria-selected="(true|false)"', html) == ["false", "true"]
    assert '<input type="hidden" id="conn-selected" name="selected" value="worklist">' in html


def test_unknown_peer_falls_back_to_the_first_row(client) -> None:
    html = client.get("/connections/region?peer=dest:NOPE").text

    assert re.findall(r'aria-selected="(true|false)"', html)[:2] == ["true", "false"]
    assert 'aria-label="PACS_TEST の詳細"' in html


def test_rows_select_through_a_get_that_swaps_the_whole_region(client) -> None:
    html = client.get("/connections").text

    assert html.count('hx-get="/connections/region"') == 2
    assert """hx-vals='{"peer": "dest:PACS_TEST"}'""" in html or 'hx-vals=\'{"peer":"dest:PACS_TEST"}\'' in html
    assert 'hx-target="#conn-sec" hx-swap="outerHTML"' in html
    # 行の中の「接続確認」は、行の hx-swap・hx-target・hx-vals を引き継がない（引き継ぐと、結果の列 td ごと差し替わる）
    assert html.count('hx-disinherit="hx-target hx-swap hx-vals"') == 2


def test_todays_sends_show_the_count_and_newest_first(client) -> None:
    for number in range(1, 8):
        _failed_job(client, f"E000{number}")

    detail = client.get("/connections").text.split('id="conn-detail"', 1)[1]

    assert "今日 <b>7</b> 件" in detail
    assert "送信失敗 7" in detail
    shown = re.findall(r'<span class="mono">(E\d+)</span>', detail)
    # 新しい 5 件だけ（新しい順）
    assert shown == ["E0007", "E0006", "E0005", "E0004", "E0003"]
    assert "今日の送信はありません。" not in detail


def test_echo_from_the_selected_peer_also_swaps_the_detail(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/connections")

    selected = client.post(
        "/pacs/echo/PACS_TEST", data={"selected": "dest:PACS_TEST"}, headers=post_headers(token)
    ).text
    other = client.post(
        "/pacs/echo/PACS_TEST", data={"selected": "worklist"}, headers=post_headers(token)
    ).text

    assert '<section class="sec" id="conn-check" hx-swap-oob="true">' in selected
    assert 'data-k="ok">成功</span>' in selected.split('id="conn-check"', 1)[1]
    # 別の相手を詳細に出しているときは、詳細を替えない
    assert 'id="conn-check"' not in other


def test_check_all_keeps_the_selected_peer(tmp_path, worklist_scp, storage_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client, "/connections")

    html = client.post(
        "/pacs/check-all", data={"selected": "worklist"}, headers=post_headers(token)
    ).text

    assert '<div id="conn-sec" class="split-v">' in html
    assert 'name="selected" value="worklist"' in html
    assert 'aria-label="ワークリスト の詳細"' in html


def test_failed_echo_is_shown_in_the_detail_too(tmp_path, worklist_scp) -> None:
    client = make_client(tmp_path, worklist_scp.port, free_port())
    token = csrf_token(client, "/connections")

    echoed = client.post(
        "/pacs/echo/PACS_TEST", data={"selected": "dest:PACS_TEST"}, headers=post_headers(token)
    ).text

    check = echoed.split('id="conn-check"', 1)[1].split("</section>", 1)[0]
    assert 'data-k="ng">失敗</span>' in check
    assert "応答がありません" in check


def test_sent_list_opens_filtered_by_the_partner_ae_title(client) -> None:
    _failed_job(client, "E0001")

    html = client.get("/sent?aet=PACS_TEST").text

    assert '<option value="PACS_TEST" selected>PACS_TEST</option>' in html
    # 登録に無い値・空は、絞らない
    other = client.get("/sent?aet=NOPE").text
    assert "selected>PACS_TEST" not in other
    assert '<option value="">すべて</option>' in other


def test_shared_ae_title_adds_the_destination_name_to_the_link(client) -> None:
    config = client.app.state.service.config
    config.destinations.append(
        DestinationConfig(name="PACS_B", ae_title="PACS_TEST", host="127.0.0.1", port=4999)
    )

    detail = client.get("/connections/region?peer=dest:PACS_B").text

    # AEタイトルだけでは相手を決められないので、名称も添える
    assert '<a href="/sent?aet=PACS_TEST&amp;destination=PACS_B">送信一覧で全部見る</a>' in detail
    sent = client.get("/sent?aet=PACS_TEST&destination=PACS_B").text
    assert '<option value="PACS_B" selected>PACS_B</option>' in sent
    # 知らない名称は、AEタイトルで絞る
    other = client.get("/sent?aet=PACS_TEST&destination=NOPE").text
    assert '<option value="PACS_TEST" selected>PACS_TEST</option>' in other


def test_sent_list_title_and_header_actions(client) -> None:
    html = client.get("/sent").text
    pagehead = html.split('<div class="pagehead">', 1)[1].split("</div>", 1)[0]

    assert "<h1>送信一覧</h1>" in pagehead
    # 区画の題は置かない。失敗の再送信は見出しの行の右
    assert '<h2 class="hd">' not in html
    assert 'id="retry-slot"' in pagehead
    assert "送信ジョブ" not in html


def test_band_link_goes_to_connections(client) -> None:
    html = client.get("/sent").text

    assert '<a class="btn btn-sm" href="/connections">接続先を開く</a>' in html
    assert "PACS を開く" not in html
