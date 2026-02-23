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
    SpatialCalculator,
    UIDContext,
    UIDGenerator,
)

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

    def __init__(self) -> None:
        self._template_loader = TemplateLoaderService()
        self._dicom_builder = DICOMBuilder()
        self._pixel_generator = PixelGenerator()
        self._file_meta_builder = FileMetaBuilder()

    def generate(
        self,
        config: GenerationConfig,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> Path:
        """設定に基づいてDICOMファイルを生成する."""
        total_images = sum(series.num_images for series in config.series_list)
        logger.info(
            "Generation started: job_name=%s patient_id=%s total_images=%s output_dir=%s",
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
            study_uid = uid_generator.generate_study_uid()
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

            output_dir = Path(config.output_dir)
            try:
                output_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise DirectoryCreateError(str(output_dir), str(exc)) from exc

            modality = self._resolve_modality(template)
            sop_class_uid, implementation_version_name = self._resolve_file_meta_settings(
                template
            )
            specific_character_set, use_ideographic, use_phonetic = (
                self._resolve_character_set_settings(config, template)
            )

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

                    filename = (
                        f"{config.patient.patient_id}_{config.study.study_date}_"
                        f"{modality}_{file_sequence:03d}.dcm"
                    )
                    filepath = output_dir / filename
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
                "Generation completed: patient_id=%s generated=%s output_dir=%s",
                config.patient.patient_id,
                generated_count,
                output_dir,
            )
            return output_dir
        except DICOMGeneratorError:
            logger.error(
                "Generation failed: patient_id=%s output_dir=%s",
                config.patient.patient_id,
                config.output_dir,
                exc_info=True,
            )
            raise
        except Exception as exc:
            logger.error(
                "Generation failed unexpectedly: patient_id=%s output_dir=%s",
                config.patient.patient_id,
                config.output_dir,
                exc_info=True,
            )
            raise GenerationError(f"Unexpected generation error: {exc}") from exc

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
