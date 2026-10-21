"""ModalityService の守り：送る前のファイルの確かめ・誤りの文に値を出さない・撮影の量と同時の数.

docs/spec/12 の 8.2・12 章、docs/spec/12a の 10.5（2026-10-19 に決めた）。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port

from app.core.exceptions import FileReadError, ModalityError, ValidationError
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.service import ExamRequest, ModalityService

SECRET_NAME = "SECRET^PATIENTNAME"


def _service(tmp_path: Path, storage_port: int, **extra) -> ModalityService:
    config = ModalityConfig.model_validate(
        {
            "ae_title": "DTG_CT01",
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "default_pixel_mode": "simple_text",
            "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": free_port()},
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


def _exam(service: ModalityService, images: list[int] | None = None) -> str:
    patient = ScheduledPatient(patient_id="E0001", patient_name="KINKYU^TARO")
    request = ExamRequest(emergency_patient=patient, images_per_series=images or [2])
    return service.exam(request).output_dir


def _outside_file(tmp_path: Path) -> Path:
    outside = tmp_path / "outside"
    outside.mkdir()
    secret = outside / "secret.dcm"
    secret.write_bytes(b"not for the PACS")
    return secret


def test_send_refuses_symlink_to_outside(tmp_path, storage_scp) -> None:
    service = _service(tmp_path, storage_scp.port)
    folder = Path(_exam(service))
    (folder / "zz_link.dcm").symlink_to(_outside_file(tmp_path))

    with pytest.raises(FileReadError) as exc_info:
        service.send(str(folder))

    assert "zz_link.dcm" in str(exc_info.value)
    assert service.list_queue() == []
    assert storage_scp.received == []


def test_send_refuses_symlink_inside_the_folder_too(tmp_path, storage_scp) -> None:
    """symbolic link は中を指していても断る（入れた後に替えられても送らないため）."""
    service = _service(tmp_path, storage_scp.port)
    folder = Path(_exam(service))
    first = sorted(folder.glob("*.dcm"))[0]
    (folder / "zz_copy.dcm").symlink_to(first)

    with pytest.raises(FileReadError):
        service.send_exam_output(str(folder))
    assert storage_scp.received == []


def test_retry_rechecks_files(tmp_path, storage_scp) -> None:
    """再送でも確かめる：失敗の後にファイルを外を指す link に替えても送らない."""
    unreachable = _service(tmp_path, free_port())
    folder = Path(_exam(unreachable))
    failed = unreachable.send(str(folder))
    assert failed.status == "failed"

    target = sorted(folder.glob("*.dcm"))[0]
    target.unlink()
    target.symlink_to(_outside_file(tmp_path))

    reachable = _service(tmp_path, storage_scp.port)
    [result] = reachable.retry(job_id=failed.job_id)

    assert result.status == "failed"
    assert target.name in result.error
    assert storage_scp.received == []
    assert reachable.queue.get_job(failed.job_id).status == "failed"


def test_broken_state_error_does_not_show_values(tmp_path) -> None:
    """壊れた保存のデータの誤りの文に、入っていた値（氏名）を出さない（12 章）."""
    service = _service(tmp_path, free_port())
    state = tmp_path / "state"
    state.mkdir()
    (state / "worklist_last.json").write_text(
        json.dumps({"items": [{"patient_name": SECRET_NAME, "birth_date": 19800101}]}),
        encoding="utf-8",
    )

    with pytest.raises(FileReadError) as exc_info:
        service.last_worklist_state()

    text = str(exc_info.value)
    assert "SECRET" not in text
    assert "items.0" in text


def test_total_images_per_exam_is_limited(tmp_path) -> None:
    service = _service(tmp_path, free_port(), max_images_per_exam=5)

    with pytest.raises(ValidationError) as exc_info:
        _exam(service, [3, 3])

    assert "5" in str(exc_info.value)
    assert not list((tmp_path / "output").rglob("*.dcm"))
    assert _exam(service, [2, 3])


def test_default_total_images_limit_is_2000(tmp_path) -> None:
    assert _service(tmp_path, free_port()).config.max_images_per_exam == 2000


def test_only_one_exam_runs_at_a_time(tmp_path, monkeypatch) -> None:
    service = _service(tmp_path, free_port())
    started, release = threading.Event(), threading.Event()
    original = service._generator.generate

    def slow_generate(*args, **kwargs):
        started.set()
        release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(service._generator, "generate", slow_generate)
    results: list[str] = []
    worker = threading.Thread(target=lambda: results.append(_exam(service)))
    worker.start()
    try:
        assert started.wait(10)
        with pytest.raises(ModalityError) as exc_info:
            _exam(service)
        assert "ほかの撮影が走っています" in str(exc_info.value)
    finally:
        release.set()
        worker.join(30)
    assert len(results) == 1
    assert _exam(service)  # 終われば次を撮れる
