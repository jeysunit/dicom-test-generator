"""Device profile loading service (docs/spec/13 の 6).

探す順は、環境の変数 DTG_PROFILE_DIRS → 設定のファイルの profiles.search_paths →
リポジトリの profiles/examples/。同じ名前が2か所以上にあれば誤りにする。
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.core.device_profile import PROFILE_NAME_PATTERN, DeviceProfile
from app.core.exceptions import (
    DuplicateProfileError,
    ProfileError,
    ProfileMismatchError,
    ProfileNotFoundError,
    ProfileParseError,
)
from app.core.models import TransferSyntaxConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = PROJECT_ROOT / "profiles" / "examples"
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config" / "app_config.yaml"
PROFILE_DIRS_ENV = "DTG_PROFILE_DIRS"
PROFILE_SUFFIX = ".yaml"

# 装置のプロファイルを選んだときに使える転送の形（docs/spec/06 の Transfer Syntax）。
# 廃止の Explicit VR Big Endian（PS3.5 A.3）は作らない
GENERATABLE_TRANSFER_SYNTAXES = {
    "1.2.840.10008.1.2": ("Implicit VR Little Endian", True, True),
    "1.2.840.10008.1.2.1": ("Explicit VR Little Endian", False, True),
}


@dataclass(frozen=True)
class ProfileEntry:
    """一覧の1行."""

    name: str
    path: Path
    profile: DeviceProfile


def profile_transfer_syntax(profile: DeviceProfile) -> TransferSyntaxConfig:
    """プロファイルの最初の転送の形（装置の好み）を使う（docs/spec/13 の 4.3）.

    最初の形をこの道具が作れなければ止める（黙って次の形に替えない）。
    """
    uid = profile.storage.transfer_syntaxes[0]
    if uid not in GENERATABLE_TRANSFER_SYNTAXES:
        raise ProfileMismatchError(
            f"The device's first Transfer Syntax {uid} cannot be generated "
            f"(supported: {', '.join(GENERATABLE_TRANSFER_SYNTAXES)})",
            {"profile": profile.name},
        )
    name, is_implicit_vr, is_little_endian = GENERATABLE_TRANSFER_SYNTAXES[uid]
    return TransferSyntaxConfig(
        uid=uid,
        name=name,
        is_implicit_vr=is_implicit_vr,
        is_little_endian=is_little_endian,
    )


def format_validation_error(exc: ValidationError) -> str:
    """Pydantic の誤りを「欄: 理由」の並びにする."""
    parts = []
    for error in exc.errors():
        location = ".".join(str(item) for item in error["loc"]) or "(root)"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)


class ProfileLoaderService:
    """装置のプロファイルを探して読む."""

    def __init__(
        self,
        config_path: Path | None = None,
        environ: Mapping[str, str] | None = None,
        examples_dir: Path | None = None,
    ) -> None:
        self._config_path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
        self._environ = os.environ if environ is None else environ
        self._examples_dir = examples_dir or EXAMPLES_DIR

    @staticmethod
    def default_examples_dir() -> Path:
        return EXAMPLES_DIR

    def search_paths(self) -> list[Path]:
        """探すフォルダを順に返す。無いフォルダは誤り（docs/spec/13 の 6.1）."""
        paths: list[Path] = []
        raw_env = self._environ.get(PROFILE_DIRS_ENV, "")
        for item in raw_env.split(os.pathsep):
            if item.strip():
                paths.append(Path(item.strip()).expanduser())
        paths.extend(self._config_search_paths())
        paths.append(self._examples_dir)

        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if not path.is_dir():
                raise ProfileError(
                    f"Profile search path does not exist: {path}",
                    {"path": str(path)},
                )
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            unique.append(path)
        return unique

    def load(self, name: str) -> DeviceProfile:
        """名前でプロファイルを読む."""
        directories = self.search_paths()
        if not re.match(PROFILE_NAME_PATTERN, name):
            raise ProfileNotFoundError(name, [str(d) for d in directories])
        found = [d / f"{name}{PROFILE_SUFFIX}" for d in directories]
        found = [path for path in found if path.is_file()]
        if not found:
            raise ProfileNotFoundError(name, [str(d) for d in directories])
        if len(found) > 1:
            raise DuplicateProfileError(name, [str(path) for path in found])
        return self._load_file(found[0])

    def list_profiles(self) -> tuple[list[ProfileEntry], list[ProfileError]]:
        """読めるプロファイルと、読めなかったものの誤りを返す."""
        by_name: dict[str, list[Path]] = {}
        for directory in self.search_paths():
            for path in sorted(directory.glob(f"*{PROFILE_SUFFIX}")):
                if path.is_file():
                    by_name.setdefault(path.stem, []).append(path)

        entries: list[ProfileEntry] = []
        errors: list[ProfileError] = []
        for name in sorted(by_name):
            paths = by_name[name]
            if len(paths) > 1:
                errors.append(DuplicateProfileError(name, [str(p) for p in paths]))
                continue
            try:
                profile = self._load_file(paths[0])
            except ProfileError as exc:
                errors.append(exc)
                continue
            entries.append(ProfileEntry(name=name, path=paths[0], profile=profile))
        return entries, errors

    def _config_search_paths(self) -> list[Path]:
        if not self._config_path.is_file():
            return []
        try:
            with self._config_path.open("r", encoding="utf-8") as fp:
                loaded = yaml.safe_load(fp)
        except (yaml.YAMLError, OSError, UnicodeDecodeError) as exc:
            raise ProfileError(
                f"Failed to read configuration file: {self._config_path}",
                {"reason": str(exc)},
            ) from exc
        if loaded is None:
            return []
        if not isinstance(loaded, dict):
            raise ProfileError(
                "Configuration root must be a mapping",
                {"config_path": str(self._config_path)},
            )
        section = loaded.get("profiles")
        if section is None:
            return []
        if not isinstance(section, dict):
            raise ProfileError(
                "'profiles' section must be a mapping",
                {"config_path": str(self._config_path)},
            )
        unknown = sorted(set(section) - {"search_paths"})
        if unknown:
            raise ProfileError(
                "Unknown keys in 'profiles' section",
                {"config_path": str(self._config_path), "keys": ", ".join(unknown)},
            )
        raw_paths = section.get("search_paths")
        if raw_paths is None:
            return []
        if not isinstance(raw_paths, list) or not all(
            isinstance(item, str) for item in raw_paths
        ):
            raise ProfileError(
                "profiles.search_paths must be a list of strings",
                {"config_path": str(self._config_path)},
            )
        base = self._config_path.parent
        paths = []
        for item in raw_paths:
            path = Path(item).expanduser()
            paths.append(path if path.is_absolute() else base / path)
        return paths

    def _load_file(self, path: Path) -> DeviceProfile:
        try:
            with path.open("r", encoding="utf-8") as fp:
                loaded = yaml.safe_load(fp)
        except yaml.YAMLError as exc:
            raise ProfileParseError(str(path), f"YAML: {exc}") from exc
        except UnicodeDecodeError as exc:
            raise ProfileParseError(str(path), f"file must be UTF-8: {exc}") from exc
        except OSError as exc:
            raise ProfileParseError(str(path), str(exc)) from exc

        if not isinstance(loaded, dict):
            raise ProfileParseError(str(path), "profile root must be a mapping")
        try:
            profile = DeviceProfile.model_validate(loaded)
        except ValidationError as exc:
            raise ProfileParseError(str(path), format_validation_error(exc)) from exc
        if profile.name != path.stem:
            raise ProfileParseError(
                str(path),
                f"name: '{profile.name}' must match the file name '{path.stem}'",
            )
        return profile
