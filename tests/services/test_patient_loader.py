from __future__ import annotations

import pytest

from app.core import PatientNotFoundError
from app.services.patient_loader import PatientLoaderService


def test_load_all() -> None:
    service = PatientLoaderService()

    patients = service.load_all()

    assert len(patients) == 100


def test_find_by_id_success() -> None:
    service = PatientLoaderService()

    patient = service.find_by_id("P000001")

    assert patient.patient_id == "P000001"


def test_find_by_id_not_found() -> None:
    service = PatientLoaderService()

    with pytest.raises(PatientNotFoundError):
        service.find_by_id("P999999")


def test_patient_data_validation() -> None:
    service = PatientLoaderService()

    patient = service.find_by_id("P000001")

    assert patient.patient_id
    assert patient.patient_name
    assert patient.birth_date
    assert patient.sex
