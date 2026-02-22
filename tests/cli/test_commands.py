from __future__ import annotations

import argparse

from app.cli.commands import generate_command, validate_command, version_command


def _write_job_yaml(path, output_dir):
    import yaml

    job = {
        "job_name": "test",
        "output_dir": str(output_dir),
        "patient": {
            "patient_id": "P000001",
            "patient_name": {"alphabetic": "TEST^PATIENT"},
            "birth_date": "20000101",
            "sex": "M",
        },
        "study": {
            "accession_number": "ACC000001",
            "study_date": "20240115",
            "study_time": "120000",
            "num_series": 1,
        },
        "series_list": [{"series_number": 1, "num_images": 1}],
        "modality_template": "fujifilm_scenaria_view_ct",
        "pixel_spec": {"mode": "simple_text"},
        "transfer_syntax": {
            "uid": "1.2.840.10008.1.2",
            "name": "Implicit VR Little Endian",
            "is_implicit_vr": True,
            "is_little_endian": True,
        },
        "character_set": {
            "specific_character_set": "",
            "use_ideographic": False,
            "use_phonetic": False,
        },
    }
    with open(path, "w") as f:
        yaml.safe_dump(job, f)


def test_version_command(capsys) -> None:
    args = argparse.Namespace()

    exit_code = version_command(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Version: 1.1.0" in captured.out


def test_validate_command_success(tmp_path) -> None:
    job_file = tmp_path / "job.yaml"
    output_dir = tmp_path / "output"
    _write_job_yaml(job_file, output_dir)
    args = argparse.Namespace(job_file=str(job_file))

    exit_code = validate_command(args)

    assert exit_code == 0


def test_validate_command_invalid_yaml(tmp_path) -> None:
    job_file = tmp_path / "invalid.yaml"
    job_file.write_text("job_name: [invalid", encoding="utf-8")
    args = argparse.Namespace(job_file=str(job_file))

    exit_code = validate_command(args)

    assert exit_code == 2


def test_generate_command_dry_run(tmp_path) -> None:
    job_file = tmp_path / "job.yaml"
    output_dir = tmp_path / "output"
    _write_job_yaml(job_file, output_dir)
    args = argparse.Namespace(
        job_file=str(job_file),
        output=None,
        dry_run=True,
        quiet=False,
    )

    exit_code = generate_command(args)

    assert exit_code == 0
    if output_dir.exists():
        assert not list(output_dir.glob("*.dcm"))


def test_generate_command_success(tmp_path) -> None:
    job_file = tmp_path / "job.yaml"
    output_dir = tmp_path / "output"
    _write_job_yaml(job_file, output_dir)
    args = argparse.Namespace(
        job_file=str(job_file),
        output=None,
        dry_run=False,
        quiet=True,
    )

    exit_code = generate_command(args)

    assert exit_code == 0
    assert len(list(output_dir.glob("*.dcm"))) == 1


def test_validate_command_pydantic_validation_error_returns_4(tmp_path) -> None:
    """Pydantic バリデーション失敗時に終了コード 4 を返す."""
    import yaml

    job_file = tmp_path / "bad_schema.yaml"
    job = {
        "job_name": "test",
        "output_dir": str(tmp_path / "output"),
        "patient": {
            "patient_id": "P000001",
            "patient_name": {"alphabetic": "TEST^PATIENT"},
            "birth_date": "INVALID_DATE",
            "sex": "M",
        },
        "study": {
            "accession_number": "ACC000001",
            "study_date": "20240115",
            "study_time": "120000",
            "num_series": 1,
        },
        "series_list": [{"series_number": 1, "num_images": 1}],
        "modality_template": "fujifilm_scenaria_view_ct",
        "pixel_spec": {"mode": "simple_text"},
        "transfer_syntax": {
            "uid": "1.2.840.10008.1.2",
            "name": "Implicit VR Little Endian",
            "is_implicit_vr": True,
            "is_little_endian": True,
        },
        "character_set": {
            "specific_character_set": "",
            "use_ideographic": False,
            "use_phonetic": False,
        },
    }
    with open(job_file, "w") as f:
        yaml.safe_dump(job, f)

    args = argparse.Namespace(job_file=str(job_file))
    exit_code = validate_command(args)

    assert exit_code == 4


def test_generate_command_nonexistent_file_returns_3(tmp_path) -> None:
    """存在しないファイル指定で終了コード 3 (I/Oエラー) を返す."""
    args = argparse.Namespace(
        job_file=str(tmp_path / "does_not_exist.yaml"),
        output=None,
        dry_run=False,
        quiet=True,
    )

    exit_code = generate_command(args)

    assert exit_code == 3
