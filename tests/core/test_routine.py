"""撮影のルーチンの形・当て方・シリーズ番号（ADR-0025）."""

from __future__ import annotations

import pytest
from pydantic import ValidationError as PydanticValidationError

from app.core.exceptions import ValidationError
from app.core.routine import (
    Routine,
    assign_series_numbers,
    check_routine_set,
    ct_series_configs,
    match_routine,
)


def _ct(name: str, keywords: list[str], default: bool = False, **series: object) -> Routine:
    return Routine.model_validate(
        {
            "name": name,
            "label": name,
            "modality": "CT",
            "protocol_name": name.upper(),
            "default": default,
            "keywords": keywords,
            "series": [{"kind": "axial", "description": "AX", "images": 3, **series}],
        }
    )


ROUTINES = [
    _ct("chest", ["胸部", "CHEST"], default=True),
    _ct("cap", ["胸腹部", "CHEST ABDOMEN"]),
    _ct("abdomen", ["腹部", "ABDOMEN"]),
    _ct("head", ["頭部", "HEAD"]),
]


@pytest.mark.parametrize(
    ("fields", "expected"),
    [
        (["胸部単純CT"], "chest"),
        (["胸腹部造影CT"], "cap"),  # 長い語が勝つ
        (["ＣＨＥＳＴ ct"], "chest"),  # NFKC・大文字と小文字を区別しない
        (["頭部・胸部CT"], "head"),  # 同じ長さなら前に出てくる語
        (["腹部CT", "胸腹部"], "abdomen"),  # 先の欄で当たれば後の欄は見ない
        (["単純CT", "単純CT", "HEAD"], "head"),  # 部位（Body Part Examined）で当たる
        (["特殊検査"], "chest"),  # 当たらなければ既定
        ([], "chest"),
    ],
)
def test_match_routine(fields: list[str], expected: str) -> None:
    assert match_routine(ROUTINES, "CT", fields).name == expected


def test_match_routine_without_routines_for_the_modality() -> None:
    with pytest.raises(ValidationError):
        match_routine(ROUTINES, "MR", ["頭部"])


def test_routine_set_needs_one_default_per_modality() -> None:
    with pytest.raises(ValueError, match="exactly one default"):
        check_routine_set([_ct("a", ["x"]), _ct("b", ["y"])])
    with pytest.raises(ValueError, match="exactly one default"):
        check_routine_set([_ct("a", ["x"], default=True), _ct("b", ["y"], default=True)])


def test_routine_set_rejects_a_keyword_in_two_routines() -> None:
    with pytest.raises(ValueError, match="胸部"):
        check_routine_set([_ct("a", ["胸部"], default=True), _ct("b", ["ＣＨＥＳＴ", "胸部"])])


def test_series_without_images_is_an_error() -> None:
    with pytest.raises(PydanticValidationError):
        Routine.model_validate(
            {
                "name": "x",
                "label": "x",
                "modality": "CT",
                "protocol_name": "X",
                "series": [{"kind": "axial", "description": "AX"}],
            }
        )


def test_localizer_views_must_match_images() -> None:
    with pytest.raises(PydanticValidationError):
        _ct("x", [], kind="localizer", images=2, views=["frontal"])


def test_cr_series_has_one_view() -> None:
    with pytest.raises(PydanticValidationError, match="one view"):
        Routine.model_validate(
            {
                "name": "cr",
                "label": "cr",
                "modality": "CR",
                "protocol_name": "CR",
                "series": [{"description": "Chest", "images": 2, "views": ["PA", "LL"]}],
            }
        )


@pytest.mark.parametrize(
    ("wanted", "used", "expected"),
    [
        ([None, None], [], [1, 2]),
        ([None], [(1, False), (2, False), (3, False), (501, True)], [4]),
        ([None], [(1, False), (2, False), (3, False), (4, True)], [5]),
        ([None, 999], [(1, False)], [2, 999]),
    ],
)
def test_assign_series_numbers(
    wanted: list[int | None], used: list[tuple[int, bool]], expected: list[int]
) -> None:
    assert assign_series_numbers(wanted, used) == expected


@pytest.mark.parametrize(
    ("wanted", "used"),
    [([999], [(1, False), (999, True)]), ([7, 7], [])],
)
def test_assign_series_numbers_rejects_a_taken_number(
    wanted: list[int | None], used: list[tuple[int, bool]]
) -> None:
    with pytest.raises(ValidationError, match="既にあります"):
        assign_series_numbers(wanted, used)


def test_ct_series_configs_carry_the_routine_values() -> None:
    routine = _ct("x", [], kind="coronal", slice_thickness=3.0, contrast=True)

    (series,) = ct_series_configs(routine, [4], [0], [10])

    assert series.series_number == 4
    assert series.num_images == 10
    assert series.kind == "coronal"
    assert series.slice_thickness == series.slice_spacing == 3.0
    assert series.contrast is True
    assert series.protocol_name == "X"
    assert series.series_description == "AX"
