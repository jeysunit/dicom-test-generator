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
    """ct_generic の中身は架空の名前だけを使う（ADR-0016）."""
    service = TemplateLoaderService()

    template = service.load_modality_template("ct_generic")

    assert template["info"]["name"] == "ct_generic"
    assert template["info"]["modality"] == "CT"
    equipment = template["general_equipment"]
    assert equipment["manufacturer"].startswith("DTG")
    assert equipment["manufacturers_model_name"].startswith("DTG")
    assert equipment["station_name"].startswith("DTG")


def test_device_specific_template_raises_with_profile_hint(monkeypatch) -> None:
    """装置ごとの古いテンプレートの名前は、プロファイルの置き場へ案内する（docs/spec/13 の 7.3）."""
    import app.services.template_loader as template_loader_module

    old_name = "old_vendor_ct"
    digest = hashlib.sha256(old_name.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        template_loader_module,
        "DEVICE_SPECIFIC_TEMPLATES",
        {digest: "ct_generic"},
    )
    service = TemplateLoaderService()

    with pytest.raises(TemplateNotFoundError) as exc_info:
        service.load_modality_template(old_name)

    hint = exc_info.value.details["hint"]
    assert "device profile" in hint
    assert "--profile" in hint
    assert "--modality ct_generic" in hint


def test_device_specific_template_bases_exist() -> None:
    """案内に出す土台のテンプレートは、どれも実在する."""
    from app.services.template_loader import DEVICE_SPECIFIC_TEMPLATES

    service = TemplateLoaderService()

    assert DEVICE_SPECIFIC_TEMPLATES
    for base_name in DEVICE_SPECIFIC_TEMPLATES.values():
        assert isinstance(service.load_modality_template(base_name), dict)


def test_unknown_template_has_no_hint() -> None:
    service = TemplateLoaderService()

    with pytest.raises(TemplateNotFoundError) as exc_info:
        service.load_modality_template("does_not_exist")

    assert "hint" not in exc_info.value.details
