"""統合の試験：MWL の SCP → `exam --from-worklist --send` → 偽の PACS が受ける（docs/development.md の 4 章）."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml
from modality_peers import LOCALHOST

from app.cli.main import main

OWN_AE = "DTG_CT01"
PEER_AE = "PACS_TEST"


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
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp,
    response_charset, charset_option, expected_charset,
) -> None:
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
                    "destinations": [{"name": PEER_AE, "ae_title": PEER_AE, "host": LOCALHOST,
                                      "port": storage_scp.port, "timeout_seconds": 5}],
                    "default_destination": PEER_AE,
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

    datasets = storage_scp.received
    assert len(datasets) == 3
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
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp
) -> None:
    config = tmp_path / "app_config.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "modality": {
                    "ae_title": OWN_AE,
                    "state_dir": str(tmp_path / "state"),
                    "output_dir": str(tmp_path / "output"),
                    "worklist": {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": worklist_scp.port},
                    "destinations": [{"name": PEER_AE, "ae_title": PEER_AE, "host": LOCALHOST,
                                      "port": storage_scp.port}],
                    "default_destination": PEER_AE,
                }
            }
        ),
        encoding="utf-8",
    )
    _, out = _run(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--json")
    item = next(i for i in json.loads(out)["items"] if i["accession_number"] == "A0002")

    # 2回目は撮影済みの予約の追加撮影（docs/spec/12 の 6.3。通常の撮影は断られる）
    for extra in ([], ["--append"]):
        code, out = _run(
            monkeypatch, capsys, tmp_path, config, "exam", "--from-worklist", item["key"],
            "--refresh", "--pixel-mode", "simple_text", "--send", "--json", *extra,
        )
        assert code == 0
        notices = json.loads(out)["notices"]
        assert "予約に Study Instance UID が無いため、このツールが生成しました" in notices
        assert "生年月日が空です" in notices

    datasets = storage_scp.received
    assert len(datasets) == 2
    assert len({ds.SeriesInstanceUID for ds in datasets}) == 2
    assert len({ds.StudyInstanceUID for ds in datasets}) == 1
    assert all(ds.PatientBirthDate == "" and "PatientAge" not in ds for ds in datasets)
