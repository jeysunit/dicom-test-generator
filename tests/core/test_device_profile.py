"""装置のプロファイルのモデルと Dataset への当て方の試験（spec/13）."""

from __future__ import annotations

import copy

import pytest
from pydantic import ValidationError
from pydicom.dataset import Dataset

from app.core.device_profile import (
    DeviceProfile,
    apply_device_profile,
    normalize_character_set,
)


def _profile_data() -> dict:
    return {
        "schema_version": 1,
        "name": "test_ct",
        "device": {
            "modality": "CT",
            "manufacturer": "DTG Test",
            "manufacturers_model_name": "DTG Test CT",
            "software_versions": ["1.0", "2.0"],
            "device_serial_number": "DTG000001",
            "station_name": "DTGTEST1",
            "implementation_version_name": "DTG_TEST_10",
        },
        "storage": {
            "sop_classes": ["1.2.840.10008.5.1.4.1.1.2"],
            "transfer_syntaxes": ["1.2.840.10008.1.2.1", "1.2.840.10008.1.2"],
        },
        "character_set": {
            "default": "ISO 2022 IR 13\\ISO 2022 IR 87",
            "supported": ["ISO 2022 IR 13\\ISO 2022 IR 87", "ISO_IR 192"],
        },
        "attributes": {
            "set": {"BodyPartExamined": "CHEST"},
            "empty": ["OperatorsName"],
            "omit": ["SliceLocation"],
        },
        "private_tags": [
            {
                "group": "0009",
                "creator": "DTG TEST 01",
                "elements": [
                    {"offset": "10", "vr": "LO", "value": "MODE-A", "name": "Mode"},
                    {"offset": "11", "vr": "US", "value": 3},
                ],
            }
        ],
    }


def _with(path: str, value) -> dict:
    data = copy.deepcopy(_profile_data())
    target = data
    keys = path.split(".")
    for key in keys[:-1]:
        target = target[int(key)] if key.isdigit() else target[key]
    last = keys[-1]
    if value is _DELETE:
        del target[last]
    else:
        target[last] = value
    return data


_DELETE = object()


def test_valid_profile_parses() -> None:
    profile = DeviceProfile.model_validate(_profile_data())

    assert profile.name == "test_ct"
    assert profile.device.software_versions == ["1.0", "2.0"]
    assert profile.private_tags[0].group_number == 0x0009
    assert profile.private_tags[0].elements[0].offset_number == 0x10
    assert profile.services.mpps is False


def test_software_versions_accepts_single_string() -> None:
    profile = DeviceProfile.model_validate(_with("device.software_versions", "V1"))

    assert profile.device.software_versions == ["V1"]


@pytest.mark.parametrize(
    ("path", "value", "fragment"),
    [
        ("unknown_field", "x", "unknown_field"),
        ("device.unknown", "x", "device.unknown"),
        ("schema_version", 2, "schema_version"),
        ("name", "Bad-Name", "name"),
        ("device.manufacturer", _DELETE, "device.manufacturer"),
        ("storage.sop_classes", [], "storage.sop_classes"),
        ("storage.sop_classes", ["1.2.03"], "storage.sop_classes"),
        ("character_set.default", "ISO_IR 100", "character_set"),
        ("attributes.set", {"NotAKeyword": "x"}, "NotAKeyword"),
        ("attributes.set", {"PatientName": "X"}, "PatientName"),
        ("attributes.set", {"Manufacturer": "X"}, "Manufacturer"),
        ("attributes.omit", ["SOPInstanceUID"], "SOPInstanceUID"),
        ("attributes.empty", ["ReferencedImageSequence"], "SQ"),
        ("attributes.empty", ["BodyPartExamined"], "BodyPartExamined"),
        ("private_tags.0.group", "0008", "group"),
        ("private_tags.0.group", "0007", "group"),
        ("private_tags.0.group", 9, "group"),
        ("private_tags.0.elements.0.offset", "0F", "offset"),
        ("private_tags.0.elements.0.offset", 16, "offset"),
        ("private_tags.0.elements.0.vr", "SQ", "vr"),
        ("private_tags.0.elements.1.value", "three", "US"),
        ("private_tags.0.creator", "", "creator"),
        ("private_tags.0.elements.1.value", -1, "offset 11"),
        ("private_tags.0.elements.0.value", "x" * 65, "offset 10"),
        ("attributes.omit", ["Modality"], "Modality"),
        ("attributes.omit", ["ImagePositionPatient"], "ImagePositionPatient"),
        ("attributes.set", {"KVP": "not-a-number"}, "KVP"),
        ("attributes.set", {"BodyPartExamined": "chest"}, "BodyPartExamined"),
    ],
)
def test_invalid_profile_is_rejected(path, value, fragment) -> None:
    with pytest.raises(ValidationError) as exc_info:
        DeviceProfile.model_validate(_with(path, value))

    assert fragment in str(exc_info.value)


