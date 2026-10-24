"""予約に当てたルーチンでの撮影と、シリーズ番号の記録（ADR-0025）."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port
from pydicom import dcmread

from app.core.exceptions import ValidationError, WorklistMappingError
from app.core.models import ScheduledPatient, WorklistItem
from app.modality.config import ModalityConfig
from app.modality.queue import QUEUE_DB_NAME
from app.modality.service import AUTO_ROUTINE, ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery
from app.services.routine_loader import RoutineLoaderService

A0001_STUDY_UID = "2.25.100000000000000000000000000000000001"


def _service(
    tmp_path: Path,
    worklist_port: int,
    routine_dir: Path | None = None,
    max_images: int | None = None,
) -> ModalityService:
    data: dict = {
        "ae_title": "DTG_CT01",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
    }
    if max_images is not None:
        data["max_images_per_exam"] = max_images
    loader = RoutineLoaderService(routine_dir) if routine_dir is not None else None
    return ModalityService(ModalityConfig.model_validate(data), routine_loader=loader)


def _key(service: ModalityService, accession: str = "A0001") -> str:
    items = service.query_worklist(WorklistQuery()).items
    return next(i for i in items if i.accession_number == accession).key


def _series(files: list[str]) -> list[tuple[int, str, int]]:
    """(Series Number, Series Description, 画像数) の並び."""
    counts: dict[tuple[int, str], int] = {}
    for path in files:
        ds = dcmread(path, stop_before_pixels=True)
        key = (int(ds.SeriesNumber), str(ds.get("SeriesDescription", "")))
        counts[key] = counts.get(key, 0) + 1
    return [(number, description, count) for (number, description), count in sorted(counts.items())]


def test_auto_routine_from_the_order_description(tmp_path, worklist_scp) -> None:
    """検査名「胸部 CT」→ 胸部 単純。画像数を減らして撮る（並びはルーチンのまま）."""
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            worklist_key=_key(service),
            routine=AUTO_ROUTINE,
            routine_images=[1, 2, 2, 2, 2, 1],
        )
    )

    assert result.routine == "ct_chest_plain"
    assert _series(result.files) == [
        (1, "Scout", 1),
        (2, "Mediastinum 5mm", 2),
        (3, "Lung 5mm", 2),
        (4, "Lung 1mm", 2),
        (5, "COR 3mm", 2),
        (6, "Dose Report", 1),
    ]


def test_auto_routine_defaults_cover_every_series(tmp_path, worklist_scp) -> None:
    """何も変えなければ、ルーチンの標準の画像数で全部のシリーズを撮る（作る前の並び）."""
    service = _service(tmp_path, worklist_scp.port)
    item = service.find_item(_key(service, "A0002"))  # 頭部 CT

    routine = service.matched_routine(item, "CT")

    assert routine.name == "ct_head_plain"
    assert [s.images for s in routine.series] == [1, 30, 60, 1]
    assert service.matched_routine(None, "CT").total_images == 505  # 緊急の患者は胸部 単純


def test_body_part_examined_matches_when_the_description_does_not() -> None:
    service = ModalityService.__new__(ModalityService)
    service._routine_loader = RoutineLoaderService()
    item = WorklistItem(
        key="k",
        modality="CT",
        requested_procedure_description="単純CT",
        body_part_examined="HEAD",
    )

    assert service.matched_routine(item, "CT").name == "ct_head_plain"
    # 予約のモダリティが空なら、テンプレートのモダリティのルーチンから当てる
    assert service.matched_routine(item.model_copy(update={"modality": ""}), "CT").name == (
        "ct_head_plain"
    )


def test_emergency_uses_the_template_modality_default(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E1", patient_name="A^B"),
            routine=AUTO_ROUTINE,
            routine_series=[0, 5],
            routine_images=[1, 1],
        )
    )

    assert result.routine == "ct_chest_plain"
    assert _series(result.files) == [(1, "Scout", 1), (2, "Dose Report", 1)]


def test_routine_and_template_modality_must_match(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    with pytest.raises(WorklistMappingError, match="予約は MR"):
        service.exam(ExamRequest(worklist_key=_key(service, "A0003"), routine=AUTO_ROUTINE))
    with pytest.raises(ValidationError, match="ルーチンは MR"):
        service.exam(
            ExamRequest(
                emergency_patient=ScheduledPatient(patient_id="E1", patient_name="A^B"),
                routine="mr_head",
            )
        )


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        ({"routine_images": [1, 2]}, "シリーズの数（6）"),
        ({"routine_series": [9]}, "1つ以上"),
        ({"routine_images": [1, 2, 2, 2, 2000, 1]}, "1〜1000"),
    ],
)
def test_bad_routine_requests(tmp_path, worklist_scp, extra: dict, message: str) -> None:
    service = _service(tmp_path, worklist_scp.port)

    with pytest.raises(ValidationError, match=message):
        service.exam(ExamRequest(worklist_key=_key(service), routine="ct_chest_plain", **extra))


def test_total_images_are_checked_after_the_routine(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, max_images=100)

    with pytest.raises(ValidationError, match="100 画像まで"):
        service.exam(ExamRequest(worklist_key=_key(service), routine="ct_chest_plain"))


def _custom_routines(tmp_path: Path, dose_number: int) -> Path:
    directory = tmp_path / "routines"
    directory.mkdir()
    (directory / "ct_custom.yaml").write_text(
        'name: "ct_custom"\nlabel: "x"\nmodality: "CT"\nprotocol_name: "X"\ndefault: true\n'
        'keywords: ["胸部"]\nseries:\n'
        '  - kind: "axial"\n    description: "AX"\n    images: 1\n'
        f'  - kind: "dose_report"\n    description: "Dose Report"\n    images: 1\n'
        f"    series_number: {dose_number}\n",
        encoding="utf-8",
    )
    return directory


def test_written_series_number_collides_on_append(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, _custom_routines(tmp_path, 999))
    key = _key(service)

    first = service.exam(ExamRequest(worklist_key=key, routine=AUTO_ROUTINE))
    assert _series(first.files) == [(1, "AX", 1), (999, "Dose Report", 1)]

    with pytest.raises(ValidationError, match="999 は既にあります"):
        service.exam(ExamRequest(worklist_key=key, routine=AUTO_ROUTINE, append=True))


def test_automatic_numbers_skip_written_numbers(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port, _custom_routines(tmp_path, 2))
    key = _key(service)
    service.exam(ExamRequest(worklist_key=key, routine=AUTO_ROUTINE))  # 1（自動）と 2（書いた番号）

    appended = service.exam(ExamRequest(worklist_key=key, images_per_series=[1], append=True))

    assert _series(appended.files) == [(3, "", 1)]


def test_record_from_the_previous_version_counts_as_automatic(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)
    key = _key(service)
    assert service.queue  # 待ち行列の表を作っておく
    with closing(sqlite3.connect(tmp_path / "state" / QUEUE_DB_NAME)) as conn, conn:
        conn.execute(
            "INSERT INTO exam_records VALUES (?, ?, '20261022', '100000', '', 2)",
            (key, A0001_STUDY_UID),
        )

    appended = service.exam(ExamRequest(worklist_key=key, images_per_series=[1], append=True))

    assert _series(appended.files)[0][0] == 3
    assert service.queue.exam_record(key).series_numbers == [(1, False), (2, False), (3, False)]


def test_worklist_query_asks_for_body_part_examined() -> None:
    from app.modality.worklist_scu import build_query_identifier

    identifier = build_query_identifier(WorklistQuery(), "ISO_IR 192")

    assert "BodyPartExamined" in identifier and identifier.BodyPartExamined == ""
