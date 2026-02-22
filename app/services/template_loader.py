"""Template loading and merging service."""

from __future__ import annotations

from pathlib import Path

import yaml

from app.core.exceptions import TemplateNotFoundError, TemplateParseError


class TemplateLoaderService:
    """テンプレート読み込みとマージを提供するサービス."""

    def __init__(self) -> None:
        self._project_root = Path(__file__).resolve().parents[2]
        self._modality_dir = self._project_root / "templates" / "modality"
        self._hospital_dir = self._project_root / "templates" / "hospital"

    def load_modality_template(self, name: str) -> dict:
        """モダリティテンプレートを読み込む."""
        template_path = self._modality_dir / f"{name}.yaml"
        return self._load_yaml_template(template_path, name)

    def load_hospital_template(self, name: str) -> dict:
        """病院テンプレートを読み込む."""
        template_path = self._hospital_dir / f"{name}.yaml"
        return self._load_yaml_template(template_path, name)

    def merge_templates(self, modality_name: str, hospital_name: str | None) -> dict:
        """テンプレートを浅いマージで統合する."""
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

        merged = dict(modality_template)
        for key, value in overrides.items():
            merged[key] = value
        return merged

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

