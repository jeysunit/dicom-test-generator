"""templates/routine/ のルーチンの読み込みと、付けるルーチンの画像数（ADR-0025）."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.exceptions import TemplateNotFoundError, TemplateParseError
from app.services.routine_loader import RoutineLoaderService

# design.md の「DTG に付けるルーチン」の表の画像数（範囲 ÷ 厚さ などの計算の値）
EXPECTED_IMAGES = {
    "ct_head_plain": [1, 30, 60, 1],
    "ct_chest_plain": [1, 60, 60, 300, 83, 1],
    "ct_chest_abdomen_pelvis_contrast": [1, 150, 133, 83, 116, 1],
    "ct_abdomen_pelvis": [1, 80, 80, 83, 116, 1],
    "ct_liver_dynamic": [1, 50, 83, 83, 83, 83, 1],
    "ct_coronary_cta": [1, 40, 280, 1],
    "ct_lumbar_spine": [2, 75, 30, 30, 75, 30, 1],
    "mr_head": [15, 25, 25, 25, 25, 25, 25, 116],
    "mr_lumbar_spine": [15, 18, 18, 45],
    "mr_knee": [15, 30, 30, 30, 30],
    "mr_shoulder": [15, 24, 24, 24, 24],
    "cr_chest": [1, 1],
    "cr_abdomen": [1, 1],
    "cr_lumbar_spine": [1, 1],
    "cr_cervical_spine": [1, 1, 1],
    "cr_knee": [1, 1],
    "cr_hand": [1, 1, 1],
    "dx_chest": [2],
    "dx_abdomen": [2],
    "dx_lumbar_spine": [2],
    "dx_cervical_spine": [3],
    "dx_knee": [2],
    "dx_hand": [3],
    "us_abdomen": [16],
    # PET/CT（ADR-0032）：Topogram 1、CT 333（1000mm ÷ 3mm）、PET 300 × 2（1000mm ÷ 3.27mm）、
    # 線量の画面 1
    "pt_whole_body": [1, 333, 300, 300, 1],
    "pt_whole_body_pet_first": [300, 300, 1, 333, 1],
}
DEFAULTS = {
    "CT": "ct_chest_plain",
    "MR": "mr_head",
    "PT": "pt_whole_body",
    "CR": "cr_chest",
    "DX": "dx_chest",
    "US": "us_abdomen",
}


def test_shipped_routines_have_the_designed_image_counts() -> None:
    routines = RoutineLoaderService().list_routines()

    assert {r.name: [s.images for s in r.series] for r in routines} == EXPECTED_IMAGES
    assert {r.modality: r.name for r in routines if r.default} == DEFAULTS
    # どれも1回の撮影の上限（既定 2000）に収まる
    assert max(r.total_images for r in routines) <= 2000


def test_chest_routine_totals_505_images() -> None:
    assert RoutineLoaderService().get("ct_chest_plain").total_images == 505


def _write(directory: Path, name: str, body: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.yaml").write_text(body, encoding="utf-8")


CT_HEADER = 'name: "{name}"\nlabel: "x"\nmodality: "CT"\nprotocol_name: "X"\n'


def test_series_without_images_names_the_file_and_position(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "broken",
        CT_HEADER.format(name="broken")
        + 'default: true\nseries:\n  - kind: "axial"\n    description: "AX"\n    images: 1\n'
        '  - kind: "axial"\n    description: "AX2"\n',
    )

    with pytest.raises(TemplateParseError) as caught:
        RoutineLoaderService(tmp_path).list_routines()

    assert "broken.yaml" in str(caught.value)
    assert "series.1.images" in str(caught.value)


def test_name_must_be_the_file_name(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "a",
        CT_HEADER.format(name="b")
        + 'default: true\nseries:\n  - kind: "axial"\n    description: "AX"\n    images: 1\n',
    )

    with pytest.raises(TemplateParseError, match="file name"):
        RoutineLoaderService(tmp_path).list_routines()


def test_unknown_routine_name(tmp_path: Path) -> None:
    with pytest.raises(TemplateNotFoundError):
        RoutineLoaderService().get("no_such_routine")
    with pytest.raises(TemplateNotFoundError):
        RoutineLoaderService().get("../ct_chest_plain")
