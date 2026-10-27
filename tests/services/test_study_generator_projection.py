"""CR・DX の画像の作成（docs/spec/06 の 5.5・ADR-0034）."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom
import pytest

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecCTRealistic,
    PixelSpecPhantom,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.exceptions import DICOMValidationError, ProfileMismatchError
from app.core.phantom import marker_bounds, xray_phantom_values
from app.core.projection import CR_IMAGE_STORAGE, DX_IMAGE_STORAGE_FOR_PRESENTATION
from app.core.routine import routine_series_configs
from app.services.profile_loader import ProfileLoaderService
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

PHANTOM_MARKS = {
    "Manufacturer": "DTG SYNTHETIC",
    "ManufacturerModelName": "DTG SYNTHETIC",
    "ImageComments": "SYNTHETIC TEST DATA",
    "BurnedInAnnotation": "NO",
    "RecognizableVisualFeatures": "NO",
}


def _routine_series(name: str) -> list[SeriesConfig]:
    routine = RoutineLoaderService().get(name)
    count = len(routine.series)
    return routine_series_configs(
        routine, list(range(1, count + 1)), list(range(count)),
        [series.images for series in routine.series],
    )


def _config(tmp_path: Path, series_list, template: str, pixel_spec=None, profile=None):
    return GenerationConfig(
        job_name="xray",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^XRAY"),
            birth_date="19800101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A1", study_date="20261028", study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template=template,
        device_profile=profile,
        pixel_spec=pixel_spec or PixelSpecPhantom(),
        transfer_syntax=TransferSyntaxConfig(
            uid="1.2.840.10008.1.2.1", name="Explicit VR Little Endian", is_implicit_vr=False
        ),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _generate(config: GenerationConfig, service: StudyGeneratorService | None = None):
    service = service or StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    output = service.generate(config)
    return [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]


def _pixels(ds: pydicom.Dataset) -> np.ndarray:
    return np.frombuffer(ds.PixelData, dtype=np.uint16).reshape(int(ds.Rows), int(ds.Columns))


def test_cr_chest_makes_one_series_per_view(tmp_path) -> None:
    datasets = _generate(_config(tmp_path, _routine_series("cr_chest"), "cr_generic"))

    assert [(int(ds.SeriesNumber), ds.ViewPosition) for ds in datasets] == [(1, "PA"), (2, "LL")]
    assert len({ds.SeriesInstanceUID for ds in datasets}) == 2
    for ds in datasets:
        assert ds.SOPClassUID == CR_IMAGE_STORAGE
        assert ds.file_meta.MediaStorageSOPClassUID == CR_IMAGE_STORAGE
        assert ds.Modality == "CR"
        assert ds.BodyPartExamined == "CHEST"
        assert "FrameOfReferenceUID" not in ds
        assert "ImagePositionPatient" not in ds
        assert (ds.Rows, ds.Columns) == (1248, 1024)
        for keyword, value in PHANTOM_MARKS.items():
            assert ds.get(keyword) == value, keyword


def test_dx_chest_makes_one_series_with_two_images(tmp_path) -> None:
    datasets = _generate(_config(tmp_path, _routine_series("dx_chest"), "dx_generic"))

    assert len(datasets) == 2
    assert len({ds.SeriesInstanceUID for ds in datasets}) == 1
    assert [ds.ViewPosition for ds in datasets] == ["PA", "LL"]
    for ds in datasets:
        assert ds.SOPClassUID == DX_IMAGE_STORAGE_FOR_PRESENTATION
        assert ds.PresentationIntentType == "FOR PRESENTATION"
        assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY", ""]
        assert ds.ImageLaterality == "U"
        assert ds.AnatomicRegionSequence[0].CodeValue == "816094009"
        assert "FrameOfReferenceUID" not in ds


@pytest.mark.parametrize(
    ("routine", "template", "keyword", "value"),
    [
        ("cr_knee", "cr_generic", "Laterality", "R"),
        ("dx_knee", "dx_generic", "ImageLaterality", "R"),
        ("dx_hand", "dx_generic", "ImageLaterality", "R"),
        ("dx_lumbar_spine", "dx_generic", "ImageLaterality", "U"),
    ],
)
def test_laterality_follows_the_routine(tmp_path, routine, template, keyword, value) -> None:
    datasets = _generate(
        _config(tmp_path, _routine_series(routine), template, pixel_spec=PixelSpecSimple())
    )

    assert {ds.get(keyword) for ds in datasets} == {value}


def test_phantom_projection_has_three_values_and_a_moving_marker(tmp_path) -> None:
    datasets = _generate(_config(tmp_path, _routine_series("dx_chest"), "dx_generic"))
    values = xray_phantom_values(12)

    for index, ds in enumerate(datasets):
        pixels = _pixels(ds)
        assert set(np.unique(pixels).tolist()) == {values.background, values.shape, values.marker}
        r0, r1, c0, c1 = marker_bounds(1248, 1024, index, 2)
        assert (pixels[r0:r1, c0:c1] == values.marker).all()
        assert pixels[624, 512] == values.shape  # 体の楕円の中央
        assert pixels[0, 0] == values.background
    assert not np.array_equal(_pixels(datasets[0]), _pixels(datasets[1]))


def test_monochrome1_template_inverts_the_phantom(tmp_path, monkeypatch) -> None:
    service = StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    original = service._template_loader.merge_templates

    def monochrome1(**kwargs):
        template = original(**kwargs)
        return {**template, "xray_image": {"photometric_interpretation": "MONOCHROME1"}}

    monkeypatch.setattr(service._template_loader, "merge_templates", monochrome1)
    (pa, _lateral) = _generate(
        _config(tmp_path, _routine_series("dx_chest"), "dx_generic"), service
    )
    values = xray_phantom_values(12)

    assert pa.PhotometricInterpretation == "MONOCHROME1"
    assert pa.PresentationLUTShape == "INVERSE"
    assert pa.PixelIntensityRelationshipSign == 1
    pixels = _pixels(pa)
    assert pixels[0, 0] == 4095 - values.background
    assert pixels[624, 512] == 4095 - values.shape


def test_invalid_photometric_interpretation_in_the_template(tmp_path, monkeypatch) -> None:
    service = StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    original = service._template_loader.merge_templates
    monkeypatch.setattr(
        service._template_loader,
        "merge_templates",
        lambda **kwargs: {**original(**kwargs), "xray_image": {"photometric_interpretation": "RGB"}},
    )

    with pytest.raises(DICOMValidationError, match="photometric_interpretation"):
        _generate(_config(tmp_path, _routine_series("cr_chest"), "cr_generic"), service)


def test_dx_without_phantom_still_writes_burned_in_annotation_no(tmp_path) -> None:
    datasets = _generate(
        _config(tmp_path, _routine_series("dx_chest"), "dx_generic", PixelSpecCTRealistic())
    )

    for ds in datasets:
        assert ds.BurnedInAnnotation == "NO"
        assert "ImageComments" not in ds
        assert ds.Manufacturer == "DTG Synthetic"
        pixels = _pixels(ds)
        assert int(pixels.min()) == 0
        assert int(pixels.max()) == 4095


def test_cr_without_phantom_has_no_fake_marks(tmp_path) -> None:
    (ds, _) = _generate(
        _config(tmp_path, _routine_series("cr_chest"), "cr_generic", PixelSpecCTRealistic())
    )

    for keyword in ("BurnedInAnnotation", "RecognizableVisualFeatures", "ImageComments"):
        assert keyword not in ds
    assert ds.ManufacturerModelName == "DTG Synthetic CR"


@pytest.mark.parametrize(
    ("template", "profile", "model"),
    [
        ("cr_generic", "dtg_synthetic_cr", "DTG Synthetic CR Reader"),
        ("dx_generic", "dtg_synthetic_dx", "DTG Synthetic DX Flat Panel"),
    ],
)
def test_example_profiles(tmp_path, template, profile, model) -> None:
    routine = "cr_chest" if template == "cr_generic" else "dx_chest"
    plain = _generate(
        _config(tmp_path / "plain", _routine_series(routine), template, PixelSpecSimple(), profile)
    )
    phantom = _generate(
        _config(tmp_path / "phantom", _routine_series(routine), template, profile=profile)
    )

    assert {ds.ManufacturerModelName for ds in plain} == {model}
    # 偽物の印はプロファイルより優先し、ほかの装置の値はプロファイルのまま
    assert {ds.ManufacturerModelName for ds in phantom} == {"DTG SYNTHETIC"}
    assert {ds.StationName for ds in phantom} == {f"DTG{template[:2].upper()}01"}
    assert all("FrameOfReferenceUID" not in ds for ds in plain + phantom)


@pytest.mark.parametrize(
    ("template", "keyword", "value"),
    [
        ("dx_generic", "RescaleSlope", "2"),
        ("dx_generic", "PresentationLUTShape", "INVERSE"),
        ("dx_generic", "ImageLaterality", "L"),
        ("cr_generic", "Laterality", "L"),
    ],
)
def test_profile_cannot_set_values_fixed_by_the_standard(
    tmp_path, template, keyword, value
) -> None:
    """Rescale・Presentation LUT Shape・左右などは規格とルーチンが決める（spec/06 の 5.5）."""
    modality = template[:2].upper()
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "fixed.yaml").write_text(
        "\n".join(
            [
                "schema_version: 1",
                'name: "fixed"',
                "device:",
                f'  modality: "{modality}"',
                '  manufacturer: "X"',
                '  manufacturers_model_name: "X"',
                "storage:",
                f'  sop_classes: ["{CR_IMAGE_STORAGE if modality == "CR" else DX_IMAGE_STORAGE_FOR_PRESENTATION}"]',
                '  transfer_syntaxes: ["1.2.840.10008.1.2.1"]',
                "attributes:",
                "  set:",
                f'    {keyword}: "{value}"',
            ]
        ),
        encoding="utf-8",
    )
    service = StudyGeneratorService(
        profile_loader=ProfileLoaderService(environ={"DTG_PROFILE_DIRS": str(profile_dir)})
    )
    routine = "cr_knee" if modality == "CR" else "dx_knee"

    with pytest.raises(ProfileMismatchError, match=keyword):
        _generate(_config(tmp_path, _routine_series(routine), template, profile="fixed"), service)


def test_manual_series_with_the_cr_template_is_a_chest_pa(tmp_path) -> None:
    series = [SeriesConfig(series_number=1, num_images=2)]

    datasets = _generate(_config(tmp_path, series, "cr_generic", PixelSpecSimple()))

    assert [(ds.Modality, ds.ViewPosition, ds.BodyPartExamined) for ds in datasets] == [
        ("CR", "PA", "CHEST"),
        ("CR", "PA", "CHEST"),
    ]


def test_ct_kind_with_the_dx_template_is_refused(tmp_path) -> None:
    series = [SeriesConfig(series_number=1, num_images=1, kind="coronal")]

    with pytest.raises(DICOMValidationError, match="DX template"):
        _generate(_config(tmp_path, series, "dx_generic"))
