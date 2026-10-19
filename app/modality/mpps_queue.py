"""MPPS の知らせの待ち行列（sqlite3。spec/12_modality_emulator.md 8.4.1）.

1件は1つの撮影の MPPS（1つの SOP Instance）。N-CREATE と、終わりの N-SET
（COMPLETED・DISCONTINUED）の値と、それぞれ送れたかを持つ。送れなかった分は
`mpps retry` で、N-CREATE を先に送り直す。待ち行列と同じ sqlite3 のファイルに置く。
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel
from pydicom.dataset import Dataset

from app.core.exceptions import ModalityError

MppsState = Literal["IN PROGRESS", "COMPLETED", "DISCONTINUED"]

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS mpps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        sop_instance_uid TEXT NOT NULL UNIQUE,
        accession_number TEXT NOT NULL DEFAULT '',
        output_dir TEXT NOT NULL DEFAULT '',
        state TEXT NOT NULL,
        create_json TEXT NOT NULL,
        create_sent INTEGER NOT NULL DEFAULT 0,
        set_json TEXT NOT NULL DEFAULT '',
        set_sent INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT NOT NULL DEFAULT ''
    )
"""
_COLUMNS = (
    "id, created_at, updated_at, sop_instance_uid, accession_number, output_dir, state,"
    " create_sent, set_json != '', set_sent, attempts, last_error"
)


class MppsRecord(BaseModel):
    model_config = {"frozen": True}

    id: int
    created_at: str
    updated_at: str
    sop_instance_uid: str
    accession_number: str
    output_dir: str
    state: MppsState
    create_sent: bool
    has_set: bool
    set_sent: bool
    attempts: int
    last_error: str

    @property
    def sent(self) -> bool:
        """いまの状態までの知らせを、すべて送れたか."""
        return self.create_sent and (not self.has_set or self.set_sent)


class MppsQueue:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                conn.execute(_SCHEMA)
        except (OSError, sqlite3.Error) as exc:
            raise ModalityError(
                f"Failed to open the MPPS queue: {db_path}",
                {"db_path": str(db_path), "reason": str(exc)},
            ) from exc

    def add(self, sop_instance_uid: str, accession_number: str, create: Dataset) -> int:
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO mpps (created_at, updated_at, sop_instance_uid, accession_number,"
                " state, create_json) VALUES (?, ?, ?, ?, 'IN PROGRESS', ?)",
                (now, now, sop_instance_uid, accession_number, _to_json(create)),
            )
            return int(cursor.lastrowid or 0)

    def set_final(self, record_id: int, state: MppsState, modification: Dataset, output_dir: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE mpps SET state = ?, set_json = ?, set_sent = 0, output_dir = ?,"
                " updated_at = ? WHERE id = ?",
                (state, _to_json(modification), output_dir, _now(), record_id),
            )

    def mark_create_sent(self, record_id: int) -> None:
        self._update(record_id, "create_sent = 1, last_error = ''")

    def mark_set_sent(self, record_id: int) -> None:
        self._update(record_id, "set_sent = 1, last_error = ''")

    def record_error(self, record_id: int, error: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE mpps SET last_error = ?, attempts = attempts + 1, updated_at = ?"
                " WHERE id = ?",
                (error, _now(), record_id),
            )

    def get(self, record_id: int) -> MppsRecord:
        records = self._select("WHERE id = ?", (record_id,))
        if not records:
            raise ModalityError(f"MPPS record not found: {record_id}", {"mpps_id": record_id})
        return records[0]

    def list_all(self) -> list[MppsRecord]:
        return self._select("", ())

    def unsent(self) -> list[MppsRecord]:
        """送れていない知らせのある件（古い順）."""
        return self._select(
            "WHERE create_sent = 0 OR (set_json != '' AND set_sent = 0)", ()
        )

    def create_dataset(self, record_id: int) -> Dataset:
        return self._dataset(record_id, "create_json")

    def set_dataset(self, record_id: int) -> Dataset:
        return self._dataset(record_id, "set_json")

    def _dataset(self, record_id: int, column: str) -> Dataset:
        with self._connect() as conn:
            row = conn.execute(f"SELECT {column} FROM mpps WHERE id = ?", (record_id,)).fetchone()
        if row is None or not row[0]:
            raise ModalityError(f"MPPS message not found: {record_id}", {"mpps_id": record_id})
        return Dataset.from_json(json.loads(row[0]))

    def _update(self, record_id: int, assignments: str) -> None:
        with self._connect() as conn:
            conn.execute(
                f"UPDATE mpps SET {assignments}, updated_at = ? WHERE id = ?", (_now(), record_id)
            )

    def _select(self, where: str, params: tuple[object, ...]) -> list[MppsRecord]:
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {_COLUMNS} FROM mpps {where} ORDER BY id", params).fetchall()
        return [
            MppsRecord(
                id=row[0],
                created_at=row[1],
                updated_at=row[2],
                sop_instance_uid=row[3],
                accession_number=row[4],
                output_dir=row[5],
                state=row[6],
                create_sent=bool(row[7]),
                has_set=bool(row[8]),
                set_sent=bool(row[9]),
                attempts=row[10],
                last_error=row[11],
            )
            for row in rows
        ]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            yield conn


def _to_json(ds: Dataset) -> str:
    return json.dumps(ds.to_json_dict(), ensure_ascii=False)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")
