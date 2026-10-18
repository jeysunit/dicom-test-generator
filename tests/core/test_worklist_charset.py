"""画像の文字コード（spec/12 の 7 章）の試験."""

from __future__ import annotations

from io import BytesIO

import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset

from app.core.exceptions import ModalityConfigError, WorklistMappingError
from app.core.worklist_charset import (
    CHARACTER_SET_CHOICES,
    ensure_dataset_encodable,
    find_unrepresentable_chars,
    resolve_image_character_set,
)

PN_KANJI = "YAMADA^TARO=山田^太郎=やまだ^たろう"
PN_HALFWIDTH_KANA = "ﾔﾏﾀﾞ^ﾀﾛｳ=山田^太郎=やまだ^たろう"
UTF8 = ["ISO_IR 192"]
JIS = ["", "ISO 2022 IR 87"]
JIS_KANA = ["ISO 2022 IR 13", "ISO 2022 IR 87"]
EXPLICIT_VR_LITTLE_ENDIAN = "1.2.840.10008.1.2.1"


def _roundtrip(patient_name: str, character_set: list[str]) -> Dataset:
    ds = Dataset()
    ds.file_meta = FileMetaDataset()
    ds.file_meta.TransferSyntaxUID = EXPLICIT_VR_LITTLE_ENDIAN
    ds.SpecificCharacterSet = character_set if len(character_set) > 1 else character_set[0]
    ds.PatientName = patient_name
    ds.PatientID = "P000001"
    ensure_dataset_encodable(ds)
    buffer = BytesIO()
    pydicom.dcmwrite(buffer, ds, enforce_file_format=False)
    return pydicom.dcmread(BytesIO(buffer.getvalue()), force=True)


@pytest.mark.parametrize(
    ("choice", "expected"),
    [("utf8", UTF8), ("jis", JIS), ("jis_kana", JIS_KANA)],
)
def test_resolve_fixed_choices(choice: str, expected: list[str]) -> None:
    assert resolve_image_character_set(choice, ["ISO_IR 100"], "utf8") == expected


def test_resolve_auto_uses_worklist_response() -> None:
    assert resolve_image_character_set("auto", ["ISO 2022 IR 13", "ISO 2022 IR 87"], "utf8") == JIS_KANA


def test_resolve_auto_without_response_uses_fallback() -> None:
    assert resolve_image_character_set("auto", [], "jis") == JIS
    assert resolve_image_character_set("auto", None, "jis_kana") == JIS_KANA


def test_resolve_fallback_cannot_be_auto() -> None:
    with pytest.raises(ModalityConfigError):
        resolve_image_character_set("auto", None, "auto")


def test_resolve_unknown_choice() -> None:
    with pytest.raises(ModalityConfigError):
        resolve_image_character_set("latin1", None, "utf8")


def test_choices_are_the_four_of_the_spec() -> None:
    assert CHARACTER_SET_CHOICES == ("auto", "utf8", "jis", "jis_kana")


@pytest.mark.parametrize(
    ("patient_name", "character_set"),
    [
        (PN_KANJI, UTF8),
        (PN_KANJI, JIS),
        (PN_KANJI, JIS_KANA),
        (PN_HALFWIDTH_KANA, UTF8),
        (PN_HALFWIDTH_KANA, JIS_KANA),
        (PN_KANJI, ["ISO 2022 IR 6", "ISO 2022 IR 87"]),
    ],
)
def test_roundtrip_each_choice(patient_name: str, character_set: list[str]) -> None:
    restored = _roundtrip(patient_name, character_set)

    assert str(restored.PatientName) == patient_name


def test_auto_roundtrip_follows_response() -> None:
    character_set = resolve_image_character_set("auto", JIS_KANA, "utf8")
    restored = _roundtrip(PN_HALFWIDTH_KANA, character_set)

    assert str(restored.PatientName) == PN_HALFWIDTH_KANA


def test_find_unrepresentable_in_jis() -> None:
    assert find_unrepresentable_chars("髙橋^𠮷", JIS) == ["髙", "𠮷"]
    assert find_unrepresentable_chars("ﾔﾏﾀﾞ", JIS) == ["ﾔ", "ﾏ", "ﾀ", "ﾞ"]
    assert find_unrepresentable_chars("山田^太郎", JIS) == []


def test_find_unrepresentable_in_jis_kana_and_utf8() -> None:
    assert find_unrepresentable_chars("ﾔﾏﾀﾞ^山田", JIS_KANA) == []
    assert find_unrepresentable_chars("髙", JIS_KANA) == ["髙"]
    assert find_unrepresentable_chars("髙橋^𠮷", UTF8) == []


def test_find_unrepresentable_in_default_repertoire() -> None:
    assert find_unrepresentable_chars("YAMADA^TARO", []) == []
    assert find_unrepresentable_chars("山田", []) == ["山", "田"]


def test_ensure_dataset_encodable_stops_with_attribute_and_char() -> None:
    ds = Dataset()
    ds.SpecificCharacterSet = JIS
    ds.PatientName = "TAKAHASHI=髙橋"
    ds.StudyDescription = "胸部 CT"

    with pytest.raises(WorklistMappingError) as exc_info:
        ensure_dataset_encodable(ds)

    assert exc_info.value.details["attribute"] == "PatientName"
    assert exc_info.value.details["characters"] == "髙"
    assert "ISO 2022 IR 87" in str(exc_info.value)


def test_ensure_dataset_encodable_checks_sequences() -> None:
    item = Dataset()
    item.RequestedProcedureDescription = "𠮷の検査"
    ds = Dataset()
    ds.SpecificCharacterSet = JIS
    ds.RequestAttributesSequence = [item]

    with pytest.raises(WorklistMappingError) as exc_info:
        ensure_dataset_encodable(ds)

    assert exc_info.value.details["attribute"] == (
        "RequestAttributesSequence>RequestedProcedureDescription"
    )


def test_ensure_dataset_encodable_accepts_ascii_without_character_set() -> None:
    ds = Dataset()
    ds.PatientName = "YAMADA^TARO"

    ensure_dataset_encodable(ds)
