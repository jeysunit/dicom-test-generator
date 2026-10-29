"""部位の図形で撮影の画像を作る試験（synthetic-images の spec の「部位と撮像で図形と値を変える」）."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pydicom

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecPhantom,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.phantom import PHANTOM_MARKS, marker_bounds
from app.core.phantom_region import mr_segment_values, xray_segment_values
from app.core.routine import routine_series_configs
from app.services.profile_loader import ProfileLoaderService
from app.services.routine_loader import RoutineLoaderService
from app.services.study_generator import StudyGeneratorService

CT_OFFSET = 1024


def _routine_series(name: str, keep: list[int], images: list[int] | None = None):
    routine = RoutineLoaderService().get(name)
    counts = images or [routine.series[index].images for index in keep]
    return routine_series_configs(routine, list(range(1, len(keep) + 1)), keep, counts)


def _generate(tmp_path: Path, series_list, template: str) -> dict[int, list[pydicom.Dataset]]:
    config = GenerationConfig(
        job_name="phantom_region",
        output_dir=str(tmp_path / "out"),
        patient=Patient(
            patient_id="P000001",
            patient_name=PatientName(alphabetic="TEST^REGION"),
            birth_date="19800101",
            sex="M",
        ),
        study=StudyConfig(
            accession_number="A1", study_date="20261029", study_time="090000",
            num_series=len(series_list),
        ),
        series_list=series_list,
        modality_template=template,
        pixel_spec=PixelSpecPhantom(),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(
            specific_character_set="", use_ideographic=False, use_phonetic=False
        ),
    )
    service = StudyGeneratorService(profile_loader=ProfileLoaderService(environ={}))
    by_series: dict[int, list[pydicom.Dataset]] = {}
    for path in sorted(service.generate(config).glob("*.dcm")):
        ds = pydicom.dcmread(path)
        by_series.setdefault(int(ds.SeriesNumber), []).append(ds)
    for items in by_series.values():
        items.sort(key=lambda ds: int(ds.InstanceNumber))
    return by_series


def _stored(ds: pydicom.Dataset) -> np.ndarray:
    """画素の格納値（Rescale を当てない）."""
    raw = np.frombuffer(ds.PixelData, dtype=np.int16 if ds.PixelRepresentation else np.uint16)
    return raw.reshape(int(ds.Rows), int(ds.Columns))


def _values(ds: pydicom.Dataset, index: int, count: int) -> set[int]:
    """目印を除いた画素の値の種類（目印は骨と同じ値なので、区分と分けて数える）."""
    pixels = _stored(ds).copy()
    r0, r1, c0, c1 = marker_bounds(int(ds.Rows), int(ds.Columns), index, count)
    pixels[max(r0, 0) : max(r1, 0), max(c0, 0) : max(c1, 0)] = pixels.min()
    return set(np.unique(pixels).tolist())


def test_ct_head_axial_has_a_bone_ring_and_soft_tissue_inside(tmp_path) -> None:
    study = _generate(tmp_path, _routine_series("ct_head_plain", [1]), "ct_generic")
    axial = study[1]
    middle = len(axial) // 2
    pixels = _stored(axial[middle])
    row = pixels[pixels.shape[0] // 2]
    bone = np.flatnonzero(row == 1000 + CT_OFFSET)
    soft = np.flatnonzero(row == 40 + CT_OFFSET)
    assert len(bone) and len(soft)
    # 骨の輪が軟部を囲む
    assert bone.min() < soft.min() and soft.max() < bone.max()
    for ds in axial:
        for keyword, value in PHANTOM_MARKS.items():
            assert ds.get(keyword) == value


def test_ct_lumbar_axial_alternates_bone_and_gap(tmp_path) -> None:
    study = _generate(tmp_path, _routine_series("ct_lumbar_spine", [1]), "ct_generic")
    axial = study[1]
    has_bone = [
        (1000 + CT_OFFSET) in _values(ds, index, len(axial)) for index, ds in enumerate(axial)
    ]
    changes = sum(a != b for a, b in zip(has_bone, has_bone[1:], strict=False))
    assert True in has_bone and False in has_bone
    assert changes >= 4


def test_mr_head_fluid_is_brighter_on_t2_ax_than_on_t1_sag(tmp_path) -> None:
    # 4 は T1 SAG、5 は T2 AX（mr_head の並びの 0 始まりの位置）
    study = _generate(tmp_path, _routine_series("mr_head", [4, 5]), "mr_generic")
    t1_sag, t2_ax = study[1], study[2]
    bits = int(t2_ax[0].BitsStored)
    t1, t2 = mr_segment_values("T1", bits), mr_segment_values("T2", bits)
    assert t2["fluid"] > t1["fluid"]
    assert t2["fluid"] in _values(t2_ax[len(t2_ax) // 2], len(t2_ax) // 2, len(t2_ax))
    t1_values = set().union(
        *(_values(ds, index, len(t1_sag)) for index, ds in enumerate(t1_sag))
    )
    assert t1["fluid"] in t1_values
    assert t2["fluid"] not in t1_values


def test_liver_dynamic_vessel_is_40_plain_and_300_arterial(tmp_path) -> None:
    study = _generate(
        tmp_path, _routine_series("ct_liver_dynamic", [1, 2], images=[10, 10]), "ct_generic"
    )
    plain, arterial = study[1], study[2]
    plain_values = _values(plain[5], 5, 10)
    arterial_values = _values(arterial[5], 5, 10)
    assert 40 + CT_OFFSET in plain_values and 300 + CT_OFFSET not in plain_values
    assert 300 + CT_OFFSET in arterial_values
    assert arterial[0].get("ContrastBolusAgent") is not None


def test_dx_chest_shows_two_lungs_on_pa_and_one_on_lateral(tmp_path) -> None:
    study = _generate(tmp_path, _routine_series("dx_chest", [0]), "dx_generic")
    pa, lateral = study[1]
    assert (pa.ViewPosition, lateral.ViewPosition) == ("PA", "LL")
    lung = xray_segment_values(12)["lung"]

    def runs(line: np.ndarray) -> int:
        hits = np.concatenate([[False], line == lung, [False]]).astype(np.int8)
        return int(np.count_nonzero(np.diff(hits) == 1))

    middle = int(pa.Rows) // 2
    assert runs(_stored(pa)[middle]) == 2
    assert runs(_stored(lateral)[middle]) == 1
    for ds in (pa, lateral):
        for keyword, value in PHANTOM_MARKS.items():
            assert ds.get(keyword) == value


def test_manual_series_in_a_region_study_keep_the_basic_shape(tmp_path) -> None:
    series = [*_routine_series("ct_head_plain", [1], images=[5]),
              SeriesConfig(series_number=2, num_images=5)]
    study = _generate(tmp_path, series, "ct_generic")
    # 手で入れたシリーズは基本の図形（背景・図形・目印の 3 種類）
    for index, ds in enumerate(study[2]):
        assert _values(ds, index, 5) <= {-1000 + CT_OFFSET, 40 + CT_OFFSET}
