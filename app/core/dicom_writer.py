"""DICOM writer helpers for file meta and spatial coordinates."""

from __future__ import annotations

from pydicom.dataset import FileMetaDataset

from .exceptions import FileMetaError
from .models import SpatialCoordinates


class FileMetaBuilder:
    """File Meta Information構築器."""

    def build(
        self,
        sop_class_uid: str,
        sop_instance_uid: str,
        transfer_syntax_uid: str,
        implementation_class_uid: str,
        implementation_version_name: str,
    ) -> FileMetaDataset:
        """File Meta (Group 0002) を構築する."""
        try:
            file_meta = FileMetaDataset()
            file_meta.FileMetaInformationVersion = b"\x00\x01"
            file_meta.MediaStorageSOPClassUID = sop_class_uid
            file_meta.MediaStorageSOPInstanceUID = sop_instance_uid
            file_meta.TransferSyntaxUID = transfer_syntax_uid
            file_meta.ImplementationClassUID = implementation_class_uid
            file_meta.ImplementationVersionName = implementation_version_name
            return file_meta
        except Exception as exc:
            if isinstance(exc, FileMetaError):
                raise
            raise FileMetaError(f"Failed to build File Meta Information: {exc}") from exc


class SpatialCalculator:
    """空間座標計算器."""

    def __init__(
        self,
        slice_thickness: float,
        slice_spacing: float,
        start_z: float = 0.0,
    ):
        self._slice_thickness = slice_thickness
        self._slice_spacing = slice_spacing
        self._start_z = start_z

    def calculate(self, slice_index: int) -> SpatialCoordinates:
        """指定スライスインデックス（0始まり）の空間座標を計算.

        instance_number = slice_index + 1
        z = start_z + (slice_index * slice_spacing)
        image_position_patient = [0.0, 0.0, z]
        slice_location = z
        """
        instance_number = slice_index + 1
        z = self._start_z + (slice_index * self._slice_spacing)

        return SpatialCoordinates(
            instance_number=instance_number,
            image_position_patient=[0.0, 0.0, z],
            slice_location=z,
        )
