"""モダリティのダミーの CLI の試験：終了コードと --json の形（docs/spec/12a の 11 章、docs/development.md の 4 章）."""

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
    assert "接続できました" in out


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
    """exam --profile：装置のプロファイルを重ねる。無い名前は終了コード 2（docs/spec/13 の 8・9）."""
    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0001",
        "--patient-name", "KINKYU^TARO", "--profile", "dtg_synthetic_ct", "-s", "1",
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
    # どの欄かは出すが、表せない字そのもの（氏名の一部）は出さない
    assert "氏名（漢字）" in err
    assert "髙" not in err
    assert list((tmp_path / "output").rglob("*.dcm")) == []


def test_exam_emergency_requires_patient(monkeypatch, capsys, tmp_path, config) -> None:
    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "exam", "--emergency")

    assert code == 2
    assert "--patient-id" in err


def test_exam_without_images_fills_one_per_series(monkeypatch, capsys, tmp_path, config) -> None:
    """-i を省いたら、シリーズごとに 1 枚（-s 3 なら 1,1,1。docs/spec/12a の 10.5）."""
    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0003",
        "--patient-name", "KINKYU^TARO", "-s", "3", "--pixel-mode", "simple_text", "--json",
    )

    data = json.loads(out)
    assert code == 0
    assert len(data["files"]) == 3
    series_numbers = {int(pydicom.dcmread(path).SeriesNumber) for path in data["files"]}
    assert series_numbers == {1, 2, 3}


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


def test_queue_retry_job_resends_a_sent_job_as_a_new_job(
    monkeypatch, capsys, tmp_path, config, storage_scp
) -> None:
    """`queue retry --job` は送信完了の件も受け、新しい件として送る（8.2・11.5）."""
    _, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0006",
        "--patient-name", "RESEND^TEST", "-i", "2", "--pixel-mode", "simple_text", "--json",
    )
    folder = json.loads(out)["output_dir"]
    _, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "send", folder, "--json")
    first_job = json.loads(out)["job_id"]

    code, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "queue", "retry", "--job", str(first_job), "--json"
    )

    assert code == 0
    [result] = json.loads(out)
    assert result["status"] == "sent" and result["job_id"] != first_job
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "queue", "list", "--json")
    assert [job["status"] for job in json.loads(out)] == ["sent", "sent"]
    assert len(storage_scp.received) == 4


def test_send_unreachable_is_exit_5_and_recorded(
    monkeypatch, capsys, tmp_path, worklist_scp
) -> None:
    config = write_config(tmp_path, worklist_scp.port, free_port())
    _, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0004",
        "--patient-name", "SEND^TEST", "-s", "1", "--pixel-mode", "simple_text", "--json",
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
    """壊れた保存のデータの誤りに、入っていた値（氏名）を出さない（docs/spec/12 の 12 章）."""
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


def _two_station_config(tmp_path: Path, worklist_port: int, storage_port: int) -> Path:
    path = write_config(tmp_path, worklist_port, storage_port)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    modality = data["modality"]
    del modality["ae_title"], modality["station_name"]
    modality["stations"] = [
        {"name": "CT1", "ae_title": "DTG_CT01", "station_name": "DTG_CT01"},
        {"name": "MR1", "ae_title": "DTG_MR01", "station_name": "DTG_MR01"},
    ]
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_station_option_applies_to_one_command(
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp
) -> None:
    """`--station` \u306f\u305d\u306e\u30b3\u30de\u30f3\u30c9\u3060\u3051\u306b\u52b9\u304f\uff08docs/spec/12a \u306e 11 \u7ae0\u30fbADR-0023\uff09."""
    config = _two_station_config(tmp_path, worklist_scp.port, storage_scp.port)
    _, out, _ = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--patient-id", "E0007",
        "--patient-name", "STATION^TEST", "-s", "1", "--pixel-mode", "simple_text", "--json",
        "--station", "MR1",
    )
    folder = json.loads(out)["output_dir"]
    image = pydicom.dcmread(next(Path(folder).glob("*.dcm")), stop_before_pixels=True)
    assert image.file_meta.SourceApplicationEntityTitle == "DTG_MR01"

    # \u9001\u4fe1\u306f\u3001\u753b\u50cf\u3092\u4f5c\u3063\u305f\u88c5\u7f6e\uff08MR1\uff09\u306e AE \u30bf\u30a4\u30c8\u30eb\u3067\u540d\u4e57\u308b
    code, _, _ = run_cli(monkeypatch, capsys, tmp_path, config, "send", folder)
    assert code == 0
    assert storage_scp.calling_ae_titles[-1] == "DTG_MR01"
    # \u8a18\u9332\u306f\u5909\u3048\u3066\u3044\u306a\u3044\u306e\u3067\u3001\u307b\u304b\u306e\u30b3\u30de\u30f3\u30c9\u306f\u65e2\u5b9a\u306e\u88c5\u7f6e\uff08CT1\uff09\u3067\u540d\u4e57\u308b
    code, _, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query")
    assert code == 0
    assert worklist_scp.calling_ae_titles[-1] == "DTG_CT01"


