"""CLI の exam のルーチン（--routine・--routine-images と既定の当て方。ADR-0025）."""

from __future__ import annotations

import json

import pytest
from tests.cli.test_modality_commands import run_cli, write_config

EMERGENCY = ("exam", "--emergency", "--patient-id", "E0001", "--patient-name", "KINKYU^TARO")


@pytest.fixture
def config(tmp_path, worklist_scp, storage_scp):
    return write_config(tmp_path, worklist_scp.port, storage_scp.port)


def test_without_series_options_the_matched_routine_is_used(
    monkeypatch, capsys, tmp_path, config
) -> None:
    """-s・-i・--routine を省くと、予約に当てたルーチン（緊急の患者は CT の既定の胸部 単純）."""
    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, config, *EMERGENCY,
        "--routine-images", "1,1,1,1,1,1", "--pixel-mode", "simple_text", "--json",
    )

    assert code == 0, err
    payload = json.loads(out)
    assert payload["routine"] == "ct_chest_plain"
    assert len(payload["files"]) == 6


def test_named_routine_and_text_output(monkeypatch, capsys, tmp_path, config) -> None:
    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, config, *EMERGENCY,
        "--routine", "ct_head_plain", "--routine-images", "1,2,2,1", "--pixel-mode", "simple_text",
    )

    assert code == 0, err
    assert "(6 files" in out and "routine: ct_head_plain" in out


@pytest.mark.parametrize(
    "extra",
    [
        ("--routine", "ct_chest_plain", "-s", "2"),
        ("--routine-images", "1,1", "-i", "1"),
        ("--routine", "ct_chest_plain", "--routine-images", "1,60"),
        ("--routine-images", "1,x"),
    ],
)
def test_routine_input_errors_exit_4(monkeypatch, capsys, tmp_path, config, extra) -> None:
    code, _, _ = run_cli(monkeypatch, capsys, tmp_path, config, *EMERGENCY, *extra)

    assert code == 4


def test_manual_series_stay_as_before(monkeypatch, capsys, tmp_path, config) -> None:
    code, out, err = run_cli(
        monkeypatch, capsys, tmp_path, config, *EMERGENCY,
        "-s", "2", "-i", "1,2", "--pixel-mode", "simple_text", "--json",
    )

    assert code == 0, err
    payload = json.loads(out)
    assert payload["routine"] is None
    assert len(payload["files"]) == 3
