"""ルーチンの図形の部位・MR の強調・CT の造影の相（exam-routines の spec）."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.routine import Routine, routine_series_configs
from app.services.routine_loader import RoutineLoaderService

ROUTINE_PHANTOMS = {
    "ct_head_plain": "head",
    "ct_chest_plain": "chest",
    "ct_chest_abdomen_pelvis_contrast": "trunk",
    "ct_abdomen_pelvis": "abdomen",
    "ct_liver_dynamic": "abdomen",
    "ct_coronary_cta": "chest",
    "ct_lumbar_spine": "spine",
    "mr_head": "head",
    "mr_lumbar_spine": "spine",
    "mr_knee": "limb",
    "mr_shoulder": "limb",
    "cr_chest": "chest",
    "cr_abdomen": "abdomen",
    "cr_lumbar_spine": "spine",
    "cr_cervical_spine": "spine",
    "cr_knee": "limb",
    "cr_hand": "limb",
    "dx_chest": "chest",
    "dx_abdomen": "abdomen",
    "dx_lumbar_spine": "spine",
    "dx_cervical_spine": "spine",
    "dx_knee": "limb",
    "dx_hand": "limb",
}
MR_WEIGHTINGS = {
    "mr_head": [None, "DWI", "ADC", "T2STAR", "T1", "T2", "FLAIR", "MRA"],
    "mr_lumbar_spine": [None, "T1", "T2", "T2"],
    "mr_knee": [None, "PD", "T2", "PD", "T1"],
    "mr_shoulder": [None, "T2", "T2", "T1", "T1"],
}


def _ct_routine(**series: object) -> Routine:
    return Routine.model_validate(
        {
            "name": "ct_x",
            "label": "x",
            "modality": "CT",
            "protocol_name": "X",
            "series": [{"kind": "axial", "description": "AX", "images": 1, **series}],
        }
    )


def _configs(routine: Routine):
    count = len(routine.series)
    return routine_series_configs(
        routine, list(range(1, count + 1)), list(range(count)),
        [series.images for series in routine.series],
    )


def test_the_bundled_routines_carry_their_phantom() -> None:
    routines = {routine.name: routine for routine in RoutineLoaderService().list_routines()}
    assert {name: routines[name].phantom for name in ROUTINE_PHANTOMS} == ROUTINE_PHANTOMS
    # PET/CT と US は部位の図形を書かない（PT のシリーズは図形にしない）
    for routine in routines.values():
        if routine.modality in ("PT", "US"):
            assert routine.phantom is None, routine.name


def test_the_bundled_mr_routines_carry_their_weighting() -> None:
    loader = RoutineLoaderService()
    for name, expected in MR_WEIGHTINGS.items():
        assert [series.weighting for series in loader.get(name).series] == expected, name


def test_the_bundled_contrast_phases() -> None:
    loader = RoutineLoaderService()
    liver = {s.description: s.phase for s in loader.get("ct_liver_dynamic").series}
    assert liver["Arterial 3mm"] == "arterial"
    assert liver["Portal 3mm"] == "portal"
    assert liver["Delayed 3mm"] == "delayed"
    assert liver["AX 5mm"] is None
    cta = {s.description: s.phase for s in loader.get("ct_coronary_cta").series}
    assert cta["CTA 0.5mm +C"] == "arterial"


def test_the_spec_scenario_values() -> None:
    loader = RoutineLoaderService()
    assert loader.get("ct_head_plain").phantom == "head"
    assert loader.get("mr_head").phantom == "head"
    knee = loader.get("dx_knee")
    assert (knee.body_part, knee.laterality) == ("KNEE", "R")
    flair = next(s for s in loader.get("mr_head").series if s.description == "FLAIR")
    assert flair.weighting == "FLAIR"


def test_series_configs_carry_the_phantom_weighting_and_phase() -> None:
    loader = RoutineLoaderService()
    mr = _configs(loader.get("mr_head"))
    assert {config.phantom for config in mr} == {"head"}
    assert [config.weighting for config in mr] == MR_WEIGHTINGS["mr_head"]
    liver = _configs(loader.get("ct_liver_dynamic"))
    assert [config.phase for config in liver] == [
        None, None, "arterial", "portal", "delayed", "portal", None,
    ]
    dx = _configs(loader.get("dx_chest"))
    assert [config.phantom for config in dx] == ["chest"]


def test_phase_without_contrast_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="contrast"):
        _ct_routine(phase="arterial")


def test_phase_with_contrast_is_accepted() -> None:
    routine = _ct_routine(contrast=True, phase="delayed")
    assert _configs(routine)[0].phase == "delayed"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"phantom": "pelvis"}, "phantom"),
        ({"series": [{"kind": "axial", "description": "AX", "images": 1, "phase": "venous",
                      "contrast": True}]}, "phase"),
    ],
)
def test_unknown_values_are_rejected(fields, message) -> None:
    data = {
        "name": "ct_x", "label": "x", "modality": "CT", "protocol_name": "X",
        "series": [{"kind": "axial", "description": "AX", "images": 1}],
        **fields,
    }
    with pytest.raises(PydanticValidationError, match=message):
        Routine.model_validate(data)


def test_weighting_on_a_ct_series_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="weighting"):
        _ct_routine(weighting="T1")


def test_unknown_mr_weighting_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="weighting"):
        Routine.model_validate(
            {
                "name": "mr_x", "label": "x", "modality": "MR", "protocol_name": "X",
                "series": [{
                    "kind": "acquisition", "description": "X", "images": 1,
                    "plane": "axial", "slice_thickness": 3.0, "weighting": "T3",
                }],
            }
        )
