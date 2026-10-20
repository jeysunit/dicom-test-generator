"""画面の Phase 3c：PACS の頁の保管の確認の状態・撮影の頁の MPPS の状態（spec/12a の 10.5・10.6）."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from modality_peers import LOCALHOST, REPORT_WAIT_SECONDS, free_port
from web_helpers import BASE_URL, csrf_token, key_for, modality_config, post_headers, query_worklist

from app.modality.config import ModalityConfig
from app.web.app import create_app
from app.web.settings import WebConfig


def _config(
    tmp_path: Path,
    worklist_port: int,
    pacs_port: int,
    *,
    commitment: bool = False,
    listen_port: int | None = None,
    mpps_port: int | None = None,
) -> ModalityConfig:
    data = modality_config(tmp_path, worklist_port, pacs_port).model_dump()
    data["destinations"][0]["storage_commitment"] = commitment
    if listen_port is not None:
        data["listen"] = {"bind_address": LOCALHOST, "port": listen_port}
    if mpps_port is not None:
        data["worklist"]["use_mpps"] = True
        data["mpps"] = {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": mpps_port}
    return ModalityConfig.model_validate(data)


def _client(tmp_path: Path, config: ModalityConfig) -> TestClient:
    app = create_app(
        config,
        config_path=tmp_path / "app_config.yaml",
        web=WebConfig(),
        password=None,
    )
    return TestClient(app, base_url=BASE_URL)


def _exam_send(client: TestClient) -> str:
    key = key_for(query_worklist(client), "A0001")
    token = csrf_token(client, f"/exam?key={key}")
    form = {
        "mode": "scheduled",
        "key": key,
        "template": "ct_generic",
        "profile": "",
        "series": "1",
        "images": "2",
        "abnormal_level": "none",
        "charset": "auto",
        "action": "exam_send",
    }
    response = client.post("/exam", data=form, headers=post_headers(token))
    assert response.status_code == 200, response.text
    return response.text


def test_pacs_queue_shows_commitment_confirmed(tmp_path, worklist_scp, commitment_pacs) -> None:
    """画面のプロセスは待ち受けを立て、「送れた」で自動に求め、結果を待ち行列の列に出す."""
    listen_port = free_port()
    commitment_pacs.listener_port = listen_port
    config = _config(
        tmp_path, worklist_scp.port, commitment_pacs.port, commitment=True, listen_port=listen_port
    )
    # with で使うと、起動と終わりの手順（待ち受けを立てる・止める）が走る
    with _client(tmp_path, config) as client:
        _exam_send(client)
        assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)

        queue = client.get("/pacs/queue").text

    assert "保管の確認" in queue
    assert "確認済" in queue
    assert commitment_pacs.report_statuses == [0x0000]


def test_pacs_queue_shows_commitment_failed_count(tmp_path, worklist_scp, commitment_pacs) -> None:
    listen_port = free_port()
    commitment_pacs.listener_port = listen_port

    def fail_first(report) -> None:
        first = report.ReferencedSOPSequence[0]
        first.FailureReason = 0x0112
        report.FailedSOPSequence = [first]
        report.ReferencedSOPSequence = report.ReferencedSOPSequence[1:]

    commitment_pacs.mutate_report = fail_first
    config = _config(
        tmp_path, worklist_scp.port, commitment_pacs.port, commitment=True, listen_port=listen_port
    )
    with _client(tmp_path, config) as client:
        _exam_send(client)
        assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
        queue = client.get("/pacs/queue").text

    assert "確認の失敗" in queue
    assert "1 image(s) not committed" in queue


def test_pacs_queue_without_commitment_shows_dash(tmp_path, worklist_scp, storage_scp) -> None:
    with _client(tmp_path, _config(tmp_path, worklist_scp.port, storage_scp.port)) as client:
        _exam_send(client)
        queue = client.get("/pacs/queue").text
    assert "送信完了" in queue
    assert "確認" not in queue.split("<tbody>", 1)[1]


def test_exam_page_and_result_show_mpps(tmp_path, worklist_scp, storage_scp, mpps_scp) -> None:
    config = _config(tmp_path, worklist_scp.port, storage_scp.port, mpps_port=mpps_scp.port)
    with _client(tmp_path, config) as client:
        assert "MPPS：使う（RIS_TEST）" in client.get("/exam").text
        result = _exam_send(client)
    assert "MPPS：COMPLETED を送信しました" in result
    assert len(mpps_scp.sets) == 1


def test_exam_result_shows_mpps_failure(tmp_path, worklist_scp, storage_scp) -> None:
    config = _config(tmp_path, worklist_scp.port, storage_scp.port, mpps_port=free_port())
    with _client(tmp_path, config) as client:
        result = _exam_send(client)
    assert "MPPS の送信に失敗しました" in result
    assert "mpps retry" in result
    # MPPS を送れなくても撮影と送信は止めない
    assert "撮影完了" in result
    assert "送信完了" in result


def test_exam_page_without_mpps(tmp_path, worklist_scp, storage_scp) -> None:
    with _client(tmp_path, _config(tmp_path, worklist_scp.port, storage_scp.port)) as client:
        page = client.get("/exam").text
        result = _exam_send(client)
    assert "MPPS：使わない" in page
    assert "MPPS：" not in result


def test_settings_page_shows_listener_and_mpps_peer(tmp_path, worklist_scp, storage_scp) -> None:
    config = _config(
        tmp_path,
        worklist_scp.port,
        storage_scp.port,
        commitment=True,
        mpps_port=4243,
        listen_port=free_port(),
    )
    with _client(tmp_path, config) as client:
        page = client.get("/settings").text
    assert "DicomModalities" in page
    assert "127.0.0.1:4243" in page
    assert "600" in page
