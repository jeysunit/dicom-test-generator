"""統合の試験：MWL の SCP → `exam --from-worklist --send` → 既存の app/scp が受ける（spec/12 の 14 章）."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pydicom
import pytest
import yaml
from modality_peers import LOCALHOST, free_port

from app.cli.main import main
from app.scp.models import SCPConfig
from app.scp.server import StorageSCP

OWN_AE = "DTG_CT01"
SCP_AE = "DICOM_GEN_SCP"


@pytest.fixture
def receiving_scp(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    storage_dir = tmp_path / "scp_storage"
    scp = StorageSCP(
        SCPConfig(enabled=True, ae_title=SCP_AE, bind_address=LOCALHOST, storage_dir=str(storage_dir))
    )
    server = scp.ae.start_server(
        (LOCALHOST, 0), block=False, evt_handlers=scp._evt_handlers
    )
    yield int(server.server_address[1]), storage_dir
    server.shutdown()


def _run(monkeypatch, capsys, tmp_path: Path, config: Path, *args: str) -> tuple[int, str]:
    argv = ["app.cli", *args, "--config", str(config), "--log-file", str(tmp_path / "cli.log")]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    out = capsys.readouterr().out
    return int(exc_info.value.code or 0), out


@pytest.mark.parametrize(
    ("response_charset", "charset_option", "expected_charset"),
    [
        (["ISO_IR 192"], None, "ISO_IR 192"),
        (["ISO_IR 192"], "jis_kana", ["ISO 2022 IR 13", "ISO 2022 IR 87"]),
        (["", "ISO 2022 IR 87"], None, ["", "ISO 2022 IR 87"]),
    ],
)
def test_worklist_exam_send_receive(
    monkeypatch, capsys, tmp_path, worklist_scp, receiving_scp,
    response_charset, charset_option, expected_charset,
) -> None:
    scp_port, storage_dir = receiving_scp
    worklist_scp.character_set = response_charset
    config = tmp_path / "app_config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "modality": {
                    "ae_title": OWN_AE,
                    "state_dir": str(tmp_path / "state"),
                    "output_dir": str(tmp_path / "output"),
                    "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_scp.port,
                                 "timeout_seconds": 5},
                    "destinations": [{"name": "LOCAL_SCP", "ae_title": SCP_AE, "host": LOCALHOST,
                                      "port": scp_port, "timeout_seconds": 5}],
                    "default_destination": "LOCAL_SCP",
                }
            }
        ),
        encoding="utf-8",
    )

    code, out = _run(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--json")
    assert code == 0
    item = next(i for i in json.loads(out)["items"] if i["accession_number"] == "A0001")

    exam_args = ["exam", "--from-worklist", item["key"], "-s", "2", "-i", "1,2",
                 "--pixel-mode", "simple_text", "--send", "--json"]
    if charset_option:
        exam_args += ["--charset", charset_option]
    code, out = _run(monkeypatch, capsys, tmp_path, config, *exam_args)
    result = json.loads(out)
    assert code == 0
    assert result["send"]["status"] == "sent"

    received = sorted(storage_dir.rglob("*.dcm"))
    assert len(received) == 3
    datasets = [pydicom.dcmread(path) for path in received]
    for ds in datasets:
        assert ds.StudyInstanceUID == "2.25.100000000000000000000000000000000001"
        assert str(ds.PatientName) == "YAMADA^TARO=山田^太郎=やまだ^たろう"
        assert ds.PatientID == "P000001"
        assert ds.IssuerOfPatientID == "DTG"
        assert ds.PatientBirthDate == "19800115"
        assert ds.PatientSex == "M"
        assert str(ds.PatientSize) == "1.72"
        assert ds.AccessionNumber == "A0001"
        assert ds.StudyID == "RP0001"
        assert ds.StudyDescription == "胸部 CT"
        assert ds.ProcedureCodeSequence[0].CodeValue == "RPC1"
        request = ds.RequestAttributesSequence[0]
        assert request.RequestedProcedureID == "RP0001"
        assert request.ScheduledProcedureStepID == "SPS0001"
        assert request.ScheduledProtocolCodeSequence[0].CodeValue == "PROT1"
        assert ds.InstitutionName == "Example Hospital"
        assert ds.Modality == "CT"
        actual_charset = ds.SpecificCharacterSet
        assert (list(actual_charset) if not isinstance(actual_charset, str) else actual_charset) == (
            expected_charset
        )
    assert len({ds.SeriesInstanceUID for ds in datasets}) == 2


def test_same_order_twice_adds_series_to_same_study(
    monkeypatch, capsys, tmp_path, worklist_scp, receiving_scp
) -> None:
    scp_port, storage_dir = receiving_scp
    config = tmp_path / "app_config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "modality": {
                    "ae_title": OWN_AE,
                    "state_dir": str(tmp_path / "state"),
                    "output_dir": str(tmp_path / "output"),
                    "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_scp.port},
                    "destinations": [{"name": "LOCAL_SCP", "ae_title": SCP_AE, "host": LOCALHOST,
                                      "port": scp_port}],
                    "default_destination": "LOCAL_SCP",
                }
            }
        ),
        encoding="utf-8",
    )
    _, out = _run(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--json")
    item = next(i for i in json.loads(out)["items"] if i["accession_number"] == "A0002")

    for _ in range(2):
        code, out = _run(
            monkeypatch, capsys, tmp_path, config, "exam", "--from-worklist", item["key"],
            "--refresh", "--pixel-mode", "simple_text", "--send", "--json",
        )
        assert code == 0
        notices = json.loads(out)["notices"]
        assert "予約に Study Instance UID が無いため、この道具が作りました" in notices
        assert "生年月日が空です" in notices

    datasets = [pydicom.dcmread(path) for path in storage_dir.rglob("*.dcm")]
    assert len(datasets) == 2
    assert len({ds.SeriesInstanceUID for ds in datasets}) == 2
    assert len({ds.StudyInstanceUID for ds in datasets}) == 1
    assert all(ds.PatientBirthDate == "" and "PatientAge" not in ds for ds in datasets)


def test_echo_to_local_storage_scp_succeeds(monkeypatch, capsys, tmp_path, receiving_scp) -> None:
    """手元の app/scp を送り先にした `echo` が「つながった」になる（spec/11 の確定事項 9）."""
    scp_port, _ = receiving_scp
    config = tmp_path / "app_config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "modality": {
                    "ae_title": OWN_AE,
                    "state_dir": str(tmp_path / "state"),
                    "output_dir": str(tmp_path / "output"),
                    "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": free_port()},
                    "destinations": [{"name": "LOCAL_SCP", "ae_title": SCP_AE, "host": LOCALHOST,
                                      "port": scp_port, "timeout_seconds": 5}],
                    "default_destination": "LOCAL_SCP",
                }
            }
        ),
        encoding="utf-8",
    )

    code, out = _run(monkeypatch, capsys, tmp_path, config, "echo", "--to", "LOCAL_SCP", "--json")

    assert code == 0
    result = json.loads(out)
    assert result["ae_title"] == SCP_AE
    assert result["status"] == 0x0000
