"""C-STORE handler for Storage SCP."""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from pydicom import dcmread

from app.core.exceptions import SCPStoreError
from app.scp.models import SCPConfig

logger = logging.getLogger(__name__)

STATUS_SUCCESS = 0x0000
STATUS_FAILURE = 0xC000
UID_SHORT_LENGTH = 20


class StorageHandler:
    """Handle incoming C-STORE requests and persist datasets."""

    def __init__(self, config: SCPConfig) -> None:
        self.config = config
        self.storage_dir = Path(config.storage_dir)

    def handle_store(self, event: Any) -> int:
        """PyNetDICOM C-STORE event handler."""
        try:
            dataset = event.dataset
            patient_id = str(dataset.get("PatientID", "")).strip() or "UNKNOWN"
            study_uid = str(dataset.get("StudyInstanceUID", "")).strip()
            series_uid = str(dataset.get("SeriesInstanceUID", "")).strip()
            sop_uid = str(dataset.get("SOPInstanceUID", "")).strip()

            if not study_uid or not series_uid or not sop_uid:
                err = SCPStoreError("Missing required DICOM UID for C-STORE", sop_uid=sop_uid or None)
                logger.error("%s", err)
                return STATUS_FAILURE

            study_dir_name = self._resolve_collision(
                self.storage_dir / patient_id,
                self._shorten_uid(study_uid),
                study_uid,
            )
            series_dir_name = self._resolve_collision(
                self.storage_dir / patient_id / study_dir_name,
                self._shorten_uid(series_uid),
                series_uid,
            )

            target_dir = self.storage_dir / patient_id / study_dir_name / series_dir_name
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                err = SCPStoreError(f"Failed to create destination directory: {exc}", sop_uid=sop_uid)
                logger.error("%s", err)
                return STATUS_FAILURE

            filepath = target_dir / f"{sop_uid}.dcm"
            if filepath.exists():
                if self.config.duplicate_handling == "reject":
                    logger.warning("Duplicate SOP Instance UID rejected: sop_uid=%s", sop_uid)
                    return STATUS_FAILURE
                if self.config.duplicate_handling == "rename":
                    filepath = self._build_renamed_path(target_dir, sop_uid)
                    logger.info("Duplicate SOP renamed: sop_uid=%s", sop_uid)

            if hasattr(event, "file_meta"):
                dataset.file_meta = event.file_meta

            try:
                dataset.save_as(filepath, write_like_original=False)
            except (OSError, AttributeError, TypeError, ValueError) as exc:
                err = SCPStoreError(f"Failed to store received dataset: {exc}", sop_uid=sop_uid)
                logger.error("%s", err)
                return STATUS_FAILURE

            logger.info("C-STORE stored successfully: sop_uid=%s", sop_uid)
            return STATUS_SUCCESS
        except (AttributeError, TypeError, ValueError) as exc:
            err = SCPStoreError(f"Invalid C-STORE event payload: {exc}")
            logger.error("%s", err)
            return STATUS_FAILURE

    def _shorten_uid(self, uid: str) -> str:
        """Return first 20 characters of UID."""
        return uid[:UID_SHORT_LENGTH]

    def _resolve_collision(self, dirpath: Path, base_name: str, full_uid: str) -> str:
        """
        Resolve shortened UID directory collision.

        If ``dirpath/base_name`` exists and already contains data from another UID,
        append ``_<sha1[:8]>`` to avoid collisions.
        """
        target = dirpath / base_name
        if not target.exists() or not target.is_dir():
            return base_name

        has_files, contains_uid = self._contains_uid(target, full_uid)
        if not has_files or contains_uid:
            return base_name

        suffix = hashlib.sha1(full_uid.encode("utf-8")).hexdigest()[:8]
        return f"{base_name}_{suffix}"

    def _contains_uid(self, directory: Path, full_uid: str) -> tuple[bool, bool]:
        """Return (has_dicom_files, contains_uid)."""
        has_dicom_files = False
        for dcm_file in directory.rglob("*.dcm"):
            has_dicom_files = True
            try:
                ds = dcmread(
                    dcm_file,
                    stop_before_pixels=True,
                    specific_tags=["StudyInstanceUID", "SeriesInstanceUID"],
                )
            except (OSError, ValueError):
                continue

            study_uid = str(ds.get("StudyInstanceUID", "")).strip()
            series_uid = str(ds.get("SeriesInstanceUID", "")).strip()
            if full_uid in {study_uid, series_uid}:
                return has_dicom_files, True
        return has_dicom_files, False

    def _build_renamed_path(self, target_dir: Path, sop_uid: str) -> Path:
        """Build a unique timestamp-based filepath for duplicate SOP UID."""
        while True:
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            candidate = target_dir / f"{sop_uid}_{timestamp}.dcm"
            if not candidate.exists():
                return candidate
