"""異常のデータ（abnormal.level）が生成の道に届くことの試験（docs/spec/02）."""

from __future__ import annotations

import argparse
import random

import pydicom
import pytest
from pydantic import ValidationError

from app.cli.commands import generate_command, quick_command
from app.cli.main import _create_parser
from app.core import AbnormalConfig
from app.services.study_generator import StudyGeneratorService

from .test_study_generator import _make_config
from tests.cli.test_commands import _write_job_yaml


def _generate(tmp_path, level: str | None, name: str = "output"):
    config = _make_config(tmp_path=tmp_path)
    update = {"output_dir": str(tmp_path / name)}
    if level is not None:
        update["abnormal"] = AbnormalConfig(level=level)
    config = config.model_copy(update=update)
    output_dir = StudyGeneratorService().generate(config=config)
    (path,) = output_dir.glob("*.dcm")
    return pydicom.dcmread(path, force=True)


def test_none_level_matches_unspecified(tmp_path) -> None:
    default = _generate(tmp_path, None, "a")
    none = _generate(tmp_path, "none", "b")

    assert default.PatientID == "P000001"
    assert none.PatientID == "P000001"
    assert "PixelData" in none
    assert none.StudyInstanceUID.startswith("2.25.")


def test_mild_breaks_values_but_keeps_tags(tmp_path) -> None:
    random.seed(1)
    ds = _generate(tmp_path, "mild")

    assert ds.PatientID != "P000001"
    assert len(ds.PatientID) > 64
    assert len(ds.AccessionNumber) > 16
    assert ds.StudyDate == "INVALID_DATE"
    assert "StudyInstanceUID" in ds
    assert "PixelData" in ds


def test_moderate_drops_type1_and_corrupts_uid(tmp_path) -> None:
    random.seed(1)
    ds = _generate(tmp_path, "moderate")

    for keyword in ("StudyInstanceUID", "SeriesInstanceUID", "Modality", "SOPInstanceUID"):
        assert keyword not in ds
    assert "PixelData" in ds


def test_severe_drops_pixel_data_and_required_tags(tmp_path) -> None:
    random.seed(1)
    ds = _generate(tmp_path, "severe")

    assert "PixelData" not in ds
    for keyword in ("StudyInstanceUID", "SeriesInstanceUID", "Modality", "PatientID"):
        assert keyword not in ds


@pytest.mark.parametrize(
    ("uid", "name", "implicit", "little"),
    [
        ("1.2.840.10008.1.2", "Implicit VR Little Endian", True, True),
        ("1.2.840.10008.1.2.1", "Explicit VR Little Endian", False, True),
    ],
)
def test_mild_writes_in_every_transfer_syntax(tmp_path, uid, name, implicit, little) -> None:
    from app.core import TransferSyntaxConfig

    random.seed(1)
    config = _make_config(tmp_path=tmp_path).model_copy(
        update={
            "abnormal": AbnormalConfig(level="mild"),
            "transfer_syntax": TransferSyntaxConfig(
                uid=uid, name=name, is_implicit_vr=implicit, is_little_endian=little
            ),
        }
    )

    output_dir = StudyGeneratorService().generate(config=config)

    (path,) = output_dir.glob("*.dcm")
    ds = pydicom.dcmread(path, force=True)
    assert ds.StudyDate == "INVALID_DATE"
    assert str(ds.InstanceNumber) == "NOT_A_NUMBER"


@pytest.mark.parametrize("level", ["mild", "moderate", "severe"])
def test_abnormal_does_not_write_retired_big_endian(tmp_path, level) -> None:
    # 廃止の Explicit VR Big Endian（PS3.5 A.3）は、異常のデータの約束（docs/spec/02 の
    # AbnormalGenerator）に無いので、異常のデータでも作らない（札 Q-2026-10-21-02）
    from app.core import DICOMValidationError, TransferSyntaxConfig

    config = _make_config(tmp_path=tmp_path).model_copy(
        update={
            "abnormal": AbnormalConfig(level=level),
            "transfer_syntax": TransferSyntaxConfig(
                uid="1.2.840.10008.1.2.2",
                name="Explicit VR Big Endian",
                is_implicit_vr=False,
                is_little_endian=False,
            ),
        }
    )

    with pytest.raises(DICOMValidationError, match="retired"):
        StudyGeneratorService().generate(config=config)
    assert not (tmp_path / "output").exists()


