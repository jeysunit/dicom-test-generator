"""線量の報告の作り方（画面・SR・両方）をルーチンの行に当てる（ADR-0031）."""

from __future__ import annotations

import pytest

from app.core.routine import (
    DOSE_SR_DESCRIPTION,
    Routine,
    apply_dose_report_mode,
    routine_series_configs,
)
from app.services.routine_loader import RoutineLoaderService


def _routine() -> Routine:
    return Routine.model_validate(
        {
            "name": "x",
            "label": "x",
            "modality": "CT",
            "protocol_name": "X",
            "default": True,
            "series": [
                {"kind": "localizer", "description": "Scout", "images": 1},
                {"kind": "axial", "description": "AX", "images": 60},
                {"kind": "dose_report", "description": "Dose Report", "images": 1,
                 "series_number": 900},
            ],
        }
    )


def _kinds(routine: Routine) -> list[str]:
    return [series.kind for series in routine.series]


def test_screen_changes_nothing() -> None:
    routine = _routine()

    assert apply_dose_report_mode(routine, [0, 1, 2], [1, 60, 1], "screen") == (
        routine,
        [0, 1, 2],
        [1, 60, 1],
    )


def test_sr_replaces_the_dose_screen_and_keeps_its_series_number() -> None:
    routine, keep, images = apply_dose_report_mode(_routine(), [0, 1, 2], [1, 60, 1], "sr")

    assert _kinds(routine) == ["localizer", "axial", "dose_sr"]
    assert (keep, images) == ([0, 1, 2], [1, 60, 1])
    assert routine.series[2].description == DOSE_SR_DESCRIPTION
    assert routine.series[2].series_number == 900


def test_both_adds_the_sr_after_the_dose_screen() -> None:
    routine, keep, images = apply_dose_report_mode(_routine(), [0, 1, 2], [1, 60, 1], "both")

    assert _kinds(routine) == ["localizer", "axial", "dose_report", "dose_sr"]
    assert (keep, images) == ([0, 1, 2, 3], [1, 60, 1, 1])
    assert routine.series[3].series_number is None  # 続きの番号


def test_both_inserts_before_the_following_series_and_shifts_their_positions() -> None:
    base = _routine()
    routine = base.model_copy(
        update={"series": [base.series[2], base.series[0], base.series[1]]}
    )

    shifted, keep, images = apply_dose_report_mode(routine, [1, 2, 0], [5, 7, 1], "both")

    assert _kinds(shifted) == ["dose_report", "dose_sr", "localizer", "axial"]
    # 撮る順は元の keep のまま：Scout(5)、AX(7)、Dose Report(1)、その SR(1)
    assert keep == [2, 3, 0, 1]
    assert images == [5, 7, 1, 1]


def test_a_dose_screen_that_is_not_taken_is_left_alone() -> None:
    routine, keep, images = apply_dose_report_mode(_routine(), [0, 1], [1, 60], "both")

    assert _kinds(routine) == ["localizer", "axial", "dose_report"]
    assert (keep, images) == ([0, 1], [1, 60])


def test_other_modalities_are_left_alone() -> None:
    mr = RoutineLoaderService().get("mr_head")

    assert apply_dose_report_mode(mr, [0], [1], "both") == (mr, [0], [1])


@pytest.mark.parametrize("mode", ["sr", "both"])
def test_bundled_ct_routines_get_a_sr_series_config(mode: str) -> None:
    routine = RoutineLoaderService().get("ct_chest_plain")
    keep = list(range(len(routine.series)))
    images = [1] * len(keep)

    moded, new_keep, new_images = apply_dose_report_mode(routine, keep, images, mode)
    configs = routine_series_configs(
        moded, list(range(1, len(new_keep) + 1)), new_keep, new_images
    )

    sr = [config for config in configs if config.kind == "dose_sr"]
    assert len(sr) == 1
    assert sr[0].modality == "SR"
    assert sr[0].series_description == DOSE_SR_DESCRIPTION
    assert [c.kind for c in configs].count("dose_report") == (1 if mode == "both" else 0)
