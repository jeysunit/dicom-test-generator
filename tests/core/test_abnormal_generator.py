from __future__ import annotations

import re
from unittest.mock import patch

import pytest

from app.core.abnormal_generator import AbnormalGenerator
from app.core.exceptions import GenerationError


def test_none_level_returns_normal_value() -> None:
    generator = AbnormalGenerator(level="none")

    assert generator.apply_abnormal_value("PatientID", "P000001", "LO", 2, 16) == "P000001"


def test_none_level_all_vr_types() -> None:
    generator = AbnormalGenerator(level="none")
    test_cases = [
        ("StudyDate", "20260101", "DA"),
        ("StudyTime", "120000", "TM"),
        ("InstanceNumber", "10", "IS"),
        ("SliceThickness", "1.0", "DS"),
        ("Modality", "CT", "CS"),
        ("SOPInstanceUID", "1.2.840.10008.1", "UI"),
        ("PatientName", "Yamada^Taro", "PN"),
    ]

    for tag_name, normal_value, vr in test_cases:
        assert generator.apply_abnormal_value(tag_name, normal_value, vr, 2) == normal_value


def test_mild_exceeds_max_length() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("PatientID", "P000001", "LO", 2, max_length=16)

    assert isinstance(value, str)
    assert len(value) > 16


def test_mild_invalid_date() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("StudyDate", "20260101", "DA", 2)

    assert isinstance(value, str)
    assert re.fullmatch(r"\d{8}", value) is None


def test_mild_invalid_time() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("StudyTime", "123456", "TM", 2)

    assert isinstance(value, str)
    assert re.fullmatch(r"\d{6}", value) is None


def test_mild_invalid_integer_string() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("InstanceNumber", "10", "IS", 2)

    assert isinstance(value, str)
    assert value.lstrip("+-").isdigit() is False


def test_mild_invalid_decimal_string() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("SliceThickness", "1.0", "DS", 2)

    assert isinstance(value, str)
    with pytest.raises(ValueError):
        float(value)


def test_mild_invalid_code_string() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("Modality", "CT", "CS", 2)

    assert isinstance(value, str)
    assert value != value.upper() or value.isalnum() is False


def test_mild_invalid_uid_too_long() -> None:
    generator = AbnormalGenerator(level="mild")

    value = generator.apply_abnormal_value("SOPInstanceUID", "1.2.840.10008.1", "UI", 1)

    assert isinstance(value, str)
    assert len(value) > 64


def test_moderate_type1_returns_none() -> None:
    generator = AbnormalGenerator(level="moderate")

    value = generator.apply_abnormal_value("PatientID", "P000001", "LO", 1)

    assert value is None


def test_moderate_type2_sometimes_none() -> None:
    generator = AbnormalGenerator(level="moderate")

    random_values = [0.1, 0.9] * 50
    with patch("app.core.abnormal_generator.random.random", side_effect=random_values):
        values = [
            generator.apply_abnormal_value("PatientID", "P000001", "LO", 2)
            for _ in range(100)
        ]

    assert any(value is None for value in values)
    assert any(value is not None for value in values)


def test_moderate_uid_starts_with_zero() -> None:
    generator = AbnormalGenerator(level="moderate")

    value = generator.apply_abnormal_value("SOPInstanceUID", "1.2.840.10008.1", "UI", 3)

    assert isinstance(value, str)
    assert value.startswith("0")


def test_severe_type1_returns_none() -> None:
    generator = AbnormalGenerator(level="severe")

    value = generator.apply_abnormal_value("PatientID", "P000001", "LO", 1)

    assert value is None


def test_severe_type2_returns_none() -> None:
    generator = AbnormalGenerator(level="severe")

    value = generator.apply_abnormal_value("PatientID", "P000001", "LO", 2)

    assert value is None


def test_severe_uid_completely_invalid() -> None:
    generator = AbnormalGenerator(level="severe")

    # tag_type=3 は 50% で None になるため、random を固定して None 回避
    with patch("app.core.abnormal_generator.random.random", return_value=0.9):
        value = generator.apply_abnormal_value("SOPInstanceUID", "1.2.840.10008.1", "UI", 3)

    assert isinstance(value, str)
    assert any(char not in "0123456789." for char in value)


def test_invalid_level_raises_error() -> None:
    with pytest.raises(GenerationError):
        AbnormalGenerator(level="invalid")  # type: ignore[arg-type]


def test_level_property() -> None:
    generator = AbnormalGenerator(level="moderate")

    assert generator.level == "moderate"
