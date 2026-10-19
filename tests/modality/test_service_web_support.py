"""ModalityService の、画面（Phase 3b）から使う道の試験（spec/12a の 10 章・spec/13 の 8 章）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST
from pydicom import dcmread

from app.core.exceptions import (
    FileReadError,
    FileWriteError,
    ProfileMismatchError,
    TemplateNotFoundError,
    ValidationError,
)
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.service import ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery

EXAMPLE_PROFILE = "dtg_synthetic_ct"


def _service(
    tmp_path: Path, worklist_port: int, storage_port: int = 104, **extra
) -> ModalityService:
    config = ModalityConfig.model_validate(
        {
            "ae_title": "DTG_CT01",
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
            "destinations": [
                {
                    "name": "PACS_TEST",
                    "ae_title": "PACS_TEST",
                    "host": LOCALHOST,
                    "port": storage_port,
                    "timeout_seconds": 5,
                }
            ],
            "default_destination": "PACS_TEST",
            **extra,
        }
    )
    return ModalityService(config)


def test_last_worklist_state_keeps_response_character_set(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)
    assert service.last_worklist_state().items == []

    service.query_worklist(WorklistQuery())
    state = service.last_worklist_state()

    assert state.response_character_set == ["ISO_IR 192"]
    assert state.queried_at
    assert [item.accession_number for item in state.items][:2] == ["A0001", "A0002"]


def test_exam_with_profile_overlays_device_values(tmp_path, worklist_scp) -> None:
    """撮影の画面の「装置」：プロファイルを重ね、最初の転送の形を使う（spec/13 の 4.3・8）."""
    service = _service(tmp_path, worklist_scp.port)
    item = service.query_worklist(WorklistQuery(accession_number="A0001")).items[0]

    result = service.exam(
        ExamRequest(worklist_key=item.key, profile=EXAMPLE_PROFILE, pixel_mode="simple_text")
    )

    ds = dcmread(result.files[0])
    assert ds.Manufacturer == "DTG Synthetic"
    assert ds.ManufacturerModelName == "DTG Synthetic CT 64"
    assert ds.file_meta.TransferSyntaxUID == "1.2.840.10008.1.2.1"
    assert ds.PatientID == "P000001"


def test_default_profile_from_config(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, default_profile=EXAMPLE_PROFILE)
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")

    result = service.exam(ExamRequest(emergency_patient=patient, pixel_mode="simple_text"))

    assert dcmread(result.files[0]).Manufacturer == "DTG Synthetic"


def test_profile_modality_must_match_template(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port)
    monkeypatch.setattr(service, "template_modality", lambda name: "MR")
    with pytest.raises(ProfileMismatchError):
        service.check_profile_modality(EXAMPLE_PROFILE, "MR")
    service.check_profile_modality(EXAMPLE_PROFILE, "CT")
    service.check_profile_modality(None, "MR")


def test_available_templates_and_profiles(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    assert "ct_generic" in service.available_templates()
    profiles, errors = service.available_profiles()
    assert (EXAMPLE_PROFILE, "CT") in [(p.name, p.modality) for p in profiles]
    assert errors == []


def test_send_exam_output_refuses_folders_outside_output_root(tmp_path, worklist_scp) -> None:
    """画面から来るフォルダは信用しない。出力の根の外は送らない（spec/12 の 6.5）."""
    service = _service(tmp_path, worklist_scp.port)
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "x.dcm").write_bytes(b"")

    with pytest.raises(FileWriteError):
        service.send_exam_output(str(outside))
    with pytest.raises(FileWriteError):
        service.send_exam_output(str(tmp_path / "output" / ".." / "elsewhere"))
    with pytest.raises(FileReadError):
        service.send_exam_output(str(tmp_path / "output" / "missing"))
    assert service.list_queue() == []


def test_send_exam_output_sends_inside_output_root(tmp_path, worklist_scp, storage_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, storage_scp.port)
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    exam = service.exam(ExamRequest(emergency_patient=patient, pixel_mode="simple_text"))

    sent = service.send_exam_output(exam.output_dir)

    assert sent.status == "sent"
    assert len(storage_scp.received) == 1


@pytest.mark.parametrize("name", ["../../config/app_config", "/etc/hosts", "ct_generic/../x", ""])
def test_template_name_must_be_a_listed_template(tmp_path, worklist_scp, name) -> None:
    """画面から来るテンプレートの名前で、テンプレートの置き場の外を読まない."""
    service = _service(tmp_path, worklist_scp.port)
    with pytest.raises(TemplateNotFoundError):
        service.template_modality(name)
    patient = ScheduledPatient(patient_id="E0001", patient_name="A^B")
    with pytest.raises(TemplateNotFoundError):
        service.exam(ExamRequest(emergency_patient=patient, template=name or "x/y"))


def test_emergency_person_name_is_normalized_on_the_server(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)
    assert service.emergency_person_name(" Kinkyu  Taro ", "緊急　太郎", "") == (
        "Kinkyu^Taro=緊急^太郎"
    )
    with pytest.raises(ValidationError):
        service.emergency_person_name("A=B", "", "")


@pytest.mark.parametrize("name", ["", "=緊急^太郎", "  "])
def test_emergency_exam_requires_alphabetic_name(tmp_path, worklist_scp, name) -> None:
    """緊急の患者の氏名（英字）は必須。CLI からも同じ（spec/12a の 10.5・11.4）."""
    service = _service(tmp_path, worklist_scp.port)
    patient = ScheduledPatient(patient_id="E0001", patient_name=name)
    with pytest.raises(ValidationError):
        service.exam(ExamRequest(emergency_patient=patient, pixel_mode="simple_text"))
    assert not list((tmp_path / "output").rglob("*.dcm"))


def test_image_character_set_for_the_band(tmp_path, worklist_scp) -> None:
    """画面の帯の「ワークリスト → 画像」の文字コード（spec/12 の 7.1）."""
    service = _service(tmp_path, worklist_scp.port)

    assert service.image_character_set(["ISO_IR 192"]) == ["ISO_IR 192"]
    assert service.image_character_set([]) == ["ISO_IR 192"]
    assert service.image_character_set(["ISO_IR 192"], "jis_kana") == [
        "ISO 2022 IR 13",
        "ISO 2022 IR 87",
    ]
