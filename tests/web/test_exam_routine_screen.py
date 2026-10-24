"""撮影の画面のルーチン（docs/spec/12a の 10.5・ADR-0025）."""

from __future__ import annotations

import re

from web_helpers import csrf_token, key_for, post_headers, query_worklist


def _selected_routine(html: str) -> str:
    select = html.split('name="routine"', 1)[1].split("</select>", 1)[0]
    return re.search(r'<option value="([^"]+)" selected>', select).group(1)


def _row_images(html: str) -> list[int]:
    return [int(v) for v in re.findall(r'name="routine_images" value="(\d+)"', html)]


def test_exam_page_selects_the_matched_routine(client) -> None:
    key = key_for(query_worklist(client), "A0001")  # 胸部 CT

    html = client.get(f"/exam?key={key}").text

    assert _selected_routine(html) == "ct_chest_plain"
    assert _row_images(html) == [1, 60, 60, 300, 83, 1]
    for label in ("位置決め", "軸位", "冠状断", "線量の画面"):
        assert f">{label}</td>" in html
    # 選択肢はテンプレートのモダリティ（CT）のルーチンと、最後の「手で入れる」
    select = html.split('name="routine"', 1)[1].split("</select>", 1)[0]
    assert select.rstrip().endswith('<option value="manual">手で入れる</option>')
    assert "mr_head" not in select


def test_head_order_selects_the_head_routine(client) -> None:
    key = key_for(query_worklist(client), "A0002")  # 頭部 CT

    assert _selected_routine(client.get(f"/exam?key={key}").text) == "ct_head_plain"


def test_emergency_page_uses_the_default_routine(client) -> None:
    assert _selected_routine(client.get("/exam").text) == "ct_chest_plain"


def test_choosing_another_routine_redraws_the_rows(client) -> None:
    html = client.get("/exam/routine?template=ct_generic&routine=ct_head_plain").text

    assert _selected_routine(html) == "ct_head_plain"
    assert _row_images(html) == [1, 30, 60, 1]


def test_manual_shows_the_series_fields(client) -> None:
    html = client.get("/exam/routine?template=ct_generic&routine=manual").text

    assert _selected_routine(html) == "manual"
    assert 'name="series"' in html and 'name="images"' in html
    assert "routine_images" not in html


def test_mr_order_lists_mr_routines(client) -> None:
    key = key_for(query_worklist(client, station="any", modality=""), "A0003")  # 頭部 MR

    html = client.get(f"/exam?key={key}").text

    assert _selected_routine(html) == "mr_head"
    assert "予約は MR、テンプレートは CT です" in html  # 撮影は押せない（今の決まり）


def test_unreadable_routines_are_reported(client, tmp_path) -> None:
    """ルーチンを読めなければ「手で入れる」にし、黙らずに理由を出す."""
    from app.services.routine_loader import RoutineLoaderService

    broken = tmp_path / "routines"
    broken.mkdir()
    (broken / "bad.yaml").write_text("name: [", encoding="utf-8")
    client.app.state.service._routine_loader = RoutineLoaderService(broken)

    html = client.get("/exam").text

    assert _selected_routine(html) == "manual"
    assert "ルーチンを読めません" in html and "bad.yaml" in html


def test_single_series_routine_cannot_lose_its_row(client) -> None:
    html = client.get("/exam/routine?template=ct_generic&routine=ct_chest_plain").text
    assert 'title="最後の1行は外せません"' not in html

    service = client.app.state.service
    routine = service.routine("ct_head_plain").model_copy(
        update={"series": service.routine("ct_head_plain").series[:1]}
    )
    service.routines = lambda modality: [routine]  # 1シリーズだけのルーチン

    one = client.get("/exam/routine?template=ct_generic&routine=ct_head_plain").text

    assert "disabled" in one.split("data-remove-series", 1)[1].split(">", 1)[0]


def test_exam_with_routine_rows(client) -> None:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    form = {
        "mode": "scheduled",
        "key": key,
        "template": "ct_generic",
        "routine": "ct_chest_plain",
        "action": "exam",
        # 3 行目（Lung 5mm）を外し、画像数を減らした
        "routine_series": ["0", "1", "3", "4", "5"],
        "routine_images": ["1", "2", "2", "2", "1"],
    }

    html = client.post("/exam", data=form, headers=post_headers(token)).text

    assert "撮影完了：8 画像" in html
