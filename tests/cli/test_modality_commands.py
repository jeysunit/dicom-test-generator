"""モダリティのダミーの CLI の試験：終了コードと --json の形（spec/12a の 11 章、spec/12b の 14 章）."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pydicom
import pytest
import yaml
from modality_peers import LOCALHOST, age_job, free_port

from app.cli.main import main
from app.modality.queue import STALE_SENDING_SECONDS, SendQueue

OWN_AE = "DTG_CT01"


def write_config(
    tmp_path: Path, worklist_port: int, storage_port: int, storage_ae: str = "PACS_TEST"
) -> Path:
    config = {
        "modality": {
            "ae_title": OWN_AE,
            "station_name": OWN_AE,
            "state_dir": str(tmp_path / "state"),
            "output_dir": str(tmp_path / "output"),
            "worklist": {
                "ae_title": "RIS_TEST",
                "host": LOCALHOST,
                "port": worklist_port,
                "timeout_seconds": 5,
            },
            "destinations": [
                {
                    "name": "PACS_TEST",
                    "ae_title": storage_ae,
                    "host": LOCALHOST,
                    "port": storage_port,
                    "timeout_seconds": 5,
                }
            ],
            "default_destination": "PACS_TEST",
        }
    }
    path = tmp_path / "app_config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return path


def run_cli(monkeypatch, capsys, tmp_path: Path, config: Path, *args: str) -> tuple[int, str, str]:
    argv = ["app.cli", *args, "--config", str(config), "--log-file", str(tmp_path / "cli.log")]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    captured = capsys.readouterr()
    return int(exc_info.value.code or 0), captured.out, captured.err


@pytest.fixture
def config(tmp_path, worklist_scp, storage_scp) -> Path:
    return write_config(tmp_path, worklist_scp.port, storage_scp.port)


def test_echo_ok_and_json(monkeypatch, capsys, tmp_path, config) -> None:
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "echo", "--json")

    assert code == 0
    assert json.loads(out)["ae_title"] == "PACS_TEST"

    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "echo", "--worklist")
    assert code == 0
    assert "つながった" in out


def test_echo_unreachable_is_exit_5(monkeypatch, capsys, tmp_path) -> None:
    config = write_config(tmp_path, free_port(), free_port())

    code, out, err = run_cli(monkeypatch, capsys, tmp_path, config, "echo")

    assert code == 5
    assert out == ""
    assert "could not connect" in err


def test_worklist_query_json_and_show(monkeypatch, capsys, tmp_path, config) -> None:
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--json")

    data = json.loads(out)
    assert code == 0
    assert data["worklist"] == "RIS_TEST"
    assert data["partial"] is False
    assert [item["patient_id"] for item in data["items"]] == ["P000001", "P000002"]
    key = data["items"][0]["key"]

    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "show", key, "--json")
    assert code == 0
    assert json.loads(out)["accession_number"] == "A0001"


def test_worklist_query_text_and_zero_items(monkeypatch, capsys, tmp_path, config) -> None:
    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "worklist", "query", "--modality", "any",
        "--station-aet", "any",
    )
    assert code == 0
    assert "A0003" in out
    assert "別の装置" in out

    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "worklist", "query", "--patient-id", "NONE"
    )
    assert code == 0
    assert "予約はありません" in out


def test_worklist_query_bad_date_is_exit_4(monkeypatch, capsys, tmp_path, config) -> None:
    code, _, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "worklist", "query", "--date", "2026-10-18"
    )

    assert code == 4
    assert "Date must be" in err


def test_worklist_show_unknown_key_is_exit_1(monkeypatch, capsys, tmp_path, config) -> None:
    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "show", "0000000000")

    assert code == 1
    assert "not found" in err


def test_exam_modality_mismatch_is_exit_4(
    monkeypatch, capsys, tmp_path, config
) -> None:
    run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--modality", "MR",
            "--station-aet", "any")
    state = json.loads((tmp_path / "state" / "worklist_last.json").read_text(encoding="utf-8"))
    key = state["items"][0]["key"]

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "exam", "--from-worklist", key)

    assert code == 4
    assert "予約は MR、テンプレートは CT です" in err


def test_exam_emergency_json(monkeypatch, capsys, tmp_path, config) -> None:
    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO=緊急^太郎", "--birth-date", "19800101", "--sex", "M",
        "--study-description", "緊急 CT", "-s", "2", "-i", "1,2", "--pixel-mode", "simple_text",
        "--json",
    )

    data = json.loads(out)
    assert code == 0
    assert len(data["files"]) == 3
    assert data["accession_number"] == ""
    assert Path(data["output_dir"]).name.startswith("emergency_")
    assert "予約なし（受付番号は空）" in data["notices"]
    assert data["send"] is None


def test_exam_with_profile(monkeypatch, capsys, tmp_path, config) -> None:
    """exam --profile：装置のプロファイルを重ねる。無い名前は終了コード 2（spec/13 の 8・9）."""
    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO", "--profile", "dtg_synthetic_ct",
        "--pixel-mode", "simple_text", "--json",
    )
    assert code == 0
    assert pydicom.dcmread(json.loads(out)["files"][0]).Manufacturer == "DTG Synthetic"

    code, _, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO", "--profile", "no_such_profile",
    )
    assert code == 2
    assert "no_such_profile" in err


def test_exam_emergency_unrepresentable_char_is_exit_4(
    monkeypatch, capsys, tmp_path, config
) -> None:
    code, _, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0002",
        "--patient-name", "TAKAHASHI=髙橋", "--charset", "jis", "--pixel-mode", "simple_text",
    )

    assert code == 4
    assert "髙" in err
    assert list((tmp_path / "output").rglob("*.dcm")) == []


def test_exam_emergency_requires_patient(monkeypatch, capsys, tmp_path, config) -> None:
    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "exam", "--emergency")

    assert code == 2
    assert "--patient-id" in err


def test_exam_series_and_images_must_match(monkeypatch, capsys, tmp_path, config) -> None:
    code, _, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E1",
        "--patient-name", "A^B", "-s", "2", "-i", "1",
    )

    assert code == 2


def test_send_queue_list_and_retry(
    monkeypatch, capsys, tmp_path, config, storage_scp
) -> None:
    _, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0003",
        "--patient-name", "SEND^TEST", "-i", "2", "--pixel-mode", "simple_text", "--json",
    )
    folder = json.loads(out)["output_dir"]

    storage_scp.status = 0xA700
    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "send", folder, "--json"
    )
    assert code == 5
    assert json.loads(out)["status"] == "failed"
    assert "status 0xA700" in err

    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "queue", "list", "--status", "failed", "--json"
    )
    jobs = json.loads(out)
    assert code == 0
    assert [job["num_sent"] for job in jobs] == [0]

    storage_scp.status = 0x0000
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "retry", "--all")
    assert code == 0
    assert "sent (2/2 files)" in out

    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list", "--json")
    assert [job["status"] for job in json.loads(out)] == ["sent"]


def test_send_unreachable_is_exit_5_and_recorded(
    monkeypatch, capsys, tmp_path, worklist_scp
) -> None:
    config = write_config(tmp_path, worklist_scp.port, free_port())
    _, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0004",
        "--patient-name", "SEND^TEST", "--pixel-mode", "simple_text", "--json",
    )
    folder = json.loads(out)["output_dir"]

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "send", folder)

    assert code == 5
    assert "could not connect" in err
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list", "--json")
    assert json.loads(out)[0]["status"] == "failed"


def test_stale_sending_is_listed_and_retried(
    monkeypatch, capsys, tmp_path, config, storage_scp
) -> None:
    """送信中のまま止まった件を queue list に出し、queue retry --stale で送る（8.2・11.5）."""
    _, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0005",
        "--patient-name", "STALE^TEST", "-i", "2", "--pixel-mode", "simple_text", "--json",
    )
    exam = json.loads(out)
    db_path = tmp_path / "state" / "queue.sqlite3"
    queue = SendQueue(db_path)
    job_id = queue.add_job(exam["output_dir"], "PACS_TEST", exam["files"])
    queue.mark_sending(job_id)
    age_job(db_path, job_id, STALE_SENDING_SECONDS + 60)

    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list")
    assert code == 0
    assert "[STALE]" in out
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list", "--json")
    assert [job["stale"] for job in json.loads(out)] == [True]

    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "retry", "--stale")
    assert code == 0
    assert "sent (2/2 files)" in out
    assert queue.get_job(job_id).status == "sent"


def test_bad_modality_config_is_exit_2(monkeypatch, capsys, tmp_path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("modality:\n  ae_title: 'X'\n", encoding="utf-8")

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, path, "echo")

    assert code == 2
    assert "Invalid modality configuration" in err


def test_broken_state_error_shows_no_values(monkeypatch, capsys, tmp_path, config) -> None:
    """壊れた保存のデータの誤りに、入っていた値（氏名）を出さない（spec/12 の 12 章）."""
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "worklist_last.json").write_text(
        '{"items": [{"patient_name": "SECRET^PATIENTNAME", "birth_date": 19800101}]}',
        encoding="utf-8",
    )

    code, out, err = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "show", "x")

    assert code != 0
    assert "SECRET" not in out + err
    assert "items.0" in err


def test_worklist_output_neutralizes_control_chars(
    monkeypatch, capsys, tmp_path, config, worklist_scp, worklist_items
) -> None:
    evil = dict(worklist_items[0])
    evil["requested_procedure_description"] = "\x1b]0;owned\x07胸部\x1b[2J"
    evil["patient_name"] = "EVIL^\u202eNAME"
    worklist_scp.items = [evil]

    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query")
    assert code == 0
    assert "\x1b" not in out and "\x07" not in out
    assert "\\x1b]0;owned\\x07胸部\\x1b[2J" in out

    key = json.loads(
        run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--json")[1]
    )["items"][0]["key"]
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "show", key)
    assert "\u202e" not in out and "\\u202e" in out

    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "worklist", "show", key, "--json"
    )
    assert "\x1b" not in out and "\u202e" not in out
    assert json.loads(out)["patient_name"] == "EVIL^\u202eNAME"
