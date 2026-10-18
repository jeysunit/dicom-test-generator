from __future__ import annotations

import hashlib

import pytest

from app.core import TemplateNotFoundError, TemplateParseError
from app.services.template_loader import TemplateLoaderService


def test_load_modality_template_success() -> None:
    service = TemplateLoaderService()

    template = service.load_modality_template("ct_generic")

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
        modality_name="ct_generic",
        hospital_name=None,
    )
    modality = service.load_modality_template("ct_generic")

    assert merged == modality


def test_merge_templates_with_hospital() -> None:
    service = TemplateLoaderService()

    merged = service.merge_templates(
        modality_name="ct_generic",
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


def test_generic_ct_template_has_no_commercial_names() -> None:
    """ct_generic の中身は架空の名前だけを使う（spec/12 の 17）."""
    service = TemplateLoaderService()

    template = service.load_modality_template("ct_generic")

    assert template["info"]["name"] == "ct_generic"
    assert template["info"]["modality"] == "CT"
    equipment = template["general_equipment"]
    assert equipment["manufacturer"].startswith("DTG")
    assert equipment["manufacturers_model_name"].startswith("DTG")
    assert equipment["station_name"].startswith("DTG")


def test_renamed_template_raises_with_new_name(monkeypatch) -> None:
    """名前を変えたテンプレートの古い名前は、新しい名前を添えたエラーにする."""
    import app.services.template_loader as template_loader_module

    old_name = "old_vendor_ct"
    digest = hashlib.sha256(old_name.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        template_loader_module,
        "RENAMED_MODALITY_TEMPLATES",
        {digest: "ct_generic"},
    )
    service = TemplateLoaderService()

    with pytest.raises(TemplateNotFoundError) as exc_info:
        service.load_modality_template(old_name)

    assert exc_info.value.details["renamed_to"] == "ct_generic"
    assert "renamed to ct_generic" in str(exc_info.value)


def test_renamed_template_targets_exist() -> None:
    """名前の変更の表の行き先は、どれも実在するテンプレート."""
    from app.services.template_loader import RENAMED_MODALITY_TEMPLATES

    service = TemplateLoaderService()

    assert RENAMED_MODALITY_TEMPLATES
    for new_name in RENAMED_MODALITY_TEMPLATES.values():
        assert isinstance(service.load_modality_template(new_name), dict)


def test_unknown_template_has_no_renamed_to() -> None:
    service = TemplateLoaderService()

    with pytest.raises(TemplateNotFoundError) as exc_info:
        service.load_modality_template("does_not_exist")

    assert "renamed_to" not in exc_info.value.details
