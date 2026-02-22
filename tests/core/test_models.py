from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.models import (
    InstanceConfig,
    Patient,
    PatientName,
    SeriesConfig,
    SpatialCoordinates,
    StudyConfig,
    UIDContext,
)


def test_patient_name_to_dicom_pn_full() -> None:
    name = PatientName(
        alphabetic="YAMADA^TARO",
        ideographic="山田^太郎",
        phonetic="ヤマダ^タロウ",
    )

    dicom_pn = name.to_dicom_pn(use_ideographic=True, use_phonetic=True)

    assert dicom_pn == "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"


def test_patient_name_to_dicom_pn_alphabetic_only() -> None:
    name = PatientName(alphabetic="YAMADA^TARO")

    dicom_pn = name.to_dicom_pn(use_ideographic=True, use_phonetic=True)

    assert dicom_pn == "YAMADA^TARO"


def test_patient_name_to_dicom_pn_no_ideographic() -> None:
    name = PatientName(
        alphabetic="YAMADA^TARO",
        ideographic="山田^太郎",
        phonetic="ヤマダ^タロウ",
    )

    dicom_pn = name.to_dicom_pn(use_ideographic=False, use_phonetic=True)

    assert dicom_pn == "YAMADA^TARO==ヤマダ^タロウ"


def test_patient_valid_creation() -> None:
    patient = Patient(
        patient_id="P000001",
        patient_name=PatientName(alphabetic="YAMADA^TARO"),
        birth_date="19800115",
        sex="M",
        age="044Y",
        weight=70.5,
        size=1.72,
    )

    assert patient.patient_id == "P000001"
    assert patient.sex == "M"


def test_patient_id_too_long() -> None:
    with pytest.raises(ValidationError):
        Patient(
            patient_id="P" * 17,
            patient_name=PatientName(alphabetic="YAMADA^TARO"),
            birth_date="19800115",
            sex="M",
        )


def test_patient_invalid_sex() -> None:
    with pytest.raises(ValidationError):
        Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="YAMADA^TARO"),
            birth_date="19800115",
            sex="X",
        )


def test_patient_invalid_birth_date() -> None:
    with pytest.raises(ValidationError):
        Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="YAMADA^TARO"),
            birth_date="1980-01-15",
            sex="M",
        )


def test_study_config_valid() -> None:
    study = StudyConfig(
        accession_number="ACC000001",
        study_date="20240115",
        study_time="120000",
        num_series=2,
    )

    assert study.num_series == 2


def test_study_config_invalid_date() -> None:
    with pytest.raises(ValidationError):
        StudyConfig(
            accession_number="ACC000001",
            study_date="2024-01-15",
            study_time="120000",
            num_series=2,
        )


def test_series_config_valid() -> None:
    series = SeriesConfig(
        series_number=1,
        num_images=10,
        slice_thickness=1.0,
        slice_spacing=1.5,
    )

    assert series.series_number == 1
    assert series.num_images == 10


def test_instance_config_defaults() -> None:
    instance = InstanceConfig(instance_number=5)

    assert instance.acquisition_number == 1


def test_spatial_coordinates_frozen() -> None:
    spatial = SpatialCoordinates(
        instance_number=1,
        image_position_patient=[0.0, 0.0, 0.0],
        slice_location=0.0,
    )

    with pytest.raises(ValidationError):
        spatial.slice_location = 1.0


def test_uid_context_creation() -> None:
    context = UIDContext(
        study_instance_uid="2.25.1",
        frame_of_reference_uid="2.25.2",
        implementation_class_uid="2.25.3",
        instance_creator_uid="2.25.4",
    )

    assert context.study_instance_uid == "2.25.1"
    assert context.frame_of_reference_uid == "2.25.2"
