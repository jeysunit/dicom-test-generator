"""手で入れる値の規格への適合の試験（PS3.5 6.2：値の区切り `\\`・DA）."""

from __future__ import annotations

from datetime import date

import pytest

from app.core.exceptions import ValidationError
from app.core.models import ScheduledPatient
from app.modality.service import ExamRequest
from app.modality.worklist_scu import parse_date_option
from tests.modality.test_service import _service


@pytest.mark.parametrize(
    ("patient_id", "patient_name", "description", "label"),
    [
        ("E\\0001", "KINKYU^TARO", "", "Patient ID"),
        ("E0001", "KINKYU\\TARO", "", "氏名"),
        ("E0001", "KINKYU^TARO", "CT\\CHEST", "検査の説明"),
    ],
)
def test_emergency_exam_rejects_value_delimiter(
    tmp_path, worklist_scp, patient_id, patient_name, description, label
) -> None:
    # `\` は値の区切りで、LO・PN・SH に入れると VM 2 で書かれる（PS3.5 6.2）
    service = _service(tmp_path, worklist_scp.port)
    patient = ScheduledPatient(patient_id=patient_id, patient_name=patient_name)

    with pytest.raises(ValidationError, match=label):
        service.exam(
            ExamRequest(
                emergency_patient=patient,
                study_description=description,
                pixel_mode="simple_text",
            )
        )
    output_root = tmp_path / "output"
    assert not output_root.exists() or not list(output_root.rglob("*.dcm"))


@pytest.mark.parametrize(
    "bad",
    [
        "20261399",
        "20260230",
        "20261000-20261031",
        "20261001-20261032",
        "２０２６1021",  # 全角の数字（DA は 0〜9 だけ）
        "٢٠٢٦1021",  # アラビア・インド数字
        "20261021\n",
    ],
)
def test_parse_date_option_rejects_dates_not_in_calendar(bad: str) -> None:
    with pytest.raises(ValidationError):
        parse_date_option(bad, date(2026, 10, 21))


def test_parse_date_option_accepts_leap_day() -> None:
    assert parse_date_option("20240229", date(2026, 10, 21)) == "20240229-20240229"
