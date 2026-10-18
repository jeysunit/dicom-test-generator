"""設定（modality: の節）と待ち行列（sqlite3）の試験."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.core.exceptions import ModalityConfigError, ModalityError
from app.modality.config import load_modality_config
from app.modality.queue import SendQueue
from app.modality.store_scu import StoreFileResult

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "app_config.yaml"


def _write(tmp_path: Path, modality: dict) -> Path:
    path = tmp_path / "app_config.yaml"
    path.write_text(yaml.safe_dump({"modality": modality}, allow_unicode=True), encoding="utf-8")
    return path


def _minimal() -> dict:
    return {
        "ae_title": "DTG_CT01",
        "worklist": {"ae_title": "RIS_TEST", "host": "127.0.0.1", "port": 4242},
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": "pacs.example.org", "port": 104}
        ],
        "default_destination": "PACS_TEST",
    }


def test_repository_config_has_valid_modality_section() -> None:
    config = load_modality_config(REPO_CONFIG)

    assert config.listen.port == 11113
    assert config.character_set == "auto"
    assert config.character_set_fallback == "utf8"
    assert config.default_template == "ct_generic"
    assert config.destination().name == config.default_destination


def test_minimal_config_defaults(tmp_path) -> None:
    config = load_modality_config(_write(tmp_path, _minimal()))

    assert config.retry.max_attempts == 0
    assert config.worklist.timeout_seconds == 30
    assert config.destination("PACS_TEST").host == "pacs.example.org"


@pytest.mark.parametrize(
    "change",
    [
        {"ae_title": "A" * 17},
        {"ae_title": "   "},
        {"ae_title": "BAD\\AE"},
        {"character_set_fallback": "auto"},
        {"character_set": "latin1"},
        {"default_destination": "NOPE"},
    ],
)
def test_invalid_config_is_config_error(tmp_path, change) -> None:
    raw = {**_minimal(), **change}

    with pytest.raises(ModalityConfigError):
        load_modality_config(_write(tmp_path, raw))


def test_missing_section_and_file(tmp_path) -> None:
    path = tmp_path / "other.yaml"
    path.write_text("storage_scp: {}\n", encoding="utf-8")

    with pytest.raises(ModalityConfigError):
        load_modality_config(path)
    with pytest.raises(ModalityConfigError):
        load_modality_config(tmp_path / "missing.yaml")


def test_unknown_destination(tmp_path) -> None:
    config = load_modality_config(_write(tmp_path, _minimal()))

    with pytest.raises(ModalityConfigError):
        config.destination("OTHER")


def test_queue_records_results_and_retry_targets(tmp_path) -> None:
    queue = SendQueue(tmp_path / "state" / "queue.sqlite3")
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm", "b.dcm"], accession_number="A0001")

    queue.mark_sending(job_id)
    status = queue.record_results(
        job_id,
        [
            StoreFileResult(path="a.dcm", sop_instance_uid="1", status=0, outcome="success"),
            StoreFileResult(
                path="b.dcm", sop_instance_uid="2", status=0xA700, outcome="failure",
                reason="status 0xA700",
            ),
        ],
    )

    job = queue.get_job(job_id)
    assert status == "failed"
    assert job.num_files == 2
    assert job.num_sent == 1
    assert job.attempts == 1
    assert job.last_error == "status 0xA700"
    assert queue.unsent_files(job_id) == ["b.dcm"]
    assert [j.id for j in queue.list_jobs("failed")] == [job_id]
    assert queue.list_jobs("sent") == []


def test_queue_job_failure_and_counters(tmp_path) -> None:
    queue = SendQueue(tmp_path / "queue.sqlite3")
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm"])

    queue.record_job_failure(job_id, "could not connect")

    assert queue.get_job(job_id).status == "failed"
    assert queue.next_value("pps") == 1
    assert queue.next_value("pps") == 2
    assert queue.next_value("study") == 1
    with pytest.raises(ModalityError):
        queue.list_jobs("unknown")
    with pytest.raises(ModalityError):
        queue.get_job(999)
