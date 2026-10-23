"""予約の撮影済みと撮り直し（追加撮影・RIS の新しい予約）の試験（docs/spec/12 の 6.3・ADR-0024）."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port
from pydicom import dcmread

from app.core.exceptions import GenerationError, ModalityConfigError, ValidationError
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.queue import QUEUE_DB_NAME, SendQueue
from app.modality.service import (
    NOT_TAKEN_MESSAGE,
    TAKEN_APPEND_MESSAGE,
    TAKEN_NEW_ORDER_MESSAGE,
    ExamRequest,
    ModalityService,
)
from app.modality.worklist_scu import WorklistQuery

A0001_STUDY_UID = "2.25.100000000000000000000000000000000001"


def _service(
    tmp_path: Path,
    worklist_port: int,
    *,
    retake_mode: str | None = None,
    mpps_port: int | None = None,
) -> ModalityService:
    data: dict = {
        "ae_title": "DTG_CT01",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {
            "ae_title": "RIS_TEST",
            "host": LOCALHOST,
            "port": worklist_port,
            "use_mpps": mpps_port is not None,
        },
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
    }
    if retake_mode is not None:
        data["retake_mode"] = retake_mode
    if mpps_port is not None:
        data["mpps"] = {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": mpps_port}
    return ModalityService(ModalityConfig.model_validate(data))


def _key(service: ModalityService, accession: str = "A0001") -> str:
    items = service.query_worklist(WorklistQuery()).items
    return next(i for i in items if i.accession_number == accession).key


def _exam(service: ModalityService, key: str, series: int = 1, **extra):
    return service.exam(ExamRequest(worklist_key=key, images_per_series=[1] * series, **extra))


def _first(files: list[str]):
    return dcmread(sorted(files)[0], stop_before_pixels=True)


def test_retake_mode_config(tmp_path, worklist_scp) -> None:
    assert _service(tmp_path, worklist_scp.port).config.retake_mode == "append"  # 既定
    assert _service(tmp_path, worklist_scp.port, retake_mode="new_order").config.retake_mode == (
        "new_order"
    )
    with pytest.raises(Exception) as exc_info:
        _service(tmp_path, worklist_scp.port, retake_mode="copy")
    assert "retake_mode" in str(exc_info.value)


def test_config_file_with_unknown_retake_mode_is_config_error(tmp_path) -> None:
    import yaml

    from app.modality.config import load_modality_config

    path = tmp_path / "app_config.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "modality": {
                    "ae_title": "DTG_CT01",
                    "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": 104},
                    "destinations": [
                        {"name": "P", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": 104}
                    ],
                    "default_destination": "P",
                    "retake_mode": "copy",
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ModalityConfigError):
        load_modality_config(path)


def test_exam_makes_the_order_taken_and_refuses_a_second_exam(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)
    key = _key(service)
    assert not service.is_taken(key)

    _exam(service, key)

    assert service.is_taken(key)
    with pytest.raises(ValidationError, match=TAKEN_APPEND_MESSAGE):
        _exam(service, key)
    # 予約を取得し直しても撮影済みは残る
    assert service.is_taken(_key(service))


def test_stopped_exam_is_not_taken(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port)
    key = _key(service)

    def stop(config, scheduled=None, progress_callback=None):
        raise GenerationError("stopped in the middle")

    monkeypatch.setattr(service._generator, "generate", stop)
    with pytest.raises(GenerationError):
        _exam(service, key)
    monkeypatch.undo()

    assert not service.is_taken(key)
    _exam(service, key)  # もう一度ふつうに撮れる
    assert service.is_taken(key)


def test_append_keeps_the_study_and_adds_series(tmp_path, worklist_scp) -> None:
    """追加撮影は同じ Study に新しいシリーズ（IHE RAD TF-2 4.6.4.1.2.3.3・TF-2x A.1-3）."""
    service = _service(tmp_path, worklist_scp.port)
    key = _key(service)
    first = _exam(service, key, series=2)
    # 最初の撮影を前の日にする（Study の日時を使い回すことを見るため）
    with closing(sqlite3.connect(tmp_path / "state" / QUEUE_DB_NAME)) as conn, conn:
        conn.execute(
            "UPDATE exam_records SET study_date = '20261022', study_time = '100000'"
            " WHERE worklist_key = ?",
            (key,),
        )

    appended = _exam(service, key, append=True)

    one, added = _first(first.files), _first(appended.files)
    assert added.StudyInstanceUID == one.StudyInstanceUID == A0001_STUDY_UID
    assert added.AccessionNumber == one.AccessionNumber == "A0001"
    assert (
        added.RequestAttributesSequence[0].ScheduledProcedureStepID
        == one.RequestAttributesSequence[0].ScheduledProcedureStepID
        == "SPS0001"
    )
    first_series = {str(dcmread(f, stop_before_pixels=True).SeriesInstanceUID) for f in first.files}
    assert str(added.SeriesInstanceUID) not in first_series
    assert (added.StudyDate, added.StudyTime) == ("20261022", "100000")  # IHE-A.3.3
    assert added.StudyDescription == one.StudyDescription
    assert int(added.SeriesNumber) == 3  # 前の撮影の 2 シリーズの続き
    # PPS の開始はこの撮影の日時（Study の日時とは別）
    assert added.PerformedProcedureStepStartDate == date.today().strftime("%Y%m%d")
    assert added.PerformedProcedureStepID != one.PerformedProcedureStepID


def test_append_without_study_uid_uses_the_first_generated_uid(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)
    key = _key(service, "A0002")  # 予約に Study Instance UID が無い

    first = _exam(service, key)
    appended = _exam(service, key, append=True)

    assert _first(appended.files).StudyInstanceUID == _first(first.files).StudyInstanceUID


def test_append_creates_a_new_mpps(tmp_path, worklist_scp, mpps_scp) -> None:
    """終わった MPPS は更新しない。追加撮影は新しい MPPS（PS3.4 F.7.2.2.2）."""
    service = _service(tmp_path, worklist_scp.port, mpps_port=mpps_scp.port)
    key = _key(service)

    first = _exam(service, key)
    appended = _exam(service, key, append=True)

    assert first.mpps.sop_instance_uid != appended.mpps.sop_instance_uid
    first_events = [event for event in mpps_scp.events if event[1] == first.mpps.sop_instance_uid]
    assert [op for op, _uid, _status in first_events] == ["N-CREATE", "N-SET"]
    added = mpps_scp.created[appended.mpps.sop_instance_uid]
    assert added.ScheduledStepAttributesSequence[0].ScheduledProcedureStepID == "SPS0001"


def test_append_needs_a_taken_order(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    with pytest.raises(ValidationError, match=NOT_TAKEN_MESSAGE):
        _exam(service, _key(service), append=True)
    with pytest.raises(ValidationError, match="緊急の患者"):
        service.exam(
            ExamRequest(
                emergency_patient=ScheduledPatient(patient_id="E1", patient_name="A^B"),
                append=True,
            )
        )


def test_new_order_mode_refuses_retakes_on_the_same_order(tmp_path, worklist_scp) -> None:
    """new_order：同じ予約は撮り直さず、RIS の新しい予約で撮る（ADR-0024）."""
    service = _service(tmp_path, worklist_scp.port, retake_mode="new_order")
    key = _key(service)
    _exam(service, key)

    with pytest.raises(ValidationError, match=TAKEN_NEW_ORDER_MESSAGE):
        _exam(service, key)
    with pytest.raises(ValidationError, match=TAKEN_NEW_ORDER_MESSAGE):
        _exam(service, key, append=True)


def test_new_order_mode_shoots_the_retake_order_from_ris(
    tmp_path, worklist_scp, worklist_items, mpps_scp
) -> None:
    service = _service(tmp_path, worklist_scp.port, retake_mode="new_order", mpps_port=mpps_scp.port)
    _exam(service, _key(service))
    # RIS が撮り直しの予約を作った（受付番号も Study Instance UID も RIS が出す）
    retake = dict(worklist_items[0])
    retake["accession_number"] = "A0001R"
    retake["study_instance_uid"] = "2.25.100000000000000000000000000000000099"
    retake["requested_procedure_id"] = "RP0001R"
    retake["sps"] = {**worklist_items[0]["sps"], "id": "SPS0001R"}
    worklist_scp.items = [*worklist_items, retake]

    result = _exam(service, _key(service, "A0001R"))

    image = _first(result.files)
    assert image.AccessionNumber == "A0001R"
    assert image.StudyInstanceUID == "2.25.100000000000000000000000000000000099"
    created = mpps_scp.created[result.mpps.sop_instance_uid]
    assert created.ScheduledStepAttributesSequence[0].AccessionNumber == "A0001R"


def test_old_study_uid_rows_become_taken(tmp_path) -> None:
    """撮影の記録が無かった前の版で撮った予約も、撮影済みとして移す."""
    db_path = tmp_path / QUEUE_DB_NAME
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE generated_study_uids (worklist_key TEXT PRIMARY KEY,"
            " study_instance_uid TEXT NOT NULL)"
        )
        conn.execute("INSERT INTO generated_study_uids VALUES ('abc', '2.25.1')")

    record = SendQueue(db_path).exam_record("abc")

    assert record is not None and record.study_instance_uid == "2.25.1"
    assert record.series_count == 0
