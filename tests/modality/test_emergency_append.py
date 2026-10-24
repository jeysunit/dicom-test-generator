"""緊急の患者の追加撮影：Study と仮の患者を引き継ぐ."""

import sqlite3
from pathlib import Path
from contextlib import closing

import pytest
from pydicom import dcmread

from app.core.exceptions import GenerationError, ModalityError, ValidationError
from app.core.models import ScheduledPatient
from app.modality.queue import QUEUE_DB_NAME, SendQueue
from app.modality.service import ExamRequest, ExamResult, ModalityService
from .test_service import _service


PATIENT = ScheduledPatient(
    patient_id="E1", patient_name="UNKNOWN^ONE", birth_date="20000101", sex="O"
)


def _exam(service: ModalityService, **extra) -> ExamResult:
    return service.exam(ExamRequest(
        emergency_patient=extra.pop("patient", PATIENT), pixel_mode="simple_text", **extra
    ))


def _snapshot(service: ModalityService, tmp_path: Path) -> tuple:
    with closing(sqlite3.connect(tmp_path / "state" / QUEUE_DB_NAME)) as conn:
        records = [conn.execute(f"SELECT * FROM {table}").fetchall() for table in (
            "emergency_exams", "exam_records", "exam_series_numbers", "counters"
        )]
    return sorted(tmp_path.rglob("*.dcm")), records, service.list_mpps()


@pytest.mark.parametrize("description", ["First exam", ""])
def test_emergency_append_preserves_study_and_patient(tmp_path, description) -> None:
    service = _service(tmp_path, 104)
    first = _exam(service, images_per_series=[1, 1], study_description=description)
    uid = first.study_instance_uid
    with closing(sqlite3.connect(tmp_path / "state" / QUEUE_DB_NAME)) as conn, conn:
        conn.execute(
            "UPDATE exam_records SET study_date = '20200101', study_time = '101112'"
        )
    # 別のプロセスでも読み直せ、生年月日と性別の訂正では最初の値を変えない
    service = ModalityService(service.config)
    patient = PATIENT.model_copy(update={"birth_date": "19990101", "sex": "M"})
    added = _exam(service, append=True, emergency_study_instance_uid=uid,
                  patient=patient, study_description="Changed")
    one, two = (dcmread(result.files[0]) for result in (first, added))
    for name in ("StudyInstanceUID", "StudyID", "PatientID", "PatientName",
                 "PatientBirthDate", "PatientSex"):
        assert getattr(one, name) == getattr(two, name)
    assert added.study_instance_uid == uid
    assert two.AccessionNumber == ""
    assert "RequestAttributesSequence" not in two
    assert "ReferencedStudySequence" not in two
    assert two.SeriesInstanceUID not in {dcmread(f).SeriesInstanceUID for f in first.files}
    assert two.SeriesNumber == 3
    assert (two.StudyDate, two.StudyTime) == ("20200101", "101112")
    assert two.get("StudyDescription", "") == one.get("StudyDescription", "")
    assert two.PerformedProcedureStepStartDate != two.StudyDate
    third = _exam(service, append=True, emergency_study_instance_uid=uid)
    assert dcmread(third.files[0]).SeriesNumber == 4


@pytest.mark.parametrize("case", ["missing", "unknown", "id", "name", "scheduled", "no_append", "busy"])
def test_emergency_append_refused_without_side_effects(tmp_path, case) -> None:
    service = _service(tmp_path, 104)
    uid = _exam(service).study_instance_uid
    extra = {"append": True, "emergency_study_instance_uid": uid}
    error = ValidationError
    if case == "missing":
        extra.pop("emergency_study_instance_uid")
    elif case == "unknown":
        extra["emergency_study_instance_uid"] = "2.25.999"
    elif case in ("id", "name"):
        field = "patient_id" if case == "id" else "patient_name"
        extra["patient"] = PATIENT.model_copy(update={field: "OTHER"})
    elif case == "scheduled":
        service.queue.record_exam("worklist-key", "2.25.123", "20200101", "101112", "", 1)
        extra["emergency_study_instance_uid"] = "2.25.123"
    elif case == "no_append":
        extra["append"] = False
    else:
        other = SendQueue(tmp_path / "state" / QUEUE_DB_NAME)
        assert other.claim_exam(f"emergency:{uid}") is not None
        error = ModalityError
    before = _snapshot(service, tmp_path)
    with pytest.raises(error):
        _exam(service, mpps=True, **extra)
    assert _snapshot(service, tmp_path) == before


