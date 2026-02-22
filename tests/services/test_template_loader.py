from __future__ import annotations

import pytest

from app.core import TemplateNotFoundError, TemplateParseError
from app.services.template_loader import TemplateLoaderService


def test_load_modality_template_success() -> None:
    service = TemplateLoaderService()

    template = service.load_modality_template("fujifilm_scenaria_view_ct")

    assert isinstance(template, dict)
    assert "info" in template


def test_load_modality_template_not_found() -> None:
    service = TemplateLoaderService()

    with pytest.raises(TemplateNotFoundError):
        service.load_modality_template("does_not_exist")


def test_load_hospital_template_success() -> None:
    service = TemplateLoaderService()

    template = service.load_hospital_template("hospital_a")

    assert isinstance(template, dict)
    assert "overrides" in template


def test_merge_templates_without_hospital() -> None:
    service = TemplateLoaderService()

    merged = service.merge_templates(
        modality_name="fujifilm_scenaria_view_ct",
        hospital_name=None,
    )
    modality = service.load_modality_template("fujifilm_scenaria_view_ct")

    assert merged == modality


def test_merge_templates_with_hospital() -> None:
    service = TemplateLoaderService()

    merged = service.merge_templates(
        modality_name="fujifilm_scenaria_view_ct",
        hospital_name="hospital_a",
    )

    assert merged["general_equipment"]["institution_name"] == "A Hospital"


def test_template_parse_error(tmp_path) -> None:
    service = TemplateLoaderService()
    modality_dir = tmp_path / "modality"
    modality_dir.mkdir(parents=True, exist_ok=True)
    invalid_template = modality_dir / "broken.yaml"
    invalid_template.write_text("info: [invalid", encoding="utf-8")

    service._modality_dir = modality_dir

    with pytest.raises(TemplateParseError):
        service.load_modality_template("broken")
