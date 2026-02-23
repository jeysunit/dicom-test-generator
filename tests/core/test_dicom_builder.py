from __future__ import annotations

import numpy as np
import pytest

from app.core.dicom_writer import FileMetaBuilder, SpatialCalculator
from app.core.exceptions import DICOMBuildError
from app.core.generator import DICOMBuilder
from app.core.models import (
    InstanceConfig,
    Patient,
    PatientName,
    SeriesConfig,
    StudyConfig,
    UIDContext,
)


def _base_inputs() -> dict:
    patient = Patient(
        patient_id="P000001",
        patient_name=PatientName(
            alphabetic="YAMADA^TARO",
            ideographic="山田^太郎",
            phonetic="ヤマダ^タロウ",
        ),
        birth_date="19800115",
        sex="M",
    )
    study = StudyConfig(
        accession_number="ACC000001",
        study_date="20240115",
        study_time="120000",
        num_series=1,
    )
    series = SeriesConfig(series_number=1, num_images=1)
    instance = InstanceConfig(instance_number=1)
    uid_context = UIDContext(
        study_instance_uid="2.25.1",
        frame_of_reference_uid="2.25.2",
        implementation_class_uid="2.25.3",
        instance_creator_uid="2.25.4",
    )
    spatial = SpatialCalculator(slice_thickness=5.0, slice_spacing=5.0).calculate(0)
    pixels = np.zeros((8, 8), dtype=np.uint8)

    return {
        "patient": patient,
        "study": study,
        "series": series,
        "instance": instance,
        "uid_context": uid_context,
        "spatial": spatial,
        "pixels": pixels,
    }


def test_transfer_syntax_explicit_little_endian_flags() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.100",
        transfer_syntax_uid="1.2.840.10008.1.2.1",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )

    ds = DICOMBuilder().build_ct_image(
        patient=data["patient"],
        study_config=data["study"],
        series_config=data["series"],
        instance_config=data["instance"],
        uid_context=data["uid_context"],
        spatial=data["spatial"],
        pixel_data=data["pixels"],
        file_meta=file_meta,
        sop_instance_uid="2.25.100",
        series_instance_uid="2.25.200",
    )

    assert str(ds.file_meta.TransferSyntaxUID) == "1.2.840.10008.1.2.1"


def test_transfer_syntax_implicit_little_endian_flags() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.101",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )

    ds = DICOMBuilder().build_ct_image(
        patient=data["patient"],
        study_config=data["study"],
        series_config=data["series"],
        instance_config=data["instance"],
        uid_context=data["uid_context"],
        spatial=data["spatial"],
        pixel_data=data["pixels"],
        file_meta=file_meta,
        sop_instance_uid="2.25.101",
        series_instance_uid="2.25.201",
    )

    assert str(ds.file_meta.TransferSyntaxUID) == "1.2.840.10008.1.2"


def test_sop_instance_uid_mismatch_raises_error() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.102",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )

    with pytest.raises(DICOMBuildError, match="UID mismatch"):
        DICOMBuilder().build_ct_image(
            patient=data["patient"],
            study_config=data["study"],
            series_config=data["series"],
            instance_config=data["instance"],
            uid_context=data["uid_context"],
            spatial=data["spatial"],
            pixel_data=data["pixels"],
            file_meta=file_meta,
            sop_instance_uid="2.25.999",
            series_instance_uid="2.25.202",
        )


def test_non_ascii_patient_name_sets_default_character_set() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.103",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )

    ds = DICOMBuilder().build_ct_image(
        patient=data["patient"],
        study_config=data["study"],
        series_config=data["series"],
        instance_config=data["instance"],
        uid_context=data["uid_context"],
        spatial=data["spatial"],
        pixel_data=data["pixels"],
        file_meta=file_meta,
        sop_instance_uid="2.25.103",
        series_instance_uid="2.25.203",
    )

    assert ds.SpecificCharacterSet == ["ISO 2022 IR 6", "ISO 2022 IR 87"]  # parsed list


def test_non_ascii_patient_name_with_empty_character_set_raises_error() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.104",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )

    with pytest.raises(DICOMBuildError, match="SpecificCharacterSet"):
        DICOMBuilder().build_ct_image(
            patient=data["patient"],
            study_config=data["study"],
            series_config=data["series"],
            instance_config=data["instance"],
            uid_context=data["uid_context"],
            spatial=data["spatial"],
            pixel_data=data["pixels"],
            file_meta=file_meta,
            sop_instance_uid="2.25.104",
            series_instance_uid="2.25.204",
            specific_character_set="",
        )


