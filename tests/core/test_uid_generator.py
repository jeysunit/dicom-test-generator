from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.exceptions import UIDGenerationError
from app.core.uid_generator import UIDGenerator


def test_uuid_2_25_default_method() -> None:
    generator = UIDGenerator()
    uid = generator.generate_study_uid()

    assert uid.startswith("2.25.")


def test_uuid_2_25_uid_length() -> None:
    generator = UIDGenerator()
    uid = generator.generate_study_uid()

    assert len(uid) >= 10


def test_uuid_2_25_unique() -> None:
    generator = UIDGenerator()
    uids = [generator.generate_study_uid() for _ in range(20)]

    assert len(set(uids)) == len(uids)


def test_custom_root_method() -> None:
    root = "1.2.392.200036.9999"
    generator = UIDGenerator(method="custom_root", custom_root=root)

    assert generator.generate_study_uid() == f"{root}.1"


def test_custom_root_sequential() -> None:
    root = "1.2.392.200036.9999"
    generator = UIDGenerator(method="custom_root", custom_root=root)

    uids = [generator.generate_study_uid() for _ in range(3)]

    assert uids == [f"{root}.1", f"{root}.2", f"{root}.3"]


def test_invalid_method_raises_error() -> None:
    with pytest.raises(UIDGenerationError):
        UIDGenerator(method="invalid_method")


def test_custom_root_empty_raises_error() -> None:
    with pytest.raises(UIDGenerationError):
        UIDGenerator(method="custom_root", custom_root="")


def test_generate_sop_uid_normal() -> None:
    generator = UIDGenerator()

    uid = generator.generate_sop_uid(allow_invalid=False)

    assert uid.startswith("2.25.")
    assert ".0" not in uid


def test_generate_sop_uid_invalid_probability() -> None:
    generator = UIDGenerator()

    random_values = [0.01] * 10 + [0.99] * 90
    with patch("app.core.uid_generator.random.random", side_effect=random_values):
        uids = [generator.generate_sop_uid(allow_invalid=True) for _ in range(100)]

    invalid_count = sum(1 for uid in uids if ".0" in uid)

    assert 5 <= invalid_count <= 15


def test_generate_study_uid() -> None:
    generator = UIDGenerator()

    uid = generator.generate_study_uid()

    assert uid.startswith("2.25.")


def test_generate_series_uid() -> None:
    generator = UIDGenerator()

    uid = generator.generate_series_uid()

    assert uid.startswith("2.25.")


def test_generate_frame_of_reference_uid() -> None:
    generator = UIDGenerator()

    uid = generator.generate_frame_of_reference_uid()

    assert uid.startswith("2.25.")


def test_generate_instance_creator_uid() -> None:
    generator = UIDGenerator()

    uid = generator.generate_instance_creator_uid()

    assert uid.startswith("2.25.")
