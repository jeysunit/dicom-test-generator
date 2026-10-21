"""UID generation utilities for DICOM entities."""

from __future__ import annotations

from typing import Literal
import random
import secrets
import uuid

from .exceptions import UIDGenerationError
from .uid_format import UID_MAX_LENGTH, is_valid_uid

# custom_root の最初の成分（ISO/ITU-T の根。0・1・2 だけ）
ROOT_FIRST_ARCS = frozenset({"0", "1", "2"})
# run_scoped のときに根の後ろにつなぐ成分の最大の桁。
# 生成ごとの番号（64 ビットの乱数、20 桁まで）と連番（7 桁まで。
# 1 回の生成は 100 シリーズ × 10000 枚と数個の UID）を足す
RUN_ID_BITS = 64
RUN_ID_MAX_DIGITS = len(str((1 << RUN_ID_BITS) - 1))
COUNTER_MAX_DIGITS = 7
CUSTOM_ROOT_MAX_LENGTH = UID_MAX_LENGTH - (1 + RUN_ID_MAX_DIGITS + 1 + COUNTER_MAX_DIGITS)


class UIDGenerator:
    """UID生成器.

    2つの生成方式:
    1. UUID 2.25方式（デフォルト）: f"2.25.{uuid.uuid4().int}"
    2. カスタムRoot方式: f"{root}.{counter}" で連番管理。
       run_scoped=True なら f"{root}.{run_id}.{counter}"。run_id は
       生成器ごとの 64 ビットの乱数で、別の生成の UID と重ならない（PS3.5 9）
    """

    def __init__(
        self,
        method: Literal["uuid_2_25", "custom_root"] = "uuid_2_25",
        custom_root: str = "",
        run_scoped: bool = False,
    ):
        if method not in ("uuid_2_25", "custom_root"):
            raise UIDGenerationError(
                f"Invalid UID generation method: {method}",
                uid_type="configuration",
            )
        if method == "custom_root":
            self._check_custom_root(custom_root, run_scoped)
            if run_scoped:
                custom_root = f"{custom_root}.{secrets.randbits(RUN_ID_BITS)}"

        self._method = method
        self._custom_root = custom_root
        self._counter = 0

    @staticmethod
    def _check_custom_root(custom_root: str, run_scoped: bool) -> None:
        """根が UID の形か（PS3.5 9.1。成分の先頭に 0 を置かない・64 字まで）."""
        if not custom_root:
            raise UIDGenerationError(
                "custom_root is required when method is 'custom_root'",
                uid_type="configuration",
            )
        if not is_valid_uid(custom_root) or custom_root.split(".")[0] not in ROOT_FIRST_ARCS:
            raise UIDGenerationError(
                f"Invalid OID format for custom_root: {custom_root} "
                "(digits and dots, first arc 0/1/2, no leading zero, up to 64 chars)",
                uid_type="configuration",
            )
        if run_scoped and len(custom_root) > CUSTOM_ROOT_MAX_LENGTH:
            raise UIDGenerationError(
                f"custom_root is too long: {len(custom_root)} chars "
                f"(up to {CUSTOM_ROOT_MAX_LENGTH} to keep UIDs within {UID_MAX_LENGTH})",
                uid_type="configuration",
            )

    def _generate_uid(self) -> str:
        if self._method == "uuid_2_25":
            return f"2.25.{uuid.uuid4().int}"

        self._counter += 1
        uid = f"{self._custom_root}.{self._counter}"
        if len(uid) > UID_MAX_LENGTH:
            raise UIDGenerationError(
                f"Generated UID exceeds {UID_MAX_LENGTH} chars: {uid}",
                uid_type="custom_root",
            )
        return uid

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