@pytest.mark.parametrize(
    ("birth_date", "study_date", "expected_age"),
    [
        # 通常: 誕生日前後
        ("19980312", "20240115", "025Y"),
        # 1/1生まれ: 加齢日=12/31
        ("20000101", "20241231", "025Y"),
        ("20000101", "20241230", "024Y"),
        # 2/29生まれ（非閏年）: 応当日=2/28、加齢日=2/27
        ("20000229", "20250227", "024Y"),
        ("20000229", "20250228", "025Y"),
        # 2/29生まれ（閏年）: 応当日=2/29、加齢日=2/28
        ("20000229", "20240228", "024Y"),
        ("20000229", "20240229", "024Y"),
        # 3/1生まれ（非閏年）: 応当日=3/1、加齢日=2/28
        ("20000301", "20250227", "024Y"),
        ("20000301", "20250228", "025Y"),
        # 3/1生まれ（閏年）: 応当日=3/1、加齢日=2/29
        ("20000301", "20240228", "023Y"),
        ("20000301", "20240229", "024Y"),
        # 当日検査
        ("20240115", "20240115", "000Y"),
    ],
    ids=[
        "normal-before-birthday",
        "jan1-born-dec31-study",
        "jan1-born-dec30-study",
        "feb29-born-nonleap-feb27",
        "feb29-born-nonleap-feb28",
        "feb29-born-leap-feb28",
        "feb29-born-leap-feb29",
        "mar1-born-nonleap-feb27",
        "mar1-born-nonleap-feb28",
        "mar1-born-leap-feb28",
        "mar1-born-leap-feb29",
        "same-day-study",
    ],
)
def test_patient_age_japanese_civil_law(
    birth_date: str, study_date: str, expected_age: str
) -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.105",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )
    patient = Patient(
        patient_id="P000001",
        patient_name=PatientName(alphabetic="TEST^PATIENT"),
        birth_date=birth_date,
        sex="M",
    )
    study = StudyConfig(
        accession_number="ACC000001",
        study_date=study_date,
        study_time="120000",
        num_series=1,
    )

    ds = DICOMBuilder().build_ct_image(
        patient=patient,
        study_config=study,
        series_config=data["series"],
        instance_config=data["instance"],
        uid_context=data["uid_context"],
        spatial=data["spatial"],
        pixel_data=data["pixels"],
        file_meta=file_meta,
        sop_instance_uid="2.25.105",
        series_instance_uid="2.25.205",
    )

    assert ds.PatientAge == expected_age


def test_study_date_before_birth_date_raises_error() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.106",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )
    patient = Patient(
        patient_id="P000001",
        patient_name=PatientName(alphabetic="TEST^PATIENT"),
        birth_date="19800115",
        sex="M",
    )
    study = StudyConfig(
        accession_number="ACC000001",
        study_date="19790101",
        study_time="120000",
        num_series=1,
    )

    with pytest.raises(DICOMBuildError, match="study_date must be on or after"):
        DICOMBuilder().build_ct_image(
            patient=patient,
            study_config=study,
            series_config=data["series"],
            instance_config=data["instance"],
            uid_context=data["uid_context"],
            spatial=data["spatial"],
            pixel_data=data["pixels"],
            file_meta=file_meta,
            sop_instance_uid="2.25.106",
            series_instance_uid="2.25.206",
        )


def test_invalid_calendar_date_raises_error() -> None:
    data = _base_inputs()
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.107",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=data["uid_context"].implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )
    patient = Patient(
        patient_id="P000001",
        patient_name=PatientName(alphabetic="TEST^PATIENT"),
        birth_date="20250229",
        sex="M",
    )
    study = StudyConfig(
        accession_number="ACC000001",
        study_date="20250315",
        study_time="120000",
        num_series=1,
    )

    with pytest.raises(DICOMBuildError, match="Invalid date format"):
        DICOMBuilder().build_ct_image(
            patient=patient,
            study_config=study,
            series_config=data["series"],
            instance_config=data["instance"],
            uid_context=data["uid_context"],
            spatial=data["spatial"],
            pixel_data=data["pixels"],
            file_meta=file_meta,
            sop_instance_uid="2.25.107",
            series_instance_uid="2.25.207",
        )
