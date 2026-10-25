"""緊急の患者の患者ID は 64 字（VR LO）まで受け、画像・送信待ちの記録・追加撮影でも切らない."""

import sqlite3
from contextlib import closing

import pytest
from pydicom import dcmread

from app.core.models import PATIENT_ID_MAX_LENGTH, ScheduledPatient
from app.core.worklist_mapping import CARRIER_PATIENT_ID_LENGTH, build_carrier_patient
from app.modality.queue import QUEUE_DB_NAME

from .test_emergency_append import _exam
from .test_service import _service

LONG_ID = "P" + "0" * (PATIENT_ID_MAX_LENGTH - 1)


@pytest.fixture
def patient() -> ScheduledPatient:
    return ScheduledPatient(
        patient_id=LONG_ID, patient_name="UNKNOWN^ONE", birth_date="20000101", sex="O"
    )


def test_longest_patient_id_reaches_the_image_whole(tmp_path, patient) -> None:
    assert len(LONG_ID) == 64
    service = _service(tmp_path, 104)
    result = _exam(service, patient=patient)
    assert all(dcmread(path).PatientID == LONG_ID for path in result.files)


def test_carrier_patient_takes_a_patient_id_longer_than_the_job_limit(patient) -> None:
    carrier = build_carrier_patient(patient, "20260101")
    assert carrier.patient_id == LONG_ID[:CARRIER_PATIENT_ID_LENGTH]


def test_longest_patient_id_survives_the_append_and_the_saved_record(tmp_path, patient) -> None:
    service = _service(tmp_path, 104)
    uid = _exam(service, patient=patient).study_instance_uid
    with closing(sqlite3.connect(tmp_path / "state" / QUEUE_DB_NAME)) as conn:
        assert conn.execute("SELECT patient_id FROM emergency_exams").fetchone() == (LONG_ID,)
    added = _exam(service, patient=patient, append=True, emergency_study_instance_uid=uid)
    assert dcmread(added.files[0]).PatientID == LONG_ID
