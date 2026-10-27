"""DTG が名乗る装置の切り替え（docs/spec/12 の 12 章・ADR-0023）の試験.

手元の偽の RIS・PACS・MPPS の相手（tests/modality_peers.py）が受けた要求の Calling AE
Title を見て、選んだ装置の AEタイトルで名乗ることを確かめる。
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from modality_peers import (
    LOCALHOST,
    REPORT_WAIT_SECONDS,
    StorageRecorder,
    free_port,
    start_mpps_recorder,
    start_server,
)
from pydicom import dcmread
from pynetdicom import AE, AllStoragePresentationContexts, evt
from pynetdicom.sop_class import Verification

from app.core.exceptions import ModalityConfigError, ModalityError
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.mpps_queue import MppsQueue
from app.modality.queue import QUEUE_DB_NAME, SendQueue
from app.modality.service import ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery

CT1 = {"name": "CT1号機", "ae_title": "DTG_CT01", "station_name": "CT01_ROOM1"}
MR1 = {"name": "MR1号機", "ae_title": "DTG_MR01", "station_name": "MR01_ROOM2"}
STATUS_PROCESSING_FAILURE = 0x0110


def _config(
    tmp_path: Path,
    worklist_port: int,
    storage_port: int,
    *,
    mpps_port: int | None = None,
    listen_port: int | None = None,
    storage_commitment: bool = False,
) -> ModalityConfig:
    data: dict = {
        "stations": [CT1, MR1],
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {
            "ae_title": "RIS_TEST",
            "host": LOCALHOST,
            "port": worklist_port,
            "timeout_seconds": 5,
            "use_mpps": mpps_port is not None,
        },
        "destinations": [
            {
                "name": "PACS_TEST",
                "ae_title": "PACS_TEST",
                "host": LOCALHOST,
                "port": storage_port,
                "timeout_seconds": 5,
                "storage_commitment": storage_commitment,
            }
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
    }
    if mpps_port is not None:
        data["mpps"] = {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": mpps_port}
    if listen_port is not None:
        data["listen"] = {"bind_address": LOCALHOST, "port": listen_port}
    return ModalityConfig.model_validate(data)


def _emergency(service: ModalityService):
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    return service.exam(ExamRequest(emergency_patient=patient, pixel_mode="simple_text"))


def test_selected_station_is_recorded_and_read_back(tmp_path, worklist_scp, storage_scp) -> None:
    config = _config(tmp_path, worklist_scp.port, storage_scp.port)
    service = ModalityService(config)
    assert service.current_station().name == "CT1号機"  # 標準は一覧の先頭

    service.select_station("MR1号機")
    # 一時のファイルに書いてから置き換えるので、書きかけのファイルは残らない
    assert sorted(p.name for p in (tmp_path / "state").iterdir() if p.suffix != ".sqlite3") == [
        "station.json"
    ]

    # 画面を再起動しても、CLI でも、記録した装置を使う
    assert ModalityService(config).current_station().ae_title == "DTG_MR01"
    # `--station` はそのコマンドだけに効き、記録は変えない
    once = ModalityService(config, station="CT1号機")
    assert once.current_station().ae_title == "DTG_CT01"
    assert ModalityService(config).current_station().name == "MR1号機"


def test_unknown_station_names_are_config_errors(tmp_path, worklist_scp, storage_scp) -> None:
    config = _config(tmp_path, worklist_scp.port, storage_scp.port)

    with pytest.raises(ModalityConfigError):
        ModalityService(config, station="XR9号機")
    with pytest.raises(ModalityConfigError):
        ModalityService(config).select_station("XR9号機")


def test_recorded_station_missing_from_config_falls_back(tmp_path, worklist_scp, storage_scp) -> None:
    config = _config(tmp_path, worklist_scp.port, storage_scp.port)
    state = tmp_path / "state"
    state.mkdir()
    (state / "station.json").write_text('{"name": "XR9号機"}', encoding="utf-8")

    service = ModalityService(config)

    assert service.current_station().name == "CT1号機"
    assert "XR9号機" in service.station_notice() and "CT1号機" in service.station_notice()


def test_station_is_not_switched_while_exam_or_send_runs(
    tmp_path, worklist_scp, storage_scp
) -> None:
    service = ModalityService(_config(tmp_path, worklist_scp.port, storage_scp.port))
    with service._exam_lock:
        with pytest.raises(ModalityError, match="撮影・送信の最中"):
            service.select_station("MR1号機")

    exam = _emergency(service)
    job_id = service.queue.add_job(exam.output_dir, "PACS_TEST", exam.files)
    service.queue.mark_sending(job_id)
    with pytest.raises(ModalityError, match="撮影・送信の最中"):
        service.select_station("MR1号機")
    assert service.current_station().name == "CT1号機"


def test_selected_station_names_itself_in_every_association(
    tmp_path, worklist_scp, storage_scp, mpps_scp
) -> None:
    """C-FIND・C-STORE・C-ECHO・MPPS の Calling AE Title と、画像・MPPS の値（4・6.2・8.4）."""
    service = ModalityService(
        _config(tmp_path, worklist_scp.port, storage_scp.port, mpps_port=mpps_scp.port)
    )
    service.select_station("MR1号機")

    assert service.default_query(service.today()).station_ae_title == "DTG_MR01"
    item = service.query_worklist(WorklistQuery(accession_number="A0001")).items[0]
    service.echo()
    exam = service.exam(ExamRequest(worklist_key=item.key, pixel_mode="simple_text"))
    sent = service.send_exam_output(exam.output_dir)

    assert worklist_scp.calling_ae_titles[-1] == "DTG_MR01"
    assert set(storage_scp.calling_ae_titles) == {"DTG_MR01"}  # C-ECHO は記録しない
    assert set(mpps_scp.calling_ae_titles) == {"DTG_MR01"}
    created = mpps_scp.created[exam.mpps.sop_instance_uid]
    assert created.PerformedStationAETitle == "DTG_MR01"
    assert created.PerformedStationName == "MR01_ROOM2"
    image = dcmread(exam.files[0], stop_before_pixels=True)
    assert image.StationName == "MR01_ROOM2"
    assert image.file_meta.SourceApplicationEntityTitle == "DTG_MR01"
    assert service.queue.get_job(sent.job_id).calling_ae_title == "DTG_MR01"


def test_station_name_of_the_station_wins_over_the_profile(
    tmp_path, worklist_scp, storage_scp
) -> None:
    """装置の Station Name を、装置のプロファイルの値より先にする。空ならプロファイル（ADR-0023）."""
    config = _config(tmp_path, worklist_scp.port, storage_scp.port)
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")

    def station_name_with(service: ModalityService) -> str:
        exam = service.exam(
            ExamRequest(
                emergency_patient=patient, profile="dtg_synthetic_ct", pixel_mode="simple_text"
            )
        )
        return str(dcmread(exam.files[0], stop_before_pixels=True).StationName)

    assert station_name_with(ModalityService(config)) == "CT01_ROOM1"
    blank = config.model_copy(
        update={"stations": [config.stations[0].model_copy(update={"station_name": ""})]}
    )
    assert station_name_with(ModalityService(blank)) == "DTGCT01"  # プロファイルの値


def test_images_are_sent_as_the_station_that_made_them(
    tmp_path, worklist_scp, storage_scp
) -> None:
    """撮った後に切り替えても、画像を作った装置の AEタイトルで送る（8.2・ADR-0023）."""
    service = ModalityService(_config(tmp_path, worklist_scp.port, storage_scp.port))
    exam = _emergency(service)  # CT1号機で撮る
    service.select_station("MR1号機")

    service.send_exam_output(exam.output_dir)

    assert storage_scp.calling_ae_titles == ["DTG_CT01"]


def test_select_station_and_exam_do_not_interleave(tmp_path, worklist_scp, storage_scp) -> None:
    """切り替えは撮影と同じ錠を取る。切り替えの最中に撮影は始まらない."""
    service = ModalityService(_config(tmp_path, worklist_scp.port, storage_scp.port))
    real_write = service._write_state
    seen = []

    def write_and_try_exam(path, data):
        with pytest.raises(ModalityError, match="ほかの撮影"):
            _emergency(service)
        seen.append(data)
        real_write(path, data)

    service._write_state = write_and_try_exam  # type: ignore[method-assign]
    service.select_station("MR1号機")

    assert seen == [{"name": "MR1号機"}]


def test_resend_after_switching_uses_the_ae_of_the_job(tmp_path, worklist_scp, storage_scp) -> None:
    service = ModalityService(_config(tmp_path, worklist_scp.port, storage_scp.port))
    exam = _emergency(service)
    storage_scp.status = 0xA700
    failed = service.send(exam.output_dir)
    assert failed.status == "failed"

    service.select_station("MR1号機")
    storage_scp.status = 0x0000
    [retried] = service.retry(job_id=failed.job_id)
    [resent] = service.retry(job_id=retried.job_id)  # 送信完了の件の再送信（新しい件）

    assert retried.status == "sent" and resent.status == "sent"
    assert set(storage_scp.calling_ae_titles) == {"DTG_CT01"}
    assert service.queue.get_job(resent.job_id).calling_ae_title == "DTG_CT01"


def test_mpps_retry_after_switching_uses_the_ae_of_the_exam(tmp_path, worklist_scp) -> None:
    down_port = free_port()
    service = ModalityService(_config(tmp_path, worklist_scp.port, free_port(), mpps_port=down_port))
    item = service.query_worklist(WorklistQuery(accession_number="A0001")).items[0]
    exam = service.exam(ExamRequest(worklist_key=item.key, pixel_mode="simple_text"))
    assert exam.mpps is not None and exam.mpps.sent is False

    service.select_station("MR1号機")
    back, server = start_mpps_recorder(down_port)
    try:
        service.retry_mpps()
    finally:
        server.shutdown()

    assert back.calling_ae_titles == ["DTG_CT01", "DTG_CT01"]  # N-CREATE と N-SET


def test_old_queue_rows_get_the_default_ae_title(tmp_path) -> None:
    """AEタイトルの列が無い前の版の待ち行列は、標準の装置の AEタイトルで埋める."""
    db_path = tmp_path / QUEUE_DB_NAME
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL, folder TEXT NOT NULL, destination TEXT NOT NULL,"
            " accession_number TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,"
            " attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '',"
            " send_token TEXT NOT NULL DEFAULT '')"
        )
        conn.execute(
            "INSERT INTO jobs (created_at, updated_at, folder, destination, status)"
            " VALUES ('2026-10-01T00:00:00', '2026-10-01T00:00:00', 'exam', 'PACS_TEST', 'sent')"
        )

    queue = SendQueue(db_path, legacy_ae_title="DTG_CT01")

    assert queue.get_job(1).calling_ae_title == "DTG_CT01"


def test_old_mpps_rows_get_the_default_ae_title(tmp_path) -> None:
    db_path = tmp_path / QUEUE_DB_NAME
    MppsQueue(db_path)  # 今の版で表を作ってから、列の無い前の版にする
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute("ALTER TABLE mpps DROP COLUMN calling_ae_title")
        conn.execute(
            "INSERT INTO mpps (created_at, updated_at, sop_instance_uid, state, create_json,"
            " peer_ae_title, peer_host, peer_port) VALUES ('t', 't', '2.25.1', 'IN PROGRESS',"
            " '{}', 'RIS_TEST', '127.0.0.1', 104)"
        )

    queue = MppsQueue(db_path, legacy_ae_title="DTG_CT01")

    assert queue.get(1).calling_ae_title == "DTG_CT01"


def test_commitment_report_to_the_requesting_station_after_switching(
    tmp_path, worklist_scp, commitment_pacs
) -> None:
    """切り替えた後に、前の装置あてに届いた結果を受ける。ほかの装置あては採らない（8.3）."""
    listen_port = free_port()
    commitment_pacs.listener_port = listen_port
    commitment_pacs.report_delay = 0.5  # 結果が要求より後に届く形にする
    service = ModalityService(
        _config(
            tmp_path,
            worklist_scp.port,
            commitment_pacs.port,
            listen_port=listen_port,
            storage_commitment=True,
        )
    )
    listener = service.start_commitment_listener()
    try:
        job_id = service.send(_emergency(service).output_dir).job_id
        state = service.request_commitment(job_id)
        service.select_station("MR1号機")
        final = service.wait_commitment(state.transaction_uid, 5)

        assert commitment_pacs.action_calling_ae_titles == ["DTG_CT01"]
        assert final.status == "confirmed"

        # 1回目の結果を送る手順が終わってから、2回目を数える
        assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
        commitment_pacs.reported.clear()
        # 件は MR1号機で作ったので、要求も MR1号機で送る。結果が CT1号機あてに届いたら、
        # その要求の結果にはしない
        second_job = service.send(_emergency(service).output_dir).job_id
        service.select_station("CT1号機")
        waiting = service.request_commitment(second_job)
        assert commitment_pacs.reported.wait(REPORT_WAIT_SECONDS)
        assert commitment_pacs.report_statuses[-1] == STATUS_PROCESSING_FAILURE
        assert service.wait_commitment(waiting.transaction_uid, 0).status == "waiting"
    finally:
        listener.shutdown()


def test_unregistered_calling_ae_title_is_told(tmp_path, worklist_scp) -> None:
    """相手が理由 3（calling-AE-title-not-recognized）で断ったら知らせる（PS3.8 9.3.4）."""
    pacs = StorageRecorder()
    ae = AE(ae_title=pacs.ae_title)
    ae.supported_contexts = AllStoragePresentationContexts
    ae.add_supported_context(Verification)
    ae.require_calling_aet = ["DTG_CT01"]  # MR1号機は登録されていない
    server, port = start_server(ae, [(evt.EVT_C_STORE, pacs.handle_store)])
    try:
        service = ModalityService(_config(tmp_path, worklist_scp.port, port))
        service.select_station("MR1号機")
        result = service.send(_emergency(service).output_dir)
    finally:
        server.shutdown()

    assert result.status == "failed"
    assert "相手が AEタイトル DTG_MR01 を受け付けませんでした" in result.error
    assert "この装置の AEタイトルを登録してください" in result.error
    assert "peer=" not in result.error  # 利用者が読む知らせに内部の値を付けない
    assert pacs.received == []
