"""CR Image・DX Image For Presentation の必須の属性（PS3.3 A.2・A.26。ADR-0034）."""

from __future__ import annotations

import numpy as np
import pytest
from pydicom.dataset import FileMetaDataset

from app.core.exceptions import DICOMBuildError
from app.core.generator import DICOMBuilder
from app.core.models import (
    InstanceConfig,
    Patient,
    PatientName,
    SeriesConfig,
    StudyConfig,
    UIDContext,
)
from app.core.projection import (
    CR_IMAGE_STORAGE,
    DX_IMAGE_STORAGE_FOR_PRESENTATION,
    PROJECTION_COLUMNS,
    PROJECTION_ROWS,
    keep_projection_shape,
)

SOP_UID = "2.25.1"
CONTEXT = UIDContext(
    study_instance_uid="2.25.2",
    frame_of_reference_uid="2.25.3",
    implementation_class_uid="2.25.4",
    instance_creator_uid="2.25.5",
)
PATIENT = Patient(
    patient_id="P1", patient_name=PatientName(alphabetic="TEST^XRAY"), birth_date="19800101",
    sex="M",
)
STUDY = StudyConfig(accession_number="A1", study_date="20261028", study_time="090000", num_series=1)


def _meta(sop_class: str) -> FileMetaDataset:
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = sop_class
    meta.MediaStorageSOPInstanceUID = SOP_UID
    meta.TransferSyntaxUID = "1.2.840.10008.1.2"
    return meta


def _series(modality: str, views: list[str], body_part: str = "CHEST", laterality=None):
    return SeriesConfig(
        series_number=1, num_images=len(views), modality=modality, kind="projection",
        view_positions=views, body_part=body_part, laterality=laterality,
    )


def _build(series: SeriesConfig, index: int = 0, photometric: str = "MONOCHROME2", pixels=None):
    sop_class = CR_IMAGE_STORAGE if series.modality == "CR" else DX_IMAGE_STORAGE_FOR_PRESENTATION
    if pixels is None:
        pixels = np.full((PROJECTION_ROWS, PROJECTION_COLUMNS), 100, dtype=np.uint16)
    return DICOMBuilder().build_projection_image(
        patient=PATIENT,
        study_config=STUDY,
        series_config=series,
        instance_config=InstanceConfig(instance_number=index + 1),
        uid_context=CONTEXT,
        pixel_data=pixels,
        file_meta=_meta(sop_class),
        sop_instance_uid=SOP_UID,
        series_instance_uid="2.25.6",
        photometric_interpretation=photometric,
    )


# Frame of Reference・Image Plane のモジュールの属性。CR・DX の IOD には無い
PLANE_KEYWORDS = (
    "FrameOfReferenceUID",
    "ImagePositionPatient",
    "ImageOrientationPatient",
    "PixelSpacing",
    "SliceLocation",
    "PatientPosition",
)


def test_cr_image_has_the_required_attributes() -> None:
    ds = _build(_series("CR", ["PA"]))

    assert ds.SOPClassUID == CR_IMAGE_STORAGE
    assert ds.Modality == "CR"
    # CR Series Module（Type 2）と CR Image Module（Type 1）
    assert ds.BodyPartExamined == "CHEST"
    assert ds.ViewPosition == "PA"
    assert ds.PhotometricInterpretation == "MONOCHROME2"
    # General Image：Patient Orientation（Type 2C）
    assert list(ds.PatientOrientation) == ["L", "F"]
    assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY"]
    # Image Pixel
    assert (ds.Rows, ds.Columns) == (1248, 1024)
    assert (ds.BitsAllocated, ds.BitsStored, ds.HighBit, ds.PixelRepresentation) == (16, 12, 11, 0)
    assert [float(v) for v in ds.ImagerPixelSpacing] == [0.342, 0.342]
    assert ds.AnatomicRegionSequence[0].CodeValue == "816094009"
    for keyword in (*PLANE_KEYWORDS, "PresentationIntentType", "ImageLaterality", "Laterality"):
        assert keyword not in ds, keyword
    # CR の Burned In Annotation は General Image の Type 3。図形の方式でなければ書かない
    assert "BurnedInAnnotation" not in ds


def test_cr_paired_body_part_has_series_laterality() -> None:
    ds = _build(_series("CR", ["LL"], body_part="KNEE", laterality="R"))

    assert ds.Laterality == "R"
    assert "ImageLaterality" not in ds
    assert list(ds.PatientOrientation) == ["P", "F"]
    assert ds.AnatomicRegionSequence[0].CodeValue == "72696002"


