"""C-STORE の Presentation Context の試験（PS3.5 10.1：Implicit VR LE を必ず申し込む）."""

from __future__ import annotations

from pathlib import Path

import pytest
from modality_peers import LOCALHOST, StorageRecorder, start_server
from pydicom import dcmread
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian
from pynetdicom import AE, evt
from pynetdicom.sop_class import CTImageStorage

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
from app.modality.config import DestinationConfig
from app.modality.store_scu import requested_transfer_syntaxes, store_files
from app.services import StudyGeneratorService

OWN_AE = "DTG_CT01"


@pytest.fixture
def explicit_files(tmp_path: Path) -> list[Path]:
    config = GenerationConfig(
        job_name="context_test",
        output_dir=str(tmp_path / "exam"),
        patient=Patient(
            patient_id="P000010",
            patient_name=PatientName(alphabetic="CONTEXT^TEST"),
            birth_date="19900101",
            sex="F",
        ),
        study=StudyConfig(
            accession_number="A0010", study_date="20261021", study_time="100000", num_series=1
        ),
        series_list=[SeriesConfig(series_number=1, num_images=2)],
        modality_template="ct_generic",
        pixel_spec=PixelSpecSimple(width=64, height=64),
        transfer_syntax=TransferSyntaxConfig(
            uid=ExplicitVRLittleEndian,
            name="Explicit VR Little Endian",
            is_implicit_vr=False,
        ),
        character_set=CharacterSetConfig(specific_character_set="", use_ideographic=False),
    )
    output_dir = StudyGeneratorService().generate(config)
    return sorted(output_dir.glob("*.dcm"))


@pytest.fixture
def implicit_only_scp():
    recorder = StorageRecorder()
    ae = AE(ae_title=recorder.ae_title)
    ae.add_supported_context(CTImageStorage, ImplicitVRLittleEndian)
    server, recorder.port = start_server(ae, [(evt.EVT_C_STORE, recorder.handle_store)])
    yield recorder
    server.shutdown()


def test_requested_transfer_syntaxes_always_include_implicit_vr_little_endian() -> None:
    assert requested_transfer_syntaxes({ExplicitVRLittleEndian}) == [
        ExplicitVRLittleEndian,
        ImplicitVRLittleEndian,
    ]
    assert requested_transfer_syntaxes({ImplicitVRLittleEndian}) == [ImplicitVRLittleEndian]


def test_explicit_files_reach_scp_that_accepts_only_implicit(
    implicit_only_scp, explicit_files
) -> None:
    node = DestinationConfig(
        name="PACS_TEST", ae_title="PACS_TEST", host=LOCALHOST, port=implicit_only_scp.port
    )

    results = store_files(OWN_AE, node, explicit_files, timeout_seconds=5)

    assert [r.outcome for r in results] == ["success"] * 2
    sent = {str(dcmread(p).SOPInstanceUID): dcmread(p).PixelData for p in explicit_files}
    for ds in implicit_only_scp.received:
        assert ds.file_meta.TransferSyntaxUID == ImplicitVRLittleEndian
        assert ds.PixelData == sent[str(ds.SOPInstanceUID)]
