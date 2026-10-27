"""MR の予約・緊急の患者の撮影（テンプレートをモダリティに合わせる。ADR-0030）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port
from pydicom import dcmread

from app.core.exceptions import ProfileMismatchError
from app.core.models import ScheduledPatient
from app.modality.config import ModalityConfig
from app.modality.service import AUTO_ROUTINE, ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery

MR_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.4"


def _service(tmp_path: Path, worklist_port: int, default_profile: str | None = None):
    data: dict = {
        "ae_title": "DTG_MR01",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
        "default_profile": default_profile,
    }
    return ModalityService(ModalityConfig.model_validate(data))


def _mr_key(service: ModalityService) -> str:
    items = service.query_worklist(WorklistQuery()).items
    return next(i for i in items if i.accession_number == "A0003").key


def _headers(files: list[str]) -> list:
    return [dcmread(path, stop_before_pixels=True) for path in files]


def test_mr_order_is_taken_with_the_mr_template_without_naming_it(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            worklist_key=_mr_key(service),
            routine=AUTO_ROUTINE,
            routine_series=[0, 1],
            routine_images=[3, 2],
        )
    )

    assert result.routine == "mr_head"
    datasets = _headers(result.files)
    assert len(datasets) == 5
    assert {ds.Modality for ds in datasets} == {"MR"}
    assert {ds.SOPClassUID for ds in datasets} == {MR_SOP_CLASS}
    assert {ds.AccessionNumber for ds in datasets} == {"A0003"}
    assert [ds.SeriesDescription for ds in datasets[:1]] == ["Localizer"]


def test_mr_order_manual_series_makes_mr_images(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(ExamRequest(worklist_key=_mr_key(service), images_per_series=[2, 1]))

    datasets = _headers(result.files)
    assert len(datasets) == 3
    assert {ds.Modality for ds in datasets} == {"MR"}
    assert {str(ds.ImageType[0]) for ds in datasets} == {"ORIGINAL"}


def test_emergency_patient_can_be_taken_with_the_mr_template(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E1", patient_name="KINKYU^TARO"),
            template="mr_generic",
            routine=AUTO_ROUTINE,
            routine_series=[0],
            routine_images=[3],
        )
    )

    assert result.routine == "mr_head"
    datasets = _headers(result.files)
    assert {ds.Modality for ds in datasets} == {"MR"}
    assert {ds.AccessionNumber for ds in datasets} == {""}
    assert {ds.SOPClassUID for ds in datasets} == {MR_SOP_CLASS}


def test_default_ct_profile_is_not_applied_to_an_mr_order(tmp_path, worklist_scp) -> None:
    """設定の既定の装置が CT でも、MR の予約は止まらず、CT の装置の値を重ねない."""
    service = _service(tmp_path, worklist_scp.port, default_profile="dtg_synthetic_ct")

    result = service.exam(
        ExamRequest(
            worklist_key=_mr_key(service), routine=AUTO_ROUTINE, routine_series=[0],
            routine_images=[1],
        )
    )

    (ds,) = _headers(result.files)
    assert ds.Modality == "MR"
    assert ds.ManufacturerModelName == "DTG Synthetic MR"
    # 黙って外さず、重ねなかったことを知らせる
    assert any("dtg_synthetic_ct" in notice and "MR" in notice for notice in result.notices)


def test_default_ct_profile_is_not_applied_with_the_mr_template_named(
    tmp_path, worklist_scp
) -> None:
    """テンプレートを明示しても（CLI の -m）、装置を指定しなければ既定の CT を重ねない."""
    service = _service(tmp_path, worklist_scp.port, default_profile="dtg_synthetic_ct")

    result = service.exam(
        ExamRequest(worklist_key=_mr_key(service), template="mr_generic", images_per_series=[1])
    )

    (ds,) = _headers(result.files)
    assert ds.Modality == "MR"
    assert ds.ManufacturerModelName == "DTG Synthetic MR"
    assert any("dtg_synthetic_ct" in notice for notice in result.notices)


def test_profile_none_does_not_apply_the_default(tmp_path, worklist_scp) -> None:
    """「なし」（""）は既定の装置を重ねず、重ねなかった知らせも出さない."""
    service = _service(tmp_path, worklist_scp.port, default_profile="dtg_synthetic_mr")

    result = service.exam(
        ExamRequest(worklist_key=_mr_key(service), profile="", images_per_series=[1])
    )

    (ds,) = _headers(result.files)
    assert ds.ManufacturerModelName == "DTG Synthetic MR"
    assert not any("dtg_synthetic_mr" in notice for notice in result.notices)


def test_named_profile_must_match_the_modality(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    with pytest.raises(ProfileMismatchError):
        service.exam(
            ExamRequest(
                worklist_key=_mr_key(service),
                profile="dtg_synthetic_ct",
                routine=AUTO_ROUTINE,
                routine_series=[0],
                routine_images=[1],
            )
        )

    result = service.exam(
        ExamRequest(
            worklist_key=_mr_key(service),
            profile="dtg_synthetic_mr",
            routine=AUTO_ROUTINE,
            routine_series=[0],
            routine_images=[1],
        )
    )
    (ds,) = _headers(result.files)
    assert ds.ManufacturerModelName == "DTG Synthetic MR 1.5T"


def test_template_for_modality(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    assert service.template_for_modality("MR") == "mr_generic"
    assert service.template_for_modality("CT") == "ct_generic"  # 設定の既定
    assert service.template_for_modality("") == "ct_generic"
    assert service.template_for_modality("XX") == "ct_generic"  # 合うものが無ければ既定
