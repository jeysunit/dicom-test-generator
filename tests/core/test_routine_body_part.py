"""CR・DX のルーチンの部位と左右（ADR-0034・exam-routines の spec）."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.models import SeriesConfig
from app.core.routine import Routine, routine_series_configs
from app.services.routine_loader import RoutineLoaderService


def _routine(modality: str, **fields: object) -> Routine:
    views = [["PA"]] if modality == "CR" else [["PA", "LL"]]
    return Routine.model_validate(
        {
            "name": f"{modality.lower()}_x",
            "label": "x",
            "modality": modality,
            "protocol_name": "X",
            "series": [
                {"description": "X", "images": len(view), "views": view} for view in views
            ],
            **fields,
        }
    )


@pytest.mark.parametrize(
    ("modality", "fields"),
    [
        ("CR", {"body_part": "KNEE", "laterality": "R"}),
        ("CR", {"body_part": "HAND", "laterality": "L"}),
        ("CR", {"body_part": "CHEST"}),
        ("DX", {"body_part": "KNEE", "laterality": "B"}),
        ("DX", {"body_part": "HAND", "laterality": "L"}),
        ("DX", {"body_part": "ABDOMEN"}),
    ],
)
def test_valid_body_part_and_laterality(modality: str, fields: dict) -> None:
    routine = _routine(modality, **fields)

    assert routine.body_part == fields["body_part"]
    assert routine.laterality == fields.get("laterality")


@pytest.mark.parametrize(
    ("modality", "fields", "message"),
    [
        ("CR", {"body_part": "KNEE", "laterality": "B"}, "not allowed for CR"),
        ("CR", {"body_part": "KNEE"}, "needs laterality"),
        ("DX", {"body_part": "HAND"}, "needs laterality"),
        ("DX", {"body_part": "CHEST", "laterality": "R"}, "not a paired structure"),
        ("CR", {"body_part": "LSPINE", "laterality": "L"}, "not a paired structure"),
        ("CR", {}, "needs body_part"),
        ("DX", {"laterality": "R"}, "needs body_part"),
        ("DX", {"body_part": "HEAD"}, "body_part"),
    ],
)
def test_invalid_body_part_and_laterality(modality: str, fields: dict, message: str) -> None:
    with pytest.raises(PydanticValidationError, match=message):
        _routine(modality, **fields)


def test_body_part_is_only_for_cr_and_dx() -> None:
    with pytest.raises(PydanticValidationError, match="only for CR and DX"):
        Routine.model_validate(
            {
                "name": "ct_x",
                "label": "x",
                "modality": "CT",
                "protocol_name": "X",
                "body_part": "CHEST",
                "series": [{"kind": "axial", "description": "AX", "images": 3}],
            }
        )


def test_bundled_cr_and_dx_routines_carry_body_part_and_laterality() -> None:
    loader = RoutineLoaderService()

    assert (loader.get("dx_knee").body_part, loader.get("dx_knee").laterality) == ("KNEE", "R")
    assert (loader.get("cr_hand").body_part, loader.get("cr_hand").laterality) == ("HAND", "R")
    assert (loader.get("cr_chest").body_part, loader.get("cr_chest").laterality) == (
        "CHEST",
        None,
    )
    for name in ("abdomen", "lumbar_spine", "cervical_spine"):
        for modality in ("cr", "dx"):
            routine = loader.get(f"{modality}_{name}")
            assert routine.body_part is not None
            assert routine.laterality is None


def test_cr_routine_series_configs_are_one_view_per_series() -> None:
    routine = RoutineLoaderService().get("cr_chest")

    configs = routine_series_configs(routine, [1, 2], [0, 1], [1, 1])

    assert [(c.modality, c.kind, c.view_positions) for c in configs] == [
        ("CR", "projection", ["PA"]),
        ("CR", "projection", ["LL"]),
    ]
    assert {c.body_part for c in configs} == {"CHEST"}


def test_dx_routine_series_configs_keep_all_views_in_one_series() -> None:
    routine = RoutineLoaderService().get("dx_knee")

    (series,) = routine_series_configs(routine, [1], [0], [2])

    assert series.modality == "DX"
    assert series.view_positions == ["AP", "LL"]
    assert (series.body_part, series.laterality) == ("KNEE", "R")


def test_series_config_checks_cr_views_and_laterality() -> None:
    with pytest.raises(PydanticValidationError, match="exactly one view"):
        SeriesConfig(
            series_number=1, num_images=2, modality="CR", kind="projection",
            view_positions=["PA", "LL"], body_part="CHEST",
        )
    with pytest.raises(PydanticValidationError, match="not allowed for CR"):
        SeriesConfig(
            series_number=1, num_images=1, modality="CR", kind="projection",
            body_part="KNEE", laterality="B",
        )
    with pytest.raises(PydanticValidationError, match="not an DX series kind"):
        SeriesConfig(series_number=1, num_images=1, modality="DX", kind="axial")
