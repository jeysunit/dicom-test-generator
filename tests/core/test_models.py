from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.models import (
    AbnormalConfig,
    CharacterSetConfig,
    GenerationConfig,
    InstanceConfig,
    Patient,
    PatientName,
    PixelSpecCTRealistic,
    PixelSpecSimple,
    SeriesConfig,
    SpatialCoordinates,
    StudyConfig,
    TransferSyntaxConfig,
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


def test_pixel_spec_simple_defaults() -> None:
    pixel_spec = PixelSpecSimple()

    assert pixel_spec.mode == "simple_text"
    assert pixel_spec.width == 512
    assert pixel_spec.height == 512
    assert pixel_spec.background_color == 0
    assert pixel_spec.text_color == 255
    assert pixel_spec.font_size == 24


def test_pixel_spec_ct_realistic_defaults() -> None:
    pixel_spec = PixelSpecCTRealistic()

    assert pixel_spec.mode == "ct_realistic"
    assert pixel_spec.width == 512
    assert pixel_spec.height == 512
    assert pixel_spec.pattern == "gradient"
    assert pixel_spec.bits_stored == 12


def test_transfer_syntax_config_defaults() -> None:
    transfer_syntax = TransferSyntaxConfig()

    assert transfer_syntax.uid == "1.2.840.10008.1.2"
    assert transfer_syntax.name == "Implicit VR Little Endian"
    assert transfer_syntax.is_implicit_vr is True
    assert transfer_syntax.is_little_endian is True


def test_character_set_config_defaults() -> None:
    character_set = CharacterSetConfig()

    assert character_set.specific_character_set == r"ISO 2022 IR 6\ISO 2022 IR 87"
    assert character_set.use_ideographic is True
    assert character_set.use_phonetic is True


def test_abnormal_config_defaults() -> None:
    abnormal = AbnormalConfig()

    assert abnormal.level == "none"
    assert abnormal.allow_invalid_sop_uid is False
    assert abnormal.invalid_sop_uid_probability == 0.1


def test_generation_config_valid() -> None:
    config = GenerationConfig(
        job_name="job-001",
        output_dir="/tmp/output",
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(
                alphabetic="YAMADA^TARO",
                ideographic="山田^太郎",
                phonetic="ヤマダ^タロウ",
            ),
            birth_date="19800115",
            sex="M",
            age="044Y",
            weight=70.5,
            size=1.72,
            patient_comments="comment",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            study_description="desc",
            referring_physician_name="doctor",
            num_series=1,
        ),
        series_list=[
            SeriesConfig(
                series_number=1,
                series_description="series",
                num_images=2,
                protocol_name="protocol",
                slice_thickness=1.0,
                slice_spacing=1.5,
                start_z=0.0,
            )
        ],
        modality_template="ct_default",
        hospital_template="hospital_a",
        uid_method="custom_root",
        uid_custom_root="1.2.392.200036.9116.2",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
        abnormal=AbnormalConfig(level="mild"),
    )

    assert config.job_name == "job-001"
    assert len(config.series_list) == 1
    assert config.uid_method == "custom_root"
    assert config.abnormal.level == "mild"


def test_generation_config_minimal() -> None:
    config = GenerationConfig(
        job_name="job-min",
        output_dir="/tmp/output",
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="YAMADA^TARO"),
            birth_date="19800115",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        series_list=[SeriesConfig(series_number=1, num_images=1)],
        modality_template="ct_default",
        pixel_spec=PixelSpecCTRealistic(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
    )

    assert config.hospital_template is None
    assert config.uid_method == "uuid_2_25"
    assert config.uid_custom_root is None
    assert config.abnormal.level == "none"


def test_generation_config_invalid_series_list_empty() -> None:
    with pytest.raises(ValidationError):
        GenerationConfig(
            job_name="job-invalid",
            output_dir="/tmp/output",
            patient=Patient(
                patient_id="P000001",
                patient_name=PatientName(alphabetic="YAMADA^TARO"),
                birth_date="19800115",
                sex="M",
            ),
            study=StudyConfig(
                accession_number="ACC000001",
                study_date="20240115",
                study_time="120000",
                num_series=1,
            ),
            series_list=[],
            modality_template="ct_default",
            pixel_spec=PixelSpecSimple(),
            transfer_syntax=TransferSyntaxConfig(),
            character_set=CharacterSetConfig(),
        )
