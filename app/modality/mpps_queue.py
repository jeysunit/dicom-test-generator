"""MPPS の知らせの待ち行列（sqlite3。spec/12_modality_emulator.md 8.4.1）.

1件は1つの撮影の MPPS（1つの SOP Instance）。N-CREATE と、終わりの N-SET
（COMPLETED・DISCONTINUED）の値と、それぞれ送れたかを持つ。送れなかった分は
`mpps retry` で、N-CREATE を先に送り直す。待ち行列と同じ sqlite3 のファイルに置く。
"""

from __future__ import annotations

import json
import secrets
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
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
        last_error TEXT NOT NULL DEFAULT '',
        peer_ae_title TEXT NOT NULL,
        peer_host TEXT NOT NULL,
        peer_port INTEGER NOT NULL,
        create_no_response INTEGER NOT NULL DEFAULT 0,
        set_no_response INTEGER NOT NULL DEFAULT 0,
        send_token TEXT NOT NULL DEFAULT '',
        send_token_at TEXT NOT NULL DEFAULT ''
    )
"""
_COLUMNS = (
    "id, created_at, updated_at, sop_instance_uid, accession_number, output_dir, state,"
    " create_sent, set_json != '', set_sent, attempts, last_error,"
    " peer_ae_title, peer_host, peer_port, create_no_response, set_no_response"
)
# 札を取ってからこの秒より長く経った行は、送る手順が落ちたとみなして札を取り直せる（8.4.1）
STALE_SEND_TOKEN_SECONDS = 10 * 60
SEND_TOKEN_BYTES = 16
MppsOperation = Literal["create", "set"]


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
    # 送り先は行に固定する（8.4.1）
    peer_ae_title: str
    peer_host: str
    peer_port: int
    # 前に送って「応答なし」で終わったか（届いていたかもしれない。8.4.1）
    create_no_response: bool
    set_no_response: bool

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

    def add(
        self,
        sop_instance_uid: str,
        accession_number: str,
        create: Dataset,
        peer: tuple[str, str, int],
    ) -> int:
        """N-CREATE の知らせを入れる。`peer` は（AE タイトル, 住所, ポート）で、行に固定する."""
        now = _now()
        ae_title, host, port = peer
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO mpps (created_at, updated_at, sop_instance_uid, accession_number,"
                " state, create_json, peer_ae_title, peer_host, peer_port)"
                " VALUES (?, ?, ?, ?, 'IN PROGRESS', ?, ?, ?, ?)",
                (now, now, sop_instance_uid, accession_number, _to_json(create), ae_title, host, port),
            )
            return int(cursor.lastrowid or 0)

    def claim(self, record_id: int) -> str | None:
        """送る権利の札を取る。札が空か古い行だけ。取れなければ None（8.4.1）."""
        token = secrets.token_hex(SEND_TOKEN_BYTES)
        cutoff = (datetime.now() - timedelta(seconds=STALE_SEND_TOKEN_SECONDS)).isoformat(
            timespec="seconds"
        )
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE mpps SET send_token = ?, send_token_at = ? WHERE id = ?"
                " AND (send_token = '' OR send_token_at < ?)",
                (token, _now(), record_id, cutoff),
            )
        return token if cursor.rowcount == 1 else None

    def release(self, record_id: int, token: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE mpps SET send_token = '', send_token_at = '' WHERE id = ? AND send_token = ?",
                (record_id, token),
            )

    def mark_no_response(self, record_id: int, operation: MppsOperation) -> None:
        column = "create_no_response" if operation == "create" else "set_no_response"
        self._update(record_id, f"{column} = 1")

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
                peer_ae_title=row[12],
                peer_host=row[13],
                peer_port=row[14],
                create_no_response=bool(row[15]),
                set_no_response=bool(row[16]),
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