def test_dx_image_has_the_required_attributes() -> None:
    series = _series("DX", ["PA", "LL"])
    ds = _build(series)

    assert ds.SOPClassUID == DX_IMAGE_STORAGE_FOR_PRESENTATION
    assert ds.Modality == "DX"
    assert ds.PresentationIntentType == "FOR PRESENTATION"
    # Image Type の Value 3 は長さ 0
    assert list(ds.ImageType) == ["ORIGINAL", "PRIMARY", ""]
    assert ds.ImageLaterality == "U"
    region = ds.AnatomicRegionSequence[0]
    assert (region.CodeValue, region.CodingSchemeDesignator, region.CodeMeaning) == (
        "816094009", "SCT", "Chest",
    )
    assert ds.PixelIntensityRelationship == "LOG"
    assert ds.PixelIntensityRelationshipSign == -1
    assert (ds.RescaleIntercept, ds.RescaleSlope, ds.RescaleType) == (0, 1, "US")
    assert ds.PresentationLUTShape == "IDENTITY"
    assert ds.LossyImageCompression == "00"
    assert ds.BurnedInAnnotation == "NO"
    assert ds.DetectorType == ""
    assert [float(v) for v in ds.ImagerPixelSpacing] == [0.342, 0.342]
    assert ds.ViewPosition == "PA"
    assert ds.ViewCodeSequence[0].CodeValue == "272479007"
    assert ds.PositionerType == ""
    assert len(ds.AcquisitionContextSequence) == 0
    # VOI LUT（FOR PRESENTATION なので必須）
    assert (float(ds.WindowCenter), float(ds.WindowWidth)) == (2048.0, 4096.0)
    for keyword in (*PLANE_KEYWORDS, "ModalityLUTSequence", "Laterality"):
        assert keyword not in ds, keyword

    lateral = _build(series, index=1)
    assert lateral.ViewPosition == "LL"
    assert lateral.ViewCodeSequence[0].CodeValue == "399173006"
    assert list(lateral.PatientOrientation) == ["P", "F"]


@pytest.mark.parametrize(("body_part", "laterality"), [("KNEE", "R"), ("KNEE", "L"), ("HAND", "B")])
def test_dx_image_laterality(body_part: str, laterality: str) -> None:
    ds = _build(_series("DX", ["AP"], body_part=body_part, laterality=laterality))

    assert ds.ImageLaterality == laterality
    assert "Laterality" not in ds


def test_oblique_view_has_no_view_code() -> None:
    ds = _build(_series("DX", ["RLO"], body_part="HAND", laterality="R"))

    assert ds.ViewPosition == "RLO"
    assert "ViewCodeSequence" not in ds
    assert list(ds.PatientOrientation) == ["L", "F"]


def test_monochrome1_inverts_pixels_and_presentation() -> None:
    pixels = np.zeros((PROJECTION_ROWS, PROJECTION_COLUMNS), dtype=np.uint16)
    pixels[0, 0] = 205
    pixels[0, 1] = 3276

    mono2 = _build(_series("DX", ["PA"]), pixels=pixels)
    mono1 = _build(_series("DX", ["PA"]), photometric="MONOCHROME1", pixels=pixels)

    stored2 = np.frombuffer(mono2.PixelData, dtype=np.uint16)
    stored1 = np.frombuffer(mono1.PixelData, dtype=np.uint16)
    assert mono1.PhotometricInterpretation == "MONOCHROME1"
    assert mono1.PresentationLUTShape == "INVERSE"
    assert mono1.PixelIntensityRelationshipSign == 1
    assert np.array_equal(stored1, 4095 - stored2)
    assert stored1[:3].tolist() == [4095 - 205, 4095 - 3276, 4095]


def test_pixels_out_of_the_12_bit_range_are_refused() -> None:
    pixels = np.full((PROJECTION_ROWS, PROJECTION_COLUMNS), 4096, dtype=np.uint16)

    with pytest.raises(DICOMBuildError, match="Bits Stored 12"):
        _build(_series("CR", ["PA"]), pixels=pixels)


def test_text_pixels_are_stretched_to_12_bits() -> None:
    pixels = np.zeros((PROJECTION_ROWS, PROJECTION_COLUMNS), dtype=np.uint8)
    pixels[0, 0] = 255

    ds = _build(_series("CR", ["PA"]), pixels=pixels)

    assert int(np.frombuffer(ds.PixelData, dtype=np.uint16).max()) == 4095


def test_unknown_photometric_interpretation_is_refused() -> None:
    with pytest.raises(DICOMBuildError, match="Photometric Interpretation"):
        _build(_series("CR", ["PA"]), photometric="RGB")


def test_sop_class_must_match_the_series() -> None:
    series = _series("DX", ["PA"])
    with pytest.raises(DICOMBuildError, match="does not match"):
        DICOMBuilder().build_projection_image(
            patient=PATIENT, study_config=STUDY, series_config=series,
            instance_config=InstanceConfig(instance_number=1), uid_context=CONTEXT,
            pixel_data=np.zeros((4, 4), dtype=np.uint16), file_meta=_meta(CR_IMAGE_STORAGE),
            sop_instance_uid=SOP_UID, series_instance_uid="2.25.6",
        )


def test_keep_projection_shape_removes_planes_and_restores_required() -> None:
    series = _series("DX", ["PA"])
    ds = _build(series)
    ds.FrameOfReferenceUID = "2.25.9"
    ds.ImagePositionPatient = [0, 0, 0]
    del ds.BurnedInAnnotation
    ds.PresentationIntentType = ""
    ds.DetectorType = "SCINTILLATOR"  # 装置のプロファイルが set で書いた値は残す

    keep_projection_shape(ds, series, 0, "MONOCHROME2")

    assert "FrameOfReferenceUID" not in ds
    assert "ImagePositionPatient" not in ds
    assert ds.BurnedInAnnotation == "NO"
    assert ds.PresentationIntentType == "FOR PRESENTATION"
    assert ds.DetectorType == "SCINTILLATOR"
