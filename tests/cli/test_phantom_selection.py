"""図形の方式（phantom）を Job と quick で選ぶ試験（docs/spec/04・07）."""

from __future__ import annotations

import pydicom
import pytest

from app.cli.commands import quick_command
from app.cli.main import _create_parser
from app.core import GenerationConfig, PixelSpecPhantom
from app.core.exceptions import ConfigurationError


def _job(mode: dict) -> dict:
    return {
        "job_name": "phantom",
        "output_dir": "out",
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
        "modality_template": "ct_generic",
        "pixel_spec": mode,
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


def test_job_selects_phantom() -> None:
    config = GenerationConfig.model_validate(_job({"mode": "phantom", "width": 256}))

    assert isinstance(config.pixel_spec, PixelSpecPhantom)
    assert config.pixel_spec.width == 256
    assert config.pixel_spec.bits_stored == 12


def test_job_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError):
        GenerationConfig.model_validate(_job({"mode": "anatomy"}))


def test_quick_with_phantom_writes_phantom_images(tmp_path) -> None:
    args = _create_parser().parse_args(
        [
            "quick", "-p", "P000001", "-m", "ct_generic", "-s", "1", "-i", "3",
            "-o", str(tmp_path / "out"), "--pixel-mode", "phantom",
        ]
    )

    assert quick_command(args) == 0

    datasets = [pydicom.dcmread(path) for path in sorted((tmp_path / "out").glob("*.dcm"))]
    assert len(datasets) == 3
    assert {ds.Manufacturer for ds in datasets} == {"DTG SYNTHETIC"}
    assert {ds.ImageComments for ds in datasets} == {"SYNTHETIC TEST DATA"}


def test_quick_still_rejects_an_unknown_mode(tmp_path) -> None:
    args = _create_parser().parse_args(
        [
            "quick", "-p", "P000001", "-m", "ct_generic", "-s", "1", "-i", "1",
            "-o", str(tmp_path / "out"), "--pixel-mode", "anatomy",
        ]
    )

    with pytest.raises(ConfigurationError):
        quick_command(args)
