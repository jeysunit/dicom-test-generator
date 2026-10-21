"""CT Image IOD の規格への適合の試験（DICOM PS3.3 C.7・C.8.2.1、PS3.5 6.2）."""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from app.core.device_profile import OMIT_FORBIDDEN_KEYWORDS, DeviceProfile
from app.core.dicom_writer import FileMetaBuilder, SpatialCalculator
from app.core.exceptions import DICOMBuildError
from app.core.generator import DICOMBuilder, format_ds
from app.core.models import (
    InstanceConfig,
    Patient,
    PatientName,
    SeriesConfig,
    StudyConfig,
    UIDContext,
)
from app.core.pixel_generator import PixelGenerator

DS_MAX_LENGTH = 16
SOP_INSTANCE_UID = "2.25.100"


def _build(
    *,
    pixels: np.ndarray | None = None,
    bits_stored: int = 12,
    slice_spacing: float = 5.0,
    slice_index: int = 0,
    size: float | None = None,
    weight: float | None = None,
):
    patient = Patient(
        patient_id="P000001",
        patient_name=PatientName(alphabetic="YAMADA^TARO"),
        birth_date="19800115",
        sex="M",
        size=size,
        weight=weight,
    )
    study = StudyConfig(
        accession_number="ACC000001",
        study_date="20240115",
        study_time="120000",
        num_series=1,
    )
    series = SeriesConfig(
        series_number=1,
        num_images=slice_index + 1,
        slice_thickness=slice_spacing,
        slice_spacing=slice_spacing,
    )
    uid_context = UIDContext(
        study_instance_uid="2.25.1",
        frame_of_reference_uid="2.25.2",
        implementation_class_uid="2.25.3",
        instance_creator_uid="2.25.4",
    )
    spatial = SpatialCalculator(
        slice_thickness=slice_spacing, slice_spacing=slice_spacing
    ).calculate(slice_index)
    file_meta = FileMetaBuilder().build(
        sop_class_uid="1.2.840.10008.5.1.4.1.1.2",
        sop_instance_uid=SOP_INSTANCE_UID,
        transfer_syntax_uid="1.2.840.10008.1.2",
        implementation_class_uid=uid_context.implementation_class_uid,
        implementation_version_name="DICOM_GEN_1.1",
    )
    return DICOMBuilder().build_ct_image(
        patient=patient,
        study_config=study,
        series_config=series,
        instance_config=InstanceConfig(instance_number=slice_index + 1),
        uid_context=uid_context,
        spatial=spatial,
        pixel_data=pixels if pixels is not None else np.zeros((8, 8), dtype=np.int16),
        file_meta=file_meta,
        sop_instance_uid=SOP_INSTANCE_UID,
        series_instance_uid="2.25.200",
        bits_stored=bits_stored,
    )


# 違反 1：CT Image IOD の必須の属性


def test_image_type_is_original_primary_axial() -> None:
    # PS3.3 C.8.2.1：Image Type は Type 1。値 3 は AXIAL か LOCALIZER（C.8.2.1.1.1）
    ds = _build()

    assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY", "AXIAL"]


def test_patient_position_is_present() -> None:
    # PS3.3 C.7.3.1：Patient Position は 2C。CT Image Storage では必須
    ds = _build()

    assert ds.PatientPosition == "HFS"


def test_position_reference_indicator_is_present_and_empty() -> None:
    # PS3.3 C.7.4.1：Position Reference Indicator は Type 2
    ds = _build()

    assert "PositionReferenceIndicator" in ds
    assert ds.PositionReferenceIndicator == ""


@pytest.mark.parametrize("keyword", ["PatientPosition", "PositionReferenceIndicator"])
def test_new_required_attributes_cannot_be_omitted_by_profile(keyword: str) -> None:
    # 装置のプロファイルの omit で必須の属性を消せない（spec/13 の 3.3）
    assert keyword in OMIT_FORBIDDEN_KEYWORDS


def _profile(attributes: dict) -> dict:
    return {
        "schema_version": 1,
        "name": "test_ct",
        "device": {
            "modality": "CT",
            "manufacturer": "DTG Test",
            "manufacturers_model_name": "DTG Test CT",
        },
        "storage": {
            "sop_classes": ["1.2.840.10008.5.1.4.1.1.2"],
            "transfer_syntaxes": ["1.2.840.10008.1.2"],
        },
        "attributes": attributes,
    }


@pytest.mark.parametrize(
    "attributes",
    [
        {"empty": ["ImageType"]},
        {"set": {"ImageType": ""}},
        {"set": {"ImageType": []}},
        {"set": {"ImageType": ["", ""]}},
        {"empty": ["Modality"]},
        {"empty": ["PixelSpacing"]},
        {"set": {"RescaleSlope": " "}},
    ],
)
def test_profile_cannot_empty_type1_attributes(attributes: dict) -> None:
    # Type 1 は空の値を許さない（PS3.3 C.8.2.1・C.7.3.1・C.7.6.2）
    with pytest.raises(ValidationError, match="Type 1"):
        DeviceProfile.model_validate(_profile(attributes))


