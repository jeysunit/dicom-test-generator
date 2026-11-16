"""焼き込み（burn_in）の選び方：CLI が設定より優先する（docs/spec/06 の 4.7）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port
from pydantic import ValidationError
from pydicom import dcmread

from app.core.exceptions import ConfigurationError
from app.core.models import WorklistItem
from app.modality.config import ModalityConfig
from app.modality.service import ExamRequest, ModalityService


def _service(tmp_path: Path, worklist_port: int, **extra) -> ModalityService:
    data: dict = {
        "ae_title": "DTG_CT01",
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_port},
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": LOCALHOST, "port": free_port()}
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "phantom",
        **extra,
    }
    return ModalityService(ModalityConfig.model_validate(data))


def _item() -> WorklistItem:
    return WorklistItem(
        key="ctorder01",
        patient_name="BURN^IN",
        patient_id="P000055",
        birth_date="19700101",
        sex="M",
        study_instance_uid="2.25.100000000000000000000000000000000055",
        accession_number="A0055",
        modality="CT",
    )


def _burned_in(service: ModalityService, monkeypatch, **request) -> set[str | None]:
    item = _item()
    monkeypatch.setattr(service, "find_item", lambda key: item)
    result = service.exam(ExamRequest(worklist_key=item.key, template="ct_generic", **request))
    return {dcmread(path, stop_before_pixels=True).get("BurnedInAnnotation") for path in result.files}


def test_the_default_does_not_burn_in(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port)

    assert _burned_in(service, monkeypatch) == {"NO"}


def test_the_config_selects_burn_in(tmp_path, worklist_scp, monkeypatch) -> None:
    service = _service(tmp_path, worklist_scp.port, burn_in=True)

    assert _burned_in(service, monkeypatch) == {"YES"}


def test_no_burn_in_on_the_command_line_wins_over_the_config(
    tmp_path, worklist_scp, monkeypatch
) -> None:
    service = _service(tmp_path, worklist_scp.port, burn_in=True)

    assert _burned_in(service, monkeypatch, burn_in=False) == {"NO"}


def test_burn_in_on_the_command_line_wins_over_the_config(
    tmp_path, worklist_scp, monkeypatch
) -> None:
    service = _service(tmp_path, worklist_scp.port, burn_in=False)

    assert _burned_in(service, monkeypatch, burn_in=True) == {"YES"}


def test_another_pixel_mode_on_the_command_line_does_not_burn_in(
    tmp_path, worklist_scp, monkeypatch
) -> None:
    service = _service(tmp_path, worklist_scp.port, burn_in=True)

    assert _burned_in(service, monkeypatch, pixel_mode="ct_realistic") == {None}


@pytest.mark.parametrize("value", [True, False])
@pytest.mark.parametrize("pixel_mode", ["ct_realistic", "simple_text"])
def test_burn_in_with_another_pixel_mode_is_refused(
    tmp_path, worklist_scp, monkeypatch, pixel_mode, value
) -> None:
    service = _service(tmp_path, worklist_scp.port)
    item = _item()
    monkeypatch.setattr(service, "find_item", lambda key: item)

    with pytest.raises(ConfigurationError):
        service.exam(
            ExamRequest(
                worklist_key=item.key, template="ct_generic", pixel_mode=pixel_mode, burn_in=value
            )
        )


def test_burn_in_without_phantom_in_the_config_is_refused(tmp_path, worklist_scp) -> None:
    with pytest.raises(ValidationError, match="burn_in"):
        _service(tmp_path, worklist_scp.port, default_pixel_mode="ct_realistic", burn_in=True)
