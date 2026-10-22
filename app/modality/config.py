"""モダリティのダミーの設定（config/app_config.yaml の `modality:` の節。docs/spec/12 の 12 章）."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.exceptions import ModalityConfigError
from app.core.validation_text import describe_validation_error

AE_TITLE_MAX_LENGTH = 16
PORT_MIN = 1
PORT_MAX = 65535
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_LISTEN_PORT = 11113
MAX_RETRY_ATTEMPTS = 10
DEFAULT_MAX_RESULTS = 1000
MAX_RESULTS_LIMIT = 100_000
DEFAULT_MAX_ITEM_BYTES = 256 * 1024
DEFAULT_MAX_TOTAL_BYTES = 16 * 1024 * 1024
DEFAULT_MAX_IMAGES_PER_EXAM = 2000  # 1回の撮影の合計の枚数（docs/spec/12a の 10.5）
DEFAULT_COMMITMENT_TIMEOUT_SECONDS = 600.0  # 保管の確認の結果を待つ（docs/spec/12 の 8.3）
MAX_COMMITMENT_TIMEOUT_SECONDS = 86400.0
MAX_COMMITMENT_WAIT_SECONDS = 60.0  # 同じ Association で待つ上限（docs/spec/12 の 12 章）
_PRINTABLE_ASCII_MIN = 0x20
_PRINTABLE_ASCII_MAX = 0x7E

CharacterSetChoice = Literal["auto", "utf8", "jis", "jis_kana"]
FallbackChoice = Literal["utf8", "jis", "jis_kana"]
QueryCharacterSet = Literal["ISO_IR 192", "utf8", "jis", "jis_kana"]
PixelMode = Literal["simple_text", "ct_realistic"]


def validate_ae_title(value: str) -> str:
    """AE タイトル：16 文字以内・空白だけは不可・表示できる ASCII で `\\` 無し（PS3.5 AE）."""
    if not value.strip():
        raise ValueError("AE title must not be empty or spaces only")
    if len(value) > AE_TITLE_MAX_LENGTH:
        raise ValueError(f"AE title must be {AE_TITLE_MAX_LENGTH} characters or fewer")
    if "\\" in value or any(
        not _PRINTABLE_ASCII_MIN <= ord(char) <= _PRINTABLE_ASCII_MAX for char in value
    ):
        raise ValueError("AE title must be printable ASCII without backslash")
    return value


class NodeConfig(BaseModel):
    """相手の AE（ワークリストの相手・送り先）."""

    model_config = {"frozen": True}

    ae_title: str
    host: str = Field(..., min_length=1)
    port: int = Field(..., ge=PORT_MIN, le=PORT_MAX)

    @field_validator("ae_title")
    @classmethod
    def _check_ae_title(cls, value: str) -> str:
        return validate_ae_title(value)


class WorklistPeerConfig(NodeConfig):
    timeout_seconds: float = Field(DEFAULT_TIMEOUT_SECONDS, gt=0)
    # 相手が返す応答の上限（5.5）。受け取りながら数え、超えたら C-CANCEL して止める
    max_results: int = Field(DEFAULT_MAX_RESULTS, ge=1, le=MAX_RESULTS_LIMIT)
    max_item_bytes: int = Field(DEFAULT_MAX_ITEM_BYTES, ge=1024)
    max_total_bytes: int = Field(DEFAULT_MAX_TOTAL_BYTES, ge=1024)
    query_character_set: QueryCharacterSet = "ISO_IR 192"
    use_mpps: bool = False  # Phase 3c


class DestinationConfig(NodeConfig):
    name: str = Field(..., min_length=1)
    storage_commitment: bool = False  # Phase 3c
    # 保管の確認の結果を待つ秒（8.3）と、同じ Association で待つ秒（8.3.1。0 は待たない）
    commitment_timeout_seconds: float = Field(
        DEFAULT_COMMITMENT_TIMEOUT_SECONDS, ge=1, le=MAX_COMMITMENT_TIMEOUT_SECONDS
    )
    commitment_wait_seconds: float = Field(0, ge=0, le=MAX_COMMITMENT_WAIT_SECONDS)
    timeout_seconds: float = Field(DEFAULT_TIMEOUT_SECONDS, gt=0)


class MppsPeerConfig(NodeConfig):
    """MPPS の送り先（Phase 3c。8.4.1）。書かなければワークリストの相手へ送る."""

    timeout_seconds: float = Field(DEFAULT_TIMEOUT_SECONDS, gt=0)


class ListenConfig(BaseModel):
    model_config = {"frozen": True}

    bind_address: str = "127.0.0.1"
    port: int = Field(DEFAULT_LISTEN_PORT, ge=PORT_MIN, le=PORT_MAX)


class RetryConfig(BaseModel):
    model_config = {"frozen": True}

    max_attempts: int = Field(0, ge=0, le=MAX_RETRY_ATTEMPTS)


class ModalityConfig(BaseModel):
    model_config = {"frozen": True}

    ae_title: str
    station_name: str = ""
    listen: ListenConfig = Field(default_factory=ListenConfig)
    state_dir: str = "modality_state"
    output_dir: str = "output/modality"
    character_set: CharacterSetChoice = "auto"
    character_set_fallback: FallbackChoice = "utf8"
    default_template: str = "ct_generic"
    default_profile: str | None = None  # 装置のプロファイル（docs/spec/13 の 8）。None は重ねない
    default_hospital: str | None = None
    default_pixel_mode: PixelMode = "ct_realistic"
    worklist: WorklistPeerConfig
    mpps: MppsPeerConfig | None = None  # Phase 3c。None はワークリストの相手
    destinations: list[DestinationConfig] = Field(..., min_length=1)
    default_destination: str
    retry: RetryConfig = Field(default_factory=RetryConfig)
    max_images_per_exam: int = Field(DEFAULT_MAX_IMAGES_PER_EXAM, ge=1)

    @field_validator("ae_title")
    @classmethod
    def _check_ae_title(cls, value: str) -> str:
        return validate_ae_title(value)

    @model_validator(mode="after")
    def _check_destinations(self) -> ModalityConfig:
        names = [destination.name for destination in self.destinations]
        if len(names) != len(set(names)):
            raise ValueError("destination names must be unique")
        if self.default_destination not in names:
            raise ValueError(
                f"default_destination '{self.default_destination}' is not in destinations"
            )
        return self

    def mpps_peer(self) -> MppsPeerConfig | WorklistPeerConfig:
        """MPPS の送り先：`mpps:` の相手、無ければワークリストの相手（8.4.1）."""
        return self.mpps if self.mpps is not None else self.worklist

    def destination(self, name: str | None = None) -> DestinationConfig:
        """名前の送り先を返す。名前が無ければ既定の送り先."""
        wanted = name or self.default_destination
        for destination in self.destinations:
            if destination.name == wanted:
                return destination
        raise ModalityConfigError(
            f"Destination not found: {wanted}",
            {"destination": wanted, "known": ", ".join(d.name for d in self.destinations)},
        )


def load_modality_config(config_path: Path) -> ModalityConfig:
    """設定のファイルから `modality:` の節を読む."""
    if not config_path.exists():
        raise ModalityConfigError(
            f"Configuration file not found: {config_path}",
            {"config_path": str(config_path)},
        )
    try:
        with config_path.open("r", encoding="utf-8") as fp:
            loaded = yaml.safe_load(fp)
    except yaml.YAMLError as exc:
        raise ModalityConfigError(
            f"Invalid YAML format: {config_path}",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc
    except OSError as exc:
        raise ModalityConfigError(
            f"Failed to read configuration file: {config_path}",
            {"config_path": str(config_path), "reason": str(exc)},
        ) from exc

    if not isinstance(loaded, dict) or not isinstance(loaded.get("modality"), dict):
        raise ModalityConfigError(
            "Missing 'modality' section in configuration",
            {"config_path": str(config_path)},
        )
    try:
        return ModalityConfig.model_validate(loaded["modality"])
    except ValidationError as exc:
        raise ModalityConfigError(
            "Invalid modality configuration",
            {"config_path": str(config_path), "reason": describe_validation_error(exc)},
        ) from exc
