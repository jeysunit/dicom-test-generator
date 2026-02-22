"""DICOM dataset builder."""

from __future__ import annotations

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset

from .exceptions import DICOMBuildError
from .models import (
    InstanceConfig,
    Patient,
    SeriesConfig,
    SpatialCoordinates,
    StudyConfig,
    UIDContext,
)

# CT Image Storage SOP Class UID
CT_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.2"


class DICOMBuilder:
    """DICOM Dataset構築器（メインクラス）."""

    def build_ct_image(
        self,
        patient: Patient,
        study_config: StudyConfig,
        series_config: SeriesConfig,
        instance_config: InstanceConfig,
        uid_context: UIDContext,
        spatial: SpatialCoordinates,
        pixel_data: np.ndarray,
        file_meta: FileMetaDataset,
        sop_instance_uid: str,
        series_instance_uid: str,
        specific_character_set: str | None = None,
        use_ideographic: bool = True,
        use_phonetic: bool = True,
        bits_stored: int = 16,
    ) -> Dataset:
        """CT Image Storageを構築."""
        try:
            media_storage_sop_uid = str(
                getattr(file_meta, "MediaStorageSOPInstanceUID", "")
            )
            if media_storage_sop_uid != sop_instance_uid:
                raise DICOMBuildError(
                    "SOP Instance UID mismatch between dataset and file meta",
                    tag="MediaStorageSOPInstanceUID",
                )

            ds = Dataset()
            ds.file_meta = file_meta

            # Patient Module
            patient_name = patient.patient_name.to_dicom_pn(
                use_ideographic=use_ideographic,
                use_phonetic=use_phonetic,
            )
            ds.PatientName = patient_name
            self._apply_character_set(ds, patient_name, specific_character_set)
            ds.PatientID = patient.patient_id
            ds.PatientBirthDate = patient.birth_date
            ds.PatientSex = patient.sex
            if patient.age is not None:
                ds.PatientAge = patient.age
            if patient.weight is not None:
                ds.PatientWeight = str(patient.weight)
            if patient.size_in_meters is not None:
                ds.PatientSize = str(patient.size_in_meters)

            # General Study Module
            ds.StudyInstanceUID = uid_context.study_instance_uid
            ds.StudyDate = study_config.study_date
            ds.StudyTime = study_config.study_time
            ds.AccessionNumber = study_config.accession_number
            if study_config.study_description is not None:
                ds.StudyDescription = study_config.study_description
            if study_config.referring_physician_name is not None:
                ds.ReferringPhysicianName = study_config.referring_physician_name
            ds.StudyID = ""

            # General Series Module
            ds.Modality = "CT"
            ds.SeriesInstanceUID = series_instance_uid
            ds.SeriesNumber = str(series_config.series_number)
            if series_config.series_description is not None:
                ds.SeriesDescription = series_config.series_description
            if series_config.protocol_name is not None:
                ds.ProtocolName = series_config.protocol_name
            ds.FrameOfReferenceUID = uid_context.frame_of_reference_uid

            # General Image Module
            ds.InstanceNumber = str(instance_config.instance_number)
            ds.AcquisitionNumber = str(instance_config.acquisition_number)
            ds.ContentDate = study_config.study_date
            ds.ContentTime = study_config.study_time

            # SOP Common Module
            ds.SOPClassUID = str(
                getattr(file_meta, "MediaStorageSOPClassUID", CT_IMAGE_STORAGE)
            )
            ds.SOPInstanceUID = sop_instance_uid
            ds.InstanceCreatorUID = uid_context.instance_creator_uid

            # Spatial
            ds.ImagePositionPatient = [str(v) for v in spatial.image_position_patient]
            ds.ImageOrientationPatient = [
                str(v) for v in spatial.image_orientation_patient
            ]
            ds.SliceLocation = str(spatial.slice_location)
            ds.SliceThickness = str(series_config.slice_thickness)
            ds.PixelSpacing = [str(v) for v in spatial.pixel_spacing]

            # Pixel Data
            self._set_pixel_data(ds, pixel_data, bits_stored=bits_stored)

            # Transfer Syntax compatibility
            self._apply_transfer_syntax(ds, file_meta)

            return ds
        except Exception as exc:
            if isinstance(exc, DICOMBuildError):
                raise
            raise DICOMBuildError(f"Failed to build CT image dataset: {exc}") from exc

    def _set_pixel_data(
        self, ds: Dataset, pixel_data: np.ndarray, bits_stored: int = 16
    ) -> None:
        """ピクセルデータをDatasetに設定."""
        rows, cols = pixel_data.shape
        ds.Rows = rows
        ds.Columns = cols
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"

        if pixel_data.dtype == np.uint8:
            ds.BitsAllocated = 8
            ds.BitsStored = 8
            ds.HighBit = 7
            ds.PixelRepresentation = 0
        elif pixel_data.dtype == np.int16:
            ds.BitsAllocated = 16
            ds.BitsStored = bits_stored
            ds.HighBit = bits_stored - 1
            ds.PixelRepresentation = 1
            ds.RescaleIntercept = "-1024"
            ds.RescaleSlope = "1"
            ds.WindowCenter = ["40", "400"]
            ds.WindowWidth = ["400", "1500"]
        else:
            raise DICOMBuildError(
                f"Unsupported pixel data dtype: {pixel_data.dtype}",
                tag="PixelData",
            )

        ds.PixelData = pixel_data.tobytes()

    _SUPPORTED_TRANSFER_SYNTAXES = {
        "1.2.840.10008.1.2",      # Implicit VR Little Endian
        "1.2.840.10008.1.2.1",    # Explicit VR Little Endian
        "1.2.840.10008.1.2.2",    # Explicit VR Big Endian
    }

    def _apply_transfer_syntax(self, ds: Dataset, file_meta: FileMetaDataset) -> None:
        transfer_syntax_uid = str(getattr(file_meta, "TransferSyntaxUID", ""))
        if transfer_syntax_uid not in self._SUPPORTED_TRANSFER_SYNTAXES:
            raise DICOMBuildError(
                f"Unsupported Transfer Syntax UID: {transfer_syntax_uid}",
                tag="TransferSyntaxUID",
            )

    _DEFAULT_JP_CHARACTER_SET = r"ISO 2022 IR 6\ISO 2022 IR 87"

    def _apply_character_set(
        self,
        ds: Dataset,
        patient_name: str,
        specific_character_set: str | None,
    ) -> None:
        if specific_character_set is not None:
            parsed = self._parse_charset(specific_character_set)
            if parsed:
                ds.SpecificCharacterSet = parsed
            elif self._contains_non_ascii(patient_name):
                raise DICOMBuildError(
                    "SpecificCharacterSet is required for non-ASCII PatientName",
                    tag="SpecificCharacterSet",
                )
            return

        if self._contains_non_ascii(patient_name):
            ds.SpecificCharacterSet = self._parse_charset(self._DEFAULT_JP_CHARACTER_SET)

    @staticmethod
    def _parse_charset(value: str) -> str | list[str]:
        """バックスラッシュ区切りの文字セット文字列をリストに変換する."""
        parts = [s.strip() for s in value.split("\\") if s.strip()]
        if len(parts) <= 1:
            return parts[0] if parts else ""
        return parts

    def _contains_non_ascii(self, value: str) -> bool:
        return any(ord(char) > 127 for char in value)
