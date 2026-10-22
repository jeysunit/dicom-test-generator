"""Template loading and merging service."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from app.core.exceptions import TemplateNotFoundError, TemplateParseError

from .profile_loader import PROFILE_DIRS_ENV

# テンプレートの名前（ADR-0016：小文字・数字・`_` 区切り。既存の名前も読めるよう `-` と大文字も許す）
TEMPLATE_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")

# 装置ごとだった古いモダリティテンプレート：古い名前の SHA-256 → 土台のテンプレート。
# 古い名前は商用の製品の名前を含むため、名前そのものを書かない
# （docs/decisions/0016-generic-template-names.md）。装置ごとの写しは装置のプロファイルに
# なった（docs/spec/13_device_profiles.md の 7.3）。別名として黙って読まず、
# プロファイルの置き場へ案内する TemplateNotFoundError にする。
DEVICE_SPECIFIC_TEMPLATES: dict[str, str] = {
    "ece4615a3432602c091b9c7abcc6e0578ee7cc1762e1360414e3c3b516859422": "ct_generic",
}


def _deep_merge(base: dict, overrides: dict) -> dict:
    """`overrides` を `base` に重ねた新しい dict を返す（どちらも変えない）.

    両方が dict の鍵は中へ進んで重ね、それ以外は `overrides` の値で置き換える。
    """
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def _device_profile_hint(base_template: str) -> str:
    return (
        "this name was a device-specific template; device-specific output is now "
        "a device profile (docs/spec/13). Put the profile in an external profile "
        f"directory ({PROFILE_DIRS_ENV} or profiles.search_paths in "
        "config/app_config.yaml) and generate with "
        f"--modality {base_template} --profile <profile name>"
    )


class TemplateLoaderService:
    """テンプレート読み込みとマージを提供するサービス."""

    def __init__(self) -> None:
        self._project_root = Path(__file__).resolve().parents[2]
        self._modality_dir = self._project_root / "templates" / "modality"
        self._hospital_dir = self._project_root / "templates" / "hospital"

    def list_modality_templates(self) -> list[str]:
        """読めるモダリティテンプレートの名前（拡張子を除く）を名前の順で返す."""
        return sorted(path.stem for path in self._modality_dir.glob("*.yaml") if path.is_file())

    def load_modality_template(self, name: str) -> dict:
        """モダリティテンプレートを読み込む."""
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        base_template = DEVICE_SPECIFIC_TEMPLATES.get(digest)
        if base_template is not None and not (self._modality_dir / f"{name}.yaml").exists():
            raise TemplateNotFoundError(name, hint=_device_profile_hint(base_template))
        return self._load_yaml_template(self._template_path(self._modality_dir, name), name)

    def load_hospital_template(self, name: str) -> dict:
        """病院テンプレートを読み込む."""
        return self._load_yaml_template(self._template_path(self._hospital_dir, name), name)

    @staticmethod
    def _template_path(directory: Path, name: str) -> Path:
        """名前は1つのファイルの名前だけを受ける（画面・Job から来る名前で置き場の外を読まない）."""
        if not TEMPLATE_NAME_PATTERN.fullmatch(name):
            raise TemplateNotFoundError(name)
        return directory / f"{name}.yaml"

    def merge_templates(self, modality_name: str, hospital_name: str | None) -> dict:
        """病院テンプレートの overrides をモダリティテンプレートに深くマージする.

        節（`general_equipment` など）の中は鍵ごとに上書きし、病院が書かない鍵は
        モダリティの値を残す。浅いマージでは節ごと置き換わり、Type 2 の
        Manufacturer (0008,0070) が消えていた（PS3.3 C.7.5.1）。
        """
        modality_template = self.load_modality_template(modality_name)
        if hospital_name is None:
            return dict(modality_template)

        hospital_template = self.load_hospital_template(hospital_name)
        overrides = hospital_template.get("overrides", {})
        if not isinstance(overrides, dict):
            raise TemplateParseError(
                str(self._hospital_dir / f"{hospital_name}.yaml"),
                "'overrides' must be a mapping",
            )

        return _deep_merge(modality_template, overrides)

    def _load_yaml_template(self, path: Path, template_name: str) -> dict:
        if not path.exists():
            raise TemplateNotFoundError(template_name)

        try:
            with path.open("r", encoding="utf-8") as fp:
                loaded = yaml.safe_load(fp)
        except yaml.YAMLError as exc:
            raise TemplateParseError(str(path), str(exc)) from exc
        except OSError as exc:
            raise TemplateParseError(str(path), str(exc)) from exc

        if not isinstance(loaded, dict):
            raise TemplateParseError(str(path), "Template root must be a mapping")

        return loaded

