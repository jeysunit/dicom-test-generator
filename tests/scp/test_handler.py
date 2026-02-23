from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from pydicom.dataset import FileDataset, FileMetaDataset
from pydicom.uid import ImplicitVRLittleEndian

from app.scp.handler import STATUS_FAILURE, STATUS_SUCCESS, StorageHandler
from app.scp.models import SCPConfig


class MockDataset:
    def __init__(self) -> None:
        self._values = {
            "PatientID": "P000001",
            "StudyInstanceUID": "2.25.123456789012345678901234",
            "SeriesInstanceUID": "2.25.987654321098765432109876",
            "SOPInstanceUID": "2.25.555555555555555555555555",
        }
        self.saved_paths: list[Path] = []
        self.file_meta: Any | None = None

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def save_as(self, filepath: Path, write_like_original: bool = False) -> None:
        del write_like_original
        filepath.parent.mkdir(parents=True, exist_ok=True)
        file_meta = FileMetaDataset()
        file_meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.2"
        file_meta.MediaStorageSOPInstanceUID = self._values["SOPInstanceUID"]
        file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
        file_meta.ImplementationClassUID = "1.2.826.0.1.3680043.8.498.1"

        ds = FileDataset(str(filepath), {}, file_meta=file_meta, preamble=b"\0" * 128)
        ds.PatientID = self._values["PatientID"]
        ds.StudyInstanceUID = self._values["StudyInstanceUID"]
        ds.SeriesInstanceUID = self._values["SeriesInstanceUID"]
        ds.SOPInstanceUID = self._values["SOPInstanceUID"]
        ds.save_as(filepath, write_like_original=False)
        self.saved_paths.append(filepath)


def _build_event(dataset: MockDataset) -> SimpleNamespace:
    return SimpleNamespace(dataset=dataset)


def test_handle_store_success_overwrite(tmp_path: Path) -> None:
    config = SCPConfig(storage_dir=str(tmp_path), duplicate_handling="overwrite")
    handler = StorageHandler(config)
    dataset = MockDataset()

    status = handler.handle_store(_build_event(dataset))

    assert status == STATUS_SUCCESS
    assert len(dataset.saved_paths) == 1
    assert dataset.saved_paths[0].exists()


def test_handle_store_duplicate_overwrite_success(tmp_path: Path) -> None:
    config = SCPConfig(storage_dir=str(tmp_path), duplicate_handling="overwrite")
    handler = StorageHandler(config)
    dataset = MockDataset()
    event = _build_event(dataset)

    first_status = handler.handle_store(event)
    second_status = handler.handle_store(event)

    assert first_status == STATUS_SUCCESS
    assert second_status == STATUS_SUCCESS
    assert len(dataset.saved_paths) == 2
    assert dataset.saved_paths[0] == dataset.saved_paths[1]
    assert dataset.saved_paths[0].exists()


def test_handle_store_duplicate_reject_failure(tmp_path: Path) -> None:
    config = SCPConfig(storage_dir=str(tmp_path), duplicate_handling="reject")
    handler = StorageHandler(config)
    dataset = MockDataset()
    event = _build_event(dataset)

    first_status = handler.handle_store(event)
    second_status = handler.handle_store(event)

    assert first_status == STATUS_SUCCESS
    assert second_status == STATUS_FAILURE
    assert len(dataset.saved_paths) == 1


def test_handle_store_duplicate_rename_creates_new_file(tmp_path: Path) -> None:
    config = SCPConfig(storage_dir=str(tmp_path), duplicate_handling="rename")
    handler = StorageHandler(config)
    dataset = MockDataset()
    event = _build_event(dataset)

    first_status = handler.handle_store(event)
    second_status = handler.handle_store(event)

    assert first_status == STATUS_SUCCESS
    assert second_status == STATUS_SUCCESS
    assert len(dataset.saved_paths) == 2
    assert dataset.saved_paths[0].name == "2.25.555555555555555555555555.dcm"
    assert dataset.saved_paths[1].name.startswith("2.25.555555555555555555555555_")
    assert dataset.saved_paths[1].name.endswith(".dcm")
    assert dataset.saved_paths[0] != dataset.saved_paths[1]


def test_shorten_uid_returns_first_20_chars(tmp_path: Path) -> None:
    handler = StorageHandler(SCPConfig(storage_dir=str(tmp_path)))

    shortened = handler._shorten_uid("123456789012345678901234567890")

    assert shortened == "12345678901234567890"


def test_resolve_collision_same_uid_returns_base_name(tmp_path: Path) -> None:
    handler = StorageHandler(SCPConfig(storage_dir=str(tmp_path)))
    parent_dir = tmp_path / "P000001"
    base_name = "2.25.123456789012345"
    target = parent_dir / base_name
    target.mkdir(parents=True)

    def _same_uid(*args: Any, **kwargs: Any) -> tuple[bool, bool]:
        del args, kwargs
        return (True, True)

    handler._contains_uid = _same_uid  # type: ignore[method-assign]

    resolved = handler._resolve_collision(parent_dir, base_name, "2.25.123456789012345999")

    assert resolved == base_name
