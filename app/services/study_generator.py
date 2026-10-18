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
    DeviceProfile,
    DICOMBuilder,
    DICOMGeneratorError,
    DirectoryCreateError,
    FileMetaBuilder,
    FileWriteError,
    GenerationConfig,
    GenerationError,
    InstanceConfig,
    PixelGenerator,
    PixelSpecCTRealistic,
    ProfileMismatchError,
    ScheduledContext,
    SpatialCalculator,
    UIDContext,
    UIDGenerator,
    apply_device_profile,
    normalize_character_set,
)
from app.core.path_safety import ensure_within, safe_path_component
from app.core.worklist_charset import ensure_dataset_encodable
from app.core.worklist_mapping import apply_scheduled_context

from .profile_loader import ProfileLoaderService
from .template_loader import TemplateLoaderService

logger = logging.getLogger(__name__)
DEFAULT_IMPLEMENTATION_VERSION_NAME = "DICOM_GEN_1.1"

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


class StudyGeneratorService:
    """DICOMスタディ生成を担うService Layer."""

    # 装置のプロファイルで作れる SOP Class（spec/13 の 4.3。P1 は CT だけ）
    PROFILE_CREATABLE_SOP_CLASSES = frozenset({CT_IMAGE_STORAGE})

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

        `scheduled` を渡すと、予約の値（spec/12 の 6 章）を画像に写す。
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
            uid_generator = UIDGenerator(
                method=config.uid_method,
                custom_root=config.uid_custom_root or "",
            )
            study_uid = (
                scheduled.study_instance_uid
                if scheduled is not None and scheduled.study_instance_uid
                else uid_generator.generate_study_uid()
            )
            frame_of_reference_uid = uid_generator.generate_frame_of_reference_uid()
            implementation_class_uid = uid_generator.generate_instance_creator_uid()
            instance_creator_uid = uid_generator.generate_instance_creator_uid()

            uid_context = UIDContext(
                study_instance_uid=study_uid,
                frame_of_reference_uid=frame_of_reference_uid,
                implementation_class_uid=implementation_class_uid,
                instance_creator_uid=instance_creator_uid,
            )

            template = self._template_loader.merge_templates(
                modality_name=config.modality_template,
                hospital_name=config.hospital_template,
            )
            site_overrides = self._hospital_overrides(config.hospital_template)
            profile = self._load_profile(config.device_profile)

            modality = self._resolve_modality(template)
            sop_class_uid, implementation_version_name = self._resolve_file_meta_settings(
                template
            )
            specific_character_set, use_ideographic, use_phonetic = (
                self._resolve_character_set_settings(config, template)
            )
            apply_station_name = True
            if profile is not None:
                site_equipment = site_overrides.get("general_equipment")
                apply_station_name = not (
                    isinstance(site_equipment, dict)
                    and site_equipment.get("station_name")
                )
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
            sequence_width = self._sequence_width(total_images)

            output_dir = Path(config.output_dir)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DirectoryCreateError(str(output_dir), str(exc)) from exc

            generated_count = 0
            file_sequence = 1
            for series_config in config.series_list:
                series_uid = uid_generator.generate_series_uid()
                spatial_calculator = SpatialCalculator(
                    slice_thickness=series_config.slice_thickness,
                    slice_spacing=series_config.slice_spacing,
                    start_z=series_config.start_z,
                )

                for image_index in range(series_config.num_images):
                    sop_uid = uid_generator.generate_sop_uid(
                        allow_invalid=config.abnormal.allow_invalid_sop_uid
                    )
                    pixel_data, bits_stored = self._generate_pixel_data(config, sop_uid)

                    file_meta = self._file_meta_builder.build(
                        sop_class_uid=sop_class_uid,
                        sop_instance_uid=sop_uid,
                        transfer_syntax_uid=config.transfer_syntax.uid,
                        implementation_class_uid=uid_context.implementation_class_uid,
                        implementation_version_name=implementation_version_name,
                    )

                    instance_config = InstanceConfig(instance_number=image_index + 1)
                    spatial = spatial_calculator.calculate(image_index)

                    dataset = self._dicom_builder.build_ct_image(
                        patient=config.patient,
                        study_config=config.study,
                        series_config=series_config,
                        instance_config=instance_config,
                        uid_context=uid_context,
                        spatial=spatial,
                        pixel_data=pixel_data,
                        file_meta=file_meta,
                        sop_instance_uid=sop_uid,
                        series_instance_uid=series_uid,
                        specific_character_set=specific_character_set,
                        use_ideographic=use_ideographic,
                        use_phonetic=use_phonetic,
                        bits_stored=bits_stored,
                    )
                    self._apply_template_attributes(dataset, template)
                    if scheduled is not None:
                        apply_scheduled_context(dataset, scheduled)
                    # 装置のプロファイルの attributes とプライベートタグは最後に当てる
                    # （spec/13 の 4.2）
                    if profile is not None:
                        apply_device_profile(
                            dataset, profile, apply_station_name=apply_station_name
                        )
                    if scheduled is not None:
                        ensure_dataset_encodable(dataset)

                    # Patient ID・検査日・モダリティは信用できない値（予約・Job）なので、
                    # 決まった字だけにしてから名前に使う（spec/12 の 6.5）
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
        """プロファイルとテンプレート・Job が合うかを確かめる（spec/13 の 4.3）.

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
        return pixels, 8

    @staticmethod
    def _sequence_width(total_images: int) -> int:
        return max(4, len(str(total_images)))

    def _apply_template_attributes(self, dataset: Dataset, template: dict) -> None:
        general_equipment = template.get("general_equipment", {})
        if isinstance(general_equipment, dict):
            self._apply_attributes(dataset, general_equipment, GENERAL_EQUIPMENT_TAG_MAP)

        ct_image = template.get("ct_image", {})
        if isinstance(ct_image, dict):
            self._apply_attributes(dataset, ct_image, CT_IMAGE_TAG_MAP)

    def _apply_attributes(
        self, dataset: Dataset, source: dict, keyword_map: dict[str, str]
    ) -> None:
        for source_key, dicom_keyword in keyword_map.items():
            value = source.get(source_key)
            if value is None:
                continue
            setattr(dataset, dicom_keyword, str(value))
