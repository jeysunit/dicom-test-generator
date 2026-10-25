"""PET/CT のルーチンの形と、線量の報告の作り方との組み合わせ（ADR-0030）."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.routine import (
    PETCTRoutineSeries,
    Routine,
    apply_dose_report_mode,
    check_routine_set,
    routine_series_configs,
)
from app.services.routine_loader import RoutineLoaderService


def _routine(series: list[dict]) -> Routine:
    return Routine.model_validate(
        {
            "name": "pt_x",
            "label": "x",
            "modality": "PT",
            "protocol_name": "X",
            "default": True,
            "series": series,
        }
    )


def test_bundled_routines_have_ct_and_pt_series_in_the_declared_order() -> None:
    loader = RoutineLoaderService()
    ct_first = loader.get("pt_whole_body")
    pet_first = loader.get("pt_whole_body_pet_first")

    assert ct_first.modality == pet_first.modality == "PT"
    assert [(s.modality, s.kind) for s in ct_first.series] == [
        ("CT", "localizer"),
        ("CT", "axial"),
        ("PT", "pet_ac"),
        ("PT", "pet_nac"),
        ("CT", "dose_report"),
    ]
    assert [s.modality for s in pet_first.series] == ["PT", "PT", "CT", "CT", "CT"]
    assert ct_first.default and not pet_first.default
    assert pet_first.keywords == []


def test_there_is_exactly_one_default_routine_for_pt() -> None:
    check_routine_set(RoutineLoaderService().list_routines())


def test_series_configs_set_the_modality_of_each_series() -> None:
    routine = RoutineLoaderService().get("pt_whole_body")
    keep = list(range(len(routine.series)))

    configs = routine_series_configs(routine, [1, 2, 3, 4, 5], keep, [1, 2, 2, 2, 1])

    assert [(c.modality, c.kind) for c in configs] == [
        ("CT", "localizer"),
        ("CT", "axial"),
        ("PT", "pet_ac"),
        ("PT", "pet_nac"),
        ("CT", "dose_report"),
    ]
    assert configs[2].slice_thickness == configs[2].slice_spacing == 3.27
    assert configs[1].slice_spacing == 3.0


@pytest.mark.parametrize("mode", ["sr", "both"])
def test_dose_report_mode_works_on_a_pet_ct_routine(mode: str) -> None:
    routine = RoutineLoaderService().get("pt_whole_body")
    keep = list(range(len(routine.series)))

    moded, new_keep, new_images = apply_dose_report_mode(routine, keep, [1] * 5, mode)
    configs = routine_series_configs(
        moded, list(range(1, len(new_keep) + 1)), new_keep, new_images
    )

    assert isinstance(moded.series[-1], PETCTRoutineSeries)
    assert [c.modality for c in configs][-1] == "SR"
    assert [c.kind for c in configs].count("dose_report") == (1 if mode == "both" else 0)


@pytest.mark.parametrize(
    ("series", "message"),
    [
        ({"modality": "PT", "kind": "axial", "description": "x", "images": 1}, "not a PT"),
        ({"modality": "CT", "kind": "pet_ac", "description": "x", "images": 1}, "needs modality PT"),
        (
            {"modality": "PT", "kind": "pet_ac", "description": "x", "images": 1,
             "contrast": True},
            "contrast",
        ),
        (
            {"modality": "CT", "kind": "axial", "description": "x", "images": 1,
             "views": ["frontal"]},
            "only for a localizer",
        ),
        (
            {"modality": "CT", "kind": "localizer", "description": "x", "images": 2,
             "views": ["frontal"]},
            "views has 1 entries",
        ),
        ({"modality": "MR", "kind": "axial", "description": "x", "images": 1}, "modality"),
    ],
)
def test_bad_pet_ct_series_are_refused(series: dict, message: str) -> None:
    with pytest.raises(PydanticValidationError, match=message):
        _routine([series])
