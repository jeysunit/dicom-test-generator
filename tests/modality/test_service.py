"""ModalityService の試験：信用できない予約の値でも出力の根の外に書かない（spec/12 の 6.5）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST

from app.modality.config import ModalityConfig
from app.modality.service import ExamRequest, ModalityService
from app.modality.worklist_scu import WorklistQuery


def _service(tmp_path: Path, worklist_port: int) -> ModalityService:
    config = ModalityConfig.model_validate(
        {
            "ae_title": "DTG_CT01",
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
            "destinations": [
                {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": 104}
            ],
            "default_destination": "PACS_TEST",
        }
    )
    return ModalityService(config)


@pytest.mark.parametrize(
    ("accession", "patient_id"),
    [
        ("../../evil", "../../evil"),
        ("/etc/passwd", "/tmp/evil"),
        ("..", ".."),
        ("CON", "NUL"),
        ("A\\..\\..\\x", "P\\..\\x"),
    ],
)
def test_untrusted_worklist_values_stay_inside_output_root(
    tmp_path, worklist_scp, worklist_items, accession, patient_id
) -> None:
    evil = dict(worklist_items[0])
    evil["accession_number"] = accession
    evil["patient_id"] = patient_id
    worklist_scp.items = [evil]
    service = _service(tmp_path, worklist_scp.port)
    item = service.query_worklist(WorklistQuery()).items[0]

    result = service.exam(ExamRequest(worklist_key=item.key, pixel_mode="simple_text"))

    output_root = (tmp_path / "output").resolve()
    files = [Path(path) for path in result.files]
    assert len(files) == 1
    assert Path(result.output_dir).resolve().parent == output_root
    assert all(path.resolve().is_relative_to(output_root) for path in files)
    assert sorted(tmp_path.rglob("*.dcm")) == sorted(path.resolve() for path in files)
