"""CT・MR・PT の Body Part Examined と Laterality（ADR-0037・spec/06 の 5.6）."""

from __future__ import annotations

from pathlib import Path

import pydicom
import pytest
from pydantic import ValidationError as PydanticValidationError

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
from app.core.models import DEFAULT_BODY_PART, PAIRED_BODY_PARTS
from app.core.routine import Routine, apply_dose_report_mode, routine_series_configs
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

TEMPLATES = {"CT": "ct_generic", "MR": "mr_generic", "PT": "petct_generic"}

# spec/06 の 5.6 の表。ルーチン名 → (body_part, laterality)
EXPECTED = {
    "ct_chest_plain": ("CHEST", None),
    "ct_chest_abdomen_pelvis_contrast": ("CHESTABDPELVIS", None),
    "ct_abdomen_pelvis": ("ABDOMENPELVIS", None),
    "ct_liver_dynamic": ("ABDOMEN", None),
    "ct_coronary_cta": ("HEART", None),
    "ct_head_plain": ("HEAD", None),
    "mr_head": ("HEAD", None),
    "ct_lumbar_spine": ("LSPINE", None),
    "mr_lumbar_spine": ("LSPINE", None),
    "mr_knee": ("KNEE", "R"),
    "mr_shoulder": ("SHOULDER", "R"),
    "pt_whole_body": ("WHOLEBODY", None),
    "pt_whole_body_pet_first": ("WHOLEBODY", None),
}


def _config(
    tmp_path: Path, series_list: list[SeriesConfig], template: str
) -> GenerationConfig:
    return GenerationConfig(
        job_name="body-part",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P1",
            patient_name=PatientName(alphabetic="TEST^BODY"),
            birth_date="19800101",
            sex="F",
            weight=60.0,
            size=165.0,
        ),
        study=StudyConfig(
            accession_number="A1",
            study_date="20261101",
            study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template=template,
        pixel_spec=PixelSpecSimple(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )


def _generate_routine(tmp_path: Path, name: str) -> list[pydicom.Dataset]:
    """ルーチンの全シリーズを 1 枚ずつ作る。線量の画面は画面と SR の両方にする."""
    routine = RoutineLoaderService().get(name)
    keep = list(range(len(routine.series)))
    routine, keep, images = apply_dose_report_mode(
        routine, keep, [1] * len(keep), "both"
    )
    series_list = routine_series_configs(
        routine, [index + 1 for index in range(len(keep))], keep, images
    )
    output = StudyGeneratorService().generate(
        _config(tmp_path, series_list, TEMPLATES[routine.modality])
    )
    return [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]


def test_bundled_routines_match_the_spec_table() -> None:
    loader = RoutineLoaderService()
    actual = {
        routine.name: (routine.body_part, routine.laterality)
        for routine in loader.list_routines()
        if routine.modality in TEMPLATES
    }

    assert actual == EXPECTED


def test_bundled_routines_of_every_imaging_modality_declare_a_body_part() -> None:
    routines = [
        routine
        for routine in RoutineLoaderService().list_routines()
        if routine.modality in ("CT", "MR", "PT", "CR", "DX")
    ]

    assert routines
    assert [routine.name for routine in routines if routine.body_part is None] == []


def test_laterality_follows_table_l5_pairedness() -> None:
    for name, (body_part, laterality) in EXPECTED.items():
        assert (laterality is not None) == (body_part in PAIRED_BODY_PARTS), name


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_every_ct_mr_pt_image_carries_the_routine_body_part(
    tmp_path: Path, name: str
) -> None:
    body_part, laterality = EXPECTED[name]

    datasets = _generate_routine(tmp_path, name)

    images = [ds for ds in datasets if ds.Modality != "SR"]
    assert images
    for ds in images:
        assert ds.BodyPartExamined == body_part
        assert ds.get("Laterality") == laterality
    # 線量の報告（SR）は General Series の Body Part Examined も Laterality も持たない
    for ds in datasets:
        if ds.Modality == "SR":
            assert "BodyPartExamined" not in ds
            assert "Laterality" not in ds


def test_dose_report_screen_carries_the_body_part(tmp_path: Path) -> None:
    datasets = _generate_routine(tmp_path, "ct_chest_plain")

    screens = [ds for ds in datasets if ds.SOPClassUID == "1.2.840.10008.5.1.4.1.1.7"]
    assert len(screens) == 1
    assert screens[0].BodyPartExamined == "CHEST"


@pytest.mark.parametrize(("modality", "template"), sorted(TEMPLATES.items()))
def test_a_manual_series_gets_the_default_body_part(
    tmp_path: Path, modality: str, template: str
) -> None:
    kind = {"CT": "axial", "MR": "acquisition", "PT": "pet_ac"}[modality]
    series = SeriesConfig(series_number=1, num_images=2, kind=kind, modality=modality)

    output = StudyGeneratorService().generate(_config(tmp_path, [series], template))

    datasets = [pydicom.dcmread(path) for path in sorted(output.glob("*.dcm"))]
    assert datasets
    for ds in datasets:
        assert ds.BodyPartExamined == DEFAULT_BODY_PART == "CHEST"
        assert "Laterality" not in ds


def test_series_config_checks_body_part_and_laterality_for_ct_mr_pt() -> None:
    SeriesConfig(
        series_number=1,
        num_images=1,
        modality="MR",
        kind="acquisition",
        body_part="KNEE",
        laterality="L",
    )
    with pytest.raises(PydanticValidationError, match="needs laterality"):
        SeriesConfig(
            series_number=1,
            num_images=1,
            modality="MR",
            kind="acquisition",
            body_part="SHOULDER",
        )
    with pytest.raises(PydanticValidationError, match="not a paired structure"):
        SeriesConfig(
            series_number=1,
            num_images=1,
            modality="CT",
            body_part="CHEST",
            laterality="R",
        )
    with pytest.raises(PydanticValidationError, match="not allowed for CT"):
        SeriesConfig(
            series_number=1,
            num_images=1,
            modality="CT",
            body_part="KNEE",
            laterality="B",
        )
    with pytest.raises(PydanticValidationError, match="not for SR"):
        SeriesConfig(
            series_number=1,
            num_images=1,
            modality="SR",
            kind="dose_sr",
            body_part="CHEST",
        )


def test_cr_and_dx_keep_their_six_body_parts() -> None:
    with pytest.raises(PydanticValidationError, match="not allowed for DX"):
        SeriesConfig(
            series_number=1,
            num_images=1,
            modality="DX",
            kind="projection",
            body_part="HEAD",
        )


def test_ct_routine_with_a_paired_body_part_needs_laterality() -> None:
    fields = {
        "name": "ct_x",
        "label": "x",
        "modality": "CT",
        "protocol_name": "X",
        "series": [{"kind": "axial", "description": "AX", "images": 3}],
    }

    with pytest.raises(PydanticValidationError, match="needs laterality"):
        Routine.model_validate({**fields, "body_part": "SHOULDER"})
    with pytest.raises(PydanticValidationError, match="laterality needs body_part"):
        Routine.model_validate({**fields, "laterality": "R"})
    assert Routine.model_validate({**fields, "body_part": "HEAD"}).body_part == "HEAD"
