"""送信の待ち行列と送った履歴（sqlite3。spec/12_modality_emulator.md 8.2）."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.core.exceptions import ModalityError

from .store_scu import StoreFileResult

JobStatus = Literal["pending", "sending", "sent", "failed"]
JOB_STATUSES: tuple[str, ...] = ("pending", "sending", "sent", "failed")
QUEUE_DB_NAME = "queue.sqlite3"

_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        folder TEXT NOT NULL,
        destination TEXT NOT NULL,
        accession_number TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_files (
        job_id INTEGER NOT NULL REFERENCES jobs(id),
        path TEXT NOT NULL,
        sop_instance_uid TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL,
        status_code INTEGER,
        error TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (job_id, path)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS counters (
        name TEXT PRIMARY KEY,
        value INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS generated_study_uids (
        worklist_key TEXT PRIMARY KEY,
        study_instance_uid TEXT NOT NULL
    )
    """,
)


class QueueJob(BaseModel):
    model_config = {"frozen": True}

    id: int
    created_at: str
    updated_at: str
    folder: str
    destination: str
    accession_number: str
    status: JobStatus
    attempts: int
    last_error: str
    num_files: int
    num_sent: int


class SendQueue:
    """待ち行列。1件は1つの検査（1つのフォルダ）を1つの送り先へ送ること."""

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                for statement in _SCHEMA:
                    conn.execute(statement)
        except (OSError, sqlite3.Error) as exc:
            raise ModalityError(
                f"Failed to open the send queue: {db_path}",
                {"db_path": str(db_path), "reason": str(exc)},
            ) from exc

    def add_job(
        self, folder: str, destination: str, files: Sequence[str], accession_number: str = ""
    ) -> int:
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (created_at, updated_at, folder, destination, accession_number,"
                " status) VALUES (?, ?, ?, ?, ?, 'pending')",
                (now, now, folder, destination, accession_number),
            )
            job_id = int(cursor.lastrowid or 0)
            conn.executemany(
                "INSERT INTO job_files (job_id, path, status) VALUES (?, ?, 'pending')",
                [(job_id, path) for path in files],
            )
        return job_id

    def mark_sending(self, job_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET status = 'sending', attempts = attempts + 1, updated_at = ?"
                " WHERE id = ?",
                (_now(), job_id),
            )

    def record_results(self, job_id: int, results: Sequence[StoreFileResult]) -> JobStatus:
        """ファイルごとの結果を残し、検査の状態（送れた・失敗）を決めて返す."""
        with self._connect() as conn:
            for result in results:
                conn.execute(
                    "UPDATE job_files SET sop_instance_uid = ?, status = ?, status_code = ?,"
                    " error = ? WHERE job_id = ? AND path = ?",
                    (
                        result.sop_instance_uid,
                        "sent" if result.sent else "failed",
                        result.status,
                        result.reason,
                        job_id,
                        result.path,
                    ),
                )
            failed = conn.execute(
                "SELECT error FROM job_files WHERE job_id = ? AND status != 'sent'", (job_id,)
            ).fetchall()
            status: JobStatus = "failed" if failed else "sent"
            last_error = failed[0][0] if failed else ""
            conn.execute(
                "UPDATE jobs SET status = ?, last_error = ?, updated_at = ? WHERE id = ?",
                (status, last_error, _now(), job_id),
            )
        return status

    def record_job_failure(self, job_id: int, reason: str) -> None:
        """Association を張れないなど、ファイルに届く前の失敗を残す."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE job_files SET status = 'failed', error = ? WHERE job_id = ?"
                " AND status != 'sent'",
                (reason, job_id),
            )
            conn.execute(
                "UPDATE jobs SET status = 'failed', last_error = ?, updated_at = ? WHERE id = ?",
                (reason, _now(), job_id),
            )

    def unsent_files(self, job_id: int) -> list[str]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT path FROM job_files WHERE job_id = ? AND status != 'sent' ORDER BY path",
                (job_id,),
            ).fetchall()
        return [str(row[0]) for row in rows]

    def get_job(self, job_id: int) -> QueueJob:
        jobs = self._select_jobs("WHERE j.id = ?", (job_id,))
        if not jobs:
            raise ModalityError(f"Queue job not found: {job_id}", {"job_id": job_id})
        return jobs[0]

    def list_jobs(self, status: str | None = None) -> list[QueueJob]:
        if status is None:
            return self._select_jobs("", ())
        if status not in JOB_STATUSES:
            raise ModalityError(
                f"Unknown queue status: {status}", {"status": status, "known": ", ".join(JOB_STATUSES)}
            )
        return self._select_jobs("WHERE j.status = ?", (status,))

    def next_value(self, name: str) -> int:
        """名前ごとの連番（1 から）。Study ID・PPS ID に使う."""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO counters (name, value) VALUES (?, 1)"
                " ON CONFLICT(name) DO UPDATE SET value = value + 1",
                (name,),
            )
            row = conn.execute("SELECT value FROM counters WHERE name = ?", (name,)).fetchone()
        return int(row[0])

    def generated_study_uid(self, worklist_key: str) -> str | None:
        """予約に Study Instance UID が無く、この道具が作った UID（同じ予約で2回撮るとき用）."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT study_instance_uid FROM generated_study_uids WHERE worklist_key = ?",
                (worklist_key,),
            ).fetchone()
        return str(row[0]) if row else None

    def remember_study_uid(self, worklist_key: str, study_instance_uid: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO generated_study_uids (worklist_key, study_instance_uid)"
                " VALUES (?, ?)",
                (worklist_key, study_instance_uid),
            )

    def _select_jobs(self, where: str, params: tuple[object, ...]) -> list[QueueJob]:
        query = (
            "SELECT j.id, j.created_at, j.updated_at, j.folder, j.destination, j.accession_number,"
            " j.status, j.attempts, j.last_error, COUNT(f.path),"
            " SUM(CASE WHEN f.status = 'sent' THEN 1 ELSE 0 END)"
            f" FROM jobs j LEFT JOIN job_files f ON f.job_id = j.id {where}"
            " GROUP BY j.id ORDER BY j.id"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [
            QueueJob(
                id=row[0],
                created_at=row[1],
                updated_at=row[2],
                folder=row[3],
                destination=row[4],
                accession_number=row[5],
                status=row[6],
                attempts=row[7],
                last_error=row[8],
                num_files=row[9] or 0,
                num_sent=row[10] or 0,
            )
            for row in rows
        ]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            yield conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
