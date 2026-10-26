"""ModalityService の試験：信用できない予約の値でも出力の根の外に書かない（docs/spec/12 の 6.5）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST

from app.core.exceptions import (
    GenerationError,
    WorklistItemGoneError,
    WorklistItemNotFoundError,
    WorklistQueryError,
    WorklistRefreshTimeoutError,
)
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.service import ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery


def _service(tmp_path: Path, worklist_port: int, timeout_seconds: float = 30) -> ModalityService:
    config = ModalityConfig.model_validate(
        {
            "ae_title": "DTG_CT01",
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "worklist": {
                "ae_title": "RIS_TEST",
                "host": LOCALHOST,
                "port": worklist_port,
                "timeout_seconds": timeout_seconds,
            },
            "destinations": [
                {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": 104}
            ],
            "default_destination": "PACS_TEST",
        }
    )
    return ModalityService(config)


@pytest.mark.parametrize(
    ("accession", "patient_id"),
    [
        ("../../evil", "../../evil"),
        ("/etc/passwd", "/tmp/evil"),
        ("..", ".."),
        ("CON", "NUL"),
        ("A\\..\\..\\x", "P\\..\\x"),
    ],
)
def test_untrusted_worklist_values_stay_inside_output_root(
    tmp_path, worklist_scp, worklist_items, accession, patient_id
) -> None:
    evil = dict(worklist_items[0])
    evil["accession_number"] = accession
    evil["patient_id"] = patient_id
    worklist_scp.items = [evil]
    service = _service(tmp_path, worklist_scp.port)
    item = service.query_worklist(WorklistQuery()).items[0]

    result = service.exam(ExamRequest(worklist_key=item.key, pixel_mode="simple_text"))

    output_root = (tmp_path / "output").resolve()
    files = [Path(path) for path in result.files]
    assert len(files) == 1
    assert Path(result.output_dir).resolve().parent == output_root
    assert all(path.resolve().is_relative_to(output_root) for path in files)
    assert sorted(tmp_path.rglob("*.dcm")) == sorted(path.resolve() for path in files)


def test_refresh_with_partial_response_is_query_error(tmp_path, worklist_scp) -> None:
    """--refresh で時間の上限により途中までなら撮らずに 5 で止める（docs/spec/12 の 5.4）."""
    service = _service(tmp_path, worklist_scp.port, timeout_seconds=0.5)
    item = service.query_worklist(WorklistQuery()).items[0]
    worklist_scp.endless_pending = True

    with pytest.raises(WorklistQueryError) as exc_info:
        service.exam(ExamRequest(worklist_key=item.key, refresh=True, pixel_mode="simple_text"))

    assert exc_info.value.details["worklist_key"] == item.key
    assert isinstance(exc_info.value, WorklistRefreshTimeoutError)
    assert list((tmp_path / "output").rglob("*.dcm")) == []


def test_refresh_errors_tell_the_kind(tmp_path, worklist_scp) -> None:
    """再検索できない理由を例外の種類で分ける（画面の知らせ。docs/spec/12a の 10.4）."""
    service = _service(tmp_path, worklist_scp.port)
    item = service.query_worklist(WorklistQuery()).items[0]

    with pytest.raises(WorklistItemNotFoundError):
        service.refresh_item("")
    with pytest.raises(WorklistItemNotFoundError):
        service.find_item("0000000000")

    worklist_scp.items = []
    with pytest.raises(WorklistItemGoneError) as exc_info:
        service.refresh_item(item.key)
    assert exc_info.value.details["accession_number"] == item.accession_number


def test_failed_exam_removes_empty_output_folder(tmp_path, worklist_scp, monkeypatch) -> None:
    """撮影が止まったら、作った出力のフォルダが空なら消す（docs/spec/12 の 7.2）."""
    service = _service(tmp_path, worklist_scp.port)
    patient = ScheduledPatient(patient_id="E0001", patient_name="TAKAHASHI")

    def fail_before_any_file(config, scheduled=None, progress_callback=None):
        Path(config.output_dir).mkdir(parents=True)
        raise GenerationError("stopped before the first file")

    monkeypatch.setattr(service._generator, "generate", fail_before_any_file)

    with pytest.raises(GenerationError):
        service.exam(ExamRequest(emergency_patient=patient, pixel_mode="simple_text"))

    output_root = tmp_path / "output"
    assert not output_root.exists() or list(output_root.iterdir()) == []


def test_failed_exam_keeps_folder_with_files(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port)
    patient = ScheduledPatient(patient_id="E0002", patient_name="A^B")

    def fail_after_one_file(config, scheduled=None, progress_callback=None):
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True)
        (output_dir / "kept.dcm").write_bytes(b"")
        raise GenerationError("stopped in the middle")

    monkeypatch.setattr(service._generator, "generate", fail_after_one_file)

    with pytest.raises(GenerationError):
        service.exam(ExamRequest(emergency_patient=patient, pixel_mode="simple_text"))

    assert [path.name for path in (tmp_path / "output").rglob("*.dcm")] == ["kept.dcm"]
