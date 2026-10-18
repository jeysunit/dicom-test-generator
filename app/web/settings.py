"""画面の設定（config/app_config.yaml の `web:` の節。spec/12 の 12 章）."""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, ValidationError

from app.core.exceptions import ConfigurationError
from app.modality.config import ModalityConfig, load_modality_config

DEFAULT_BIND_ADDRESS = "127.0.0.1"
DEFAULT_PORT = 8080
PORT_MIN = 1
PORT_MAX = 65535


class WebConfig(BaseModel):
    model_config = {"frozen": True, "extra": "forbid"}

    bind_address: str = Field(DEFAULT_BIND_ADDRESS, min_length=1)
    port: int = Field(DEFAULT_PORT, ge=PORT_MIN, le=PORT_MAX)


def load_app_config(config_path: Path) -> tuple[ModalityConfig, WebConfig]:
    """`modality:` と `web:` の節を読む。`web:` が無ければ既定（手元の 8080）."""
    modality = load_modality_config(config_path)
    try:
        with config_path.open("r", encoding="utf-8") as fp:
            loaded = yaml.safe_load(fp)
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigurationError(
            f"Failed to read configuration file: {config_path}",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc
    raw_web = loaded.get("web") if isinstance(loaded, dict) else None
    if raw_web is None:
        return modality, WebConfig()
    if not isinstance(raw_web, dict):
        raise ConfigurationError(
            "The 'web' section must be a mapping", {"config_path": str(config_path)}
        )
    try:
        return modality, WebConfig.model_validate(raw_web)
    except ValidationError as exc:
        raise ConfigurationError(
            "Invalid web configuration",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc
