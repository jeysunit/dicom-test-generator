"""行の操作の列：切らずに、表の右端へ固定する（docs/spec/12a の 10.2「表」の操作の列）.

幅が足りなくて表が横に動くときも、操作のボタンが見えて押せるようにする。ブラウザでの
寸法（幅 390・1280 で、ボタンが表の包みの中にあり最前面にある）は、この試験では測れない
（ブラウザの試験の仕組みを持たない）。ここでは、そのための CSS の規則と、3 つの表の最後の列の
印（`.act`）が、組み立てた CSS とテンプレートの両方にあることを確かめる。
"""

from __future__ import annotations

import re
from pathlib import Path

from web_helpers import key_for, query_worklist

from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest

ROOT = Path(__file__).resolve().parents[2]
INPUT_CSS = ROOT / "app" / "web" / "styles" / "input.css"
APP_CSS = ROOT / "app" / "web" / "static" / "app.css"


def _rule(css: str, selector: str) -> str:
    """selector を末尾に持つ規則の中身を、空白を除いてつないだもの."""
    bodies = re.findall(r"(?:^|[\s,}])" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert bodies, f"{selector} の規則が無い"
    return "".join(re.sub(r"\s+", "", body) for body in bodies)


def test_action_column_is_pinned_to_the_right_edge() -> None:
    source = INPUT_CSS.read_text(encoding="utf-8")
    built = APP_CSS.read_text(encoding="utf-8")

    pinned = re.sub(r"\s+", "", source.split(".tbl th.act,", 1)[1].split("}", 1)[0])
    assert "position:sticky" in pinned
    assert "right:0" in pinned
    # 組み立てた CSS にも入っている（commit した app.css と作り直しが合っていることは CI が見る）
    assert ".tbl td.act" in built and ".tbl th.act" in built


def test_action_column_follows_the_row_background() -> None:
    source = INPUT_CSS.read_text(encoding="utf-8")

    assert "var(--color-background)" in _rule(source, ".tbl td.act")
    assert "var(--color-muted)" in _rule(source, ".tbl tbody tr:hover td.act")
    selected = _rule(source, '.tbl tbody tr[aria-selected="true"]:hover td.act')
    assert "var(--color-selected-strong)" in selected


def _last_cells(html: str, table_marker: str) -> tuple[str, str]:
    """表の見出しの最後の th と、最初の行の最後の td の開始タグ."""
    table = html.split(table_marker, 1)[1].split("</table>", 1)[0]
    heads = re.findall(r"<th\b[^>]*>", table)
    cells = re.findall(r"<td\b[^>]*>", table.split("<tbody>", 1)[1].split("</tr>", 1)[0])
    return heads[-1], cells[-1]


def test_connection_table_marks_its_action_column(client) -> None:
    head, cell = _last_cells(client.get("/pacs").text, '<table class="tbl conn">')

    assert 'class="act"' in head
    assert 'class="act"' in cell


def test_job_table_marks_its_action_column(client) -> None:
    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="P1", patient_name="A^B"),
            pixel_mode="simple_text",
        )
    )
    service.send(exam.output_dir)

    head, cell = _last_cells(client.get("/pacs/queue").text, '<table class="tbl">')

    assert 'class="act"' in head
    assert 'class="act"' in cell


def test_routine_table_marks_its_action_column(client) -> None:
    key = key_for(query_worklist(client), "A0001")

    head, cell = _last_cells(client.get(f"/exam?key={key}").text, 'class="tbl routine-table"')

    assert 'class="act"' in head
    assert 'class="act"' in cell
