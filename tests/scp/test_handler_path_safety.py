"""Storage SCP は受けた Patient ID・UID をそのままパスに使わない（spec/11 の「受けた値は信用しない」）."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.scp.handler import (
    STATUS_FAILURE,
    STATUS_OUT_OF_RESOURCES,
    STATUS_SUCCESS,
    StorageHandler,
)
from app.scp.models import SCPConfig

from .test_handler import MockDataset, _build_event

GOOD_STUDY = "2.25.123456789012345678901234"


def _store(tmp_path: Path, **values: str) -> tuple[int, MockDataset, Path]:
    storage_dir = tmp_path / "storage"
    handler = StorageHandler(SCPConfig(storage_dir=str(storage_dir)))
    dataset = MockDataset()
    dataset._values.update(values)
    status = handler.handle_store(_build_event(dataset))
    return status, dataset, storage_dir


def _files_outside(tmp_path: Path, storage_dir: Path) -> list[Path]:
    root = storage_dir.resolve()
    return [
        path for path in tmp_path.rglob("*") if path.is_file() and not path.resolve().is_relative_to(root)
    ]


@pytest.mark.parametrize(
    ("patient_id", "folder"),
    [
        ("../../evil", ".._.._evil"),
        ("/abs/evil", "_abs_evil"),
        ("a\x00b", "a_b"),
        ("..", "UNKNOWN"),
        ("", "UNKNOWN"),
        ("CON", "_CON"),
        ("P\\..\\x", "P_.._x"),
    ],
)
def test_untrusted_patient_id_stays_inside_storage_dir(
    tmp_path: Path, patient_id: str, folder: str
) -> None:
    status, dataset, storage_dir = _store(tmp_path, PatientID=patient_id)

    assert status == STATUS_SUCCESS
    saved = dataset.saved_paths[0]
    assert saved.resolve().is_relative_to(storage_dir.resolve())
    assert saved.relative_to(storage_dir).parts[0] == folder
    assert _files_outside(tmp_path, storage_dir) == []


@pytest.mark.parametrize("keyword", ["StudyInstanceUID", "SeriesInstanceUID", "SOPInstanceUID"])
@pytest.mark.parametrize(
    "uid", ["..", "../../x", "/etc/x", "1.2\x00", "1.2/../../x", "1" * 65, "01.2", "1..2", "abc"]
)
def test_bad_uid_is_failure_and_writes_nothing(tmp_path: Path, keyword: str, uid: str) -> None:
    status, dataset, storage_dir = _store(tmp_path, **{keyword: uid})

    assert status == STATUS_FAILURE
    assert dataset.saved_paths == []
    assert not storage_dir.exists() or list(storage_dir.rglob("*.dcm")) == []
    assert _files_outside(tmp_path, storage_dir) == []


def test_symlink_escape_is_refused(tmp_path: Path) -> None:
    """storage_dir の中のリンクで外へ抜ける形も、保存せずに Failure を返す."""
    storage_dir = tmp_path / "storage"
    outside = tmp_path / "outside"
    storage_dir.mkdir()
    outside.mkdir()
    (storage_dir / "P000001").symlink_to(outside, target_is_directory=True)

    status, dataset, _ = _store(tmp_path, PatientID="P000001")

    assert status == STATUS_OUT_OF_RESOURCES
    assert dataset.saved_paths == []
    assert list(outside.rglob("*")) == []


def test_write_failure_is_out_of_resources(tmp_path: Path) -> None:
    storage_dir = tmp_path / "storage"
    storage_dir.mkdir()
    (storage_dir / "P000001").write_text("not a folder", encoding="utf-8")

    status, dataset, _ = _store(tmp_path, PatientID="P000001")

    assert status == STATUS_OUT_OF_RESOURCES
    assert dataset.saved_paths == []


def test_logs_received_values_with_repr(tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.scp.handler")

    status, _, _ = _store(tmp_path, SOPInstanceUID="1.2\x1b[2J")
    assert status == STATUS_FAILURE
    status, _, _ = _store(tmp_path, PatientID="P\x1b]0;x\x07")
    assert status == STATUS_SUCCESS

    messages = [record.getMessage() for record in caplog.records]
    assert messages
    assert not any("\x1b" in message or "\x07" in message for message in messages)
    assert any(repr("1.2\x1b[2J") in message for message in messages)
