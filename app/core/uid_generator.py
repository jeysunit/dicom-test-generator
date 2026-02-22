"""UID generation utilities for DICOM entities."""

from __future__ import annotations

from typing import Literal
import re
import random
import uuid

from .exceptions import UIDGenerationError


class UIDGenerator:
    """UID生成器.

    2つの生成方式:
    1. UUID 2.25方式（デフォルト）: f"2.25.{uuid.uuid4().int}"
    2. カスタムRoot方式: f"{root}.{counter}" で連番管理
    """

    def __init__(
        self,
        method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25",
        custom_root: str = "",
    ):
        if method not in ("uuid_2_25", "custom_root"):
            raise UIDGenerationError(
                f"Invalid UID generation method: {method}",
                uid_type="configuration",
            )
        if method == "custom_root" and not custom_root:
            raise UIDGenerationError(
                "custom_root is required when method is 'custom_root'",
                uid_type="configuration",
            )
        if method == "custom_root" and not re.match(r"^[0-2](\.\d+)+$", custom_root):
            raise UIDGenerationError(
                f"Invalid OID format for custom_root: {custom_root}",
                uid_type="configuration",
            )

        self._method = method
        self._custom_root = custom_root
        self._counter = 0

    def _generate_uid(self) -> str:
        if self._method == "uuid_2_25":
            return f"2.25.{uuid.uuid4().int}"

        self._counter += 1
        return f"{self._custom_root}.{self._counter}"

    def generate_study_uid(self) -> str:
        return self._generate_uid()

    def generate_series_uid(self) -> str:
        return self._generate_uid()

    def generate_sop_uid(self, allow_invalid: bool = False) -> str:
        """SOP Instance UIDを生成.

        allow_invalid=True の場合、10%の確率で0始まり不正OIDを生成
        不正パターン: "2.25.0{split}.{rest}" のようにドット直後に0を配置
        """
        uid = self._generate_uid()

        if allow_invalid and random.random() < 0.1:
            if self._method == "uuid_2_25":
                uuid_part = str(uuid.uuid4().int)
                split_pos = random.randint(3, len(uuid_part) - 3)
                uid = f"2.25.0{uuid_part[:split_pos]}.{uuid_part[split_pos:]}"
            else:
                self._counter += 1
                uid = f"{self._custom_root}.0{self._counter}"

        return uid

    def generate_frame_of_reference_uid(self) -> str:
        return self._generate_uid()

    def generate_instance_creator_uid(self) -> str:
        return self._generate_uid()
