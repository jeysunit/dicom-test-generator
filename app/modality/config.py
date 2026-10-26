"""モダリティのダミーの設定（config/app_config.yaml の `modality:` の節。docs/spec/12 の 12 章）."""

from __future__ import annotations

from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.exceptions import ModalityConfigError
from app.core.patient_input import (
    DEFAULT_TEMPORARY_ID_PREFIX,
    DEFAULT_TIMEZONE,
    DEFAULT_UNKNOWN_NAME_IDEOGRAPHIC,
    DEFAULT_UNKNOWN_NAME_PHONETIC,
    validate_temporary_id_prefix,
    validate_unknown_name_group,
)
from app.core.validation_text import describe_validation_error

AE_TITLE_MAX_LENGTH = 16
STATION_NAME_MAX_LENGTH = 16  # SH（PS3.5 6.2）
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
_DELETE = 0x7F

CharacterSetChoice = Literal["auto", "utf8", "jis", "jis_kana"]
FallbackChoice = Literal["utf8", "jis", "jis_kana"]
QueryCharacterSet = Literal["ISO_IR 192", "utf8", "jis", "jis_kana"]
PixelMode = Literal["simple_text", "ct_realistic"]
# 撮影済みの予約の撮り直しの形（docs/spec/12 の 6.3・ADR-0024）
RetakeMode = Literal["append", "new_order"]


def validate_ae_title(value: str) -> str:
    """AEタイトル：16 文字以内・空白だけは不可・表示できる ASCII で `\\` 無し（PS3.5 AE）."""
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
    """相手の AE（ワークリストの相手・送信先）."""

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
    """MPPS の送信先（Phase 3c。8.4.1）。書かなければワークリストの相手へ送る."""

    timeout_seconds: float = Field(DEFAULT_TIMEOUT_SECONDS, gt=0)


class ListenConfig(BaseModel):
    model_config = {"frozen": True}

    bind_address: str = "127.0.0.1"
    port: int = Field(DEFAULT_LISTEN_PORT, ge=PORT_MIN, le=PORT_MAX)


class RetryConfig(BaseModel):
    model_config = {"frozen": True}

    max_attempts: int = Field(0, ge=0, le=MAX_RETRY_ATTEMPTS)


class StationConfig(BaseModel):
    """DTG が名乗る装置の1つ：表示名・AEタイトル・Station Name（docs/spec/12 の 12 章）."""

    model_config = {"frozen": True}

    name: str = Field(..., min_length=1)
    ae_title: str
    station_name: str = ""

    @field_validator("ae_title")
    @classmethod
    def _check_ae_title(cls, value: str) -> str:
        # 前後の空白は AEタイトルの値に含めない（PS3.5 の AE）。比べる前にそろえる
        return validate_ae_title(value).strip()

    @field_validator("station_name")
    @classmethod
    def _check_station_name(cls, value: str) -> str:
        """Station Name (0008,1010) は SH：16 文字まで・`\\` と制御文字は不可（PS3.5 6.2）."""
        if len(value) > STATION_NAME_MAX_LENGTH:
            raise ValueError(f"station_name must be {STATION_NAME_MAX_LENGTH} characters or fewer")
        if "\\" in value or any(
            ord(char) < _PRINTABLE_ASCII_MIN or ord(char) == _DELETE for char in value
        ):
            raise ValueError("station_name must not contain backslash or control characters")
        return value


