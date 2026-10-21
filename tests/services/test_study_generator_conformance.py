"""生成したファイルを読み戻して規格への適合を確かめる試験（PS3.3 C.8.2.1・PS3.5 6.2・8）."""

from __future__ import annotations

import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecCTRealistic,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.services.study_generator import StudyGeneratorService

DS_MAX_LENGTH = 16


def _config(tmp_path, pattern: str = "gradient") -> GenerationConfig:
    return GenerationConfig(
        job_name="conformance",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^PATIENT"),
            birth_date="20000101",
            sex="M",
            size=165.7,
            weight=62.3,
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        series_list=[
            SeriesConfig(series_number=1, num_images=4, slice_thickness=0.1, slice_spacing=0.1)
        ],
        modality_template="ct_generic",
        pixel_spec=PixelSpecCTRealistic(width=64, height=64, pattern=pattern),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _read_all(tmp_path, **kwargs) -> list[pydicom.Dataset]:
    output_dir = StudyGeneratorService().generate(_config(tmp_path, **kwargs))
    return [pydicom.dcmread(path) for path in sorted(output_dir.glob("*.dcm"))]


def test_generated_ct_has_required_attributes(tmp_path) -> None:
    for ds in _read_all(tmp_path):
        assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY", "AXIAL"]
        assert ds.PatientPosition == "HFS"
        assert "PositionReferenceIndicator" in ds


@pytest.mark.parametrize("pattern", ["gradient", "circle", "noise"])
def test_pixels_read_back_without_sign_flip(tmp_path, pattern: str) -> None:
    # 12 ビットの符号ありで読み戻しても負にならない（HU は -1024 以上）
    for ds in _read_all(tmp_path, pattern=pattern):
        pixels = ds.pixel_array
        assert int(pixels.min()) >= 0
        assert int(pixels.max()) <= 2047
        hu = pixels.astype(int) * int(ds.RescaleSlope) + int(ds.RescaleIntercept)
        assert int(hu.min()) >= -1024


def test_decimal_strings_in_file_fit_sixteen_bytes(tmp_path) -> None:
    datasets = _read_all(tmp_path)

    for ds in datasets:
        for element in ds:
            if element.VR != "DS" or element.value is None:
                continue
            values = element.value if element.VM > 1 else [element.value]
            for value in values:
                assert len(str(value)) <= DS_MAX_LENGTH, element.keyword
    assert [str(ds.SliceLocation) for ds in datasets] == ["0.0", "0.1", "0.2", "0.3"]
    assert str(datasets[0].PatientSize) == "1.657"
