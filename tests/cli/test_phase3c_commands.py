"""Phase 3c の CLI の試験：`commit`・`mpps`・`exam --mpps`・`queue list` の COMMIT（spec/12 の 11.8・11.9）."""

from __future__ import annotations

import json
import socket
import sys
from pathlib import Path

import pytest
import yaml
from modality_peers import LOCALHOST, free_port, start_mpps_recorder

from app.cli.main import main

OWN_AE = "DTG_CT01"


def write_config(
    tmp_path: Path,
    *,
    worklist_port: int,
    pacs_port: int,
    listen_port: int,
    mpps_port: int | None = None,
    storage_commitment: bool = True,
) -> Path:
    modality: dict = {
        "ae_title": OWN_AE,
        "station_name": OWN_AE,
        "state_dir": str(tmp_path / "state"),
        "output_dir": str(tmp_path / "output"),
        "listen": {"bind_address": LOCALHOST, "port": listen_port},
        "worklist": {
            "ae_title": "RIS_TEST",
            "host": LOCALHOST,
            "port": worklist_port,
            "timeout_seconds": 5,
            "use_mpps": mpps_port is not None,
        },
        "destinations": [
            {
                "name": "PACS_TEST",
                "ae_title": "PACS_TEST",
                "host": LOCALHOST,
                "port": pacs_port,
                "timeout_seconds": 5,
                "storage_commitment": storage_commitment,
            }
        ],
        "default_destination": "PACS_TEST",
        "default_pixel_mode": "simple_text",
    }
    if mpps_port is not None:
        modality["mpps"] = {"ae_title": "RIS_TEST", "host": LOCALHOST, "port": mpps_port}
    path = tmp_path / "app_config.yaml"
    path.write_text(yaml.safe_dump({"modality": modality}), encoding="utf-8")
    return path


def run_cli(monkeypatch, capsys, tmp_path: Path, config: Path, *args: str) -> tuple[int, str, str]:
    argv = ["app.cli", *args, "--config", str(config), "--log-file", str(tmp_path / "cli.log")]
    monkeypatch.setattr(sys, "argv", argv)
    with pytest.raises(SystemExit) as exc_info:
        main()
    captured = capsys.readouterr()
    return int(exc_info.value.code or 0), captured.out, captured.err


def _emergency_send(monkeypatch, capsys, tmp_path, config, *extra: str) -> dict:
    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO", "--send", "--json", *extra,
    )
    assert code == 0, err
    return json.loads(out)


def test_commit_confirmed_is_exit_0(monkeypatch, capsys, tmp_path, worklist_scp, commitment_pacs) -> None:
    listen_port = free_port()
    commitment_pacs.listener_port = listen_port
    config = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=commitment_pacs.port,
        listen_port=listen_port,
    )
    job_id = _emergency_send(monkeypatch, capsys, tmp_path, config)["send"]["job_id"]

    # CLI の send では自動で求めない（8.3.3）
    assert commitment_pacs.actions == []
    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "commit", "--job", str(job_id), "--wait", "5", "--json"
    )

    assert code == 0
    result = json.loads(out)
    assert result["status"] == "confirmed"
    assert result["num_requested"] == result["num_confirmed"] == 1
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list", "--json")
    assert json.loads(out)[0]["commitment"] == "confirmed"
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list")
    assert "COMMIT" in out and "confirmed" in out


def test_commit_failed_is_exit_5(monkeypatch, capsys, tmp_path, worklist_scp, commitment_pacs) -> None:
    listen_port = free_port()
    commitment_pacs.listener_port = listen_port
    config = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=commitment_pacs.port,
        listen_port=listen_port,
    )
    job_id = _emergency_send(monkeypatch, capsys, tmp_path, config)["send"]["job_id"]
    commitment_pacs.fail_instance_uids = {str(commitment_pacs.received[0].SOPInstanceUID)}

    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "commit", "--job", str(job_id), "--wait", "5"
    )

    assert code == 5
    assert "failed" in out
    assert "[ERROR]" in err


