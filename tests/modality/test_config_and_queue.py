"""設定（modality: の節）と待ち行列（sqlite3）の試験."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
import yaml
from modality_peers import age_job

from app.core.exceptions import ModalityConfigError, ModalityError
from app.modality.config import load_modality_config
from app.modality.queue import STALE_SENDING_SECONDS, SendQueue
from app.modality.store_scu import StoreFileResult

REPO_CONFIG = Path(__file__).resolve().parents[2] / "config" / "app_config.yaml"


def _write(tmp_path: Path, modality: dict) -> Path:
    path = tmp_path / "app_config.yaml"
    path.write_text(yaml.safe_dump({"modality": modality}, allow_unicode=True), encoding="utf-8")
    return path


def _minimal() -> dict:
    return {
        "ae_title": "DTG_CT01",
        "worklist": {"ae_title": "RIS_TEST", "host": "127.0.0.1", "port": 4242},
        "destinations": [
            {"name": "PACS_TEST", "ae_title": "PACS_TEST", "host": "pacs.example.org", "port": 104}
        ],
        "default_destination": "PACS_TEST",
    }


def test_repository_config_has_valid_modality_section() -> None:
    config = load_modality_config(REPO_CONFIG)

    assert config.listen.port == 11113
    assert config.character_set == "auto"
    assert config.character_set_fallback == "utf8"
    assert config.default_template == "ct_generic"
    assert config.destination().name == config.default_destination


def test_minimal_config_defaults(tmp_path) -> None:
    config = load_modality_config(_write(tmp_path, _minimal()))

    assert config.retry.max_attempts == 0
    assert config.worklist.timeout_seconds == 30
    assert config.destination("PACS_TEST").host == "pacs.example.org"


@pytest.mark.parametrize(
    "change",
    [
        {"ae_title": "A" * 17},
        {"ae_title": "   "},
        {"ae_title": "BAD\\AE"},
        {"character_set_fallback": "auto"},
        {"character_set": "latin1"},
        {"default_destination": "NOPE"},
    ],
)
def test_invalid_config_is_config_error(tmp_path, change) -> None:
    raw = {**_minimal(), **change}

    with pytest.raises(ModalityConfigError):
        load_modality_config(_write(tmp_path, raw))


def _stations(*stations: dict, default: str | None = None) -> dict:
    raw = {key: value for key, value in _minimal().items() if key != "ae_title"}
    raw["stations"] = list(stations)
    if default is not None:
        raw["default_station"] = default
    return raw


CT1 = {"name": "CT1号機", "ae_title": "DTG_CT01", "station_name": "DTG_CT01"}
MR1 = {"name": "MR1号機", "ae_title": "DTG_MR01", "station_name": "DTG_MR01"}


def test_config_reads_two_stations(tmp_path) -> None:
    """設定に装置を複数書ける（docs/spec/12 の 12 章・openspec の station-identity）."""
    config = load_modality_config(_write(tmp_path, _stations(CT1, MR1, default="MR1号機")))

    assert [station.name for station in config.stations] == ["CT1号機", "MR1号機"]
    assert config.default_station == "MR1号機"
    assert config.station("MR1号機").ae_title == "DTG_MR01"
    # 既定の装置の値は、今までの ae_title・station_name としても読める
    assert (config.ae_title, config.station_name) == ("DTG_MR01", "DTG_MR01")


def test_default_station_is_the_first_one(tmp_path) -> None:
    config = load_modality_config(_write(tmp_path, _stations(CT1, MR1)))

    assert config.default_station == "CT1号機"
    assert config.ae_title == "DTG_CT01"


def test_config_without_stations_is_one_station(tmp_path) -> None:
    raw = {**_minimal(), "station_name": "ST01"}
    config = load_modality_config(_write(tmp_path, raw))

    [station] = config.stations
    assert (station.name, station.ae_title, station.station_name) == ("DTG_CT01", "DTG_CT01", "ST01")
    assert config.default_station == "DTG_CT01"


@pytest.mark.parametrize(
    "raw",
    [
        _stations(CT1, {**MR1, "ae_title": "DTG_CT01"}),  # AE タイトルの重複
        _stations(CT1, {**MR1, "name": "CT1号機"}),  # 表示名の重複
        _stations(CT1, default="XR9号機"),  # 一覧に無い既定
        _stations({**CT1, "ae_title": "A" * 17}),  # AE の VR に合わない
        _stations({**CT1, "station_name": "S" * 17}),  # SH は 16 文字まで
        _stations({**CT1, "station_name": "A\\B"}),  # SH に `\` は入れない
        _stations({**CT1, "station_name": "A\x7fB"}),  # 制御文字（DEL）も入れない
        {**_stations(CT1), "ae_title": "DTG_XX01"},  # 一覧と食い違う今の形の値
        _stations(),  # 空の一覧
    ],
)
def test_invalid_stations_are_config_errors(tmp_path, raw) -> None:
    with pytest.raises(ModalityConfigError):
        load_modality_config(_write(tmp_path, raw))


def test_station_ae_titles_are_compared_without_padding(tmp_path) -> None:
    """装置の AE タイトルの前後の空白はそろえる（PS3.5 の AE）。空白だけ違うものは重複."""
    config = load_modality_config(_write(tmp_path, _stations({**CT1, "ae_title": " DTG_CT01 "})))
    assert config.stations[0].ae_title == "DTG_CT01"

    with pytest.raises(ModalityConfigError):
        load_modality_config(_write(tmp_path, _stations(CT1, {**MR1, "ae_title": "DTG_CT01 "})))


def test_unknown_station_name(tmp_path) -> None:
    config = load_modality_config(_write(tmp_path, _stations(CT1, MR1)))

    with pytest.raises(ModalityConfigError):
        config.station("XR9号機")


def test_missing_section_and_file(tmp_path) -> None:
    path = tmp_path / "other.yaml"
    path.write_text("profiles: {}\n", encoding="utf-8")

    with pytest.raises(ModalityConfigError):
        load_modality_config(path)
    with pytest.raises(ModalityConfigError):
        load_modality_config(tmp_path / "missing.yaml")


def test_unknown_destination(tmp_path) -> None:
    config = load_modality_config(_write(tmp_path, _minimal()))

    with pytest.raises(ModalityConfigError):
        config.destination("OTHER")


def test_queue_records_results_and_retry_targets(tmp_path) -> None:
    queue = SendQueue(tmp_path / "state" / "queue.sqlite3")
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm", "b.dcm"], accession_number="A0001")

    queue.mark_sending(job_id)
    status = queue.record_results(
        job_id,
        [
            StoreFileResult(path="a.dcm", sop_instance_uid="1", status=0, outcome="success"),
            StoreFileResult(
                path="b.dcm", sop_instance_uid="2", status=0xA700, outcome="failure",
                reason="status 0xA700",
            ),
        ],
    )

    job = queue.get_job(job_id)
    assert status == "failed"
    assert job.num_files == 2
    assert job.num_sent == 1
    assert job.attempts == 1
    assert job.last_error == "status 0xA700"
    assert queue.unsent_files(job_id) == ["b.dcm"]
    assert [j.id for j in queue.list_jobs("failed")] == [job_id]
    assert queue.list_jobs("sent") == []


def test_queue_job_failure_and_counters(tmp_path) -> None:
    queue = SendQueue(tmp_path / "queue.sqlite3")
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm"])

    queue.record_job_failure(job_id, "could not connect")

    assert queue.get_job(job_id).status == "failed"
    assert queue.next_value("pps") == 1
    assert queue.next_value("pps") == 2
    assert queue.next_value("study") == 1
    with pytest.raises(ModalityError):
        queue.list_jobs("unknown")
    with pytest.raises(ModalityError):
        queue.get_job(999)


def test_mark_sending_only_from_pending_or_failed(tmp_path) -> None:
    """同じ件を2つの手順が同時に送らない（docs/spec/12 の 8.2）."""
    queue = SendQueue(tmp_path / "queue.sqlite3")
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm"])

    queue.mark_sending(job_id)
    with pytest.raises(ModalityError) as exc_info:
        queue.mark_sending(job_id)
    assert exc_info.value.details["status"] == "sending"
    assert queue.get_job(job_id).attempts == 1

    queue.record_job_failure(job_id, "could not connect")
    queue.mark_sending(job_id)
    queue.record_results(
        job_id, [StoreFileResult(path="a.dcm", sop_instance_uid="1", status=0, outcome="success")]
    )
    with pytest.raises(ModalityError):
        queue.mark_sending(job_id)
    with pytest.raises(ModalityError):
        queue.mark_sending(999)


def test_stale_sending_is_listed_and_reset_to_failed(tmp_path) -> None:
    db_path = tmp_path / "queue.sqlite3"
    queue = SendQueue(db_path)
    stale_id = queue.add_job("exam1", "PACS_TEST", ["a.dcm"])
    fresh_id = queue.add_job("exam2", "PACS_TEST", ["b.dcm"])
    queue.mark_sending(stale_id)
    queue.mark_sending(fresh_id)
    age_job(db_path, stale_id, STALE_SENDING_SECONDS + 60)

    assert [(job.id, job.stale) for job in queue.list_jobs()] == [
        (stale_id, True),
        (fresh_id, False),
    ]

    assert queue.reset_stale_sending() == [stale_id]

    stale = queue.get_job(stale_id)
    assert stale.status == "failed"
    assert stale.stale is False
    assert "stale" in stale.last_error
    assert queue.get_job(fresh_id).status == "sending"
    assert queue.reset_stale_sending() == []


def test_progress_keeps_long_send_fresh(tmp_path) -> None:
    """送っている間はファイルごとに時刻を進め、長い送信を止まったとみなさない（8.2）."""
    db_path = tmp_path / "queue.sqlite3"
    queue = SendQueue(db_path)
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm", "b.dcm"])
    token = queue.mark_sending(job_id)
    age_job(db_path, job_id, STALE_SENDING_SECONDS + 60)

    queue.touch_sending(job_id, token)

    assert queue.get_job(job_id).stale is False
    assert queue.reset_stale_sending() == []


def test_old_sender_cannot_overwrite_after_stale_takeover(tmp_path) -> None:
    """止まったとみなして引き取った後、古い手順は進み・結果・失敗を書けない（8.2）."""
    db_path = tmp_path / "queue.sqlite3"
    queue = SendQueue(db_path)
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm"])
    old_token = queue.mark_sending(job_id)
    age_job(db_path, job_id, STALE_SENDING_SECONDS + 60)
    assert queue.reset_stale_sending() == [job_id]
    new_token = queue.mark_sending(job_id)
    assert new_token != old_token
    success = [StoreFileResult(path="a.dcm", sop_instance_uid="1", status=0, outcome="success")]
    failure = [
        StoreFileResult(
            path="a.dcm", sop_instance_uid="1", status=0xA700, outcome="failure",
            reason="status 0xA700",
        )
    ]

    with pytest.raises(ModalityError):
        queue.touch_sending(job_id, old_token)
    with pytest.raises(ModalityError):
        queue.record_results(job_id, failure, token=old_token)
    with pytest.raises(ModalityError):
        queue.record_job_failure(job_id, "late failure", token=old_token)
    assert queue.get_job(job_id).status == "sending"
    assert queue.unsent_files(job_id) == ["a.dcm"]

    assert queue.record_results(job_id, success, token=new_token) == "sent"
    assert queue.get_job(job_id).last_error == ""


def test_queue_adds_token_column_to_older_database(tmp_path) -> None:
    db_path = tmp_path / "queue.sqlite3"
    with closing(sqlite3.connect(db_path)) as conn, conn:
        conn.execute(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL,"
            " updated_at TEXT NOT NULL, folder TEXT NOT NULL, destination TEXT NOT NULL,"
            " accession_number TEXT NOT NULL DEFAULT '', status TEXT NOT NULL,"
            " attempts INTEGER NOT NULL DEFAULT 0, last_error TEXT NOT NULL DEFAULT '')"
        )

    queue = SendQueue(db_path)
    job_id = queue.add_job("exam", "PACS_TEST", ["a.dcm"])

    assert queue.mark_sending(job_id)
