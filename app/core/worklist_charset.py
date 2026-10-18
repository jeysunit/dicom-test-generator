"""画像の文字コードの決め方と、表せない字の確かめ（spec/12_modality_emulator.md 7 章）.

Core Engine の Pure な処理。ファイル・通信・ログを使わない。
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from pydicom.charset import python_encoding
from pydicom.dataset import Dataset
from pydicom.multival import MultiValue

from .exceptions import ModalityConfigError, WorklistMappingError

CHARACTER_SET_CHOICES = ("auto", "utf8", "jis", "jis_kana")
FALLBACK_CHOICES = ("utf8", "jis", "jis_kana")

# 選択 → 画像の Specific Character Set（値 1 の空は ISO 2022 IR 6）
CHOICE_TO_CHARACTER_SET: dict[str, list[str]] = {
    "utf8": ["ISO_IR 192"],
    "jis": ["", "ISO 2022 IR 87"],
    "jis_kana": ["ISO 2022 IR 13", "ISO 2022 IR 87"],
}

# 文字コードの影響を受ける VR（PS3.5 6.1.2.3）
_TEXT_VRS = frozenset({"SH", "LO", "ST", "LT", "UT", "PN", "UC"})
_DEFAULT_REPERTOIRE_TERMS = frozenset({"", "ISO_IR 6", "ISO 2022 IR 6"})
_JIS_X_0208_TERMS = frozenset({"ISO 2022 IR 87", "ISO_IR 87"})
_JIS_X_0201_TERMS = frozenset({"ISO 2022 IR 13", "ISO_IR 13"})
_UTF8_TERMS = frozenset({"ISO_IR 192"})
_JIS_X_0208_ESCAPES = (b"\x1b$B", b"\x1b$@")
_ASCII_MAX = 0x7F


def resolve_image_character_set(
    choice: str,
    response_character_set: Sequence[str] | None,
    fallback: str,
) -> list[str]:
    """画像の Specific Character Set を決める（7.1 の表）.

    `auto` はワークリストの応答の値を使い、応答に無い・予約なしのときは
    `fallback` を使う。`fallback` に `auto` は選べない。
    """
    if fallback not in FALLBACK_CHOICES:
        raise ModalityConfigError(
            "character_set_fallback must be one of utf8, jis, jis_kana",
            {"character_set_fallback": fallback},
        )
    if choice not in CHARACTER_SET_CHOICES:
        raise ModalityConfigError(
            "character_set must be one of auto, utf8, jis, jis_kana",
            {"character_set": choice},
        )
    if choice != "auto":
        return list(CHOICE_TO_CHARACTER_SET[choice])

    response = [term.strip() for term in (response_character_set or [])]
    if any(response):
        return response
    return list(CHOICE_TO_CHARACTER_SET[fallback])


def find_unrepresentable_chars(value: str, character_set: Sequence[str]) -> list[str]:
    """`character_set` で表せない字を、出た順に重ねずに返す."""
    terms = [term.strip() for term in character_set] or [""]
    found: list[str] = []
    for char in value:
        if char in found or _is_representable(char, terms):
            continue
        found.append(char)
    return found


def ensure_dataset_encodable(ds: Dataset) -> None:
    """データセットの文字の属性が、その Specific Character Set で表せるかを確かめる.

    表せない字があれば、黙って消さずに WorklistMappingError で止める（7.2）。
    """
    character_set = character_set_of(ds)
    for attribute, text in _iter_text_values(ds, prefix=""):
        unrepresentable = find_unrepresentable_chars(text, character_set)
        if unrepresentable:
            chars = "".join(unrepresentable)
            label = "\\".join(character_set) if character_set else "ISO 2022 IR 6"
            raise WorklistMappingError(
                f"「{chars}」は {label} で表せません（{attribute}）",
                {"attribute": attribute, "characters": chars, "character_set": label},
            )


def character_set_of(ds: Dataset) -> list[str]:
    """データセットの Specific Character Set を、値の並びとして返す."""
    value = ds.get("SpecificCharacterSet")
    if value is None:
        return []
    if isinstance(value, (list, MultiValue)):
        return [str(term) for term in value]
    return [str(value)]


def _is_representable(char: str, terms: Sequence[str]) -> bool:
    if ord(char) <= _ASCII_MAX:
        return True
    return any(_term_accepts(term, char) for term in terms)


def _term_accepts(term: str, char: str) -> bool:
    if term in _DEFAULT_REPERTOIRE_TERMS:
        return False
    if term in _UTF8_TERMS:
        return _encodes(char, "utf-8")
    if term in _JIS_X_0208_TERMS:
        try:
            encoded = char.encode("iso2022_jp")
        except UnicodeEncodeError:
            return False
        return any(escape in encoded for escape in _JIS_X_0208_ESCAPES)
    if term in _JIS_X_0201_TERMS:
        try:
            return len(char.encode("shift_jis")) == 1
        except UnicodeEncodeError:
            return False
    codec = python_encoding.get(term)
    return codec is not None and _encodes(char, codec)


def _encodes(char: str, codec: str) -> bool:
    try:
        char.encode(codec)
    except UnicodeEncodeError:
        return False
    return True


def _iter_text_values(ds: Dataset, prefix: str) -> Iterator[tuple[str, str]]:
    for element in ds:
        name = element.keyword or str(element.tag)
        path = f"{prefix}{name}"
        if element.VR == "SQ":
            for item in element.value:
                yield from _iter_text_values(item, prefix=f"{path}>")
            continue
        if element.VR not in _TEXT_VRS or element.value is None:
            continue
        values = element.value if isinstance(element.value, (list, MultiValue)) else [element.value]
        for value in values:
            yield path, str(value)
