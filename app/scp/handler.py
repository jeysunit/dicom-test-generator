"""C-STORE handler for Storage SCP."""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from pydicom import dcmread
from pydicom.errors import InvalidDicomError

from app.core.exceptions import FileWriteError, SCPStoreError
from app.core.path_safety import ensure_within, safe_path_component
from app.core.uid_format import is_valid_uid
from app.scp.models import SCPConfig

logger = logging.getLogger(__name__)

STATUS_SUCCESS = 0x0000
# Error: Cannot understand（PS3.4 B.2.3）。受けた値の誤り・重複の拒否
STATUS_FAILURE = 0xC000
# Refused: Out of Resources（PS3.4 B.2.3）。保存先に書けない・保存先の外
STATUS_OUT_OF_RESOURCES = 0xA700
UID_SHORT_LENGTH = 20
UNKNOWN_PATIENT_FOLDER = "UNKNOWN"


class StorageHandler:
    """Handle incoming C-STORE requests and persist datasets."""

    def __init__(self, config: SCPConfig) -> None:
        self.config = config
        self.storage_dir = Path(config.storage_dir)

    def handle_store(self, event: Any) -> int:
        """PyNetDICOM C-STORE event handler."""
        try:
            dataset = event.dataset
            # 受けた値は送ってきた相手が自由に入れられる。名前に直してから使う（spec/11）
            raw_patient_id = str(dataset.get("PatientID", ""))
            patient_id = safe_path_component(raw_patient_id, UNKNOWN_PATIENT_FOLDER)
            study_uid = str(dataset.get("StudyInstanceUID", "")).strip()
            series_uid = str(dataset.get("SeriesInstanceUID", "")).strip()
            sop_uid = str(dataset.get("SOPInstanceUID", "")).strip()

            if not study_uid or not series_uid or not sop_uid:
                logger.error(
                    "Missing required DICOM UID for C-STORE: study=%r series=%r sop=%r",
                    study_uid,
                    series_uid,
                    sop_uid,
                )
                return STATUS_FAILURE
            invalid = [
                (keyword, uid)
                for keyword, uid in (
                    ("StudyInstanceUID", study_uid),
                    ("SeriesInstanceUID", series_uid),
                    ("SOPInstanceUID", sop_uid),
                )
                if not is_valid_uid(uid)
            ]
            if invalid:
                keyword, uid = invalid[0]
                logger.error("Invalid UID in C-STORE: %s=%r patient_id=%r", keyword, uid, raw_patient_id)
                return STATUS_FAILURE

            try:
                patient_dir = ensure_within(self.storage_dir, self.storage_dir / patient_id)
                study_dir_name = self._resolve_collision(
                    patient_dir,
                    self._shorten_uid(study_uid),
                    study_uid,
                )
                series_dir_name = self._resolve_collision(
                    patient_dir / study_dir_name,
                    self._shorten_uid(series_uid),
                    series_uid,
                )
                target_dir = ensure_within(
                    self.storage_dir, patient_dir / study_dir_name / series_dir_name
                )
                target_dir.mkdir(parents=True, exist_ok=True)
                # mkdir の間に差し替えられたリンクも、作った後に確かめ直す
                target_dir = ensure_within(self.storage_dir, target_dir)
                filepath = ensure_within(self.storage_dir, target_dir / f"{sop_uid}.dcm")
            except FileWriteError as exc:
                logger.error(
                    "Refused to store outside of storage_dir: sop_uid=%r reason=%s", sop_uid, exc
                )
                return STATUS_OUT_OF_RESOURCES
            except OSError as exc:
                err = SCPStoreError(f"Failed to create destination directory: {exc}", sop_uid=sop_uid)
                logger.error("%s", err)
                return STATUS_OUT_OF_RESOURCES

            if filepath.exists():
                if self.config.duplicate_handling == "reject":
                    logger.warning("Duplicate SOP Instance UID rejected: sop_uid=%r", sop_uid)
                    return STATUS_FAILURE
                try:
                    if self.config.duplicate_handling == "rename":
                        filepath = self._build_renamed_path(target_dir, sop_uid)
                        logger.info("Duplicate SOP renamed: sop_uid=%r", sop_uid)
                    elif os.lstat(filepath).st_nlink > 1:
                        # 外のファイルへのハードリンクを書き換えないよう、名前を外してから書く
                        filepath.unlink()
                except FileWriteError as exc:
                    logger.error(
                        "Refused to store outside of storage_dir: sop_uid=%r reason=%s", sop_uid, exc
                    )
                    return STATUS_OUT_OF_RESOURCES
                except OSError as exc:
                    err = SCPStoreError(f"Failed to replace the duplicate: {exc}", sop_uid=sop_uid)
                    logger.error("%s", err)
                    return STATUS_OUT_OF_RESOURCES

            if hasattr(event, "file_meta"):
                dataset.file_meta = event.file_meta

            try:
                dataset.save_as(filepath, write_like_original=False)
            except OSError as exc:
                err = SCPStoreError(f"Failed to store received dataset: {exc}", sop_uid=sop_uid)
                logger.error("%s", err)
                return STATUS_OUT_OF_RESOURCES
            except (AttributeError, TypeError, ValueError) as exc:
                err = SCPStoreError(f"Failed to store received dataset: {exc}", sop_uid=sop_uid)
                logger.error("%s", err)
                return STATUS_FAILURE

            logger.info("C-STORE stored successfully: sop_uid=%r patient_dir=%r", sop_uid, patient_id)
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
        # 外へのリンクなら中を読む前に止める（FileWriteError。呼ぶ側で Failure にする）
        ensure_within(self.storage_dir, target)
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
            # リンク・通常のファイルでないもの（FIFO など）は読まない
            if dcm_file.is_symlink() or not dcm_file.is_file():
                continue
            has_dicom_files = True
            try:
                ds = dcmread(
                    dcm_file,
                    stop_before_pixels=True,
                    specific_tags=["StudyInstanceUID", "SeriesInstanceUID"],
                )
            except (OSError, ValueError, InvalidDicomError):
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
            # 壊れたリンクは exists() が False になるので、リンクも「ある」とみなす
            if not candidate.exists() and not candidate.is_symlink():
                return ensure_within(self.storage_dir, candidate)