def test_unknown_station_option_is_exit_2(
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp
) -> None:
    config = _two_station_config(tmp_path, worklist_scp.port, storage_scp.port)

    code, _, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "worklist", "query", "--station", "XR9"
    )

    assert code == 2
    assert "Station not found" in err
    assert worklist_scp.queries == []


def _a0001_key(monkeypatch, capsys, tmp_path, config) -> str:
    _, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query", "--json")
    return next(i for i in json.loads(out)["items"] if i["accession_number"] == "A0001")["key"]


def test_exam_twice_needs_append(monkeypatch, capsys, tmp_path, config) -> None:
    """撮影済みの予約は `--append` で追加撮影する（docs/spec/12a の 11.4・ADR-0024）."""
    key = _a0001_key(monkeypatch, capsys, tmp_path, config)
    args = ("exam", "--from-worklist", key, "-s", "1", "--pixel-mode", "simple_text")

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, *args, "--append")
    assert code == 4 and "まだ撮影していません" in err

    assert run_cli(monkeypatch, capsys, tmp_path, config, *args)[0] == 0
    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, *args)
    assert code == 4 and "撮影済みです" in err
    assert run_cli(monkeypatch, capsys, tmp_path, config, *args, "--append")[0] == 0

    _, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, "worklist", "query")
    assert "撮影済み" in out


def test_append_is_refused_in_new_order_mode(
    monkeypatch, capsys, tmp_path, worklist_scp, storage_scp
) -> None:
    config = write_config(tmp_path, worklist_scp.port, storage_scp.port)
    data = yaml.safe_load(config.read_text(encoding="utf-8"))
    data["modality"]["retake_mode"] = "new_order"
    config.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    key = _a0001_key(monkeypatch, capsys, tmp_path, config)
    args = ("exam", "--from-worklist", key, "-s", "1", "--pixel-mode", "simple_text")
    assert run_cli(monkeypatch, capsys, tmp_path, config, *args)[0] == 0

    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, *args, "--append")

    assert code == 4
    assert "撮り直しの予約が要ります" in err


def test_emergency_append_study_uid_json(monkeypatch, capsys, tmp_path) -> None:
    config = write_config(tmp_path, 104, 104)
    args = ("exam", "--emergency", "--patient-id", "E1", "--patient-name", "UNKNOWN^ONE",
            "-s", "1", "-i", "1", "--pixel-mode", "simple_text", "--json")
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, *args)
    assert code == 0
    uid = json.loads(out)["study_instance_uid"]
    code, out, _ = run_cli(monkeypatch, capsys, tmp_path, config, *args,
                           "--append", "--study-uid", uid)
    assert code == 0
    data = json.loads(out)
    assert data["study_instance_uid"] == uid
    assert pydicom.dcmread(data["files"][0]).SeriesNumber == 2


@pytest.mark.parametrize("source", [("--from-worklist", "some-key"), ("--emergency",)])
def test_study_uid_requires_emergency_append(monkeypatch, capsys, tmp_path, source) -> None:
    config = write_config(tmp_path, 104, 104)
    code, _, err = run_cli(monkeypatch, capsys, tmp_path, config, "exam", *source,
                           "--study-uid", "2.25.123")
    assert code == 2
    assert "--study-uid is only for --emergency --append" in err
    assert list(tmp_path.rglob("*.dcm")) == []


def test_emergency_append_requires_study_uid(monkeypatch, capsys, tmp_path) -> None:
    config = write_config(tmp_path, 104, 104)
    code, _, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", "--append",
        "--patient-id", "E1", "--patient-name", "UNKNOWN^ONE",
    )
    assert code == 2
    assert "--emergency --append requires --study-uid" in err
    assert list(tmp_path.rglob("*.dcm")) == []


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--patient-name", "山田^太郎"], "氏名（英字）は半角の英字"),
        (["--patient-name", "YAMADA^TARO=ﾔﾏﾀﾞ"], "氏名（漢字）に使えない字"),
        (["--patient-name", "YAMADA^TARO", "--patient-id", "患者01"], "患者ID は半角の英数字"),
        (["--patient-name", "YAMADA^TARO", "--birth-date", "20230229"], "暦にある日付"),
        (["--patient-name", "YAMADA^TARO", "--birth-date", "20991231"], "今日以前"),
        (["--patient-name", "A" * 65], "64 字以内"),
        (["--patient-name", "YAMADA^TARO", "--study-description", "あ" * 65], "検査名は 64 字以内"),
    ],
)
def test_exam_emergency_bad_input_is_refused_in_japanese(
    monkeypatch, capsys, tmp_path, config, extra, message
) -> None:
    args = ["--patient-id", "E0009", *extra]
    code, _, err = run_cli(
        monkeypatch, capsys, tmp_path, config, "exam", "--emergency", *args,
        "--pixel-mode", "simple_text",
    )

    assert code == 4
    assert message in err
    assert list((tmp_path / "output").rglob("*.dcm")) == []
