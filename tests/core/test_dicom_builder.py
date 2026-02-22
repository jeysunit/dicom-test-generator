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
