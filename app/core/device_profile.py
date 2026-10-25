"""Device profile model and its application to a dataset (docs/spec/13).

装置のプロファイルは、ある装置のコンフォーマンスステートメント（DICOM PS3.2）
から写した、その装置の DICOM の出し方。モダリティのテンプレートの上に重ねる。
この module は Pure（ファイルを読まない）。読み込みは Service Layer が行う。
"""

from __future__ import annotations

import re
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydicom import config
from pydicom.datadict import dictionary_VR, tag_for_keyword
from pydicom.dataset import Dataset
from pydicom.valuerep import validate_value

UID_PATTERN = r"^[0-2](\.(0|[1-9][0-9]*))+$"
PROFILE_NAME_PATTERN = r"^[a-z0-9][a-z0-9_]*$"

# プロファイルの attributes で触れない属性（docs/spec/13 の 3.3）。
# 患者の値・UID・画素・文字コードはほかの仕組みが、装置の値は device の欄が決める。
PROTECTED_KEYWORDS: frozenset[str] = frozenset(
    {
        # 患者の値
        "PatientName",
        "PatientID",
        "PatientBirthDate",
        "PatientSex",
        "PatientAge",
        "PatientWeight",
        "PatientSize",
        # UID
        "SOPClassUID",
        "SOPInstanceUID",
        "StudyInstanceUID",
        "SeriesInstanceUID",
        "FrameOfReferenceUID",
        # 画素
        "PixelData",
        "Rows",
        "Columns",
        "BitsAllocated",
        "BitsStored",
        "HighBit",
        "PixelRepresentation",
        "SamplesPerPixel",
        "PhotometricInterpretation",
        # 文字コード
        "SpecificCharacterSet",
        # device の欄が決める
        "Manufacturer",
        "ManufacturerModelName",
        "SoftwareVersions",
        "DeviceSerialNumber",
        "StationName",
        "Modality",
    }
)

# attributes.omit で消せない属性（docs/spec/13 の 3.3）。この道具が CT Image で出す
# Type 1・Type 2 の属性。omit は装置の表に無い Type 3 を消すためのもので、
# 必須の属性を欠いた画像は異常のデータ（abnormal）の仕事にする。
OMIT_FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    {
        "Modality",
        "StudyDate",
        "StudyTime",
        "AccessionNumber",
        "ReferringPhysicianName",
        "StudyID",
        "SeriesNumber",
        "InstanceNumber",
        "AcquisitionNumber",
        "ContentDate",
        "ContentTime",
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "PixelSpacing",
        "SliceThickness",
        "KVP",
        "RescaleIntercept",
        "RescaleSlope",
        "ImageType",
        "PatientPosition",
        "PositionReferenceIndicator",
        "InstanceCreatorUID",
    }
)

# attributes.empty と空の attributes.set で空にできない属性（docs/spec/13 の 3.3）。
# この道具が CT Image で出す Type 1 の属性で、PROTECTED_KEYWORDS に無いもの
# （PS3.3 C.7.3.1・C.7.6.2・C.8.2.1）。Type 1 は空の値を許さない。
# Modality は device.modality が決めるので PROTECTED_KEYWORDS に入れている
EMPTY_FORBIDDEN_KEYWORDS: frozenset[str] = frozenset(
    {
        "ImageType",
        "ImagePositionPatient",
        "ImageOrientationPatient",
        "PixelSpacing",
        "RescaleIntercept",
        "RescaleSlope",
    }
)

# attributes.set で Type 1 の属性に書ける値の数（VM）。Image Type は 2 以上、ほかは固定
# （PS3.3 C.7.6.2・C.8.2.1）
_TYPE1_VALUE_COUNTS: dict[str, int] = {
    "ImagePositionPatient": 3,
    "ImageOrientationPatient": 6,
    "PixelSpacing": 2,
    "RescaleIntercept": 1,
    "RescaleSlope": 1,
}
_IMAGE_TYPE_MIN_VALUES = 2
# Image Type の値 1（PS3.3 C.8.2.1.1.1）
_IMAGE_TYPE_FIRST_VALUES = frozenset({"ORIGINAL", "DERIVED"})

# 数の値だけを受ける VR（バイナリの数）
_BINARY_NUMBER_VRS = frozenset({"US", "UL", "SS", "SL", "FL", "FD"})
_INTEGER_VRS = frozenset({"US", "UL", "SS", "SL"})

