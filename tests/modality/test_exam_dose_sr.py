"""撮影の線量の報告：画面・SR・両方（ADR-0029）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, MppsRecorder, free_port
from pydicom import dcmread

from app.core.exceptions import ValidationError
from app.modality.config import ModalityConfig
from app.modality.service import AUTO_ROUTINE, ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery

SR_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.88.67"
SC_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.7"


def _service(tmp_path: Path, worklist_port: int, mpps_port: int | None = None):
    data: dict = {
        "ae_title": "DTG_CT01",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {
            "ae_title": "RIS_TEST",
            "host": LOCALHOST,
            "port": worklist_port,
            "use_mpps": mpps_port is not None,
        },
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
    }
    if mpps_port is not None:
        data["mpps"] = {"ae_title": "MPPS_TEST", "host": LOCALHOST, "port": mpps_port}
    return ModalityService(ModalityConfig.model_validate(data))


def _key(service: ModalityService) -> str:
    items = service.query_worklist(WorklistQuery()).items
    return next(i for i in items if i.accession_number == "A0001").key


def _exam(service: ModalityService, **extra):
    # 胸部 単純：Scout、縦断の4シリーズ、線量の画面（6 シリーズ）。画像数は最小にする
    return service.exam(
        ExamRequest(
            worklist_key=_key(service),
            routine=AUTO_ROUTINE,
            routine_images=extra.pop("routine_images", [1, 1, 1, 1, 1, 1]),
            **extra,
        )
    )


def _series(result) -> list[tuple[int, str, str, str]]:
    """(Series Number, Modality, SOP Class, Series Description) の並び."""
    rows = set()
    for path in result.files:
        ds = dcmread(path, stop_before_pixels=True)
        rows.add(
            (
                int(ds.SeriesNumber),
                str(ds.Modality),
                str(ds.SOPClassUID),
                str(ds.get("SeriesDescription", "")),
            )
        )
    return sorted(rows)


def test_default_is_the_dose_screen_only(tmp_path, worklist_scp) -> None:
    result = _exam(_service(tmp_path, worklist_scp.port))

    assert [row[1:3] for row in _series(result)][-1] == ("CT", SC_SOP_CLASS)
    assert SR_SOP_CLASS not in {row[2] for row in _series(result)}


def test_sr_replaces_the_dose_screen(tmp_path, worklist_scp) -> None:
    result = _exam(_service(tmp_path, worklist_scp.port), dose_report="sr")

    series = _series(result)
    assert len(series) == 6
    assert series[-1] == (6, "SR", SR_SOP_CLASS, "Radiation Dose SR")
    assert SC_SOP_CLASS not in {row[2] for row in series}


def test_both_has_the_screen_then_the_sr_in_the_same_study(tmp_path, worklist_scp) -> None:
    result = _exam(
        _service(tmp_path, worklist_scp.port),
        dose_report="both",
        routine_images=[1, 1, 1, 1, 1, 1],
    )

    series = _series(result)
    assert [(row[0], row[1], row[2]) for row in series[-2:]] == [
        (6, "CT", SC_SOP_CLASS),
        (7, "SR", SR_SOP_CLASS),
    ]
    uids = {dcmread(path, stop_before_pixels=True).StudyInstanceUID for path in result.files}
    assert len(uids) == 1


def test_sr_numbers_the_sr_like_the_dose_screen_it_replaced(tmp_path, worklist_scp) -> None:
    """ルーチンが書いたシリーズ番号（999 など）は、替えた SR が引き継ぐ."""
    service = _service(tmp_path, worklist_scp.port)
    routine = service.routine("ct_chest_plain")
    dose = [s for s in routine.series if s.kind == "dose_report"]

    result = _exam(service, dose_report="sr")

    sr_number = _series(result)[-1][0]
    assert sr_number == (dose[0].series_number or 6)


def test_sr_without_an_exposure_series_is_refused_in_japanese(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    with pytest.raises(ValidationError, match="線量の報告（SR）を撮るときは"):
        service.exam(
            ExamRequest(
                worklist_key=_key(service),
                routine=AUTO_ROUTINE,
                routine_series=[5],
                routine_images=[1],
                dose_report="sr",
            )
        )


def test_mpps_lists_the_sr_as_a_non_image_composite(
    tmp_path, worklist_scp, mpps_scp: MppsRecorder
) -> None:
    service = _service(tmp_path, worklist_scp.port, mpps_scp.port)

    result = _exam(service, dose_report="sr")

    assert result.mpps is not None and result.mpps.sent
    (_uid, modification), = mpps_scp.sets
    by_description = {s.SeriesDescription: s for s in modification.PerformedSeriesSequence}
    sr = by_description["Radiation Dose SR"]
    assert len(sr.ReferencedNonImageCompositeSOPInstanceSequence) == 1
    assert list(sr.ReferencedImageSequence) == []
    assert sr.ReferencedNonImageCompositeSOPInstanceSequence[0].ReferencedSOPClassUID == (
        SR_SOP_CLASS
    )
    scout = by_description["Scout"]
    assert len(scout.ReferencedImageSequence) == 1
    assert list(scout.ReferencedNonImageCompositeSOPInstanceSequence) == []


def test_manual_series_ignore_the_dose_report_choice(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(worklist_key=_key(service), images_per_series=[1], dose_report="sr")
    )

    assert {row[1] for row in _series(result)} == {"CT"}
