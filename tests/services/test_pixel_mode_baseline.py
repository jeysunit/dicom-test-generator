"""既定の画素の方式の画素と属性が変わらないことの試験.

図形の方式（phantom）を足す前の `ct_realistic` と `simple_text` の値を固定する
（openspec の change add-modality-synthetic-images の design.md「既定を変えないこと」）。
UID（VR が UI）は生成のたびに変わるので比べない。`simple_text` の画素は
SOP Instance UID の文字なので、属性だけを比べる。
"""

from __future__ import annotations

import hashlib

import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecCTRealistic,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.services.profile_loader import ProfileLoaderService
from app.services.study_generator import StudyGeneratorService

EXPLICIT_LE = TransferSyntaxConfig(
    uid="1.2.840.10008.1.2.1",
    name="Explicit VR Little Endian",
    is_implicit_vr=False,
    is_little_endian=True,
)

CT_SERIES = [
    SeriesConfig(series_number=1, num_images=2, kind="localizer", views=["frontal", "lateral"]),
    SeriesConfig(series_number=2, num_images=3, slice_spacing=5.0),
    SeriesConfig(series_number=3, num_images=2, kind="coronal", slice_spacing=3.0),
    SeriesConfig(series_number=4, num_images=2, kind="sagittal", slice_spacing=3.0),
    SeriesConfig(series_number=5, num_images=1, kind="dose_report"),
]
MR_SERIES = [
    SeriesConfig(
        series_number=1, num_images=3, kind="localizer", modality="MR", plane="three_plane"
    ),
    SeriesConfig(
        series_number=2, num_images=2, kind="acquisition", modality="MR", plane="sagittal"
    ),
    SeriesConfig(
        series_number=3, num_images=2, kind="acquisition", modality="MR", plane="coronal"
    ),
    SeriesConfig(
        series_number=4, num_images=3, kind="acquisition", modality="MR", plane="axial"
    ),
]

# 変更の前（main 6f8cbfb）の値
EXPECTED = {
    ("ct_generic", "ct_realistic"): (
        "dfb936264874d423ea40567e791bf4598d90843d867d23d5eb2b83eec7afe71e"
    ),
    ("ct_generic", "simple_text"): (
        "0a7f4f5ffeb4142bc2789378c37d7602302c87fe0a0780d3e91498734de0d226"
    ),
    ("mr_generic", "ct_realistic"): (
        "8926d8e004d86f4ff5d385bb1c4c203852ef365f24bfe8c21997c7396ea9020d"
    ),
    ("mr_generic", "simple_text"): (
        "4f759dd2b9928e4c5f733d19da6e98b9e3cd389cfe13ed883eb1977e1ad62805"
    ),
}


def _config(tmp_path, template: str, pixel_spec) -> GenerationConfig:
    return GenerationConfig(
        job_name="baseline",
        output_dir=str(tmp_path / "output"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="YAMADA^TARO"),
            birth_date="19800115",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="ACC000001",
            study_date="20240115",
            study_time="120000",
            num_series=1,
        ),
        series_list=CT_SERIES if template == "ct_generic" else MR_SERIES,
        modality_template=template,
        device_profile="dtg_synthetic_ct" if template == "ct_generic" else "dtg_synthetic_mr",
        pixel_spec=pixel_spec,
        transfer_syntax=EXPLICIT_LE,
        character_set=CharacterSetConfig(),
    )


def _digest(datasets: list[pydicom.Dataset], with_pixels: bool) -> str:
    digest = hashlib.sha256()
    for ds in datasets:
        for element in ds.iterall():
            if element.VR == "UI":
                continue
            if element.keyword == "PixelData":
                if with_pixels:
                    digest.update(element.value)
                continue
            digest.update(f"{element.tag}{element.VR}{element.value!r}".encode())
    return digest.hexdigest()


@pytest.mark.parametrize(("template", "mode"), sorted(EXPECTED))
def test_default_pixel_modes_keep_their_values(tmp_path, template: str, mode: str) -> None:
    pixel_spec = PixelSpecCTRealistic() if mode == "ct_realistic" else PixelSpecSimple()
    service = StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    output_dir = service.generate(_config(tmp_path, template, pixel_spec))
    datasets = [pydicom.dcmread(path) for path in sorted(output_dir.glob("*.dcm"))]

    assert _digest(datasets, with_pixels=mode == "ct_realistic") == EXPECTED[(template, mode)]
