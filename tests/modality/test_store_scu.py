"""C-STORE・C-ECHO の SCU の試験（手元の Storage の SCP を相手にする）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, free_port

from app.core import (
    CharacterSetConfig,
    GenerationConfig,
    Patient,
    PatientName,
    PixelSpecSimple,
    SeriesConfig,
    StudyConfig,
    TransferSyntaxConfig,
)
from app.core.exceptions import AssociationError
from app.modality.config import DestinationConfig
from app.modality.store_scu import echo, store_files
from app.services import StudyGeneratorService

OWN_AE = "DTG_CT01"


def _node(port: int, ae_title: str = "PACS_TEST") -> DestinationConfig:
    return DestinationConfig(name="PACS_TEST", ae_title=ae_title, host=LOCALHOST, port=port)


@pytest.fixture
def dicom_files(tmp_path: Path) -> list[Path]:
    config = GenerationConfig(
        job_name="store_test",
        output_dir=str(tmp_path / "exam"),
        patient=Patient(
            patient_id="P000009",
            patient_name=PatientName(alphabetic="STORE^TEST"),
            birth_date="19900101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A0009", study_date="20261018", study_time="100000", num_series=1
        ),
        series_list=[SeriesConfig(series_number=1, num_images=3)],
        modality_template="ct_generic",
        pixel_spec=PixelSpecSimple(width=64, height=64),
        transfer_syntax=TransferSyntaxConfig(),
        character_set=CharacterSetConfig(specific_character_set="", use_ideographic=False),
    )
    output_dir = StudyGeneratorService().generate(config)
    return sorted(output_dir.glob("*.dcm"))


def test_echo_success(storage_scp) -> None:
    result = echo(OWN_AE, _node(storage_scp.port), timeout_seconds=5)

    assert result.status == 0x0000
    assert result.elapsed_ms >= 0


def test_echo_unreachable() -> None:
    with pytest.raises(AssociationError) as exc_info:
        echo(OWN_AE, _node(free_port()), timeout_seconds=1)

    assert "could not connect" in str(exc_info.value)


def test_store_success(storage_scp, dicom_files) -> None:
    results = store_files(OWN_AE, _node(storage_scp.port), dicom_files, timeout_seconds=5)

    assert [r.outcome for r in results] == ["success"] * 3
    assert len(storage_scp.received) == 3
    assert {r.sop_instance_uid for r in results} == {
        str(ds.SOPInstanceUID) for ds in storage_scp.received
    }


def test_store_warning_counts_as_sent(storage_scp, dicom_files) -> None:
    storage_scp.status = 0xB000

    results = store_files(OWN_AE, _node(storage_scp.port), dicom_files, timeout_seconds=5)

    assert all(r.outcome == "warning" and r.sent for r in results)
    assert results[0].status == 0xB000


def test_store_failure_status(storage_scp, dicom_files) -> None:
    storage_scp.status = 0xA700

    results = store_files(OWN_AE, _node(storage_scp.port), dicom_files, timeout_seconds=5)

    assert all(r.outcome == "failure" and not r.sent for r in results)
    assert results[0].reason == "status 0xA700"


def test_store_unreachable(dicom_files) -> None:
    with pytest.raises(AssociationError):
        store_files(OWN_AE, _node(free_port()), dicom_files, timeout_seconds=1)


def test_store_unreadable_file_is_failure(storage_scp, dicom_files, tmp_path) -> None:
    broken = tmp_path / "broken.dcm"
    broken.write_bytes(b"not dicom")

    results = store_files(
        OWN_AE, _node(storage_scp.port), [broken, dicom_files[0]], timeout_seconds=5
    )

    by_path = {r.path: r for r in results}
    assert by_path[str(broken)].outcome == "failure"
    assert by_path[str(dicom_files[0])].outcome == "success"