def test_read_study_uid_tolerates_missing_tag(tmp_path) -> None:
    from app.modality.service import ModalityService

    random.seed(1)
    ds = _generate(tmp_path, "moderate")
    path = tmp_path / "output" / "x.dcm"
    path.parent.mkdir(exist_ok=True)
    pydicom.dcmwrite(path, ds, enforce_file_format=True)

    assert ModalityService._read_study_uid([str(path)]) == ""


def test_invalid_level_in_config_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AbnormalConfig(level="extreme")


def test_job_yaml_level_is_used(tmp_path) -> None:
    import yaml

    job_file = tmp_path / "job.yaml"
    _write_job_yaml(job_file, tmp_path / "out")
    job = yaml.safe_load(job_file.read_text())
    job["abnormal"] = {"level": "mild"}
    job_file.write_text(yaml.safe_dump(job))
    args = argparse.Namespace(
        job_file=str(job_file), output=None, dry_run=False, quiet=True, abnormal_level=None
    )

    assert generate_command(args) == 0

    (path,) = (tmp_path / "out").glob("*.dcm")
    assert pydicom.dcmread(path, force=True).StudyDate == "INVALID_DATE"


def test_cli_level_overrides_job_yaml(tmp_path) -> None:
    import yaml

    job_file = tmp_path / "job.yaml"
    _write_job_yaml(job_file, tmp_path / "out")
    job = yaml.safe_load(job_file.read_text())
    job["abnormal"] = {"level": "mild"}
    job_file.write_text(yaml.safe_dump(job))
    args = argparse.Namespace(
        job_file=str(job_file), output=None, dry_run=False, quiet=True, abnormal_level="none"
    )

    assert generate_command(args) == 0

    (path,) = (tmp_path / "out").glob("*.dcm")
    assert pydicom.dcmread(path, force=True).StudyDate == "20240115"


def test_cli_level_without_job_section(tmp_path) -> None:
    job_file = tmp_path / "job.yaml"
    _write_job_yaml(job_file, tmp_path / "out")
    args = argparse.Namespace(
        job_file=str(job_file), output=None, dry_run=False, quiet=True, abnormal_level="mild"
    )

    assert generate_command(args) == 0

    (path,) = (tmp_path / "out").glob("*.dcm")
    assert pydicom.dcmread(path, force=True).StudyDate == "INVALID_DATE"


def test_cli_invalid_level_in_job_yaml_is_validation_error(tmp_path) -> None:
    import yaml

    job_file = tmp_path / "job.yaml"
    _write_job_yaml(job_file, tmp_path / "out")
    job = yaml.safe_load(job_file.read_text())
    job["abnormal"] = {"level": "extreme"}
    job_file.write_text(yaml.safe_dump(job))
    args = argparse.Namespace(
        job_file=str(job_file), output=None, dry_run=True, quiet=True, abnormal_level=None
    )

    with pytest.raises(ValidationError):
        generate_command(args)


def test_quick_command_passes_level(tmp_path) -> None:
    args = argparse.Namespace(
        patient="P000001",
        modality="ct_generic",
        series=1,
        images="1",
        output=str(tmp_path / "out"),
        accession_number="ACC1",
        study_date="20240115",
        hospital=None,
        profile=None,
        pixel_mode="simple_text",
        abnormal_level="mild",
    )

    assert quick_command(args) == 0

    (path,) = (tmp_path / "out").glob("*.dcm")
    assert pydicom.dcmread(path, force=True).StudyDate == "INVALID_DATE"


def test_parser_accepts_abnormal_level() -> None:
    parser = _create_parser()

    generate_args = parser.parse_args(["generate", "job.yaml", "--abnormal-level", "severe"])
    quick_args = parser.parse_args(
        ["quick", "-p", "P1", "-m", "ct_generic", "-s", "1", "-i", "1", "-o", "out"]
    )

    assert generate_args.abnormal_level == "severe"
    assert quick_args.abnormal_level == "none"


def test_parser_rejects_invalid_abnormal_level(capsys) -> None:
    parser = _create_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["generate", "job.yaml", "--abnormal-level", "extreme"])

    assert exc_info.value.code == 2
    assert "extreme" in capsys.readouterr().err
