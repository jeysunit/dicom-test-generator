"""CR・DX の予約・緊急の患者の撮影（ADR-0034）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port
from pydicom import dcmread

from app.core.models import ScheduledPatient, WorklistItem
from app.core.projection import CR_IMAGE_STORAGE, DX_IMAGE_STORAGE_FOR_PRESENTATION
from app.modality.config import ModalityConfig
from app.modality.service import AUTO_ROUTINE, ExamRequest, ModalityService


def _service(tmp_path: Path, worklist_port: int) -> ModalityService:
    data: dict = {
        "ae_title": "DTG_CR01",
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


def _order(modality: str, description: str) -> WorklistItem:
    return WorklistItem(
        key=f"{modality.lower()}order01",
        patient_name="XRAY^HANAKO",
        patient_id="P000077",
        birth_date="19700101",
        sex="F",
        study_instance_uid="2.25.100000000000000000000000000000000077",
        accession_number="A0077",
        requested_procedure_description=description,
        modality=modality,
    )


def _rows(files: list[str]) -> list[tuple[int, str, str, str]]:
    datasets = [dcmread(path, stop_before_pixels=True) for path in files]
    return [
        (int(ds.SeriesNumber), ds.Modality, ds.ViewPosition, ds.SOPClassUID) for ds in datasets
    ]


@pytest.mark.parametrize(("modality", "template"), [("CR", "cr_generic"), ("DX", "dx_generic")])
def test_template_for_cr_and_dx(tmp_path, worklist_scp, modality, template) -> None:
    service = _service(tmp_path, worklist_scp.port)

    assert service.template_for_modality(modality) == template
    assert service.template_modality(template) == modality


def test_cr_chest_order_is_taken_with_the_cr_routine(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port)
    item = _order("CR", "胸部 正面・側面")
    monkeypatch.setattr(service, "find_item", lambda key: item)

    result = service.exam(
        ExamRequest(worklist_key=item.key, template="cr_generic", routine=AUTO_ROUTINE)
    )

    assert result.routine == "cr_chest"
    assert _rows(result.files) == [
        (1, "CR", "PA", CR_IMAGE_STORAGE),
        (2, "CR", "LL", CR_IMAGE_STORAGE),
    ]
    datasets = [dcmread(path, stop_before_pixels=True) for path in result.files]
    assert {ds.AccessionNumber for ds in datasets} == {"A0077"}
    assert {ds.StudyInstanceUID for ds in datasets} == {item.study_instance_uid}


def test_dx_knee_order_is_one_series_with_laterality(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port)
    item = _order("DX", "右膝 2方向")
    monkeypatch.setattr(service, "find_item", lambda key: item)

    result = service.exam(
        ExamRequest(worklist_key=item.key, template="dx_generic", routine=AUTO_ROUTINE)
    )

    assert result.routine == "dx_knee"
    assert _rows(result.files) == [
        (1, "DX", "AP", DX_IMAGE_STORAGE_FOR_PRESENTATION),
        (1, "DX", "LL", DX_IMAGE_STORAGE_FOR_PRESENTATION),
    ]
    datasets = [dcmread(path, stop_before_pixels=True) for path in result.files]
    assert {(ds.BodyPartExamined, ds.ImageLaterality) for ds in datasets} == {("KNEE", "R")}


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("cr_generic", [(1, "CR", "PA", CR_IMAGE_STORAGE), (2, "CR", "LL", CR_IMAGE_STORAGE)]),
        (
            "dx_generic",
            [
                (1, "DX", "PA", DX_IMAGE_STORAGE_FOR_PRESENTATION),
                (1, "DX", "LL", DX_IMAGE_STORAGE_FOR_PRESENTATION),
            ],
        ),
    ],
)
def test_emergency_patient_with_the_cr_and_dx_templates(
    tmp_path, worklist_scp, template, expected
) -> None:
    service = _service(tmp_path, worklist_scp.port)

    result = service.exam(
        ExamRequest(
            emergency_patient=ScheduledPatient(patient_id="E1", patient_name="KINKYU^TARO"),
            template=template,
            routine=AUTO_ROUTINE,
        )
    )

    assert result.routine == f"{template[:2]}_chest"
    assert _rows(result.files) == expected
