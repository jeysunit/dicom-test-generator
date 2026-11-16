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


def _quick(tmp_path, *extra: str):
    return _create_parser().parse_args(
        [
            "quick", "-p", "P000001", "-m", "ct_generic", "-s", "1", "-i", "2",
            "-o", str(tmp_path / "out"), *extra,
        ]
    )


def test_job_selects_burn_in_only_with_phantom() -> None:
    config = GenerationConfig.model_validate(_job({"mode": "phantom", "burn_in": True}))

    assert config.pixel_spec.burn_in is True
    assert GenerationConfig.model_validate(_job({"mode": "phantom"})).pixel_spec.burn_in is False


@pytest.mark.parametrize("mode", ["simple_text", "ct_realistic"])
@pytest.mark.parametrize("value", [True, False])
def test_job_rejects_burn_in_with_other_modes(mode, value) -> None:
    with pytest.raises(ValueError, match="burn_in"):
        GenerationConfig.model_validate(_job({"mode": mode, "burn_in": value}))


def test_quick_burn_in_writes_yes(tmp_path) -> None:
    assert quick_command(_quick(tmp_path, "--pixel-mode", "phantom", "--burn-in")) == 0

    datasets = [pydicom.dcmread(path) for path in sorted((tmp_path / "out").glob("*.dcm"))]
    assert {ds.BurnedInAnnotation for ds in datasets} == {"YES"}


@pytest.mark.parametrize("flags", [("--pixel-mode", "phantom"), ("--pixel-mode", "phantom", "--no-burn-in")])
def test_quick_without_burn_in_writes_no(tmp_path, flags) -> None:
    assert quick_command(_quick(tmp_path, *flags)) == 0

    datasets = [pydicom.dcmread(path) for path in sorted((tmp_path / "out").glob("*.dcm"))]
    assert {ds.BurnedInAnnotation for ds in datasets} == {"NO"}


@pytest.mark.parametrize("flag", ["--burn-in", "--no-burn-in"])
@pytest.mark.parametrize("mode", ["simple_text", "ct_realistic"])
def test_quick_rejects_burn_in_with_other_modes(tmp_path, mode, flag) -> None:
    with pytest.raises(ConfigurationError):
        quick_command(_quick(tmp_path, "--pixel-mode", mode, flag))

    assert not list((tmp_path / "out").glob("*.dcm"))
