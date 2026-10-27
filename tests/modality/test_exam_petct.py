"""PET/CT の予約・緊急の患者の撮影（ADR-0032）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port
from pydicom import dcmread

from app.core.exceptions import WorklistMappingError
from app.core.models import ScheduledPatient, WorklistItem
from app.modality.config import ModalityConfig
from app.modality.service import AUTO_ROUTINE, ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery

PT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.128"
CT_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.2"


def _service(tmp_path: Path, worklist_port: int) -> ModalityService:
    data: dict = {
        "ae_title": "DTG_PT01",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
    }
    return ModalityService(ModalityConfig.model_validate(data))


def _pt_order() -> WorklistItem:
    return WorklistItem(
        key="ptorder001",
        patient_name="PET^HANAKO",
        patient_id="P000099",
        birth_date="19600101",
        sex="F",
        study_instance_uid="2.25.100000000000000000000000000000000099",
        accession_number="A0099",
        requested_procedure_description="FDG PET/CT 全身",
        modality="PT",
    )


def _series(files: list[str]) -> list[tuple[int, str, str]]:
    rows = set()
    for path in files:
        ds = dcmread(path, stop_before_pixels=True)
        rows.add((int(ds.SeriesNumber), str(ds.Modality), str(ds.SeriesDescription)))
    return sorted(rows)


def test_template_for_pt_is_the_pet_ct_template(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    assert service.template_for_modality("PT") == "petct_generic"
    assert service.template_modality("petct_generic") == "PT"


def test_pt_order_is_taken_with_the_default_pet_ct_routine(
    tmp_path, worklist_scp, monkeypatch
) -> None:
    service = _service(tmp_path, worklist_scp.port)
    item = _pt_order()
    monkeypatch.setattr(service, "find_item", lambda key: item)

    result = service.exam(
        ExamRequest(
            worklist_key=item.key,
            routine=AUTO_ROUTINE,
            routine_images=[1, 2, 2, 2, 1],
        )
    )

    assert result.routine == "pt_whole_body"  # 「FDG」「PET」に当たる
    assert _series(result.files) == [
        (1, "CT", "Topogram"),
        (2, "CT", "CT WB 3mm"),
        (3, "PT", "PET WB AC"),
        (4, "PT", "PET WB NAC"),
        (5, "CT", "Dose Report"),
    ]
    datasets = [dcmread(path, stop_before_pixels=True) for path in result.files]
    assert {ds.AccessionNumber for ds in datasets} == {"A0099"}
    assert {ds.StudyInstanceUID for ds in datasets} == {item.study_instance_uid}
    assert {ds.SOPClassUID for ds in datasets if ds.Modality == "PT"} == {PT_SOP_CLASS}


def test_files_are_listed_in_the_order_they_were_written(
    tmp_path, worklist_scp, monkeypatch
) -> None:
    """名前の順＝送る順。PT を先に撮るルーチンは PT のファイルが先に並ぶ."""
    service = _service(tmp_path, worklist_scp.port)
    item = _pt_order()
    monkeypatch.setattr(service, "find_item", lambda key: item)

    result = service.exam(
        ExamRequest(
            worklist_key=item.key,
            routine="pt_whole_body_pet_first",
            routine_images=[1, 1, 1, 1, 1],
        )
    )

    modalities = [dcmread(path, stop_before_pixels=True).Modality for path in result.files]
    assert modalities == ["PT", "PT", "CT", "CT", "CT"]


def test_emergency_patient_with_the_pet_ct_template(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E1", patient_name="KINKYU^TARO"),
            template="petct_generic",
            routine=AUTO_ROUTINE,
            routine_series=[2, 3],
            routine_images=[1, 1],
        )
    )

    assert result.routine == "pt_whole_body"
    assert _series(result.files) == [(1, "PT", "PET WB AC"), (2, "PT", "PET WB NAC")]


def test_dose_sr_with_a_pet_ct_exam(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E1", patient_name="KINKYU^TARO"),
            template="petct_generic",
            routine=AUTO_ROUTINE,
            routine_images=[1, 1, 1, 1, 1],
            dose_report="both",
        )
    )

    assert [row[1] for row in _series(result.files)] == ["CT", "CT", "PT", "PT", "CT", "SR"]


def test_pt_template_refuses_a_ct_order(tmp_path, worklist_scp) -> None:
    service = _service(tmp_path, worklist_scp.port)
    items = service.query_worklist(WorklistQuery()).items
    key = next(i for i in items if i.accession_number == "A0001").key

    with pytest.raises(WorklistMappingError, match="予約は CT、テンプレートは PT です"):
        service.exam(ExamRequest(worklist_key=key, template="petct_generic"))
