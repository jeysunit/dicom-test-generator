"""以前に受け付けた値の緊急の患者にも、追加撮影できる（入力の確かめは新規の撮影だけ。docs/spec/12a の 10.5）."""

import sqlite3
from contextlib import closing

import pytest
from pydicom import dcmread

from app.core.exceptions import ValidationError
from app.core.models import ScheduledPatient
from app.core.patient_input import build_emergency_patient
from app.modality.queue import QUEUE_DB_NAME
from app.modality.service import ExamRequest

from .test_emergency_append import PATIENT, _exam
from .test_service import _service

LEGACY_NAME = "SMITH^JOHN^^DR."


def test_append_to_a_patient_saved_before_the_input_rules(tmp_path) -> None:
    service = _service(tmp_path, 104)
    uid = _exam(service).study_instance_uid
    with closing(sqlite3.connect(tmp_path / "state" / QUEUE_DB_NAME)) as conn, conn:
        conn.execute("UPDATE emergency_exams SET patient_name = ?", (LEGACY_NAME,))
    legacy = ScheduledPatient(patient_id=PATIENT.patient_id, patient_name=LEGACY_NAME)

    added = _exam(service, append=True, emergency_study_instance_uid=uid, patient=legacy)

    assert dcmread(added.files[0]).PatientName == LEGACY_NAME


def test_new_exam_still_refuses_the_same_name(tmp_path) -> None:
    service = _service(tmp_path, 104)
    legacy = ScheduledPatient(patient_id="E2", patient_name=LEGACY_NAME)
    with pytest.raises(ValidationError, match="氏名（英字）は半角"):
        service.exam(ExamRequest(emergency_patient=legacy, pixel_mode="simple_text"))


def test_builder_skips_the_rules_only_when_not_strict() -> None:
    with pytest.raises(ValidationError):
        build_emergency_patient("E1", LEGACY_NAME)
    assert build_emergency_patient("E1", LEGACY_NAME, strict=False).patient_name == LEGACY_NAME
