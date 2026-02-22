from __future__ import annotations

from unittest.mock import MagicMock

import pydicom

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.services.study_generator import StudyGeneratorService


def _make_config(tmp_path, num_series=1, images_per_series=None):
    if images_per_series is None:
        images_per_series = [1]
    return GenerationConfig(
        job_name="test",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^PATIENT"),
            birth_date="20000101",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=num_series,
        ),
        series_list=[
            SeriesConfig(series_number=i + 1, num_images=n)
            for i, n in enumerate(images_per_series)
        ],
        modality_template="fujifilm_scenaria_view_ct",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="",
            use_ideographic=False,
            use_phonetic=False,
        ),
    )


def test_generate_minimal(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(config=config)
    files = list(output_dir.glob("*.dcm"))

    assert output_dir == tmp_path / "output"
    assert len(files) == 1


def test_generate_multiple_series(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=2, images_per_series=[2, 2])

    output_dir = service.generate(config=config)
    files = list(output_dir.glob("*.dcm"))

    assert output_dir == tmp_path / "output"
    assert len(files) == 4


def test_progress_callback(tmp_path) -> None:
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])
    progress_callback = MagicMock()

    service.generate(config=config, progress_callback=progress_callback)

    progress_callback.assert_called_once_with(1, 1)


def test_generated_file_has_dicm_preamble(tmp_path) -> None:
    """生成ファイルが DICOM File Format (128-byte preamble + DICM) であることを検証."""
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(config=config)
    dcm_file = next(output_dir.glob("*.dcm"))

    with open(dcm_file, "rb") as f:
        preamble_and_magic = f.read(132)

    assert len(preamble_and_magic) == 132
    assert preamble_and_magic[128:132] == b"DICM"


def test_sop_class_uid_consistency(tmp_path) -> None:
    """File Meta の MediaStorageSOPClassUID と Dataset の SOPClassUID が一致することを検証."""
    service = StudyGeneratorService()
    config = _make_config(tmp_path=tmp_path, num_series=1, images_per_series=[1])

    output_dir = service.generate(config=config)
    dcm_file = next(output_dir.glob("*.dcm"))

    ds = pydicom.dcmread(str(dcm_file))
    media_storage_sop_class = str(ds.file_meta.MediaStorageSOPClassUID)
    sop_class = str(ds.SOPClassUID)

    assert media_storage_sop_class == sop_class


def test_japanese_patient_name_roundtrip(tmp_path) -> None:
    """日本語患者名の書き出し→再読込で PatientName と SpecificCharacterSet が保持されることを検証."""
    config = GenerationConfig(
        job_name="test_jp",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(
                alphabetic="TANAKA^HIROSHI",
                ideographic="田中^博",
                phonetic="タナカ^ヒロシ",
            ),
            birth_date="19980312",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        series_list=[SeriesConfig(series_number=1, num_images=1)],
        modality_template="fujifilm_scenaria_view_ct",
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(),
    )

    service = StudyGeneratorService()
    output_dir = service.generate(config=config)
    dcm_file = next(output_dir.glob("*.dcm"))

    ds = pydicom.dcmread(str(dcm_file))

    assert str(ds.PatientName) == "TANAKA^HIROSHI=田中^博=タナカ^ヒロシ"
    assert ds.SpecificCharacterSet == ["ISO 2022 IR 6", "ISO 2022 IR 87"]
