"""Abnormal data generator for DICOM tags."""

from __future__ import annotations

import random
import string
from typing import Any, Literal

from .exceptions import GenerationError

ABNORMAL_LEVELS = ("none", "mild", "moderate", "severe")
DEFAULT_APPEND_LENGTH = 8
UID_MAX_LENGTH = 64
TYPE2_NONE_PROBABILITY = 0.5
TYPE3_NONE_PROBABILITY = 0.5


class AbnormalGenerator:
    """異常データ生成器.

    レベル別挙動:
    - none: 正常値をそのまま返す
    - mild: VR違反、文字数超過
    - moderate: Type 1,2タグをNone返却（欠落）、UID 0始まり
    - severe: File Meta破損、Pixel Data欠落
    """

    def __init__(self, level: Literal["none", "mild", "moderate", "severe"]):
        if level not in ABNORMAL_LEVELS:
            raise GenerationError(
                f"Invalid abnormal level: {level}",
                {"level": level, "allowed_levels": ABNORMAL_LEVELS},
            )
        self._level = level

    @property
    def level(self) -> str:
        return self._level

    def apply_abnormal_value(
        self,
        tag_name: str,
        normal_value: Any,
        vr: str,
        tag_type: int,
        max_length: int | None = None,
    ) -> Any | None:
        """異常値を適用.

        Args:
            tag_name: タグ名（例: "PatientID"）
            normal_value: 正常値
            vr: Value Representation (LO, SH, DA, TM, UI, IS, DS, CS, PN 等)
            tag_type: DICOM Type (1, 2, 3)
            max_length: 最大長（VRによる制限。例: LO=64, SH=16）

        Returns:
            異常値。None はタグ欠落を意味する。
        """
        _ = tag_name

        if self._level == "none":
            return normal_value

        vr_upper = vr.upper()

        if self._level == "mild":
            return self._apply_mild_abnormal(normal_value, vr_upper, max_length)

        if self._level == "moderate":
            if tag_type == 1:
                return None
            if tag_type == 2 and random.random() < TYPE2_NONE_PROBABILITY:
                return None
            if vr_upper == "UI":
                return self._invalid_uid_starts_with_zero()
            return self._apply_mild_abnormal(normal_value, vr_upper, max_length)

        if tag_type in (1, 2):
            return None
        if tag_type == 3 and random.random() < TYPE3_NONE_PROBABILITY:
            return None
        if vr_upper == "UI":
            return self._invalid_uid_with_non_digit()
        return self._type_mismatch_value(normal_value)

    def _apply_mild_abnormal(
        self,
        normal_value: Any,
        vr: str,
        max_length: int | None,
    ) -> Any:
        if max_length is not None:
            return self._generate_random_string(max(max_length * 2, max_length + 1, 1))

        if vr == "DA":
            return "INVALID_DATE"
        if vr == "TM":
            return "INVALID_TIME"
        if vr == "IS":
            return "NOT_A_NUMBER"
        if vr == "DS":
            return "NOT_DECIMAL"
        if vr == "CS":
            return "invalid_cs!"
        if vr == "UI":
            return self._invalid_uid_too_long()

        return f"{normal_value}{self._generate_random_string(DEFAULT_APPEND_LENGTH)}"

    def _invalid_uid_starts_with_zero(self) -> str:
        suffix = self._generate_random_string(20, charset=string.digits)
        return f"0.2.25.{suffix}"

    def _invalid_uid_too_long(self) -> str:
        return "1." + "2" * (UID_MAX_LENGTH + 1)

    def _invalid_uid_with_non_digit(self) -> str:
        return "INVALID_UID_XXXX"

    def _type_mismatch_value(self, normal_value: Any) -> Any:
        if isinstance(normal_value, (int, float)):
            return "INVALID_TYPE"
        return 12345

    def _generate_random_string(
        self,
        length: int,
        charset: str = string.ascii_letters + string.digits,
    ) -> str:
        return "".join(random.choice(charset) for _ in range(length))