def test_numbers_for_string_vrs_are_written_as_strings() -> None:
    data = _with("attributes.set", {"KVP": 120, "BodyPartExamined": "CHEST"})
    profile = DeviceProfile.model_validate(data)
    ds = _dataset()

    apply_device_profile(ds, profile)

    assert ds.KVP == 120
    assert ds["KVP"].VR == "DS"


def test_duplicate_private_offset_is_rejected() -> None:
    data = _profile_data()
    data["private_tags"][0]["elements"][1]["offset"] = "10"

    with pytest.raises(ValidationError, match="offset"):
        DeviceProfile.model_validate(data)


def test_duplicate_private_creator_in_group_is_rejected() -> None:
    data = _profile_data()
    data["private_tags"].append(copy.deepcopy(data["private_tags"][0]))

    with pytest.raises(ValidationError, match="creator"):
        DeviceProfile.model_validate(data)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("ISO 2022 IR 6\\ISO 2022 IR 87", ("ISO 2022 IR 6", "ISO 2022 IR 87")),
        ("\\ISO 2022 IR 87", ("ISO 2022 IR 6", "ISO 2022 IR 87")),
        (" ISO_IR 192 ", ("ISO_IR 192",)),
        ("", ("ISO_IR 6",)),
        (None, ("ISO_IR 6",)),
        (["ISO 2022 IR 13", "ISO 2022 IR 87"], ("ISO 2022 IR 13", "ISO 2022 IR 87")),
    ],
)
def test_normalize_character_set(value, expected) -> None:
    assert normalize_character_set(value) == expected


def _dataset() -> Dataset:
    ds = Dataset()
    ds.Manufacturer = "Template Maker"
    ds.StationName = "TEMPLATE"
    ds.SliceLocation = "0.0"
    ds.OperatorsName = "SOMEONE"
    return ds


def test_apply_device_profile_sets_identity_attributes_and_private_tags() -> None:
    profile = DeviceProfile.model_validate(_profile_data())
    ds = _dataset()

    apply_device_profile(ds, profile, apply_station_name=True)

    assert ds.Manufacturer == "DTG Test"
    assert ds.ManufacturerModelName == "DTG Test CT"
    assert list(ds.SoftwareVersions) == ["1.0", "2.0"]
    assert ds.DeviceSerialNumber == "DTG000001"
    assert ds.StationName == "DTGTEST1"
    assert ds.BodyPartExamined == "CHEST"
    assert "OperatorsName" in ds
    assert ds["OperatorsName"].is_empty
    assert "SliceLocation" not in ds
    block = ds.private_block(0x0009, "DTG TEST 01")
    assert block[0x10].value == "MODE-A"
    assert block[0x10].VR == "LO"
    assert block[0x11].value == 3


def test_apply_device_profile_keeps_station_name_when_site_sets_it() -> None:
    profile = DeviceProfile.model_validate(_profile_data())
    ds = _dataset()

    apply_device_profile(ds, profile, apply_station_name=False)

    assert ds.StationName == "TEMPLATE"
