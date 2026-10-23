"""画面の装置の切り替え（docs/spec/12a の 10.3・10.7・ADR-0023）."""

from __future__ import annotations

from fastapi.testclient import TestClient
from web_helpers import BASE_URL, csrf_token, modality_config, post_headers
from web_helpers import query_worklist as _query

from app.modality.config import ModalityConfig
from app.web.app import create_app
from app.web.settings import WebConfig

STATIONS = [
    {"name": "CT1号機", "ae_title": "DTG_CT01", "station_name": "DTG_CT01"},
    {"name": "MR1号機", "ae_title": "DTG_MR01", "station_name": "DTG_MR01"},
]


def _client(tmp_path, worklist_port: int, storage_port: int) -> TestClient:
    data = modality_config(tmp_path, worklist_port, storage_port).model_dump()
    del data["ae_title"], data["station_name"], data["default_station"]
    data["stations"] = STATIONS
    app = create_app(
        ModalityConfig.model_validate(data),
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(),
        password=None,
    )
    return TestClient(app, base_url=BASE_URL)


def test_band_offers_the_stations(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)

    html = client.get("/worklist").text

    assert 'hx-post="/station"' in html
    assert ">CT1号機（DTG_CT01）</option>" in html.replace(" selected", "")
    assert "MR1号機（DTG_MR01）" in html
    assert "この装置で絞る（DTG_CT01）" in html


def test_switching_the_station_reloads_and_is_used(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client)

    switched = client.post("/station", data={"station": "MR1号機"}, headers=post_headers(token))

    assert switched.status_code == 200
    assert switched.headers.get("HX-Refresh") == "true"
    page = client.get("/worklist").text
    assert '<option value="MR1号機" selected>' in page
    assert "この装置で絞る（DTG_MR01）" in page
    _query(client)
    assert worklist_scp.calling_ae_titles[-1] == "DTG_MR01"
    assert worklist_scp.queries[-1].ScheduledProcedureStepSequence[0].ScheduledStationAETitle == (
        "DTG_MR01"
    )
    # 画面を起動し直しても、選んだ装置を使う
    again = _client(tmp_path, worklist_scp.port, storage_scp.port)
    assert '<option value="MR1号機" selected>' in again.get("/worklist").text


def test_switching_during_an_exam_is_refused(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    token = csrf_token(client)
    service = client.app.state.service

    with service._exam_lock:
        refused = client.post(
            "/station", data={"station": "MR1号機"}, headers=post_headers(token)
        )

    assert "HX-Refresh" not in refused.headers
    assert "撮影・送信の最中は装置を切り替えられません" in refused.text
    assert '<option value="CT1号機" selected>' in refused.text
    assert service.current_station().name == "CT1号機"


def test_queue_details_show_the_calling_ae_title(tmp_path, worklist_scp, storage_scp) -> None:
    """再送で名乗る AE タイトルを、送信ジョブの詳細に出す（docs/spec/12a の 10.6）."""
    from app.core.models import ScheduledPatient
    from app.modality.service import ExamRequest

    client = _client(tmp_path, worklist_scp.port, storage_scp.port)
    service = client.app.state.service
    exam = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E0001", patient_name="A^B"),
            pixel_mode="simple_text",
        )
    )
    service.send(exam.output_dir)

    html = client.get("/pacs/queue").text

    assert '<dt>名乗る AE タイトル</dt><dd class="font-mono">DTG_CT01</dd>' in html


def test_settings_lists_the_stations_and_registration(tmp_path, worklist_scp, storage_scp) -> None:
    client = _client(tmp_path, worklist_scp.port, storage_scp.port)

    html = client.get("/settings").text

    assert "CT1号機（既定・使用中）" in html
    assert "MR1号機</dt>" in html
    assert "DTG_MR01" in html
    assert "相手の側に登録してください" in html
