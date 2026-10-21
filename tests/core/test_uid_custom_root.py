"""custom_root の UID の一意と形の試験（PS3.5 9・9.1）."""

from __future__ import annotations

import pytest

from app.core.exceptions import UIDGenerationError
from app.core.uid_format import UID_MAX_LENGTH, is_valid_uid
from app.core.uid_generator import CUSTOM_ROOT_MAX_LENGTH, UIDGenerator

ROOT = "1.2.392.999"


def _all_uids(generator: UIDGenerator) -> list[str]:
    return [
        generator.generate_study_uid(),
        generator.generate_series_uid(),
        generator.generate_sop_uid(),
        generator.generate_frame_of_reference_uid(),
        generator.generate_instance_creator_uid(),
    ]


def test_run_scoped_custom_root_differs_between_generators() -> None:
    # 生成のたびに連番が 0 に戻っても、別の生成の UID と重ならない（PS3.5 9）
    first = _all_uids(UIDGenerator(method="custom_root", custom_root=ROOT, run_scoped=True))
    second = _all_uids(UIDGenerator(method="custom_root", custom_root=ROOT, run_scoped=True))

    assert not set(first) & set(second)


def test_run_scoped_custom_root_keeps_root_and_counter() -> None:
    generator = UIDGenerator(method="custom_root", custom_root=ROOT, run_scoped=True)

    first, second = generator.generate_study_uid(), generator.generate_series_uid()

    assert first.startswith(f"{ROOT}.")
    run_id = first.split(".")[-2]
    assert first == f"{ROOT}.{run_id}.1"
    assert second == f"{ROOT}.{run_id}.2"


def test_run_scoped_uids_are_valid() -> None:
    generator = UIDGenerator(method="custom_root", custom_root=ROOT, run_scoped=True)

    assert all(is_valid_uid(uid) for uid in _all_uids(generator))


def test_run_scoped_uid_with_longest_root_fits_64() -> None:
    root = "1." + "2" * (CUSTOM_ROOT_MAX_LENGTH - 2)
    generator = UIDGenerator(method="custom_root", custom_root=root, run_scoped=True)

    uids = [generator.generate_sop_uid() for _ in range(3)]

    assert all(len(uid) <= UID_MAX_LENGTH for uid in uids)


@pytest.mark.parametrize(
    "root",
    [
        "1.02.3",  # 成分の先頭が 0（PS3.5 9.1）
        "1.2.03",
        "3.2.1",  # 最初の成分は 0・1・2
        "1..2",
        "1.2.",
        "1.2.a",
        "1." + "2" * 70,  # 64 字を超える
    ],
)
def test_invalid_custom_root_is_rejected(root: str) -> None:
    with pytest.raises(UIDGenerationError):
        UIDGenerator(method="custom_root", custom_root=root)


def test_run_scoped_root_too_long_for_suffix_is_rejected() -> None:
    root = "1." + "2" * (CUSTOM_ROOT_MAX_LENGTH - 1)

    with pytest.raises(UIDGenerationError, match=str(CUSTOM_ROOT_MAX_LENGTH)):
        UIDGenerator(method="custom_root", custom_root=root, run_scoped=True)


def test_generated_uid_longer_than_64_is_rejected() -> None:
    # run_scoped でなくても、64 字を超える UID は作らない
    root = "1." + "2" * (UID_MAX_LENGTH - 3)
    generator = UIDGenerator(method="custom_root", custom_root=root)

    with pytest.raises(UIDGenerationError, match="64"):
        generator.generate_study_uid()
