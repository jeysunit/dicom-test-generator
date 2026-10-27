"""統合の試験：CR・DX の予約と緊急の患者を CLI で撮り、偽の PACS が受ける（ADR-0034）."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from modality_peers import LOCALHOST

from app.cli.main import main
from app.core.projection import CR_IMAGE_STORAGE, DX_IMAGE_STORAGE_FOR_PRESENTATION

OWN_AE = "DTG_CR01"
PEER_AE = "PACS_TEST"
# 合成の患者の CR の予約（試験の中だけで MWL の SCP に足す）
CR_ITEM = {
    "patient_name": "XRAY^HANAKO",
    "patient_id": "P000077",
    "birth_date": "19700101",
    "sex": "F",
    "study_instance_uid": "2.25.100000000000000000000000000000000077",
    "accession_number": "A0077",
    "requested_procedure_id": "RP0077",
    "requested_procedure_description": "胸部 X 線",
    "sps": {
        "station_ae_title": OWN_AE,
        "start_date": "TODAY",
        "start_time": "110000",
        "modality": "CR",
        "id": "SPS0077",
        "description": "胸部 2方向",
    },
}


def _run(monkeypatch, capsys, tmp_path: Path, config: Path, *args: str) -> tuple[int, str]:
    argv = ["app.cli", *args, "--config", str(config), "--log-file", str(tmp_path / "cli.log")]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    out = capsys.readouterr().out
    return int(exc_info.value.code or 0), out


def _config(tmp_path: Path, worklist_port: int, storage_port: int) -> Path:
    config = tmp_path / "app_config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "modality": {
                    "ae_title": OWN_AE,
                    "state_dir": str(tmp_path / "state"),
                    "output_dir": str(tmp_path / "output"),
                    "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST,
                                 "port": worklist_port, "timeout_seconds": 5},
                    "destinations": [{"name": PEER_AE, "ae_title": PEER_AE, "host": LOCALHOST,
                                      "port": storage_port, "timeout_seconds": 5}],
                    "default_destination": PEER_AE,
                }
            }
        ),
        encoding="utf-8",
    )
    return config


def test_cr_order_is_taken_and_sent(monkeypatch, capsys, tmp_path, worklist_scp, storage_scp) -> None:
    worklist_scp.items.append(CR_ITEM)
    config = _config(tmp_path, worklist_scp.port, storage_scp.port)
    code, out = _run(
        monkeypatch, capsys, tmp_path, config, "worklist", "query", "--modality", "CR", "--json"
    )
    assert code == 0
    item = next(i for i in json.loads(out)["items"] if i["accession_number"] == "A0077")

    code, out = _run(
        monkeypatch, capsys, tmp_path, config, "exam", "--from-worklist", item["key"],
        "-m", "cr_generic", "--pixel-mode", "phantom", "--send", "--json",
    )

    assert code == 0, out
    assert json.loads(out)["send"]["status"] == "sent"
    received = sorted(storage_scp.received, key=lambda ds: int(ds.SeriesNumber))
    assert [(ds.Modality, ds.ViewPosition, ds.SOPClassUID) for ds in received] == [
        ("CR", "PA", CR_IMAGE_STORAGE),
        ("CR", "LL", CR_IMAGE_STORAGE),
    ]
    for ds in received:
        assert ds.AccessionNumber == "A0077"
        assert ds.StudyInstanceUID == CR_ITEM["study_instance_uid"]
        assert ds.Manufacturer == "DTG SYNTHETIC"
        assert "FrameOfReferenceUID" not in ds


def test_dx_emergency_patient_is_taken_and_sent(
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp
) -> None:
    config = _config(tmp_path, worklist_scp.port, storage_scp.port)

    code, out = _run(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO", "-m", "dx_generic", "--routine", "dx_knee",
        "--send", "--json",
    )

    assert code == 0, out
    received = storage_scp.received
    assert [(ds.Modality, ds.ViewPosition, ds.ImageLaterality) for ds in received] == [
        ("DX", "AP", "R"),
        ("DX", "LL", "R"),
    ]
    assert {ds.SOPClassUID for ds in received} == {DX_IMAGE_STORAGE_FOR_PRESENTATION}
    assert {ds.BurnedInAnnotation for ds in received} == {"NO"}
