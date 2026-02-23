"""Storage SCP configuration models and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import SCPConfigError

CT_IMAGE_STORAGE_UID = "1.2.840.10008.5.1.4.1.1.2"


class SCPConfig(BaseModel):
    """Storage SCP settings."""

    model_config = {"frozen": True}

    enabled: bool = False
    ae_title: str = Field("DICOM_GEN_SCP", max_length=16)
    port: int = Field(11112, ge=1024, le=65535)
    bind_address: str = "0.0.0.0"
    storage_dir: str = "scp_storage"
    duplicate_handling: Literal["overwrite", "reject", "rename"] = "overwrite"
    supported_sop_classes: list[str] = Field(
        default_factory=lambda: [CT_IMAGE_STORAGE_UID],
        min_length=1,
    )


def load_scp_config(config_path: Path) -> SCPConfig:
    """Load `storage_scp` section from YAML config file."""
    if not config_path.exists():
        raise SCPConfigError(
            f"Configuration file not found: {config_path}",
            {"config_path": str(config_path)},
        )

    try:
        with config_path.open("r", encoding="utf-8") as fp:
            loaded = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        raise SCPConfigError(
            f"Invalid YAML format: {config_path}",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc
    except OSError as exc:
        raise SCPConfigError(
            f"Failed to read configuration file: {config_path}",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc

    if not isinstance(loaded, dict):
        raise SCPConfigError(
            "Configuration root must be a mapping",
            {"config_path": str(config_path)},
        )

    if "storage_scp" not in loaded:
        raise SCPConfigError(
            "Missing 'storage_scp' section in configuration",
            {"config_path": str(config_path)},
        )

    storage_scp_raw = loaded["storage_scp"]
    if not isinstance(storage_scp_raw, dict):
        raise SCPConfigError(
            "'storage_scp' section must be a mapping",
            {"config_path": str(config_path)},
        )

    try:
        return SCPConfig.model_validate(storage_scp_raw)
    except ValidationError as exc:
        raise SCPConfigError(
            "Invalid storage_scp configuration",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc

