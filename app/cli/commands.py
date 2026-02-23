"""CLI subcommand handlers."""

from __future__ import annotations

import argparse
import platform
from datetime import datetime
from pathlib import Path
from typing import Any

import pydicom
import yaml

from app.cli.progress import create_progress_callback
from app.core import (
    AbnormalConfig,
    CharacterSetConfig,
    ConfigurationError,
    FileReadError,
    GenerationConfig,
    PixelSpecCTRealistic,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.services import PatientLoaderService, StudyGeneratorService, TemplateLoaderService

TOOL_NAME = "DICOMテストデータ生成ツール"
VERSION = "1.1.0"


def generate_command(args: argparse.Namespace) -> int:
    """Job YAMLからDICOM生成を実行する."""
    job_data = _load_job_yaml(args.job_file)
    if args.output:
        job_data["output_dir"] = args.output

    config = GenerationConfig.model_validate(job_data)

    if args.dry_run:
        print("Dry-run mode: configuration is valid.")
        print(f"Patient ID: {config.patient.patient_id}")
        print(f"Accession Number: {config.study.accession_number}")
        print(f"Series: {len(config.series_list)}")
        print(f"Total Images: {_total_images(config.series_list)}")
        return 0

    progress_callback = create_progress_callback(bool(getattr(args, "quiet", False)))
    output_path = StudyGeneratorService().generate(
        config=config,
        progress_callback=progress_callback,
    )
    print(f"Generation completed: {output_path}")
    return 0


def validate_command(args: argparse.Namespace) -> int:
    """Job YAMLのバリデーションのみを実行する."""
    job_data = _load_job_yaml(args.job_file)
    config = GenerationConfig.model_validate(job_data)

    print("Job configuration is valid")
    print(f"Patient ID: {config.patient.patient_id}")
    print(f"Accession Number: {config.study.accession_number}")
    print(f"Series: {len(config.series_list)}")
    print(f"Total Images: {_total_images(config.series_list)}")
    return 0


def quick_command(args: argparse.Namespace) -> int:
    """CLI引数のみで簡易生成を実行する."""
    patient = PatientLoaderService().find_by_id(args.patient)
    TemplateLoaderService().merge_templates(
        modality_name=args.modality,
        hospital_name=args.hospital,
    )

    images_per_series = _parse_images(args.images)
    if args.series != len(images_per_series):
        raise ConfigurationError(
            "Series count and image list length do not match",
            {"series": args.series, "images_count": len(images_per_series)},
        )

    study = StudyConfig(
        accession_number=args.accession_number,
        study_date=args.study_date,
        study_time=datetime.now().strftime("%H%M%S"),
        study_description=None,
        referring_physician_name=None,
        num_series=args.series,
    )

    series_list = [
        SeriesConfig(
            series_number=index + 1,
            series_description=None,
            num_images=image_count,
            protocol_name=None,
        )
        for index, image_count in enumerate(images_per_series)
    ]

    if args.pixel_mode == "simple_text":
        pixel_spec = PixelSpecSimple()
    elif args.pixel_mode == "ct_realistic":
        pixel_spec = PixelSpecCTRealistic()
    else:
        raise ConfigurationError(
            "Unsupported pixel mode",
            {"pixel_mode": args.pixel_mode},
        )

    config = GenerationConfig(
        job_name=f"quick_{args.accession_number}",
        output_dir=args.output,
        patient=patient,
        study=study,
        series_list=series_list,
        modality_template=args.modality,
        hospital_template=args.hospital,
        uid_method="uuid_2_25",
        uid_custom_root=None,
        pixel_spec=pixel_spec,
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
        abnormal=AbnormalConfig(),
    )

    output_path = StudyGeneratorService().generate(config=config, progress_callback=None)
    print(f"Generation completed: {output_path}")
    return 0


def version_command(args: argparse.Namespace) -> int:
    """バージョン情報を表示する."""
    _ = args
    print(TOOL_NAME)
    print(f"Version: {VERSION}")
    print(f"Python: {platform.python_version()}")
    print(f"PyDicom: {pydicom.__version__}")
    return 0


def _load_job_yaml(job_file: str) -> dict[str, Any]:
    path = Path(job_file)
    if not path.exists():
        raise FileReadError(str(path), "File does not exist")

    try:
        with path.open("r", encoding="utf-8") as fp:
            loaded = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            f"Failed to parse job YAML: {path}",
            {"error": str(exc)},
        ) from exc
    except OSError as exc:
        raise FileReadError(str(path), str(exc)) from exc

    if not isinstance(loaded, dict):
        raise ConfigurationError("Job YAML root must be a mapping", {"path": str(path)})
    return loaded


def _parse_images(images: str) -> list[int]:
    try:
        values = [int(item.strip()) for item in images.split(",")]
    except ValueError as exc:
        raise ConfigurationError(
            "Images must be comma-separated integers",
            {"images": images},
        ) from exc

    if not values:
        raise ConfigurationError("Images list must not be empty")
    if any(value <= 0 for value in values):
        raise ConfigurationError(
            "Each image count must be greater than 0",
            {"images": images},
        )
    return values


def _total_images(series_list: list[SeriesConfig]) -> int:
    return sum(series.num_images for series in series_list)