def test_commit_without_result_is_exit_5(monkeypatch, capsys, tmp_path, worklist_scp, commitment_pacs) -> None:
    commitment_pacs.report_path = "none"
    config = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=commitment_pacs.port,
        listen_port=free_port(),
    )
    job_id = _emergency_send(monkeypatch, capsys, tmp_path, config)["send"]["job_id"]

    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "commit", "--job", str(job_id), "--wait", "1",
        "--json",
    )

    assert code == 5
    assert json.loads(out)["status"] == "waiting"


def test_commit_destination_without_commitment_is_exit_2(
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp
) -> None:
    config = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=storage_scp.port,
        listen_port=free_port(), storage_commitment=False,
    )
    job_id = _emergency_send(monkeypatch, capsys, tmp_path, config)["send"]["job_id"]

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "commit", "--job", str(job_id))

    assert code == 2
    assert "storage commitment" in err


def test_commit_listener_port_in_use_is_exit_2(
    monkeypatch, capsys, tmp_path, worklist_scp, commitment_pacs
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as busy:
        busy.bind((LOCALHOST, 0))
        busy.listen()
        config = write_config(
            tmp_path, worklist_port=worklist_scp.port, pacs_port=commitment_pacs.port,
            listen_port=int(busy.getsockname()[1]),
        )
        job_id = _emergency_send(monkeypatch, capsys, tmp_path, config)["send"]["job_id"]

        code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "commit", "--job", str(job_id))

    assert code == 2
    assert "listener" in err
    # 待ち受けを立てられないときは N-ACTION を送らない
    assert commitment_pacs.actions == []


def test_exam_mpps_json_and_mpps_list(monkeypatch, capsys, tmp_path, worklist_scp, storage_scp, mpps_scp) -> None:
    config = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=storage_scp.port,
        listen_port=free_port(), mpps_port=mpps_scp.port, storage_commitment=False,
    )

    result = _emergency_send(monkeypatch, capsys, tmp_path, config)

    assert result["mpps"]["state"] == "COMPLETED"
    assert result["mpps"]["sent"] is True
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "mpps", "list", "--json")
    assert code == 0
    rows = json.loads(out)
    assert [(row["state"], row["sent"]) for row in rows] == [("COMPLETED", True)]

    result = _emergency_send(monkeypatch, capsys, tmp_path, config, "--no-mpps")
    assert result["mpps"] is None


def test_exam_mpps_failure_warns_and_retry(monkeypatch, capsys, tmp_path, worklist_scp, storage_scp) -> None:
    """MPPS を送れなくても撮影は 0。`[WARN]` を出し、`mpps retry` で送る（11.4・11.9）.

    送り先は行に固定するので、落ちていた相手が同じポートで戻ってから送り直す（8.4.1）。
    """
    mpps_port = free_port()
    down = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=storage_scp.port,
        listen_port=free_port(), mpps_port=mpps_port, storage_commitment=False,
    )
    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, down, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO",
    )
    assert code == 0
    assert "[WARN] MPPS" in err

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, down, "mpps", "retry")
    assert code == 5

    back, server = start_mpps_recorder(mpps_port)
    try:
        code, out, _ = run_cli(monkeypatch, capsys, tmp_path, down, "mpps", "retry")
    finally:
        server.shutdown()
    assert code == 0
    assert "COMPLETED" in out
    assert len(back.sets) == 1
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, down, "mpps", "list")
    assert "COMPLETED" in out and "sent" in out


def test_mpps_retry_without_mpps_is_exit_2(monkeypatch, capsys, tmp_path, worklist_scp, storage_scp) -> None:
    config = write_config(
        tmp_path, worklist_port=worklist_scp.port, pacs_port=storage_scp.port,
        listen_port=free_port(), storage_commitment=False,
    )
    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "mpps", "retry")
    assert code == 2
    assert "use_mpps" in err
