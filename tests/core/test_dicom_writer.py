from __future__ import annotations

from app.core.dicom_writer import FileMetaBuilder, SpatialCalculator


def test_file_meta_builder_required_fields() -> None:
    builder = FileMetaBuilder()

    file_meta = builder.build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.12345",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid="2.25.99999",
        implementation_version_name="DICOM_GEN_1.1",
    )

    assert file_meta.MediaStorageSOPClassUID == "1.2.840.10008.5.1.4.1.1.2"
    assert file_meta.MediaStorageSOPInstanceUID == "2.25.12345"
    assert file_meta.TransferSyntaxUID == "1.2.840.10008.1.2"
    assert file_meta.ImplementationClassUID == "2.25.99999"
    assert file_meta.ImplementationVersionName == "DICOM_GEN_1.1"


def test_file_meta_builder_version_bytes() -> None:
    builder = FileMetaBuilder()

    file_meta = builder.build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid="2.25.12346",
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid="2.25.99999",
        implementation_version_name="DICOM_GEN_1.1",
    )

    assert file_meta.FileMetaInformationVersion == b"\x00\x01"


def test_spatial_calculator_first_slice() -> None:
    calculator = SpatialCalculator(slice_thickness=5.0, slice_spacing=2.5, start_z=10.0)

    spatial = calculator.calculate(0)

    assert spatial.instance_number == 1
    assert spatial.slice_location == 10.0
    assert spatial.image_position_patient == [0.0, 0.0, 10.0]


def test_spatial_calculator_sequential() -> None:
    calculator = SpatialCalculator(slice_thickness=5.0, slice_spacing=2.5, start_z=0.0)

    first = calculator.calculate(0)
    second = calculator.calculate(1)
    third = calculator.calculate(2)

    assert first.slice_location == 0.0
    assert second.slice_location == 2.5
    assert third.slice_location == 5.0


def test_spatial_calculator_custom_start_z() -> None:
    calculator = SpatialCalculator(slice_thickness=1.0, slice_spacing=1.5, start_z=-30.0)

    spatial = calculator.calculate(2)

    assert spatial.instance_number == 3
    assert spatial.slice_location == -27.0
    assert spatial.image_position_patient == [0.0, 0.0, -27.0]


def test_spatial_calculator_default_orientation() -> None:
    calculator = SpatialCalculator(slice_thickness=5.0, slice_spacing=5.0)

    spatial = calculator.calculate(0)

    assert spatial.image_orientation_patient == [1.0, 0.0, 0.0, 0.0, 1.0, 0.0]
