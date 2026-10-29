"""DICOM study generation service."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pydicom
from pydicom.dataset import Dataset

from app.core import (
    CT_IMAGE_STORAGE,
    AbnormalGenerator,
    apply_abnormal_to_dataset,
    DeviceProfile,
    DICOMBuilder,
    DICOMGeneratorError,
    DICOMValidationError,
    DirectoryCreateError,
    FileMetaBuilder,
    FileWriteError,
    GenerationConfig,
    GenerationError,
    InstanceConfig,
    PixelGenerator,
    PixelSpecCTRealistic,
    PixelSpecPhantom,
    ProfileMismatchError,
    ScheduledContext,
    UIDContext,
    UIDGenerator,
    WorklistMappingError,
    apply_device_profile,
    normalize_character_set,
)
from app.core.exceptions import DICOMValidationError
from app.core.generator import (
    DOSE_REPORT_CONVERSION_TYPE,
    MR_IMAGE_STORAGE,
    PT_IMAGE_STORAGE,
    RETIRED_TRANSFER_SYNTAXES,
    SECONDARY_CAPTURE_IMAGE_STORAGE,
)
from app.core.models import SeriesConfig, SpatialCoordinates
from app.core.phantom import (
    PHANTOM_MARKS,
    PhantomShape,
    projection_phantom_pixels,
    projection_region_pixels,
    series_phantom_pixels,
    study_phantom_shape,
    xray_phantom_values,
)
from app.core.projection import (
    DEFAULT_PHOTOMETRIC_INTERPRETATION,
    IMAGER_PIXEL_SPACING_MM,
    LATERAL_VIEWS,
    PHOTOMETRIC_INTERPRETATIONS,
    PROJECTION_BITS_STORED,
    PROJECTION_COLUMNS,
    PROJECTION_ROWS,
    PROJECTION_SOP_CLASSES,
    fixed_keywords_set_by,
    keep_projection_shape,
)
from pydantic import ValidationError as PydanticValidationError
from app.core.dose_sr import (
    XRAY_RADIATION_DOSE_SR_STORAGE,
    InstanceReference,
    dose_events_of,
    evidence_sequence,
)
from app.core.series_layout import (
    PET_MATRIX_SIZE,
    dose_events,
    dose_report_lines,
    series_spatial,
)
from app.core.path_safety import ensure_within, safe_path_component
from app.core.worklist_charset import ensure_dataset_encodable
from app.core.worklist_mapping import apply_scheduled_context, apply_sr_request

from .profile_loader import ProfileLoaderService
from .template_loader import TemplateLoaderService

logger = logging.getLogger(__name__)
DEFAULT_IMPLEMENTATION_VERSION_NAME = "DICOM_GEN_1.1"
# この道具（DTG）の実装を表す固定の UID。同じ実装は同じ Implementation Class UID
# を使う（PS3.7 D.3.3.2、PS3.10 7.1）。版の違いは Implementation Version Name で表す
IMPLEMENTATION_CLASS_UID = "2.25.209401092321175805341347975050777963523"
# Instance Creator UID (0008,0014) も、作った画像すべてで共通の固定の値にする（docs/spec/06）
INSTANCE_CREATOR_UID = "2.25.79995515066742824497440504634117232234"

GENERAL_EQUIPMENT_TAG_MAP = {
    "manufacturer": "Manufacturer",
    "institution_name": "InstitutionName",
    "station_name": "StationName",
    "manufacturers_model_name": "ManufacturerModelName",
    "software_versions": "SoftwareVersions",
}

CT_IMAGE_TAG_MAP = {
    "kvp": "KVP",
    "exposure_time": "ExposureTime",
    "x_ray_tube_current": "XRayTubeCurrent",
    "convolution_kernel": "ConvolutionKernel",
}

MR_IMAGE_TAG_MAP = {
    "magnetic_field_strength": "MagneticFieldStrength",
    "imaged_nucleus": "ImagedNucleus",
    "receive_coil_name": "ReceiveCoilName",
}

# この道具が画像を作れるモダリティ（シリーズの Modality。ADR-0030・ADR-0032・ADR-0034）
GENERATABLE_MODALITIES = ("CT", "MR", "PT", "CR", "DX")
# 一般撮影（投影の画像）のモダリティ。手で入れたシリーズは胸部の PA にする
PROJECTION_MODALITIES = ("CR", "DX")
MANUAL_PROJECTION_BODY_PART = "CHEST"
MANUAL_PROJECTION_VIEW = "PA"
# テンプレートと違うモダリティのシリーズに使う SOP Class
MODALITY_SOP_CLASSES = {
    "CT": CT_IMAGE_STORAGE,
    "MR": MR_IMAGE_STORAGE,
    "PT": PT_IMAGE_STORAGE,
    "SR": XRAY_RADIATION_DOSE_SR_STORAGE,
    **PROJECTION_SOP_CLASSES,
}

# PET の ct_realistic の画素の符号なし 16 ビットの上限を決める Bits（PS3.3 C.8.9.4）
PET_PIXEL_BITS = 16

# 線量の報告（SR）の Enhanced General Equipment が空のときの値
SR_EQUIPMENT_DEFAULTS = {
    "Manufacturer": "DTG Synthetic",
    "ManufacturerModelName": "DTG Synthetic",
    "DeviceSerialNumber": "DTG0001",
    "SoftwareVersions": "DTG",
}

# simple_text の画像の Bits Stored（CT Image は 12〜16。PS3.3 C.8.2.1.1.5）
SIMPLE_TEXT_BITS_STORED = 12

# 線量の画面（Secondary Capture）から外す、CT の画像だけの属性（装置のプロファイルが
# 足したものも外す。ADR-0025）
CT_ONLY_KEYWORDS = (
    "KVP",
    "ExposureTime",
    "XRayTubeCurrent",
    "ConvolutionKernel",
    "RescaleIntercept",
    "RescaleSlope",
    "WindowCenter",
    "WindowWidth",
    "SliceThickness",
    "SliceLocation",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "PixelSpacing",
    "FrameOfReferenceUID",
    "PositionReferenceIndicator",
    "PatientPosition",
    "AcquisitionNumber",
)


class StudyGeneratorService:
    """DICOMスタディ生成を担うService Layer."""

    # 装置のプロファイルで作れる SOP Class（docs/spec/13 の 4.3）
    PROFILE_CREATABLE_SOP_CLASSES = frozenset(
        {CT_IMAGE_STORAGE, MR_IMAGE_STORAGE, PT_IMAGE_STORAGE, *PROJECTION_SOP_CLASSES.values()}
    )

    def __init__(self, profile_loader: ProfileLoaderService | None = None) -> None:
        self._template_loader = TemplateLoaderService()
        self._profile_loader = profile_loader or ProfileLoaderService()
        self._dicom_builder = DICOMBuilder()
        self._pixel_generator = PixelGenerator()
        self._file_meta_builder = FileMetaBuilder()

    def generate(
        self,
        config: GenerationConfig,
        progress_callback: Callable[[int, int], None] | None = None,
        scheduled: ScheduledContext | None = None,
    ) -> Path:
        """設定に基づいてDICOMファイルを生成する.

        `scheduled` を渡すと、予約の値（docs/spec/12 の 6 章）を画像に写す。
        予約に Study Instance UID があればそれを使う。各画像は書き出す前に
        文字コードで表せるかを確かめ、表せなければ WorklistMappingError で止める。
        渡さなければいまと同じ動き。
        """
        total_images = sum(series.num_images for series in config.series_list)
        logger.info(
            "Generation started: job_name=%r patient_id=%r total_images=%s output_dir=%s",
            config.job_name,
            config.patient.patient_id,
            total_images,
            config.output_dir,
        )

        try:
            # custom_root は生成ごとの番号を根の後ろにつなぎ、前の生成の UID と
            # 重ならないようにする（PS3.5 9。docs/spec/06 の「カスタム Root 方式」）
            uid_generator = UIDGenerator(
                method=config.uid_method,
                custom_root=config.uid_custom_root or "",
                run_scoped=True,
            )
            study_uid = (
                scheduled.study_instance_uid
                if scheduled is not None and scheduled.study_instance_uid
                else uid_generator.generate_study_uid()
            )
            frame_of_reference_uid = uid_generator.generate_frame_of_reference_uid()

            uid_context = UIDContext(
                study_instance_uid=study_uid,
                frame_of_reference_uid=frame_of_reference_uid,
                implementation_class_uid=IMPLEMENTATION_CLASS_UID,
                instance_creator_uid=INSTANCE_CREATOR_UID,
            )

            template = self._template_loader.merge_templates(
                modality_name=config.modality_template,
                hospital_name=config.hospital_template,
            )
            site_overrides = self._hospital_overrides(config.hospital_template)
            profile = self._load_profile(config.device_profile)

            modality = self._resolve_modality(template)
            if modality not in GENERATABLE_MODALITIES:
                raise DICOMValidationError(
                    f"Modality {modality} cannot be generated "
                    f"(supported: {', '.join(GENERATABLE_MODALITIES)})",
                    {"modality": modality},
                )
            series_list = [
                self._resolve_series(series, modality) for series in config.series_list
            ]
            sop_class_uid, implementation_version_name = self._resolve_file_meta_settings(
                template
            )
            specific_character_set, use_ideographic, use_phonetic = (
                self._resolve_character_set_settings(config, template)
            )
            photometric = self._resolve_photometric_interpretation(template)
            apply_station_name = True
            if profile is not None:
                site_equipment = site_overrides.get("general_equipment")
                apply_station_name = not (
                    isinstance(site_equipment, dict)
                    and site_equipment.get("station_name")
                )
                if scheduled is not None and scheduled.station_name:
                    # 選んだ装置の Station Name を、装置のプロファイルより先にする（ADR-0023）
                    apply_station_name = False
                site_charset = site_overrides.get("character_set")
                site_sets_charset = isinstance(site_charset, dict) and (
                    "specific_character_set" in site_charset
                )
                if profile.character_set.default is not None and not site_sets_charset:
                    specific_character_set = profile.character_set.default
                sop_class_uid = self._check_profile(
                    profile, modality, config.transfer_syntax.uid, specific_character_set
                )
                if profile.device.implementation_version_name is not None:
                    implementation_version_name = (
                        profile.device.implementation_version_name
                    )
            self._reject_retired_transfer_syntax(config.transfer_syntax.uid)
            sequence_width = self._sequence_width(total_images)
            # 図形は撮影（この Frame of Reference）ごとに一度だけ決める（ADR-0033）
            shape = self._phantom_shape(config, series_list)
            top_z = shape.top_z if shape is not None else None

            output_dir = Path(config.output_dir)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DirectoryCreateError(str(output_dir), str(exc)) from exc

            abnormal_generator = AbnormalGenerator(level=config.abnormal.level)
            if config.abnormal.level != "none":
                logger.warning(
                    "Abnormal data injection is enabled: level=%s", config.abnormal.level
                )

            generated_count = 0
            file_sequence = 1
            # 線量の報告（SR）の撮影ごとの UID は、SR のシリーズが何枚あっても同じにする
            dose_sr_events = []
            if any(series.kind == "dose_sr" for series in series_list):
                dose_sr_events = dose_events_of(
                    series_list,
                    [uid_generator.generate_event_uid() for _ in dose_events(series_list)],
                )
            # SR が参照する同じ検査の画像（Current Requested Procedure Evidence）。SR は
            # 画像を全部作った後に作る（並びの途中に書いてあっても、最後のファイルにする）
            evidence: list[InstanceReference] = []
            for series_config in self._sr_last(series_list):
                series_uid = uid_generator.generate_series_uid()
                dose_report = series_config.kind == "dose_report"
                dose_sr = series_config.kind == "dose_sr"
                mr_series = series_config.modality == "MR"
                pt_series = series_config.modality == "PT"
                projection = series_config.modality in PROJECTION_MODALITIES
                for image_index in range(series_config.num_images):
                    sop_uid = uid_generator.generate_sop_uid(
                        allow_invalid=config.abnormal.allow_invalid_sop_uid
                    )
                    file_meta = self._file_meta_builder.build(
                        sop_class_uid=(
                            SECONDARY_CAPTURE_IMAGE_STORAGE
                            if dose_report
                            else sop_class_uid
                            if series_config.modality == modality
                            else MODALITY_SOP_CLASSES[series_config.modality]
                        ),
                        sop_instance_uid=sop_uid,
                        transfer_syntax_uid=config.transfer_syntax.uid,
                        implementation_class_uid=uid_context.implementation_class_uid,
                        implementation_version_name=implementation_version_name,
                    )
                    instance_config = InstanceConfig(instance_number=image_index + 1)
                    common = {
                        "patient": config.patient,
                        "study_config": config.study,
                        "series_config": series_config,
                        "instance_config": instance_config,
                        "uid_context": uid_context,
                        "file_meta": file_meta,
                        "sop_instance_uid": sop_uid,
                        "series_instance_uid": series_uid,
                        "specific_character_set": specific_character_set,
                        "use_ideographic": use_ideographic,
                        "use_phonetic": use_phonetic,
                    }
                    if dose_report:
                        dataset = self._dicom_builder.build_dose_report(
                            pixel_data=self._pixel_generator.generate_text_lines(
                                dose_report_lines(series_list, image_index)
                            ),
                            **common,
                        )
                    elif dose_sr:
                        dataset = self._dicom_builder.build_dose_sr(
                            events=dose_sr_events, **common
                        )
                    elif projection:
                        dataset = self._dicom_builder.build_projection_image(
                            pixel_data=self._generate_projection_pixels(
                                config, series_config, image_index, sop_uid
                            ),
                            photometric_interpretation=photometric,
                            **common,
                        )
                    else:
                        spatial = series_spatial(series_config, image_index, top_z)
                        if pt_series:
                            dataset = self._dicom_builder.build_pt_image(
                                spatial=spatial,
                                pixel_data=self._generate_pet_pixels(config, sop_uid),
                                **common,
                            )
                        else:
                            pixel_data, bits_stored = (
                                self._generate_phantom_pixels(
                                    config, shape, series_config, spatial, image_index
                                )
                                if shape is not None
                                else self._generate_pixel_data(config, sop_uid)
                            )
                            build = (
                                self._dicom_builder.build_mr_image
                                if mr_series
                                else self._dicom_builder.build_ct_image
                            )
                            dataset = build(
                                spatial=spatial,
                                pixel_data=pixel_data,
                                bits_stored=bits_stored,
                                **common,
                            )
                    self._apply_template_attributes(
                        dataset,
                        template,
                        # テンプレートのモダリティが PET/CT の PT でも、CT のシリーズには
                        # テンプレートの CT の撮影の値を当てる
                        ct_image=series_config.modality == "CT" and not dose_report,
                        mr_image=mr_series,
                    )
                    if scheduled is not None:
                        apply_scheduled_context(dataset, scheduled)
                    # 装置のプロファイルの attributes とプライベートタグは最後に当てる
                    # （docs/spec/13 の 4.2）
                    if profile is not None:
                        apply_device_profile(
                            dataset, profile, apply_station_name=apply_station_name
                        )
                    if shape is not None and not (dose_report or dose_sr or pt_series):
                        # 図形で画素を作った画像だけに、偽物の印を書く
                        for keyword, value in PHANTOM_MARKS.items():
                            setattr(dataset, keyword, value)
                    if dose_report:
                        self._keep_secondary_capture_shape(dataset)
                    elif projection:
                        keep_projection_shape(dataset, series_config, image_index, photometric)
                    elif dose_sr:
                        self._keep_sr_shape(dataset)
                        if scheduled is not None:
                            apply_sr_request(dataset, scheduled)
                        if evidence:
                            dataset.CurrentRequestedProcedureEvidenceSequence = (
                                evidence_sequence(evidence)
                            )
                    # 異常のデータは最後に当てる（予約・プロファイルの値にも効く。
                    # docs/spec/02 の AbnormalGenerator）。none では何も変えない
                    apply_abnormal_to_dataset(dataset, abnormal_generator)
                    # 表せない字は黙って `?` にせず止める（PS3.3 C.12.1・PS3.5 6.1）
                    self._ensure_encodable(dataset, scheduled is not None)

                    # Patient ID・検査日・モダリティは信用できない値（予約・Job）なので、
                    # 決まった字だけにしてから名前に使う（docs/spec/12 の 6.5）。モダリティは
                    # テンプレートの値で、検査の中で同じにする（シリーズのモダリティで
                    # 変えると、名前の順が書いた順と変わる）
                    filename = (
                        f"{safe_path_component(config.patient.patient_id, 'UNKNOWN')}_"
                        f"{safe_path_component(config.study.study_date, 'NODATE')}_"
                        f"{safe_path_component(modality, 'OT')}_"
                        f"{file_sequence:0{sequence_width}d}.dcm"
                    )
                    filepath = ensure_within(output_dir, output_dir / filename)
                    try:
                        pydicom.dcmwrite(
                            str(filepath), dataset, enforce_file_format=True
                        )
                    except Exception as exc:
                        raise FileWriteError(str(filepath), str(exc)) from exc

                    if not dose_sr:
                        # 作った UID で参照する（異常のデータが画像の属性を消していても）
                        evidence.append(
                            InstanceReference(
                                study_instance_uid=uid_context.study_instance_uid,
                                series_instance_uid=series_uid,
                                sop_class_uid=str(file_meta.MediaStorageSOPClassUID),
                                sop_instance_uid=sop_uid,
                            )
                        )
                    generated_count += 1
                    file_sequence += 1
                    if progress_callback is not None:
                        progress_callback(generated_count, total_images)

            logger.info(
                "Generation completed: patient_id=%r generated=%s output_dir=%s",
                config.patient.patient_id,
                generated_count,
                output_dir,
            )
            return output_dir
        except DICOMGeneratorError:
            logger.error(
                "Generation failed: patient_id=%r output_dir=%s",
                config.patient.patient_id,
                config.output_dir,
                exc_info=True,
            )
            raise
        except Exception as exc:
            logger.error(
                "Generation failed unexpectedly: patient_id=%r output_dir=%s",
                config.patient.patient_id,
                config.output_dir,
                exc_info=True,
            )
            raise GenerationError(f"Unexpected generation error: {exc}") from exc

    @staticmethod
    def _keep_secondary_capture_shape(dataset: Dataset) -> None:
        """線量の画面に装置のプロファイルを重ねた後、Secondary Capture の形に戻す.

        CT の画像だけの属性は外し、SC の必須の属性（Conversion Type は Type 1、Patient
        Orientation は Type 2C。PS3.3 C.8.6.1・C.7.6.1）は、プロファイルが外しても戻す。
        異常のデータはこの後に当てる。
        """
        for keyword in CT_ONLY_KEYWORDS:
            if keyword in dataset:
                delattr(dataset, keyword)
        if not dataset.get("ConversionType"):
            dataset.ConversionType = DOSE_REPORT_CONVERSION_TYPE
        if "PatientOrientation" not in dataset:
            dataset.PatientOrientation = ""

    @staticmethod
    def _sr_last(series_list: list[SeriesConfig]) -> list[SeriesConfig]:
        """線量の報告（SR）のシリーズを最後に回す。ほかの並びは変えない."""
        return [s for s in series_list if s.kind != "dose_sr"] + [
            s for s in series_list if s.kind == "dose_sr"
        ]

    @staticmethod
    def _keep_sr_shape(dataset: Dataset) -> None:
        """線量の報告（SR）に装置のプロファイルを重ねた後、画像の属性を外す.

        SR Document は画素も Frame of Reference も持たない（PS3.3 A.35.8）。装置の
        プロファイルが足した画像の属性も外す。異常のデータはこの後に当てる。
        """
        for keyword in (*CT_ONLY_KEYWORDS, "PatientOrientation", "ConversionType"):
            if keyword in dataset:
                delattr(dataset, keyword)
        # Enhanced General Equipment（PS3.3 C.7.5.2）は 4 つとも Type 1。テンプレートや
        # 病院テンプレートが空にしても、空では出さない
        for keyword, default in SR_EQUIPMENT_DEFAULTS.items():
            if not dataset.get(keyword):
                setattr(dataset, keyword, default)

    @staticmethod
    def _reject_retired_transfer_syntax(transfer_syntax_uid: str) -> None:
        """廃止の転送の形を、出力のフォルダを作る前に断る（PS3.5 A.3）.

        Explicit VR Big Endian は異常のデータの約束（docs/spec/02）にも無いので、
        異常のデータのレベルに関わらず作らない（docs/spec/06 の「通常の経路と
        異常のデータの経路」）。
        """
        name = RETIRED_TRANSFER_SYNTAXES.get(transfer_syntax_uid)
        if name is not None:
            raise DICOMValidationError(
                f"{name} ({transfer_syntax_uid}) is retired and is not generated "
                "(PS3.5 A.3). Use Implicit VR Little Endian (1.2.840.10008.1.2) or "
                "Explicit VR Little Endian (1.2.840.10008.1.2.1)",
                {"transfer_syntax": transfer_syntax_uid},
            )

    def _hospital_overrides(self, hospital_name: str | None) -> dict:
        if hospital_name is None:
            return {}
        overrides = self._template_loader.load_hospital_template(hospital_name).get(
            "overrides", {}
        )
        return overrides if isinstance(overrides, dict) else {}

    def _load_profile(self, name: str | None) -> DeviceProfile | None:
        if name is None:
            return None
        profile = self._profile_loader.load(name)
        logger.info("Device profile: %s", profile.name)
        return profile

    def _check_profile(
        self,
        profile: DeviceProfile,
        template_modality: str,
        transfer_syntax_uid: str,
        specific_character_set: str | None,
    ) -> str:
        """プロファイルとテンプレート・Job が合うかを確かめる（docs/spec/13 の 4.3）.

        合えば、作る SOP Class UID を返す。
        """
        details = {"profile": profile.name}
        if profile.device.modality != template_modality:
            raise ProfileMismatchError(
                f"Device profile modality {profile.device.modality} does not match "
                f"template modality {template_modality}",
                details,
            )
        if transfer_syntax_uid not in profile.storage.transfer_syntaxes:
            raise ProfileMismatchError(
                f"Transfer Syntax {transfer_syntax_uid} is not supported by the device "
                f"(supported: {', '.join(profile.storage.transfer_syntaxes)})",
                details,
            )
        if not profile.character_set.allows(specific_character_set):
            shown = "\\".join(normalize_character_set(specific_character_set))
            raise ProfileMismatchError(
                f"Specific Character Set {shown} is not supported by the device "
                f"(supported: {'; '.join(profile.character_set.supported)})",
                details,
            )
        fixed = fixed_keywords_set_by(template_modality, profile.attributes.set_values)
        if fixed:
            # CR・DX の規格が決める値とルーチンの部位・左右は変えられない（docs/spec/06 の 5.5）
            raise ProfileMismatchError(
                f"attributes.set cannot change {', '.join(fixed)} for {template_modality} "
                "images (fixed by PS3.3 C.8.1・C.8.11 or the routine)",
                details,
            )
        sop_class_uid = profile.storage.sop_classes[0]
        if sop_class_uid not in self.PROFILE_CREATABLE_SOP_CLASSES:
            raise ProfileMismatchError(
                f"SOP Class {sop_class_uid} cannot be generated yet "
                f"(supported: {', '.join(sorted(self.PROFILE_CREATABLE_SOP_CLASSES))})",
                details,
            )
        return sop_class_uid

    def _resolve_modality(self, template: dict) -> str:
        info = template.get("info", {})
        if isinstance(info, dict) and isinstance(info.get("modality"), str):
            return info["modality"]
        return "CT"

    def _resolve_file_meta_settings(self, template: dict) -> tuple[str, str]:
        file_meta_config = template.get("file_meta", {})
        if not isinstance(file_meta_config, dict):
            return CT_IMAGE_STORAGE, DEFAULT_IMPLEMENTATION_VERSION_NAME

        sop_class_uid = str(
            file_meta_config.get("media_storage_sop_class_uid", CT_IMAGE_STORAGE)
        )
        implementation_version_name = str(
            file_meta_config.get(
                "implementation_version_name", DEFAULT_IMPLEMENTATION_VERSION_NAME
            )
        )
        return sop_class_uid, implementation_version_name

    def _resolve_character_set_settings(
        self, config: GenerationConfig, template: dict
    ) -> tuple[str | None, bool, bool]:
        specific_character_set: str | None = config.character_set.specific_character_set
        use_ideographic = config.character_set.use_ideographic
        use_phonetic = config.character_set.use_phonetic

        character_set_config = template.get("character_set", {})
        if isinstance(character_set_config, dict):
            if "specific_character_set" in character_set_config:
                value = character_set_config["specific_character_set"]
                specific_character_set = None if value is None else str(value)

        patient_module = template.get("patient_module", {})
        if isinstance(patient_module, dict):
            patient_name_cfg = patient_module.get("patient_name", {})
            if isinstance(patient_name_cfg, dict):
                if "use_ideographic" in patient_name_cfg:
                    use_ideographic = bool(patient_name_cfg["use_ideographic"])
                if "use_phonetic" in patient_name_cfg:
                    use_phonetic = bool(patient_name_cfg["use_phonetic"])

        return specific_character_set, use_ideographic, use_phonetic

    def _generate_pixel_data(
        self, config: GenerationConfig, sop_uid: str
    ) -> tuple[np.ndarray, int]:
        if isinstance(config.pixel_spec, PixelSpecCTRealistic):
            pixels = self._pixel_generator.generate_ct_realistic(
                width=config.pixel_spec.width,
                height=config.pixel_spec.height,
                pattern=config.pixel_spec.pattern,
                bits_stored=config.pixel_spec.bits_stored,
            )
            return pixels, config.pixel_spec.bits_stored

        pixels = self._pixel_generator.generate_simple_text(
            sop_instance_uid=sop_uid,
            width=config.pixel_spec.width,
            height=config.pixel_spec.height,
        )
        # 文字の画像も CT の 16 ビットで書く（PS3.3 C.8.2.1.1.5。DICOMBuilder が広げる）
        return pixels, SIMPLE_TEXT_BITS_STORED

    @staticmethod
    def _resolve_photometric_interpretation(template: dict) -> str:
        """CR・DX の Photometric Interpretation（テンプレートの `xray_image`。ADR-0034）."""
        section = template.get("xray_image", {})
        value = (
            section.get("photometric_interpretation", DEFAULT_PHOTOMETRIC_INTERPRETATION)
            if isinstance(section, dict)
            else DEFAULT_PHOTOMETRIC_INTERPRETATION
        )
        if value not in PHOTOMETRIC_INTERPRETATIONS:
            raise DICOMValidationError(
                f"xray_image.photometric_interpretation {value!r} is not allowed "
                f"(allowed: {', '.join(PHOTOMETRIC_INTERPRETATIONS)})",
                {"photometric_interpretation": str(value)},
            )
        return str(value)

    def _generate_projection_pixels(
        self,
        config: GenerationConfig,
        series_config: SeriesConfig,
        image_index: int,
        sop_uid: str,
    ) -> np.ndarray:
        """CR・DX の画素（MONOCHROME2 の値）。大きさは固定で、Job の幅と高さには従わない.

        `phantom` は部位の図形（ルーチンの `phantom`）か、無ければ体の楕円と位置の目印、
        `ct_realistic` は 0〜上限（4095）の模様、`simple_text` は文字（DICOMBuilder が
        0〜上限に広げる）。
        """
        if isinstance(config.pixel_spec, PixelSpecPhantom) and series_config.phantom:
            views = series_config.view_positions
            return projection_region_pixels(
                PROJECTION_ROWS,
                PROJECTION_COLUMNS,
                image_index,
                series_config.num_images,
                region=series_config.phantom,
                lateral=views[image_index % len(views)] in LATERAL_VIEWS,
                bits_stored=PROJECTION_BITS_STORED,
                pixel_spacing_mm=IMAGER_PIXEL_SPACING_MM,
            )
        if isinstance(config.pixel_spec, PixelSpecPhantom):
            return projection_phantom_pixels(
                PROJECTION_ROWS,
                PROJECTION_COLUMNS,
                image_index,
                series_config.num_images,
                xray_phantom_values(PROJECTION_BITS_STORED),
            )
        if isinstance(config.pixel_spec, PixelSpecCTRealistic):
            # 符号ありの Bits Stored 13 の上限は、符号なしの 12 の上限（4095）と同じ
            return self._pixel_generator.generate_ct_realistic(
                width=PROJECTION_COLUMNS,
                height=PROJECTION_ROWS,
                pattern=config.pixel_spec.pattern,
                bits_stored=PROJECTION_BITS_STORED + 1,
            )
        return self._pixel_generator.generate_simple_text(
            sop_instance_uid=sop_uid, width=PROJECTION_COLUMNS, height=PROJECTION_ROWS
        )

    @staticmethod
    def _phantom_shape(
        config: GenerationConfig, series_list: list[SeriesConfig]
    ) -> PhantomShape | None:
        """図形の方式のときだけ、軸位の視野と範囲から図形を決める."""
        if not isinstance(config.pixel_spec, PixelSpecPhantom):
            return None
        return study_phantom_shape(
            series_list, rows=config.pixel_spec.height, cols=config.pixel_spec.width
        )

    @staticmethod
    def _generate_phantom_pixels(
        config: GenerationConfig,
        shape: PhantomShape,
        series_config: SeriesConfig,
        spatial: SpatialCoordinates,
        image_index: int,
    ) -> tuple[np.ndarray, int]:
        bits_stored = config.pixel_spec.bits_stored
        pixels = series_phantom_pixels(
            shape,
            series_config,
            spatial,
            image_index,
            rows=config.pixel_spec.height,
            cols=config.pixel_spec.width,
            bits_stored=bits_stored,
        )
        return pixels, bits_stored

    def _generate_pet_pixels(self, config: GenerationConfig, sop_uid: str) -> np.ndarray:
        """PET の画素。行列は PET の大きさ（128）で、ジョブの画素の大きさには従わない.

        図形の方式（phantom）でも PT のシリーズは図形にせず、既定の `gradient` にする
        （ADR-0033 の「決めないこと」）。
        """
        if isinstance(config.pixel_spec, (PixelSpecCTRealistic, PixelSpecPhantom)):
            pattern = (
                config.pixel_spec.pattern
                if isinstance(config.pixel_spec, PixelSpecCTRealistic)
                else "gradient"
            )
            return self._pixel_generator.generate_ct_realistic(
                width=PET_MATRIX_SIZE,
                height=PET_MATRIX_SIZE,
                pattern=pattern,
                bits_stored=PET_PIXEL_BITS,
            )
        return self._pixel_generator.generate_simple_text(
            sop_instance_uid=sop_uid, width=PET_MATRIX_SIZE, height=PET_MATRIX_SIZE
        )

    @staticmethod
    def _ensure_encodable(dataset: Dataset, scheduled: bool) -> None:
        """文字の属性が Specific Character Set で表せるかを確かめる.

        予約の撮影は WorklistMappingError（docs/spec/12 の 7.2）、Job の生成は
        DICOMValidationError で止める（どちらも CLI の終了コード 4。docs/spec/04）。
        Job の値（紹介医名・検査の説明など）も、宣言の無い字のまま書けば
        受け手で `?` や別の字に化ける。
        """
        try:
            ensure_dataset_encodable(dataset)
        except WorklistMappingError as exc:
            # 表せない字そのもの（氏名の一部など）は、どちらの経路も文・details・
            # ログに出さない。元の例外は字を含むので、つながりを切る
            # （ログの exc_info に出るため）
            attribute = str(exc.details.get("attribute", ""))
            character_set = str(exc.details.get("character_set", ""))
            if scheduled:
                raise WorklistMappingError(
                    f"{attribute} に {character_set} で表せない字があります",
                    {"attribute": attribute, "character_set": character_set},
                ) from None
            raise DICOMValidationError(
                f"{attribute} に {character_set} で表せない字があります。"
                "Job の character_set か病院テンプレートの文字コードを見直してください",
                {"attribute": attribute, "character_set": character_set},
            ) from None

    @staticmethod
    def _sequence_width(total_images: int) -> int:
        return max(4, len(str(total_images)))

    @staticmethod
    def _resolve_series(series: SeriesConfig, template_modality: str) -> SeriesConfig:
        """モダリティを決めていないシリーズに、テンプレートのモダリティを入れる（ADR-0030）.

        MR のテンプレートで手で入れたシリーズ（種類の既定は axial）は、MR の撮像にする。
        """
        if series.modality is not None:
            return series
        if series.kind == "dose_sr":
            return series.model_copy(update={"modality": "SR"})
        update: dict[str, object] = {"modality": template_modality}
        if template_modality == "MR" and series.kind == "axial":
            update["kind"] = "acquisition"
        elif template_modality == "PT" and series.kind == "axial":
            # PET/CT のテンプレートで手で入れたシリーズは、減弱補正ありの PET にする
            update["kind"] = "pet_ac"
        elif template_modality == "PT" and series.kind in ("localizer", "dose_report"):
            # 位置決めと線量の画面は CT の画像
            update["modality"] = "CT"
        elif template_modality in PROJECTION_MODALITIES and series.kind == "axial":
            # CR・DX のテンプレートで手で入れたシリーズは、胸部の PA の投影の画像（ADR-0034）
            update["kind"] = "projection"
            update["view_positions"] = [MANUAL_PROJECTION_VIEW]
        if update.get("kind", series.kind) == "projection" and series.body_part is None:
            update["body_part"] = MANUAL_PROJECTION_BODY_PART
        try:
            # 組み合わせの検証（MR に冠状断など）をやり直す
            return SeriesConfig.model_validate({**series.model_dump(), **update})
        except PydanticValidationError as exc:
            raise DICOMValidationError(
                f"Series {series.series_number} (kind {series.kind}) cannot be made with "
                f"the {template_modality} template: {exc.errors()[0]['msg']}",
                {"series_number": series.series_number, "modality": template_modality},
            ) from exc

    def _apply_template_attributes(
        self,
        dataset: Dataset,
        template: dict,
        ct_image: bool = True,
        mr_image: bool = False,
    ) -> None:
        """テンプレートの装置の値と、`ct_image`・`mr_image` なら撮影の値を当てる."""
        general_equipment = template.get("general_equipment", {})
        if isinstance(general_equipment, dict):
            self._apply_attributes(dataset, general_equipment, GENERAL_EQUIPMENT_TAG_MAP)

        ct_values = template.get("ct_image", {})
        if ct_image and isinstance(ct_values, dict):
            self._apply_attributes(dataset, ct_values, CT_IMAGE_TAG_MAP)
        mr_values = template.get("mr_image", {})
        if mr_image and isinstance(mr_values, dict):
            self._apply_attributes(dataset, mr_values, MR_IMAGE_TAG_MAP)

    def _apply_attributes(
        self, dataset: Dataset, source: dict, keyword_map: dict[str, str]
    ) -> None:
        for source_key, dicom_keyword in keyword_map.items():
            value = source.get(source_key)
            if value is None:
                continue
            setattr(dataset, dicom_keyword, str(value))