@pytest.mark.parametrize(
    "attributes",
    [
        {"set": {"ImageType": ["DERIVED", "SECONDARY", "AXIAL"]}},
        {"set": {"PatientPosition": "FFS"}},
        {"empty": ["PatientPosition", "PositionReferenceIndicator"]},
    ],
)
def test_profile_can_change_or_empty_type2_attributes(attributes: dict) -> None:
    # Image Type は別の値にでき、Type 2・2C は空にできる
    DeviceProfile.model_validate(_profile(attributes))


# 違反 5：DS は 16 バイトまで（PS3.5 6.2）


def test_decimal_strings_fit_sixteen_bytes_for_fractional_spacing() -> None:
    # 間隔 0.1 の 4 枚目は z = 0.30000000000000004 になる
    ds = _build(slice_spacing=0.1, slice_index=3)

    values = [*ds.ImagePositionPatient, ds.SliceLocation, ds.SliceThickness]
    assert all(len(str(v)) <= DS_MAX_LENGTH for v in values)
    assert str(ds.SliceLocation) == "0.3"
    assert str(ds.ImagePositionPatient[2]) == "0.3"


def test_patient_size_and_weight_fit_sixteen_bytes() -> None:
    # 165.7 cm / 100 = 1.6569999999999998
    ds = _build(size=165.7, weight=62.3)

    assert str(ds.PatientSize) == "1.657"
    assert str(ds.PatientWeight) == "62.3"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0.30000000000000004, "0.3"),
        (1.6569999999999998, "1.657"),
        (1e-7, "1e-07"),
        (-1e-7, "-1e-07"),
        (0.0, "0.0"),
        (-1024.0, "-1024.0"),
        (1e20, "1e+20"),
        (123456789.12345679, "123456789.123"),
    ],
)
def test_format_ds_keeps_value_within_sixteen_bytes(value: float, expected: str) -> None:
    # 小さい値を 0 に丸めず、指数の形で残す
    assert format_ds(value) == expected


def test_format_ds_long_value_fits_sixteen_bytes() -> None:
    formatted = format_ds(-1.2345678901234567e-300)

    assert len(formatted) <= DS_MAX_LENGTH
    assert float(formatted) == pytest.approx(-1.2345678901234567e-300, rel=1e-8)


def test_every_decimal_string_in_dataset_fits_sixteen_bytes() -> None:
    ds = _build(slice_spacing=0.1, slice_index=7, size=165.7, weight=62.3)

    for element in ds:
        if element.VR != "DS" or element.value is None:
            continue
        values = element.value if element.VM > 1 else [element.value]
        for value in values:
            assert len(str(value)) <= DS_MAX_LENGTH, element.keyword


# 違反 3：画素は Bits Stored の範囲の 2 の補数（PS3.3 C.7.6.3、PS3.5 8）


@pytest.mark.parametrize("pattern", ["gradient", "circle", "noise"])
@pytest.mark.parametrize("bits_stored", [12, 13, 16])
def test_ct_realistic_pixels_fit_signed_bits_stored(pattern: str, bits_stored: int) -> None:
    pixels = PixelGenerator().generate_ct_realistic(
        width=64, height=64, pattern=pattern, bits_stored=bits_stored
    )

    assert int(pixels.min()) >= -(1 << (bits_stored - 1))
    assert int(pixels.max()) <= (1 << (bits_stored - 1)) - 1


def test_ct_realistic_gradient_twelve_bits_spans_air_to_upper_limit() -> None:
    # Rescale Intercept -1024 で HU -1024（空気）から HU 1023 まで
    pixels = PixelGenerator().generate_ct_realistic(
        width=64, height=64, pattern="gradient", bits_stored=12
    )

    assert int(pixels.min()) == 0
    assert int(pixels.max()) == 2047


def test_ct_realistic_circle_bone_is_below_twelve_bit_limit() -> None:
    pixels = PixelGenerator().generate_ct_realistic(
        width=64, height=64, pattern="circle", bits_stored=12
    )

    assert int(pixels[32, 32]) > int(pixels[0, 0])
    assert int(pixels[32, 32]) <= 2047


def test_builder_rejects_pixels_outside_signed_bits_stored_range() -> None:
    pixels = np.full((8, 8), 2048, dtype=np.int16)

    with pytest.raises(DICOMBuildError, match="Bits Stored"):
        _build(pixels=pixels, bits_stored=12)


def test_builder_rejects_pixels_below_signed_bits_stored_range() -> None:
    pixels = np.full((8, 8), -2049, dtype=np.int16)

    with pytest.raises(DICOMBuildError, match="Bits Stored"):
        _build(pixels=pixels, bits_stored=12)


def test_builder_accepts_pixels_at_signed_bits_stored_limits() -> None:
    pixels = np.array([[-2048, 2047]], dtype=np.int16)

    ds = _build(pixels=pixels, bits_stored=12)

    assert ds.BitsStored == 12
    assert ds.HighBit == 11
    assert ds.PixelRepresentation == 1