class ModalityConfig(BaseModel):
    model_config = {"frozen": True}

    # 装置の一覧（docs/spec/12 の 12 章）。`ae_title`・`station_name` は標準の装置の値で、
    # 一覧を書かない今の形の設定では、この2つから装置1つの一覧を作る
    stations: list[StationConfig] = Field(..., min_length=1)
    default_station: str
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
    # 試験の形：緊急の患者の氏名（かな）を確かめず、直さず、そのまま DICOM に出す（半角カナ・
    # ひらがな・混ざった値の受け側の試験用。docs/spec/12a の 10.5）。false が通常
    patient_input_test_mode: bool = False
    # 緊急の患者の生年月日の「今日」を決めるタイムゾーン（IANA の名前）。サーバーの OS の
    # 時計の地域に頼らない（UTC のコンテナでも日本の日付で確かめる。docs/spec/12a の 10.5）
    timezone: str = DEFAULT_TIMEZONE
    # 身元不明の患者（docs/spec/12a の 10.5）。「仮の ID を作る」ボタンが作る患者ID の頭と、
    # 「氏名が分からない」を選んだときの漢字・かなの氏名。英字の氏名は空にする
    temporary_patient_id_prefix: str = DEFAULT_TEMPORARY_ID_PREFIX
    unknown_name_ideographic: str = DEFAULT_UNKNOWN_NAME_IDEOGRAPHIC
    unknown_name_phonetic: str = DEFAULT_UNKNOWN_NAME_PHONETIC
    worklist: WorklistPeerConfig
    mpps: MppsPeerConfig | None = None  # Phase 3c。None はワークリストの相手
    destinations: list[DestinationConfig] = Field(..., min_length=1)
    default_destination: str
    retry: RetryConfig = Field(default_factory=RetryConfig)
    max_images_per_exam: int = Field(DEFAULT_MAX_IMAGES_PER_EXAM, ge=1)
    # append：同じ予約で追加撮影（IHE の Append Case）。new_order：RIS の新しい予約で撮り直す
    retake_mode: RetakeMode = "append"

    @field_validator("ae_title")
    @classmethod
    def _check_ae_title(cls, value: str) -> str:
        return validate_ae_title(value)

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"タイムゾーン {value!r} が見つかりません（例：Asia/Tokyo）") from exc
        return value

    @field_validator("temporary_patient_id_prefix")
    @classmethod
    def _check_temporary_id_prefix(cls, value: str) -> str:
        return validate_temporary_id_prefix(value)

    @field_validator("unknown_name_ideographic")
    @classmethod
    def _check_unknown_name_ideographic(cls, value: str) -> str:
        return validate_unknown_name_group("漢字", value)

    @field_validator("unknown_name_phonetic")
    @classmethod
    def _check_unknown_name_phonetic(cls, value: str) -> str:
        return validate_unknown_name_group("かな", value)

    @model_validator(mode="before")
    @classmethod
    def _normalize_stations(cls, data: object) -> object:
        """今の形（`ae_title` だけ）を装置1つの一覧にし、標準の装置の値を写す."""
        if not isinstance(data, dict):
            return data
        raw = dict(data)
        mirrored = {key: raw.pop(key) for key in ("ae_title", "station_name") if key in raw}
        if "stations" in raw:
            stations = raw["stations"]
            if not isinstance(stations, list) or not stations:
                raise ValueError("stations must list at least one station")
        else:
            if "ae_title" not in mirrored:
                return {**raw, **mirrored}  # 項目が無いことは、ふつうの検証で知らせる
            stations = [
                {
                    "name": mirrored["ae_title"],
                    "ae_title": mirrored["ae_title"],
                    "station_name": mirrored.get("station_name", ""),
                }
            ]
            raw["stations"] = stations
            mirrored = {}
        default_name = raw.get("default_station")
        if default_name is None:
            first = stations[0]
            default_name = first.get("name") if isinstance(first, dict) else None
            raw["default_station"] = default_name
        default = next(
            (s for s in stations if isinstance(s, dict) and s.get("name") == default_name), None
        )
        if default is None:
            raise ValueError(f"default_station '{default_name}' is not in stations")
        raw["ae_title"] = default.get("ae_title")
        raw["station_name"] = default.get("station_name", "")
        # 一覧と今の形の両方を書くのは、標準の装置の値と同じとき（読み直した値）だけ
        if any(raw[key] != value for key, value in mirrored.items()):
            raise ValueError("write either stations or ae_title/station_name, not both")
        return raw

    @model_validator(mode="after")
    def _check_stations(self) -> ModalityConfig:
        names = [station.name for station in self.stations]
        ae_titles = [station.ae_title for station in self.stations]
        if len(names) != len(set(names)):
            raise ValueError("station names must be unique")
        if len(ae_titles) != len(set(ae_titles)):
            raise ValueError("station AE titles must be unique")
        return self

    def station(self, name: str | None = None) -> StationConfig:
        """名前の装置を返す。名前が無ければ標準の装置."""
        wanted = name or self.default_station
        for station in self.stations:
            if station.name == wanted:
                return station
        raise ModalityConfigError(
            f"Station not found: {wanted}",
            {"station": wanted, "known": ", ".join(s.name for s in self.stations)},
        )

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
        """MPPS の送信先：`mpps:` の相手、無ければワークリストの相手（8.4.1）."""
        return self.mpps if self.mpps is not None else self.worklist

    def destination(self, name: str | None = None) -> DestinationConfig:
        """名前の送信先を返す。名前が無ければ標準の送信先."""
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
