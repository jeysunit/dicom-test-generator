"""撮影の画面の線量の報告の選択（ADR-0029）."""

from __future__ import annotations

import re

from web_helpers import csrf_token, key_for, post_headers, query_worklist


def _form(key: str, dose_report: str | None) -> dict:
    form = {
        "mode": "scheduled",
        "key": key,
        "template": "ct_generic",
        "routine": "ct_chest_plain",
        "action": "exam",
        "routine_series": ["0", "1", "5"],
        "routine_images": ["1", "1", "1"],
    }
    if dose_report is not None:
        form["dose_report"] = dose_report
    return form


def test_exam_page_offers_the_dose_report_choices_with_the_screen_first(client) -> None:
    html = client.get("/exam").text

    select = html.split('name="dose_report"', 1)[1].split("</select>", 1)[0]
    assert re.findall(r'<option value="([^"]+)"', select) == ["screen", "sr", "both"]
    assert "線量の報告（CT）" in html


def test_exam_with_sr_makes_the_sr_series(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")

    html = client.post("/exam", data=_form(key, "sr"), headers=post_headers(token)).text

    assert "撮影完了：3 画像" in html


def test_exam_with_both_has_one_more_image(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")

    html = client.post("/exam", data=_form(key, "both"), headers=post_headers(token)).text

    assert "撮影完了：4 画像" in html


def test_exam_without_the_field_keeps_the_dose_screen(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")

    html = client.post("/exam", data=_form(key, None), headers=post_headers(token)).text

    assert "撮影完了：3 画像" in html


def test_unknown_choice_is_refused_on_the_screen(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")

    html = client.post("/exam", data=_form(key, "xx"), headers=post_headers(token)).text

    assert "撮影完了" not in html


def test_sr_without_an_exposure_row_says_why(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    form = {**_form(key, "sr"), "routine_series": ["5"], "routine_images": ["1"]}

    html = client.post("/exam", data=form, headers=post_headers(token)).text

    assert "位置決めか軸位のシリーズも撮ってください" in html
