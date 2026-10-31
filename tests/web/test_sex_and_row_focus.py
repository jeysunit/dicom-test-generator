"""性別の 4 値の表示（男・女・その他・不明）と、丸い選択ボタンのある行に tabindex を付けない決め（ui-kit 1.2.5）."""

from __future__ import annotations

import re

import pytest
from web_helpers import key_for, query_worklist

from app.web.display import birth_label, sex_label


@pytest.mark.parametrize(
    ("value", "label"),
    [("M", "男"), ("F", "女"), ("O", "その他"), ("U", "不明"), ("", "不明"), ("X", "不明")],
)
def test_sex_label_never_shows_the_letter(value: str, label: str) -> None:
    assert sex_label(value) == label


def test_birth_label_for_a_sex_u_item_says_unknown(client) -> None:
    html = query_worklist(client)
    key = key_for(html, "A0002")  # 性別が空の予約（読むと U になる）
    detail = client.get(f"/worklist/item/{key}").text

    assert "不明" in detail
    assert not re.search(r">\s*U\s*<", detail)


def test_worklist_rows_with_a_radio_button_have_no_tabindex(client) -> None:
    html = query_worklist(client)
    table = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]

    rows = re.findall(r"<tr\b[^>]*>", table)
    assert rows
    assert all("tabindex" not in row for row in rows)
    # 選ぶ操作は丸い選択ボタンが受け持つ（同じ行で Tab が 2 回止まらない）
    assert table.count('type="radio"') == len(rows)


def test_exam_notice_names_an_unknown_sex(client) -> None:
    key = key_for(query_worklist(client), "A0002")

    page = client.get(f"/exam?key={key}").text

    assert "性別が不明です" in page
    assert "性別が空です" not in page


def test_birth_label_function_handles_u() -> None:
    from app.core.models import WorklistItem

    item = WorklistItem(key="k", birth_date="19800115", sex="U", scheduled_start_date="20261031")
    assert birth_label(item).endswith("不明")
