"""撮影の画面の「装置：なし」は装置を重ねない（docs/spec/12a の 10.5・ADR-0030）."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pydicom import dcmread
from web_helpers import (
    BASE_URL,
    csrf_token,
    key_for,
    modality_config,
    post_headers,
    query_worklist,
)

from app.core.models import WorklistItem
from app.web.app import create_app
from app.web.settings import WebConfig


@pytest.fixture
def ct_default_client(tmp_path, worklist_scp, storage_scp) -> TestClient:
    """設定の既定の装置が CT のプロファイルの画面."""
    config = modality_config(tmp_path, worklist_scp.port, storage_scp.port).model_copy(
        update={"default_profile": "dtg_synthetic_ct"}
    )
    app = create_app(
        config, config_path=tmp_path / "app_config.yaml", web=WebConfig(), password=None
    )
    return TestClient(app, base_url=BASE_URL)


def _selected_profile(html: str) -> str:
    select = html.split('name="profile"', 1)[1].split("</select>", 1)[0]
    return select.split(" selected>", 1)[0].rsplit('value="', 1)[1].split('"', 1)[0]


def _exam(client: TestClient, key: str, template: str, profile: str) -> str:
    token = csrf_token(client, f"/exam?key={key}")
    form = {
        "mode": "scheduled",
        "key": key,
        "template": template,
        "profile": profile,
        "routine": "manual",
        "series": "1",
        "images": "1",
        "action": "exam",
    }
    return client.post("/exam", data=form, headers=post_headers(token)).text


def _written(tmp_path) -> list:
    files = sorted((tmp_path / "output").rglob("*.dcm"))
    return [dcmread(path, stop_before_pixels=True) for path in files]


def test_mr_order_is_taken_from_the_screen_with_a_ct_default_profile(
    ct_default_client, tmp_path
) -> None:
    """画面は MR の予約に mr_generic と「なし」を選び、そのまま撮れる."""
    key = key_for(query_worklist(ct_default_client, station="any", modality=""), "A0003")
    page = ct_default_client.get(f"/exam?key={key}").text
    assert _selected_profile(page) == ""

    html = _exam(ct_default_client, key, "mr_generic", "")

    assert "撮影完了" in html, html
    assert "設定の既定の装置（dtg_synthetic_ct）は MR ではない" in html
    (ds,) = _written(tmp_path)
    assert ds.Modality == "MR"
    assert ds.ManufacturerModelName == "DTG Synthetic MR"  # 装置の値を重ねていない


def test_none_on_the_screen_does_not_apply_the_default_profile(
    ct_default_client, tmp_path
) -> None:
    """CT の予約でも、画面で「なし」を選べば設定の既定の装置を重ねない."""
    key = key_for(query_worklist(ct_default_client), "A0001")
    assert _selected_profile(ct_default_client.get(f"/exam?key={key}").text) == (
        "dtg_synthetic_ct"
    )

    html = _exam(ct_default_client, key, "ct_generic", "")

    assert "撮影完了" in html, html
    assert "dtg_synthetic_ct" not in html  # 重ねなかった知らせも出さない（選んだのは利用者）
    (ds,) = _written(tmp_path)
    assert ds.ManufacturerModelName != "DTG Synthetic CT 64"


def test_pt_order_is_taken_from_the_screen_with_a_ct_default_profile(
    ct_default_client, tmp_path
) -> None:
    """PT の予約も同じ：画面は petct_generic と「なし」を選び、そのまま撮れる（ADR-0032）."""
    item = WorklistItem(
        key="ptorder001",
        patient_name="PET^HANAKO",
        patient_id="P000099",
        birth_date="19600101",
        sex="F",
        study_instance_uid="2.25.100000000000000000000000000000000099",
        accession_number="A0099",
        requested_procedure_description="FDG PET/CT 全身",
        modality="PT",
    )
    ct_default_client.app.state.service.find_item = lambda key: item
    page = ct_default_client.get(f"/exam?key={item.key}").text
    assert '<option value="petct_generic" selected>' in page
    assert _selected_profile(page) == ""

    html = _exam(ct_default_client, item.key, "petct_generic", "")

    assert "撮影完了" in html, html
    assert "設定の既定の装置（dtg_synthetic_ct）は PT ではない" in html
    datasets = _written(tmp_path)
    assert {ds.Modality for ds in datasets} == {"PT"}
    assert {ds.ManufacturerModelName for ds in datasets} == {"DTG Synthetic PET/CT"}