PrivateVR = Literal[
    "AE", "AS", "CS", "DA", "DS", "DT", "IS", "LO", "LT", "SH", "ST", "TM",
    "UC", "UI", "UR", "UT", "US", "UL", "SS", "SL", "FL", "FD",
]

Scalar = Union[str, int, float]
AttributeValue = Union[Scalar, list[Scalar]]


def normalize_character_set(value: str | list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """Specific Character Set の値を比べられる形にする（docs/spec/13 の 4.3）.

    `\\` で分け、前後の空白を除く。値 1 が空なら ISO 2022 IR 6 とみなす
    （PS3.3 C.12.1.1.2）。値が無ければ既定の字の集まり（ISO_IR 6）とみなす。
    """
    if value is None:
        return ("ISO_IR 6",)
    parts = list(value) if isinstance(value, (list, tuple)) else str(value).split("\\")
    parts = [str(part).strip() for part in parts]
    if not any(parts):
        return ("ISO_IR 6",)
    if parts[0] == "":
        parts[0] = "ISO 2022 IR 6"
    return tuple(parts)


def to_dicom_value(value: AttributeValue, vr: str) -> AttributeValue:
    """YAML の値を Dataset に入れる形にする（文字の VR の数は文字にする）."""
    if vr in _BINARY_NUMBER_VRS:
        return value
    if isinstance(value, list):
        return [item if isinstance(item, str) else str(item) for item in value]
    return value if isinstance(value, str) else str(value)


def _check_value_for_vr(value: AttributeValue, vr: str, label: str) -> None:
    """VR に合う値かを確かめる（型・数の範囲・文字の長さと字）.

    生成のときではなく読み込みのときに分かる誤り（ProfileParseError）にする。
    """
    values = value if isinstance(value, list) else [value]
    for item in values:
        if isinstance(item, bool):
            raise ValueError(f"{label}: boolean is not a DICOM value")
        if vr in _BINARY_NUMBER_VRS:
            if not isinstance(item, (int, float)):
                raise ValueError(f"{label}: VR {vr} needs a number, got {item!r}")
            if vr in _INTEGER_VRS and not isinstance(item, int):
                raise ValueError(f"{label}: VR {vr} needs an integer, got {item!r}")
        converted = to_dicom_value(item, vr)
        try:
            validate_value(vr, converted, config.RAISE)
        except ValueError as exc:
            reason = str(exc).split(" Please see")[0]
            raise ValueError(f"{label}: {reason}") from exc


def _check_type1_value(keyword: str, value: AttributeValue) -> None:
    """Type 1 の属性に、規格に合わない値（値の数・先頭の値・0）を書かせない.

    意図して壊した画像は異常のデータ（abnormal）の仕事で、プロファイルは
    正しい装置の写しにする。空の値は呼び出し側が先に断っている。
    """
    values = value if isinstance(value, list) else [value]
    if keyword == "ImageType":
        if len(values) < _IMAGE_TYPE_MIN_VALUES:
            raise ValueError(
                f"{keyword} is a Type 1 attribute with at least "
                f"{_IMAGE_TYPE_MIN_VALUES} values (PS3.3 C.8.2.1.1.1)"
            )
        if values[0] not in _IMAGE_TYPE_FIRST_VALUES:
            raise ValueError(
                f"{keyword}: the first value must be ORIGINAL or DERIVED "
                "(PS3.3 C.8.2.1.1.1)"
            )
        return
    count = _TYPE1_VALUE_COUNTS[keyword]
    if len(values) != count:
        raise ValueError(
            f"{keyword} is a Type 1 attribute that needs exactly {count} "
            f"value(s), got {len(values)}"
        )
    for item in values:
        try:
            number = float(item)
        except ValueError:
            raise ValueError(f"{keyword}: {item!r} is not a number") from None
        if keyword == "RescaleSlope" and number == 0:
            raise ValueError(f"{keyword} must not be 0 (it cannot convert pixels)")


class _StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProfileSource(_StrictModel):
    """元になったコンフォーマンスステートメント（分からない欄は空）."""

    title: str = ""
    version: str = ""
    date: str = ""
    url: str = ""
    document_id: str = ""
    notes: str = ""


class ProfileDevice(_StrictModel):
    modality: str = Field(..., pattern=r"^[A-Z0-9_ ]{1,16}$")
    manufacturer: str = Field(..., min_length=1, max_length=64)
    manufacturers_model_name: str = Field(..., min_length=1, max_length=64)
    software_versions: list[str] = Field(default_factory=list)
    device_serial_number: str | None = Field(None, min_length=1, max_length=64)
    station_name: str | None = Field(None, min_length=1, max_length=16)
    implementation_version_name: str | None = Field(None, min_length=1, max_length=16)

    @field_validator("software_versions", mode="before")
    @classmethod
    def _single_version_to_list(cls, value):
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("software_versions")
    @classmethod
    def _check_versions(cls, value: list[str]) -> list[str]:
        for item in value:
            if not item or len(item) > 64:
                raise ValueError("each software version must be 1-64 characters")
        return value


class ProfileStorage(_StrictModel):
    sop_classes: list[str] = Field(..., min_length=1)
    transfer_syntaxes: list[str] = Field(..., min_length=1)

    @field_validator("sop_classes", "transfer_syntaxes")
    @classmethod
    def _check_uids(cls, value: list[str]) -> list[str]:
        for uid in value:
            if len(uid) > 64 or not re.match(UID_PATTERN, uid):
                raise ValueError(f"invalid UID: {uid!r}")
        return value


class ProfileCharacterSet(_StrictModel):
    default: str | None = None
    supported: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _default_is_supported(self) -> ProfileCharacterSet:
        if self.default is not None and self.supported:
            supported = {normalize_character_set(item) for item in self.supported}
            if normalize_character_set(self.default) not in supported:
                raise ValueError(
                    f"character_set.default {self.default!r} is not in "
                    "character_set.supported"
                )
        return self

    def allows(self, value: str | None) -> bool:
        if not self.supported:
            return True
        supported = {normalize_character_set(item) for item in self.supported}
        return normalize_character_set(value) in supported


def _keyword_vr(keyword: str) -> str:
    tag = tag_for_keyword(keyword)
    if tag is None:
        raise ValueError(f"unknown DICOM keyword: {keyword}")
    return dictionary_VR(tag)


def _is_empty_value(value: AttributeValue) -> bool:
    """空の文字か、空の文字だけの並びか（値の無い属性になる）."""
    values = value if isinstance(value, list) else [value]
    return all(isinstance(item, str) and not item.strip() for item in values)


def _check_keyword(keyword: str) -> str:
    vr = _keyword_vr(keyword)
    if keyword in PROTECTED_KEYWORDS:
        raise ValueError(
            f"{keyword} cannot be changed by attributes "
            "(patient values, UIDs, pixel, character set and device fields)"
        )
    if vr == "SQ":
        raise ValueError(f"{keyword}: sequences (SQ) are not supported yet")
    return vr


class ProfileAttributes(_StrictModel):
    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    set_values: dict[str, AttributeValue] = Field(default_factory=dict, alias="set")
    empty: list[str] = Field(default_factory=list)
    omit: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> ProfileAttributes:
        seen: dict[str, str] = {}
        for group, keywords in (
            ("set", list(self.set_values)),
            ("empty", self.empty),
            ("omit", self.omit),
        ):
            for keyword in keywords:
                vr = _check_keyword(keyword)
                if keyword in seen:
                    raise ValueError(
                        f"{keyword} is listed in both attributes.{seen[keyword]} "
                        f"and attributes.{group}"
                    )
                seen[keyword] = group
                if group == "omit" and keyword in OMIT_FORBIDDEN_KEYWORDS:
                    raise ValueError(
                        f"{keyword} is a Type 1/2 attribute and cannot be omitted "
                        "(use abnormal data to break required attributes)"
                    )
                if keyword in EMPTY_FORBIDDEN_KEYWORDS and (
                    group == "empty"
                    or (group == "set" and _is_empty_value(self.set_values[keyword]))
                ):
                    raise ValueError(
                        f"{keyword} is a Type 1 attribute and cannot be empty "
                        "(use abnormal data to break required attributes)"
                    )
                if group == "set":
                    if " or " in vr:
                        raise ValueError(f"{keyword}: VR {vr} is ambiguous")
                    _check_value_for_vr(self.set_values[keyword], vr, keyword)
                    if keyword == "ImageType" or keyword in _TYPE1_VALUE_COUNTS:
                        _check_type1_value(keyword, self.set_values[keyword])
        return self


class PrivateElement(_StrictModel):
    offset: str = Field(..., description="要素の下 2 桁（16 進、10〜FF）")
    vr: PrivateVR
    value: AttributeValue
    name: str = ""

    @field_validator("offset")
    @classmethod
    def _check_offset(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9A-Fa-f]{2}", value) or int(value, 16) < 0x10:
            raise ValueError("offset must be two hex digits from 10 to FF")
        return value.upper()

    @model_validator(mode="after")
    def _check_value(self) -> PrivateElement:
        _check_value_for_vr(self.value, self.vr, f"offset {self.offset}")
        return self

    @property
    def offset_number(self) -> int:
        return int(self.offset, 16)


class PrivateTagBlock(_StrictModel):
    group: str = Field(..., description="奇数の群（16 進 4 桁）")
    creator: str = Field(..., min_length=1, max_length=64)
    elements: list[PrivateElement] = Field(..., min_length=1)

    @field_validator("group")
    @classmethod
    def _check_group(cls, value: str) -> str:
        if not re.fullmatch(r"[0-9A-Fa-f]{4}", value):
            raise ValueError("group must be four hex digits")
        number = int(value, 16)
        if number % 2 == 0 or number < 0x0009:
            raise ValueError("group must be an odd group from 0009 to FFFF")
        return value.upper()

    @field_validator("creator")
    @classmethod
    def _check_creator(cls, value: str) -> str:
        if value.strip() != value or "\\" in value:
            raise ValueError("creator must not have edge spaces or backslashes")
        return value

    @model_validator(mode="after")
    def _unique_offsets(self) -> PrivateTagBlock:
        offsets = [element.offset for element in self.elements]
        duplicates = sorted({o for o in offsets if offsets.count(o) > 1})
        if duplicates:
            raise ValueError(f"duplicate offset in {self.creator!r}: {duplicates}")
        return self

    @property
    def group_number(self) -> int:
        return int(self.group, 16)


class ProfileServices(_StrictModel):
    """装置が対応するサービス（値を持つだけ。効くのは 3a・3c）."""

    modality_worklist: bool = False
    mpps: bool = False
    storage_commitment: bool = False


class DeviceProfile(_StrictModel):
    """装置のプロファイル（docs/spec/13 の 3）."""

    schema_version: Literal[1]
    name: str = Field(..., pattern=PROFILE_NAME_PATTERN, max_length=64)
    description: str = ""
    source: ProfileSource = Field(default_factory=ProfileSource)
    device: ProfileDevice
    storage: ProfileStorage
    character_set: ProfileCharacterSet = Field(default_factory=ProfileCharacterSet)
    attributes: ProfileAttributes = Field(default_factory=ProfileAttributes)
    private_tags: list[PrivateTagBlock] = Field(default_factory=list)
    services: ProfileServices = Field(default_factory=ProfileServices)

    @model_validator(mode="after")
    def _unique_creators(self) -> DeviceProfile:
        pairs = [(block.group, block.creator) for block in self.private_tags]
        duplicates = sorted({p for p in pairs if pairs.count(p) > 1})
        if duplicates:
            raise ValueError(f"duplicate private creator in group: {duplicates}")
        return self


def apply_device_profile(
    ds: Dataset, profile: DeviceProfile, apply_station_name: bool = True
) -> None:
    """プロファイルの装置の値・属性・プライベートタグを Dataset に当てる.

    docs/spec/13 の 4.2：装置の値は病院テンプレートでも変えない。Station Name は
    施設が決めていなければ（apply_station_name=True）プロファイルの値にする。
    attributes とプライベートタグは最後に当てる。
    """
    device = profile.device
    ds.Manufacturer = device.manufacturer
    ds.ManufacturerModelName = device.manufacturers_model_name
    if device.software_versions:
        versions = device.software_versions
        ds.SoftwareVersions = versions[0] if len(versions) == 1 else list(versions)
    if device.device_serial_number is not None:
        ds.DeviceSerialNumber = device.device_serial_number
    if apply_station_name and device.station_name is not None:
        ds.StationName = device.station_name

    attributes = profile.attributes
    for keyword, value in attributes.set_values.items():
        setattr(ds, keyword, to_dicom_value(value, _keyword_vr(keyword)))
    for keyword in attributes.empty:
        tag = tag_for_keyword(keyword)
        ds.add_new(tag, dictionary_VR(tag), None)
    for keyword in attributes.omit:
        if keyword in ds:
            delattr(ds, keyword)

    for block in profile.private_tags:
        private_block = ds.private_block(block.group_number, block.creator, create=True)
        for element in block.elements:
            private_block.add_new(
                element.offset_number,
                element.vr,
                to_dicom_value(element.value, element.vr),
            )
