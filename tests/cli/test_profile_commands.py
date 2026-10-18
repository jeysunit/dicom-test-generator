"""装置のプロファイルの CLI の試験（spec/13 の 7）."""

from __future__ import annotations

import argparse

import pydicom
import pytest
import yaml

from app.cli.commands import generate_command, profiles_list_command
from app.cli.main import _create_parser, _map_exception_to_exit_code
from app.core import ProfileNotFoundError, TemplateNotFoundError
from app.services.profile_loader import PROFILE_DIRS_ENV
from app.services.template_loader import TemplateLoaderService

from tests.cli.test_commands import _write_job_yaml


def test_parser_accepts_profile_options() -> None:
    parser = _create_parser()

    generate_args = parser.parse_args(["generate", "job.yaml", "--profile", "x"])
    quick_args = parser.parse_args(
        ["quick", "-p", "P1", "-m", "ct_generic", "-s", "1", "-i", "1",
         "-o", "out", "--profile", "x"]
    )
    list_args = parser.parse_args(["profiles", "list"])

    assert generate_args.profile == "x"
    assert quick_args.profile == "x"
    assert list_args.func is profiles_list_command


def test_generate_with_profile_option(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.delenv(PROFILE_DIRS_ENV, raising=False)
    job_file = tmp_path / "job.yaml"
    output_dir = tmp_path / "output"
    _write_job_yaml(job_file, output_dir)
    args = argparse.Namespace(
        job_file=str(job_file),
        output=None,
        dry_run=False,
        quiet=True,
        profile="dtg_synthetic_ct",
    )

    exit_code = generate_command(args)

    assert exit_code == 0
    files = list(output_dir.glob("*.dcm"))
    assert len(files) == 1
    ds = pydicom.dcmread(files[0])
    assert ds.ManufacturerModelName == "DTG Synthetic CT 64"


def test_generate_with_device_profile_in_job(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv(PROFILE_DIRS_ENV, raising=False)
    job_file = tmp_path / "job.yaml"
    output_dir = tmp_path / "output"
    _write_job_yaml(job_file, output_dir)
    job = yaml.safe_load(job_file.read_text(encoding="utf-8"))
    job["device_profile"] = "no_such_device"
    job_file.write_text(yaml.safe_dump(job), encoding="utf-8")
    args = argparse.Namespace(
        job_file=str(job_file), output=None, dry_run=False, quiet=True, profile=None
    )

    with pytest.raises(ProfileNotFoundError) as exc_info:
        generate_command(args)

    assert _map_exception_to_exit_code(exc_info.value) == 2


def test_profiles_list_shows_examples_and_external(tmp_path, monkeypatch, capsys) -> None:
    external = tmp_path / "private"
    external.mkdir()
    (external / "site_ct.yaml").write_text(
        yaml.safe_dump(
            {
                "schema_version": 1,
                "name": "site_ct",
                "device": {
                    "modality": "CT",
                    "manufacturer": "Site Maker",
                    "manufacturers_model_name": "Site CT",
                },
                "storage": {
                    "sop_classes": ["1.2.840.10008.5.1.4.1.1.2"],
                    "transfer_syntaxes": ["1.2.840.10008.1.2"],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv(PROFILE_DIRS_ENV, str(external))

    exit_code = profiles_list_command(argparse.Namespace())
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "dtg_synthetic_ct" in out
    assert "site_ct" in out
    assert "Site Maker" in out
    assert str(external) in out


def test_profiles_list_reports_broken_profile(tmp_path, monkeypatch, capsys) -> None:
    external = tmp_path / "private"
    external.mkdir()
    (external / "broken.yaml").write_text("device: [unclosed", encoding="utf-8")
    monkeypatch.setenv(PROFILE_DIRS_ENV, str(external))

    exit_code = profiles_list_command(argparse.Namespace())
    captured = capsys.readouterr()

    assert exit_code == 2
    assert "dtg_synthetic_ct" in captured.out
    assert "broken.yaml" in captured.err


def test_quick_uses_first_transfer_syntax_and_does_not_fall_back(
    tmp_path, monkeypatch
) -> None:
    from app.cli.commands import _profile_transfer_syntax
    from app.core import ProfileMismatchError

    external = tmp_path / "private"
    external.mkdir()
    base = {
        "schema_version": 1,
        "device": {
            "modality": "CT",
            "manufacturer": "Site Maker",
            "manufacturers_model_name": "Site CT",
        },
    }
    for name, syntaxes in (
        ("explicit_first", ["1.2.840.10008.1.2.1", "1.2.840.10008.1.2"]),
        ("jpeg_first", ["1.2.840.10008.1.2.4.70", "1.2.840.10008.1.2"]),
    ):
        data = dict(base, name=name, storage={
            "sop_classes": ["1.2.840.10008.5.1.4.1.1.2"],
            "transfer_syntaxes": syntaxes,
        })
        (external / f"{name}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setenv(PROFILE_DIRS_ENV, str(external))

    assert _profile_transfer_syntax("explicit_first").uid == "1.2.840.10008.1.2.1"
    with pytest.raises(ProfileMismatchError, match="1.2.840.10008.1.2.4.70"):
        _profile_transfer_syntax("jpeg_first")


def test_old_device_template_name_points_to_profiles(monkeypatch) -> None:
    """装置ごとの古いテンプレートの名前は、プロファイルの置き場へ案内する."""
    import hashlib

    import app.services.template_loader as template_loader_module

    old_name = "old_vendor_ct"
    digest = hashlib.sha256(old_name.encode("utf-8")).hexdigest()
    monkeypatch.setattr(
        template_loader_module,
        "DEVICE_SPECIFIC_TEMPLATES",
        {digest: "ct_generic"},
    )

    with pytest.raises(TemplateNotFoundError) as exc_info:
        TemplateLoaderService().load_modality_template(old_name)

    hint = exc_info.value.details["hint"]
    assert "--profile" in hint
    assert PROFILE_DIRS_ENV in hint
    assert "ct_generic" in hint
    assert _map_exception_to_exit_code(exc_info.value) == 2
