"""撮影の画面で CR・DX の予約と緊急の患者を撮る（ADR-0034）."""

from __future__ import annotations

import re

from pydicom import dcmread
from web_helpers import csrf_token, post_headers

from app.core.models import WorklistItem

CR_ORDER = WorklistItem(
    key="crorder001",
    patient_name="XRAY^HANAKO",
    patient_id="P000077",
    birth_date="19700101",
    sex="F",
    study_instance_uid="2.25.100000000000000000000000000000000077",
    accession_number="A0077",
    requested_procedure_description="胸部 X 線",
    modality="CR",
)


def _selected(html: str, name: str) -> str:
    select = html.split(f'name="{name}"', 1)[1].split("</select>", 1)[0]
    return re.search(r'<option value="([^"]+)" selected>', select).group(1)


def _written(tmp_path) -> list:
    files = sorted((tmp_path / "output").rglob("*.dcm"))
    return [dcmread(path, stop_before_pixels=True) for path in files]


def test_cr_order_opens_with_the_cr_template_and_routine(client) -> None:
    client.app.state.service.find_item = lambda key: CR_ORDER

    html = client.get(f"/exam?key={CR_ORDER.key}").text

    assert _selected(html, "template") == "cr_generic"
    assert _selected(html, "routine") == "cr_chest"
    assert "予約は CR" not in html  # 撮影は押せる


def test_cr_order_is_taken_from_the_screen(client, tmp_path) -> None:
    client.app.state.service.find_item = lambda key: CR_ORDER
    token = csrf_token(client, f"/exam?key={CR_ORDER.key}")
    form = {
        "mode": "scheduled",
        "key": CR_ORDER.key,
        "template": "cr_generic",
        "profile": "",
        "routine": "cr_chest",
        "routine_series": ["0", "1"],
        "routine_images": ["1", "1"],
        "action": "exam",
    }

    html = client.post("/exam", data=form, headers=post_headers(token)).text

    assert "撮影完了" in html, html
    datasets = _written(tmp_path)
    assert [(ds.Modality, ds.ViewPosition, int(ds.SeriesNumber)) for ds in datasets] == [
        ("CR", "PA", 1),
        ("CR", "LL", 2),
    ]
    assert {ds.AccessionNumber for ds in datasets} == {"A0077"}


def test_emergency_patient_with_the_dx_template(client, tmp_path) -> None:
    token = csrf_token(client, "/exam")
    form = {
        "mode": "emergency",
        "patient_id": "E0001",
        "name_alphabetic": "KINKYU TARO",
        "name_ideographic": "緊急 太郎",
        "sex": "M",
        "template": "dx_generic",
        "profile": "",
        "routine": "dx_chest",
        "routine_series": ["0"],
        "routine_images": ["2"],
        "action": "exam",
    }

    html = client.post("/exam", data=form, headers=post_headers(token)).text

    assert "撮影完了" in html, html
    datasets = _written(tmp_path)
    assert [(ds.Modality, ds.ViewPosition) for ds in datasets] == [("DX", "PA"), ("DX", "LL")]
    assert len({ds.SeriesInstanceUID for ds in datasets}) == 1
    assert {ds.PatientID for ds in datasets} == {"E0001"}