def test_failed_emergency_exam_is_not_recorded(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, 104)
    seen = []

    def stop(config, scheduled, progress_callback):
        seen.append(scheduled.study_instance_uid)
        raise GenerationError("stopped")

    monkeypatch.setattr(service._generator, "generate", stop)
    with pytest.raises(GenerationError):
        _exam(service)
    assert seen[0]
    assert service.queue.emergency_exam(seen[0]) is None
    assert service.queue.exam_record(f"emergency:{seen[0]}") is None
    with pytest.raises(ValidationError):
        _exam(service, append=True, emergency_study_instance_uid=seen[0] or "2.25.999")
    assert _snapshot(service, tmp_path)[0] == []
    assert service.queue.claim_exam(f"emergency:{seen[0]}") is not None


def test_old_database_gains_emergency_table(tmp_path) -> None:
    path = tmp_path / QUEUE_DB_NAME
    queue = SendQueue(path)
    queue.record_exam("old", "2.25.1", "20200101", "101112", "Old", 1)
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute("DROP TABLE emergency_exams")
    queue = SendQueue(path)
    assert queue.emergency_exam("2.25.1") is None
    assert queue.exam_record("old").study_description == "Old"


def test_emergency_append_creates_new_mpps(tmp_path, mpps_scp) -> None:
    service = _service(tmp_path, mpps_scp.port)
    first = _exam(service, mpps=True)
    added = _exam(service, append=True, emergency_study_instance_uid=first.study_instance_uid,
                  mpps=True)
    assert first.mpps.sop_instance_uid != added.mpps.sop_instance_uid
    uid = added.mpps.sop_instance_uid
    assert [op for op, sop, _ in mpps_scp.events if sop == uid] == ["N-CREATE", "N-SET"]
    created = mpps_scp.created[uid]
    assert created.PerformedProcedureStepStatus == "IN PROGRESS"
    step = created.ScheduledStepAttributesSequence[0]
    assert step.StudyInstanceUID == first.study_instance_uid
    assert step.AccessionNumber == ""
    assert service.mpps_queue.get(added.mpps.id).state == "COMPLETED"
    assert mpps_scp.sets[-1][1].PerformedProcedureStepStatus == "COMPLETED"


def test_emergency_append_mpps_without_connection(tmp_path, monkeypatch) -> None:
    """通信を置き換えて、開始と完了へ渡す値も確かめる."""
    from app.modality import mpps_scu

    events = []

    def create(own, peer, timeout, uid, dataset, **kwargs):
        events.append(("N-CREATE", uid, dataset))

    def finish(own, peer, timeout, uid, dataset, **kwargs):
        events.append(("N-SET", uid, dataset))

    monkeypatch.setattr(mpps_scu, "send_n_create", create)
    monkeypatch.setattr(mpps_scu, "send_n_set", finish)
    service = _service(tmp_path, 104)
    first = _exam(service, mpps=True)
    added = _exam(service, append=True, emergency_study_instance_uid=first.study_instance_uid,
                  mpps=True)
    assert first.mpps.sent and added.mpps.sent
    assert first.mpps.sop_instance_uid != added.mpps.sop_instance_uid
    assert [(op, uid) for op, uid, _ in events] == [
        ("N-CREATE", first.mpps.sop_instance_uid), ("N-SET", first.mpps.sop_instance_uid),
        ("N-CREATE", added.mpps.sop_instance_uid), ("N-SET", added.mpps.sop_instance_uid),
    ]
    created, completed = events[2][2], events[3][2]
    assert created.PerformedProcedureStepStatus == "IN PROGRESS"
    assert completed.PerformedProcedureStepStatus == "COMPLETED"
    step = created.ScheduledStepAttributesSequence[0]
    assert step.StudyInstanceUID == first.study_instance_uid
    assert step.AccessionNumber == ""
    assert created.StudyID == dcmread(first.files[0]).StudyID
    assert completed.PerformedSeriesSequence[0].SeriesInstanceUID == (
        dcmread(added.files[0]).SeriesInstanceUID
    )
