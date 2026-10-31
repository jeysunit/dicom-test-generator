"""性別の 4 値（M・F・O・U）：製品の中は U、DICOM に書くときは空、DICOM から読むときは空と規格外を U に."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydicom.dataset import Dataset

from app.core.models import Patient, PatientName, ScheduledPatient
from app.core.patient_input import FieldValidationError, validate_sex
from app.core.patient_sex import SEX_VALUES, from_dicom_sex, to_dicom_sex
from app.core.worklist_mapping import (
    apply_scheduled_context,
    scheduled_context_from_item,
    worklist_item_from_identifier,
)
from app.modality.mpps_scu import build_n_create
from app.services.patient_loader import PatientLoaderService


def test_the_four_values() -> None:
    assert SEX_VALUES == ("M", "F", "O", "U")


@pytest.mark.parametrize(("value", "written"), [("M", "M"), ("F", "F"), ("O", "O"), ("U", ""), ("", "")])
def test_dicom_gets_mfo_and_an_empty_value_for_the_rest(value: str, written: str) -> None:
    assert to_dicom_sex(value) == written


@pytest.mark.parametrize(
    ("value", "read"),
    [("M", "M"), ("F", "F"), ("O", "O"), ("", "U"), ("U", "U"), ("X", "U"), ("m", "U"), ("MALE", "U")],
)
def test_reading_dicom_turns_an_empty_or_out_of_range_value_into_u(value: str, read: str) -> None:
    assert from_dicom_sex(value) == read


def test_models_accept_u_and_refuse_other_letters() -> None:
    name = PatientName(alphabetic="TEST^U")
    assert Patient(patient_id="P1", patient_name=name, birth_date="19800101", sex="U").sex == "U"
    assert ScheduledPatient(patient_id="E1", patient_name="A", sex="U").sex == "U"
    for bad in ("X", "u"):
        with pytest.raises(ValueError):
            Patient(patient_id="P1", patient_name=name, birth_date="19800101", sex=bad)
        with pytest.raises(ValueError):
            ScheduledPatient(patient_id="E1", patient_name="A", sex=bad)


def test_input_check_accepts_the_four_values() -> None:
    for value in ("", *SEX_VALUES):
        validate_sex(value)
    with pytest.raises(FieldValidationError, match="男・女・その他・不明"):
        validate_sex("X")


def test_patient_master_values_are_in_the_four_values() -> None:
    patients = PatientLoaderService().load_all()
    assert len(patients) == 100
    assert {patient.sex for patient in patients} <= set(SEX_VALUES)


def _identifier(sex: str | None) -> Dataset:
    ds = Dataset()
    ds.SpecificCharacterSet = "ISO_IR 192"
    ds.PatientName = "YAMADA^TARO"
    ds.PatientID = "P1"
    if sex is not None:
        ds.PatientSex = sex
    ds.StudyInstanceUID = "2.25.1111"
    return ds


@pytest.mark.parametrize(
    ("sent", "inside"), [("M", "M"), ("F", "F"), ("O", "O"), ("", "U"), ("U", "U"), ("X", "U"), (None, "U")]
)
def test_worklist_item_reads_sex_as_one_of_the_four(sent: str | None, inside: str) -> None:
    assert worklist_item_from_identifier(_identifier(sent)).sex == inside


@pytest.mark.parametrize(("sent", "written"), [("M", "M"), ("O", "O"), ("U", ""), ("", ""), ("X", "")])
def test_image_and_mpps_never_get_u_or_a_value_outside_the_dicom_set(sent: str, written: str) -> None:
    item = worklist_item_from_identifier(_identifier(sent))
    ctx = scheduled_context_from_item(
        item, performed_procedure_step_id="PPS1", specific_character_set=["ISO_IR 192"],
        source_ae_title="DTG_CT01",
    )
    assert ctx.patient.sex == item.sex

    image = Dataset()
    apply_scheduled_context(image, ctx)
    mpps = build_n_create(
        ctx, modality="CT", study_instance_uid="2.25.1111", station_ae_title="DTG_CT01",
        station_name="DTG", started=datetime(2026, 10, 31, 9, 0, 0),
    )
    assert image.PatientSex == written
    assert mpps.PatientSex == written
