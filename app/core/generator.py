"""DICOM dataset builder."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.valuerep import format_number_as_ds

from .exceptions import DICOMBuildError
from .series_layout import (
    CONTRAST_AGENT,
    MR_FIELD_OF_VIEW_MM,
    MR_SEQUENCE_PARAMETERS,
    image_type,
)
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
# MR Image Storage SOP Class UID（PS3.4 B.5）
MR_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.4"
# MR Image の Bits Stored の範囲。Bits Allocated は 16 で、Bits Stored は 12 以上にする
MR_BITS_STORED_MIN = 12
MR_BITS_STORED_MAX = 16
# Secondary Capture Image Storage（線量の画面。PS3.4 B.5・PS3.3 A.8.1）
SECONDARY_CAPTURE_IMAGE_STORAGE = "1.2.840.10008.5.1.4.1.1.7"
# SC Equipment Module の Conversion Type（PS3.3 C.8.6.1）。装置の画面を写した画像
DOSE_REPORT_CONVERSION_TYPE = "WSD"

# CT Image IOD の必須の属性の既定値（docs/spec/06 の「CT Image の必須の属性」）。
# 装置のプロファイルの attributes.set で変えられる（docs/spec/13）
DEFAULT_IMAGE_TYPE = ("ORIGINAL", "PRIMARY", "AXIAL")  # PS3.3 C.8.2.1.1.1
DEFAULT_PATIENT_POSITION = "HFS"  # PS3.3 C.7.3.1.1.2
DEFAULT_POSITION_REFERENCE_INDICATOR = ""  # PS3.3 C.7.4.1.1.2（Type 2）
# CT Image の Bits Stored の範囲（PS3.3 C.8.2.1.1.5）
CT_BITS_STORED_MIN = 12
CT_BITS_STORED_MAX = 16
# 廃止の転送の形（PS3.5 A.3）。作らない。異常のデータの約束（docs/spec/02）にも無い
RETIRED_TRANSFER_SYNTAXES = {"1.2.840.10008.1.2.2": "Explicit VR Big Endian"}

# DS（PS3.5 6.2、16 バイトまで）に書く前に丸める有効桁の数。
# float の誤差（16〜17 桁目）を落とし、小さい値も指数で残す
DS_SIGNIFICANT_DIGITS = 12


def format_ds(value: float) -> str:
    """数を 16 バイト以内の DS の文字にする（PS3.5 6.2）.

    浮動小数の誤差（0.1 * 3 = 0.30000000000000004）を有効 12 桁で丸めてから、
    なお長ければ pydicom で 16 字に収める（指数の形を含む）。
    """
    rounded = float(f"{float(value):.{DS_SIGNIFICANT_DIGITS}g}")
    return format_number_as_ds(rounded)


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

            ds = self._patient_study_series(
                file_meta,
                patient,
                study_config,
                series_config,
                uid_context,
                series_instance_uid,
                specific_character_set,
                use_ideographic,
                use_phonetic,
            )
            ds.PatientPosition = DEFAULT_PATIENT_POSITION

            # Frame of Reference Module
            ds.FrameOfReferenceUID = uid_context.frame_of_reference_uid
            ds.PositionReferenceIndicator = DEFAULT_POSITION_REFERENCE_INDICATOR

            # General Image Module・CT Image Module。種類はルーチンのシリーズの種類
            # （手で入れたシリーズは axial で、DEFAULT_IMAGE_TYPE と同じ）
            ds.ImageType = image_type(series_config)
            if series_config.contrast:
                # Contrast/Bolus Module は造影を使ったときに要る（PS3.3 C.7.6.4）
                ds.ContrastBolusAgent = CONTRAST_AGENT
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
            ds.ImagePositionPatient = [
                format_ds(v) for v in spatial.image_position_patient
            ]
            ds.ImageOrientationPatient = [
                format_ds(v) for v in spatial.image_orientation_patient
            ]
            ds.SliceLocation = format_ds(spatial.slice_location)
            ds.SliceThickness = format_ds(series_config.slice_thickness)
            ds.PixelSpacing = [format_ds(v) for v in spatial.pixel_spacing]

            # Pixel Data
            self._set_pixel_data(ds, pixel_data, bits_stored=bits_stored)

            # Transfer Syntax compatibility
            self._apply_transfer_syntax(ds, file_meta)

            return ds
        except Exception as exc:
            if isinstance(exc, DICOMBuildError):
                raise
            raise DICOMBuildError(f"Failed to build CT image dataset: {exc}") from exc

    def build_mr_image(
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
        bits_stored: int = 12,
    ) -> Dataset:
        """MR Image Storage を構築（PS3.3 A.4、MR Image Module は C.8.3.1）."""
        try:
            if str(getattr(file_meta, "MediaStorageSOPInstanceUID", "")) != sop_instance_uid:
                raise DICOMBuildError(
                    "SOP Instance UID mismatch between dataset and file meta",
                    tag="MediaStorageSOPInstanceUID",
                )
            if series_config.modality != "MR":
                raise DICOMBuildError(
                    f"MR image needs an MR series, got {series_config.modality}",
                    tag="Modality",
                )
            ds = self._patient_study_series(
                file_meta,
                patient,
                study_config,
                series_config,
                uid_context,
                series_instance_uid,
                specific_character_set,
                use_ideographic,
                use_phonetic,
            )
            ds.PatientPosition = DEFAULT_PATIENT_POSITION
            # Frame of Reference Module
            ds.FrameOfReferenceUID = uid_context.frame_of_reference_uid
            ds.PositionReferenceIndicator = DEFAULT_POSITION_REFERENCE_INDICATOR
            # General Image Module・MR Image Module
            ds.ImageType = image_type(series_config)
            ds.InstanceNumber = str(instance_config.instance_number)
            ds.AcquisitionNumber = str(instance_config.acquisition_number)
            ds.ContentDate = study_config.study_date
            ds.ContentTime = study_config.study_time
            self._set_mr_acquisition(ds, series_config)
            # SOP Common Module
            ds.SOPClassUID = MR_IMAGE_STORAGE
            ds.SOPInstanceUID = sop_instance_uid
            ds.InstanceCreatorUID = uid_context.instance_creator_uid
            # Image Plane Module。画素間隔は視野 ÷ 画素数
            ds.ImagePositionPatient = [format_ds(v) for v in spatial.image_position_patient]
            ds.ImageOrientationPatient = [format_ds(v) for v in spatial.image_orientation_patient]
            ds.SliceLocation = format_ds(spatial.slice_location)
            ds.SliceThickness = format_ds(series_config.slice_thickness)
            ds.SpacingBetweenSlices = format_ds(series_config.slice_spacing)
            rows, cols = pixel_data.shape
            ds.PixelSpacing = [
                format_ds(MR_FIELD_OF_VIEW_MM / rows),
                format_ds(MR_FIELD_OF_VIEW_MM / cols),
            ]
            self._set_mr_pixel_data(ds, pixel_data, bits_stored)
            self._apply_transfer_syntax(ds, file_meta)
            return ds
        except Exception as exc:
            if isinstance(exc, DICOMBuildError):
                raise
            raise DICOMBuildError(f"Failed to build MR image dataset: {exc}") from exc

    @staticmethod
    def _set_mr_acquisition(ds: Dataset, series_config: SeriesConfig) -> None:
        """MR Image Module の撮像の値（Scanning Sequence ごとの架空の条件。PS3.3 C.8.3.1）."""
        params = MR_SEQUENCE_PARAMETERS[series_config.sequence]
        ds.ScanningSequence = series_config.sequence
        ds.SequenceVariant = (
            params.sequence_variant[0]
            if len(params.sequence_variant) == 1
            else list(params.sequence_variant)
        )
        ds.ScanOptions = ""
        ds.MRAcquisitionType = series_config.acquisition_type
        ds.RepetitionTime = format_ds(params.repetition_time_ms)
        ds.EchoTime = format_ds(params.echo_time_ms)
        ds.EchoTrainLength = params.echo_train_length
        if params.inversion_time_ms is not None:
            ds.InversionTime = format_ds(params.inversion_time_ms)

    def _set_mr_pixel_data(
        self, ds: Dataset, pixel_data: np.ndarray, bits_stored: int
    ) -> None:
        """MR の画素（Bits Allocated 16・符号なし。PS3.3 C.8.3.1.1.4）を設定する."""
        if not MR_BITS_STORED_MIN <= bits_stored <= MR_BITS_STORED_MAX:
            raise DICOMBuildError(
                f"Bits Stored {bits_stored} is not allowed for MR "
                f"({MR_BITS_STORED_MIN}..{MR_BITS_STORED_MAX})",
                tag="BitsStored",
            )
        upper = (1 << bits_stored) - 1
        if pixel_data.dtype == np.uint8:
            pixels = np.rint(pixel_data.astype(np.float64) * upper / np.iinfo(np.uint8).max)
            pixels = pixels.astype(np.uint16)
        elif pixel_data.dtype == np.int16:
            if pixel_data.size and (int(pixel_data.min()) < 0 or int(pixel_data.max()) > upper):
                raise DICOMBuildError(
                    f"Pixel values {int(pixel_data.min())}..{int(pixel_data.max())} "
                    f"do not fit unsigned Bits Stored {bits_stored} (0..{upper})",
                    tag="PixelData",
                )
            pixels = pixel_data.astype(np.uint16)
        else:
            raise DICOMBuildError(
                f"Unsupported pixel data dtype: {pixel_data.dtype}", tag="PixelData"
            )
        rows, cols = pixels.shape
        ds.Rows = rows
        ds.Columns = cols
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"
        ds.BitsAllocated = 16
        ds.BitsStored = bits_stored
        ds.HighBit = bits_stored - 1
        ds.PixelRepresentation = 0
        ds.WindowCenter = format_ds((upper + 1) / 4)
        ds.WindowWidth = format_ds((upper + 1) / 2)
        ds.PixelData = pixels.tobytes()

    def build_dose_report(
        self,
        patient: Patient,
        study_config: StudyConfig,
        series_config: SeriesConfig,
        instance_config: InstanceConfig,
        uid_context: UIDContext,
        pixel_data: np.ndarray,
        file_meta: FileMetaDataset,
        sop_instance_uid: str,
        series_instance_uid: str,
        specific_character_set: str | None = None,
        use_ideographic: bool = True,
        use_phonetic: bool = True,
    ) -> Dataset:
        """線量の画面を Secondary Capture Image Storage で構築（PS3.3 A.8.1）.

        Modality は CT（装置が作った画面）。Frame of Reference・Image Plane・CT Image の
        属性は持たない。画素は 8 ビットの MONOCHROME2。
        """
        try:
            if str(getattr(file_meta, "MediaStorageSOPInstanceUID", "")) != sop_instance_uid:
                raise DICOMBuildError(
                    "SOP Instance UID mismatch between dataset and file meta",
                    tag="MediaStorageSOPInstanceUID",
                )
            if pixel_data.dtype != np.uint8:
                raise DICOMBuildError(
                    f"Dose report pixel data must be uint8, got {pixel_data.dtype}",
                    tag="PixelData",
                )
            ds = self._patient_study_series(
                file_meta,
                patient,
                study_config,
                series_config,
                uid_context,
                series_instance_uid,
                specific_character_set,
                use_ideographic,
                use_phonetic,
            )
            # SC Equipment Module（PS3.3 C.8.6.1）
            ds.ConversionType = DOSE_REPORT_CONVERSION_TYPE
            # General Image Module。Patient Orientation は Type 2C で、Image Orientation
            # (Patient) を持たない画像で要る。人体の向きの無い画面なので空（PS3.3 C.7.6.1）
            ds.ImageType = image_type(series_config)
            ds.InstanceNumber = str(instance_config.instance_number)
            ds.PatientOrientation = ""
            ds.ContentDate = study_config.study_date
            ds.ContentTime = study_config.study_time
            # SOP Common Module
            ds.SOPClassUID = SECONDARY_CAPTURE_IMAGE_STORAGE
            ds.SOPInstanceUID = sop_instance_uid
            ds.InstanceCreatorUID = uid_context.instance_creator_uid
            # Image Pixel Module（8 ビット。PS3.3 C.7.6.3）
            rows, cols = pixel_data.shape
            ds.Rows = rows
            ds.Columns = cols
            ds.SamplesPerPixel = 1
            ds.PhotometricInterpretation = "MONOCHROME2"
            ds.BitsAllocated = 8
            ds.BitsStored = 8
            ds.HighBit = 7
            ds.PixelRepresentation = 0
            ds.PixelData = pixel_data.tobytes()
            self._apply_transfer_syntax(ds, file_meta)
            return ds
        except Exception as exc:
            if isinstance(exc, DICOMBuildError):
                raise
            raise DICOMBuildError(f"Failed to build dose report dataset: {exc}") from exc

    def _patient_study_series(
        self,
        file_meta: FileMetaDataset,
        patient: Patient,
        study_config: StudyConfig,
        series_config: SeriesConfig,
        uid_context: UIDContext,
        series_instance_uid: str,
        specific_character_set: str | None,
        use_ideographic: bool,
        use_phonetic: bool,
    ) -> Dataset:
        """Patient・General Study・General Series の Module（CT と線量の画面で共通）."""
        ds = Dataset()
        ds.file_meta = file_meta

        # Patient Module
        patient_name = patient.patient_name.to_dicom_pn(
            use_ideographic=use_ideographic,
            use_phonetic=use_phonetic,
        )
        self._apply_character_set(ds, patient_name, specific_character_set)
        ds.PatientName = patient_name
        ds.PatientID = patient.patient_id
        ds.PatientBirthDate = patient.birth_date
        ds.PatientSex = patient.sex
        ds.PatientAge = self._calculate_patient_age(
            patient.birth_date,
            study_config.study_date,
        )
        if patient.weight is not None:
            ds.PatientWeight = format_ds(patient.weight)
        if patient.size_in_meters is not None:
            ds.PatientSize = format_ds(patient.size_in_meters)

        # General Study Module
        ds.StudyInstanceUID = uid_context.study_instance_uid
        ds.StudyDate = study_config.study_date
        ds.StudyTime = study_config.study_time
        ds.AccessionNumber = study_config.accession_number
        if study_config.study_description is not None:
            ds.StudyDescription = study_config.study_description
        # Type 2（PS3.3 C.7.2.1）。紹介医が無ければ空の値で出す
        ds.ReferringPhysicianName = study_config.referring_physician_name or ""
        ds.StudyID = ""

        # General Series Module
        # SC の線量の画面は CT の装置の画面なので、Modality はシリーズの値（CT）のまま
        ds.Modality = series_config.modality or "CT"
        ds.SeriesInstanceUID = series_instance_uid
        ds.SeriesNumber = str(series_config.series_number)
        if series_config.series_description is not None:
            ds.SeriesDescription = series_config.series_description
        if series_config.protocol_name is not None:
            ds.ProtocolName = series_config.protocol_name
        return ds

    def _set_pixel_data(
        self, ds: Dataset, pixel_data: np.ndarray, bits_stored: int = 16
    ) -> None:
        """ピクセルデータをDatasetに設定."""
        rows, cols = pixel_data.shape
        ds.Rows = rows
        ds.Columns = cols
        ds.SamplesPerPixel = 1
        ds.PhotometricInterpretation = "MONOCHROME2"

        if not CT_BITS_STORED_MIN <= bits_stored <= CT_BITS_STORED_MAX:
            raise DICOMBuildError(
                f"Bits Stored {bits_stored} is not allowed for CT "
                f"({CT_BITS_STORED_MIN}..{CT_BITS_STORED_MAX}, PS3.3 C.8.2.1.1.5)",
                tag="BitsStored",
            )
        if pixel_data.dtype == np.uint8:
            # CT Image は Bits Allocated 16・Bits Stored 12〜16 で、Rescale が
            # Type 1（PS3.3 C.8.2.1.1.4・C.8.2.1.1.5）。8 ビットの文字の画像は
            # 0〜255 を 0〜Bits Stored の上限に広げ、CT の画素として書く
            pixel_data = self._text_image_to_ct(pixel_data, bits_stored)
        if pixel_data.dtype == np.int16:
            self._check_signed_range(pixel_data, bits_stored)
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

    @staticmethod
    def _text_image_to_ct(pixel_data: np.ndarray, bits_stored: int) -> np.ndarray:
        """uint8 の画像（0〜255）を、符号ありの Bits Stored の 0〜上限にする."""
        upper = (1 << (bits_stored - 1)) - 1
        scaled = np.rint(pixel_data.astype(np.float64) * upper / np.iinfo(np.uint8).max)
        return scaled.astype(np.int16)

    @staticmethod
    def _check_signed_range(pixel_data: np.ndarray, bits_stored: int) -> None:
        """符号ありの画素が Bits Stored で表せるかを確かめる（PS3.5 8）.

        Bits Stored を超える値は、読む側が High Bit で符号を広げるため
        別の値に化ける（12 ビットの 2048 は -2048 になる）。
        """
        lower = -(1 << (bits_stored - 1))
        upper = (1 << (bits_stored - 1)) - 1
        if pixel_data.size and (
            int(pixel_data.min()) < lower or int(pixel_data.max()) > upper
        ):
            raise DICOMBuildError(
                f"Pixel values {int(pixel_data.min())}..{int(pixel_data.max())} "
                f"do not fit signed Bits Stored {bits_stored} ({lower}..{upper})",
                tag="PixelData",
            )

    _SUPPORTED_TRANSFER_SYNTAXES = {
        "1.2.840.10008.1.2",      # Implicit VR Little Endian
        "1.2.840.10008.1.2.1",    # Explicit VR Little Endian
    }

    def _apply_transfer_syntax(self, ds: Dataset, file_meta: FileMetaDataset) -> None:
        transfer_syntax_uid = str(getattr(file_meta, "TransferSyntaxUID", ""))
        if transfer_syntax_uid in RETIRED_TRANSFER_SYNTAXES:
            raise DICOMBuildError(
                f"{RETIRED_TRANSFER_SYNTAXES[transfer_syntax_uid]} ({transfer_syntax_uid}) "
                "is retired and is not generated (PS3.5 A.3)",
                tag="TransferSyntaxUID",
            )
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

    @staticmethod
    def _age_reached_date(birth: date, n: int) -> date:
        """民法143条に基づきN歳到達日（加齢日）を算出する.

        年齢計算ニ関スル法律: 出生日から起算し、誕生日の前日の満了をもって加齢。
        加齢日 = 誕生日のN年後の応当日の前日。
        応当日が存在しない場合（2/29生まれの非閏年）→ その月の末日（2/28）を
        応当日とみなし、その前日（2/27）…ではなく、
        誕生日の前日（2/28）のN年後 = 2/28 が加齢日。
        """
        # 誕生日の前日のN年後を直接求める（前日は常に存在する）
        eve = birth - timedelta(days=1)
        target_year = eve.year + n
        try:
            return eve.replace(year=target_year)
        except ValueError:
            # eve が 2/28 で target_year が閏年の場合は起こらない
            # eve が 2/29（birth=3/1 で閏年）で非閏年の場合 → 2/28
            return date(target_year, eve.month, 28)

    def _calculate_patient_age(self, birth_date: str, study_date: str) -> str:
        try:
            birth = datetime.strptime(birth_date, "%Y%m%d").date()
            study = datetime.strptime(study_date, "%Y%m%d").date()
        except ValueError as exc:
            raise DICOMBuildError(
                f"Invalid date format for PatientAge calculation: {exc}",
                tag="PatientAge",
            ) from exc

        if study < birth:
            raise DICOMBuildError(
                "study_date must be on or after birth_date for PatientAge",
                tag="PatientAge",
            )

        age_years = study.year - birth.year
        if study >= self._age_reached_date(birth, age_years + 1):
            age_years += 1
        elif study < self._age_reached_date(birth, age_years):
            age_years -= 1

        if not 0 <= age_years <= 999:
            raise DICOMBuildError(
                "Calculated PatientAge is out of DICOM AS range",
                tag="PatientAge",
            )
        return f"{age_years:03d}Y"
