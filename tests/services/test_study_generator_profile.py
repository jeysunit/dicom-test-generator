"""装置のプロファイルを重ねた生成の試験（spec/13 の 4）."""

from __future__ import annotations

import os

import pydicom
import pytest
import yaml

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    ProfileMismatchError,
    ProfileNotFoundError,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.services.profile_loader import PROFILE_DIRS_ENV, ProfileLoaderService
from app.services.study_generator import StudyGeneratorService

EXPLICIT_LE = TransferSyntaxConfig(
    uid="1.2.840.10008.1.2.1",
    name="Explicit VR Little Endian",
    is_implicit_vr=False,
    is_little_endian=True,
)


def _config(tmp_path, **overrides) -> GenerationConfig:
    values = {
        "job_name": "profile_test",
        "output_dir": str(tmp_path / "output"),
        "patient": Patient(
            patient_id="P000001",
            patient_name=PatientName(
                alphabetic="YAMADA^TARO",
                ideographic="山田^太郎",
                phonetic="ヤマダ^タロウ",
            ),
            birth_date="19800115",
            sex="M",
        ),
        "study": StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        "series_list": [SeriesConfig(series_number=1, num_images=1)],
        "modality_template": "ct_generic",
        "device_profile": "dtg_synthetic_ct",
        "pixel_spec": PixelSpecSimple(),
        "transfer_syntax": EXPLICIT_LE,
        "character_set": CharacterSetConfig(),
    }
    values.update(overrides)
    return GenerationConfig(**values)


def _service(environ: dict | None = None) -> StudyGeneratorService:
    return StudyGeneratorService(
        profile_loader=ProfileLoaderService(environ=environ or {})
    )


def _read_single(output_dir) -> pydicom.Dataset:
    files = sorted(output_dir.glob("*.dcm"))
    assert len(files) == 1
    return pydicom.dcmread(files[0])


def test_profile_identity_private_tags_and_charset_are_written(tmp_path) -> None:
    output_dir = _service().generate(_config(tmp_path))
    ds = _read_single(output_dir)

    assert ds.Manufacturer == "DTG Synthetic"
    assert ds.ManufacturerModelName == "DTG Synthetic CT 64"
    assert list(ds.SoftwareVersions) == ["DTG-CT 2.1.0", "RECON 5.3"]
    assert ds.DeviceSerialNumber == "DTG000123"
    assert ds.StationName == "DTGCT01"
    assert ds.file_meta.ImplementationVersionName == "DTG_CT_210"
    assert ds.file_meta.TransferSyntaxUID == "1.2.840.10008.1.2.1"
    assert list(ds.SpecificCharacterSet) == ["ISO 2022 IR 13", "ISO 2022 IR 87"]
    assert str(ds.PatientName) == "YAMADA^TARO=山田^太郎=ヤマダ^タロウ"
    assert ds.BodyPartExamined == "CHEST"
    assert ds.OperatorsName == ""
    assert "SliceLocation" not in ds
    block = ds.private_block(0x0009, "DTG SYNTHETIC CT 01")
    assert block[0x10].value == "SCAN-MODE-A"
    assert block[0x11].value == 3


def test_without_profile_output_is_unchanged(tmp_path) -> None:
    config = _config(
        tmp_path,
        device_profile=None,
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )
    ds = _read_single(_service().generate(config))

    assert ds.Manufacturer == "DTG Synthetic"
    assert ds.ManufacturerModelName == "DTG Synthetic CT"
    assert "DeviceSerialNumber" not in ds
    assert "SliceLocation" in ds


def test_hospital_charset_and_station_win_but_identity_does_not_change(tmp_path) -> None:
    config = _config(tmp_path, hospital_template="hospital_a")
    ds = _read_single(_service().generate(config))

    assert list(ds.SpecificCharacterSet) == ["ISO 2022 IR 6", "ISO 2022 IR 87"]
    assert ds.StationName == "CT_A_01"
    assert ds.InstitutionName == "A Hospital"
    assert ds.Manufacturer == "DTG Synthetic"
    assert ds.ManufacturerModelName == "DTG Synthetic CT 64"


def test_profile_from_external_directory(tmp_path) -> None:
    external = tmp_path / "private_profiles"
    external.mkdir()
    data = yaml.safe_load(
        (ProfileLoaderService.default_examples_dir() / "dtg_synthetic_ct.yaml")
        .read_text(encoding="utf-8")
    )
    data["name"] = "site_ct"
    data["device"]["manufacturer"] = "Site Maker"
    (external / "site_ct.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True), encoding="utf-8"
    )
    service = _service({PROFILE_DIRS_ENV: os.pathsep.join([str(external)])})

    ds = _read_single(service.generate(_config(tmp_path, device_profile="site_ct")))

    assert ds.Manufacturer == "Site Maker"


def test_transfer_syntax_not_supported_by_device_is_rejected(tmp_path) -> None:
    config = _config(
        tmp_path,
        transfer_syntax=TransferSyntaxConfig(
            uid="1.2.840.10008.1.2.2",
            name="Explicit VR Big Endian",
            is_implicit_vr=False,
            is_little_endian=False,
        ),
    )

    with pytest.raises(ProfileMismatchError, match="1.2.840.10008.1.2.2"):
        _service().generate(config)
    assert not list((tmp_path / "output").glob("*.dcm"))


def test_character_set_not_supported_by_device_is_rejected(tmp_path, monkeypatch) -> None:
    service = _service()
    original = service._template_loader.load_hospital_template

    def fake_hospital(name):
        if name == "utf8_site":
            return {"overrides": {"character_set": {"specific_character_set": "ISO_IR 100"}}}
        return original(name)

    monkeypatch.setattr(service._template_loader, "load_hospital_template", fake_hospital)

    with pytest.raises(ProfileMismatchError, match="ISO_IR 100"):
        service.generate(_config(tmp_path, hospital_template="utf8_site"))


def test_modality_mismatch_is_rejected(tmp_path, monkeypatch) -> None:
    service = _service()
    original = service._template_loader.load_modality_template

    def fake_modality(name):
        template = dict(original("ct_generic"))
        template["info"] = dict(template["info"], modality="MR")
        return template

    monkeypatch.setattr(service._template_loader, "load_modality_template", fake_modality)

    with pytest.raises(ProfileMismatchError, match="MR"):
        service.generate(_config(tmp_path))


def test_unknown_profile_is_rejected(tmp_path) -> None:
    with pytest.raises(ProfileNotFoundError):
        _service().generate(_config(tmp_path, device_profile="no_such_device"))
