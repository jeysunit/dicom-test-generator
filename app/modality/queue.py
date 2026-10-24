"""送信の待ち行列と送った履歴（sqlite3。docs/spec/12_modality_emulator.md 8.2）."""

from __future__ import annotations

import secrets
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import closing, contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from app.core.exceptions import ModalityError

from .store_scu import StoreFileResult

JobStatus = Literal["pending", "sending", "sent", "failed"]
JOB_STATUSES: tuple[str, ...] = ("pending", "sending", "sent", "failed")
QUEUE_DB_NAME = "queue.sqlite3"
# 送信中のままこの秒数より長く変わらない件は、送る手順が途中で落ちたとみなす（8.2）
STALE_SENDING_SECONDS = 30 * 60
STALE_SENDING_ERROR = "stale sending: the sender stopped before recording the result"
SEND_TOKEN_BYTES = 16
_SENDABLE_STATUSES: tuple[str, ...] = ("pending", "failed")
_SENDABLE_PLACEHOLDERS = ", ".join("?" for _ in _SENDABLE_STATUSES)

_SCHEMA = (
    # 緊急の撮影の Study と仮の患者（追加撮影で引き継ぐ値）
    """
    CREATE TABLE IF NOT EXISTS emergency_exams (
        study_instance_uid TEXT PRIMARY KEY,
        study_id TEXT NOT NULL,
        patient_id TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        birth_date TEXT NOT NULL,
        sex TEXT NOT NULL
    )
    """,
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
        last_error TEXT NOT NULL DEFAULT '',
        send_token TEXT NOT NULL DEFAULT ''
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
    # 予約を撮っている間の札（別のプロセスが同じ予約を同時に撮らない。ADR-0024）
    """
    CREATE TABLE IF NOT EXISTS exam_locks (
        worklist_key TEXT PRIMARY KEY,
        token TEXT NOT NULL,
        locked_at TEXT NOT NULL
    )
    """,
    # 予約ごとの撮影の記録（撮影済みの判定と追加撮影の値。docs/spec/12 の 6.3・ADR-0024）
    """
    CREATE TABLE IF NOT EXISTS exam_records (
        worklist_key TEXT PRIMARY KEY,
        study_instance_uid TEXT NOT NULL DEFAULT '',
        study_date TEXT NOT NULL DEFAULT '',
        study_time TEXT NOT NULL DEFAULT '',
        study_description TEXT NOT NULL DEFAULT '',
        series_count INTEGER NOT NULL DEFAULT 0
    )
    """,
    # 予約で使ったシリーズ番号と、ルーチンに書いた番号か（ADR-0025）。行の無い予約（前の
    # 版の記録）は 1〜series_count を自動で使ったとみなす
    """
    CREATE TABLE IF NOT EXISTS exam_series_numbers (
        worklist_key TEXT NOT NULL,
        series_number INTEGER NOT NULL,
        explicit INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (worklist_key, series_number)
    )
    """,
    # 保管の確認の要求と画像ごとの結果（Phase 3c。8.3.3）
    """
    CREATE TABLE IF NOT EXISTS commitments (
        transaction_uid TEXT PRIMARY KEY,
        job_id INTEGER NOT NULL REFERENCES jobs(id),
        destination TEXT NOT NULL,
        peer_ae_title TEXT NOT NULL,
        status TEXT NOT NULL,
        requested_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        deadline TEXT NOT NULL,
        error TEXT NOT NULL DEFAULT ''
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS commitment_items (
        transaction_uid TEXT NOT NULL REFERENCES commitments(transaction_uid),
        sop_class_uid TEXT NOT NULL,
        sop_instance_uid TEXT NOT NULL,
        status TEXT NOT NULL,
        failure_reason INTEGER,
        note TEXT NOT NULL DEFAULT '',
        PRIMARY KEY (transaction_uid, sop_class_uid, sop_instance_uid)
    )
    """,
    # 撮影の出力のフォルダと、撮影に使った装置のプロファイル（docs/spec/13 の 8 を効かせる）
    """
    CREATE TABLE IF NOT EXISTS exam_profiles (
        output_dir TEXT PRIMARY KEY,
        profile TEXT NOT NULL
    )
    """,
)

CommitmentStatus = Literal["waiting", "confirmed", "failed", "timed_out"]
COMMITMENT_NOT_REPORTED = "not in the result"
SopReference = tuple[str, str]  # (SOP Class UID, SOP Instance UID)


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
    # 件を作ったときの装置の AEタイトル。再送信もこの AEタイトルで送る（docs/spec/12 の 8.2）
    calling_ae_title: str = ""
    stale: bool = False  # 送信中のまま止まった件（8.2）
    commitment: str = ""  # 最後の保管の確認の状態。使わない件は空（8.3.3）
    commitment_error: str = ""
    # 元のファイルの先頭から読んだ値（一覧の表示用。ファイルが無ければ空）
    patient_id: str = ""
    patient_name: str = ""
    study_datetime: str = ""


class EmergencyExamRecord(BaseModel):
    """緊急の撮影の Study と仮の患者。追加撮影でも同じ値を使う."""

    model_config = {"frozen": True}

    study_instance_uid: str
    study_id: str
    patient_id: str
    patient_name: str
    birth_date: str
    sex: str


class ExamRecord(BaseModel):
    """予約の撮影の記録：最初の撮影の Study の値と、作ったシリーズの数（docs/spec/12 の 6.3）."""

    model_config = {"frozen": True}

    worklist_key: str
    study_instance_uid: str
    study_date: str
    study_time: str
    study_description: str
    series_count: int
    # 使ったシリーズ番号と、ルーチンに書いた番号か（True）自動か（False）（ADR-0025）
    series_numbers: list[tuple[int, bool]] = []


class CommitmentState(BaseModel):
    """保管の確認の1つの要求の状態（8.3.3）."""

    model_config = {"frozen": True}

    job_id: int
    transaction_uid: str
    destination: str
    peer_ae_title: str
    status: CommitmentStatus
    num_requested: int
    num_confirmed: int
    num_failed: int
    error: str = ""


class SendQueue:
    """待ち行列。1件は1つの検査（1つのフォルダ）を1つの送信先へ送ること."""

    def __init__(self, db_path: Path, legacy_ae_title: str = "") -> None:
        """`legacy_ae_title` は、AEタイトルの列が無い前の版の行に入れる AEタイトル."""
        self._db_path = db_path
        try:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as conn:
                for statement in _SCHEMA:
                    conn.execute(statement)
                columns = {row[1] for row in conn.execute("PRAGMA table_info(jobs)")}
                if "send_token" not in columns:
                    # 札の列が無い前の版の待ち行列に足す
                    conn.execute(
                        "ALTER TABLE jobs ADD COLUMN send_token TEXT NOT NULL DEFAULT ''"
                    )
                # 装置を切り替えられる前の版の待ち行列に足す。前の行は今の装置の AEタイトル
                _add_ae_title_column(conn, "jobs", "calling_ae_title", legacy_ae_title)
                _add_ae_title_column(conn, "commitments", "own_ae_title", legacy_ae_title)
                # 撮影の記録が無かった前の版で撮った予約も、撮影済みとして移す（UID だけ）
                conn.execute(
                    "INSERT OR IGNORE INTO exam_records (worklist_key, study_instance_uid)"
                    " SELECT worklist_key, study_instance_uid FROM generated_study_uids"
                )
                file_columns = {row[1] for row in conn.execute("PRAGMA table_info(job_files)")}
                if "sop_class_uid" not in file_columns:
                    # 保管の確認の前の版の待ち行列に足す（Phase 3c）
                    conn.execute(
                        "ALTER TABLE job_files ADD COLUMN sop_class_uid TEXT NOT NULL DEFAULT ''"
                    )
        except (OSError, sqlite3.Error) as exc:
            raise ModalityError(
                f"Failed to open the send queue: {db_path}",
                {"db_path": str(db_path), "reason": str(exc)},
            ) from exc

    def add_job(
        self,
        folder: str,
        destination: str,
        files: Sequence[str],
        accession_number: str = "",
        calling_ae_title: str = "",
    ) -> int:
        now = _now()
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO jobs (created_at, updated_at, folder, destination, accession_number,"
                " calling_ae_title, status) VALUES (?, ?, ?, ?, ?, ?, 'pending')",
                (now, now, folder, destination, accession_number, calling_ae_title),
            )
            job_id = int(cursor.lastrowid or 0)
            conn.executemany(
                "INSERT INTO job_files (job_id, path, status) VALUES (?, ?, 'pending')",
                [(job_id, path) for path in files],
            )
        return job_id

    def mark_sending(self, job_id: int) -> str:
        """待ち・失敗の件だけを送信中にし、送る権利の札を返す（8.2）.

        同じ件を2つの手順が同時に送らない。札は touch_sending・record_results・
        record_job_failure に渡し、止まったとみなされて別の手順が引き取った後に、
        古い手順が書き込めないようにする。
        """
        token = secrets.token_hex(SEND_TOKEN_BYTES)
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE jobs SET status = 'sending', attempts = attempts + 1, updated_at = ?,"
                f" send_token = ? WHERE id = ? AND status IN ({_SENDABLE_PLACEHOLDERS})",
                (_now(), token, job_id, *_SENDABLE_STATUSES),
            )
            if cursor.rowcount == 1:
                return token
            row = conn.execute("SELECT status FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise ModalityError(f"Queue job not found: {job_id}", {"job_id": job_id})
        raise ModalityError(
            f"Queue job cannot be sent now: {job_id}",
            {"job_id": job_id, "status": str(row[0]), "sendable": ", ".join(_SENDABLE_STATUSES)},
        )

    def reset_stale_sending(self) -> list[int]:
        """送信中のまま STALE_SENDING_SECONDS より長く変わらない件を失敗に戻す（8.2）.

        戻した件の ID を返す。送る手順が途中で落ちた件を `queue retry --stale` で送り直すため。
        """
        cutoff = _stale_cutoff()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status = 'sending' AND updated_at < ? ORDER BY id",
                (cutoff,),
            ).fetchall()
            reset: list[int] = []
            for (job_id,) in rows:
                cursor = conn.execute(
                    "UPDATE jobs SET status = 'failed', last_error = ?, updated_at = ?,"
                    " send_token = '' WHERE id = ? AND status = 'sending' AND updated_at < ?",
                    (STALE_SENDING_ERROR, _now(), job_id, cutoff),
                )
                if cursor.rowcount == 1:
                    reset.append(int(job_id))
        return reset

    def touch_sending(self, job_id: int, token: str) -> None:
        """送っている間に時刻を進める（長い送信を止まったとみなさない）。札が違えば止める."""
        with self._connect() as conn:
            self._claim(conn, job_id, token)

    def record_results(
        self, job_id: int, results: Sequence[StoreFileResult], token: str | None = None
    ) -> JobStatus:
        """ファイルごとの結果を残し、検査の状態（送れた・失敗）を決めて返す.

        `token` を渡すと、その札の送信中のときだけ書く（違えば ModalityError で何も書かない）。
        """
        with self._connect() as conn:
            if token is not None:
                self._claim(conn, job_id, token)
            for result in results:
                conn.execute(
                    "UPDATE job_files SET sop_instance_uid = ?, sop_class_uid = ?, status = ?,"
                    " status_code = ?, error = ? WHERE job_id = ? AND path = ?",
                    (
                        result.sop_instance_uid,
                        result.sop_class_uid,
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
                "UPDATE jobs SET status = ?, last_error = ?, updated_at = ?, send_token = ''"
                " WHERE id = ?",
                (status, last_error, _now(), job_id),
            )
        return status

    def record_job_failure(self, job_id: int, reason: str, token: str | None = None) -> None:
        """Association を張れないなど、ファイルに届く前の失敗を残す.

        `token` を渡すと、その札の送信中のときだけ書く（違えば ModalityError で何も書かない）。
        """
        with self._connect() as conn:
            if token is not None:
                self._claim(conn, job_id, token)
            conn.execute(
                "UPDATE job_files SET status = 'failed', error = ? WHERE job_id = ?"
                " AND status != 'sent'",
                (reason, job_id),
            )
            conn.execute(
                "UPDATE jobs SET status = 'failed', last_error = ?, updated_at = ?, send_token = ''"
                " WHERE id = ?",
                (reason, _now(), job_id),
            )

    @staticmethod
    def _claim(conn: sqlite3.Connection, job_id: int, token: str) -> None:
        """札の送信中なら時刻を進める。違えば止める（同じ取引の中の書き込みは巻き戻る）."""
        cursor = conn.execute(
            "UPDATE jobs SET updated_at = ? WHERE id = ? AND status = 'sending' AND send_token = ?",
            (_now(), job_id, token),
        )
        if cursor.rowcount != 1:
            raise ModalityError(
                f"Queue job is no longer owned by this sender: {job_id}",
                {"job_id": job_id, "hint": "it was reset as stale or finished elsewhere"},
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

    def exam_record(self, worklist_key: str) -> ExamRecord | None:
        """予約の撮影の記録。撮っていなければ None（撮影済みの判定。docs/spec/12 の 6.3）."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT worklist_key, study_instance_uid, study_date, study_time,"
                " study_description, series_count FROM exam_records WHERE worklist_key = ?",
                (worklist_key,),
            ).fetchone()
            if row is None:
                return None
            numbers = _used_series_numbers(conn, worklist_key, row[5])
        return ExamRecord(
            worklist_key=row[0],
            study_instance_uid=row[1],
            study_date=row[2],
            study_time=row[3],
            study_description=row[4],
            series_count=row[5],
            series_numbers=numbers,
        )

    def claim_exam(self, worklist_key: str) -> str | None:
        """予約の撮影の札を取り、札を返す。ほかが持っていれば None.

        札の時刻は撮影の間 `touch_exam` で進める。進まないまま古くなった札（撮影の処理が
        落ちた）は取り直せる。
        """
        token = secrets.token_hex(SEND_TOKEN_BYTES)
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM exam_locks WHERE worklist_key = ? AND locked_at < ?",
                (worklist_key, _stale_cutoff()),
            )
            cursor = conn.execute(
                "INSERT OR IGNORE INTO exam_locks (worklist_key, token, locked_at)"
                " VALUES (?, ?, ?)",
                (worklist_key, token, _now()),
            )
        return token if cursor.rowcount == 1 else None

    def touch_exam(self, worklist_key: str, token: str) -> None:
        """撮影の間、札の時刻を進める（長い撮影を落ちたとみなさない）."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE exam_locks SET locked_at = ? WHERE worklist_key = ? AND token = ?",
                (_now(), worklist_key, token),
            )

    def release_exam(self, worklist_key: str, token: str) -> None:
        """自分の札だけを戻す（取り直されていたら、ほかの札は消さない）."""
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM exam_locks WHERE worklist_key = ? AND token = ?",
                (worklist_key, token),
            )

    def taken_keys(self) -> set[str]:
        """撮影済みの予約の鍵（一覧の印）."""
        with self._connect() as conn:
            rows = conn.execute("SELECT worklist_key FROM exam_records").fetchall()
        return {str(row[0]) for row in rows}

    def emergency_exam(self, study_instance_uid: str) -> EmergencyExamRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT study_instance_uid, study_id, patient_id, patient_name, birth_date, sex"
                " FROM emergency_exams WHERE study_instance_uid = ?",
                (study_instance_uid,),
            ).fetchone()
        if row is None:
            return None
        return EmergencyExamRecord(
            study_instance_uid=row[0],
            study_id=row[1],
            patient_id=row[2],
            patient_name=row[3],
            birth_date=row[4],
            sex=row[5],
        )

    def record_exam(
        self,
        worklist_key: str,
        study_instance_uid: str,
        study_date: str,
        study_time: str,
        study_description: str,
        series_count: int,
        series_numbers: list[tuple[int, bool]] | None = None,
        emergency: EmergencyExamRecord | None = None,
    ) -> None:
        """撮影を終えた予約を記録する。2回目以降（追加撮影）はシリーズの数だけ足す.

        前の版から移した記録（日時が空）は、移した後の最初の撮影の日時・説明で埋め、
        その後の追加撮影をそろえる。`series_numbers`（使った番号と、書いた番号か）は
        前の記録の後ろに足す。無ければ、続きの自動の番号を使ったとみなす。
        `emergency` があれば、緊急の患者の値も同じトランザクションで残す。
        """
        with self._connect() as conn:
            if emergency is not None:
                # Study の値と仮の患者を一緒に残す。追加撮影では最初の値を変えない
                conn.execute(
                    "INSERT OR IGNORE INTO emergency_exams"
                    " (study_instance_uid, study_id, patient_id, patient_name, birth_date, sex)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        emergency.study_instance_uid, emergency.study_id, emergency.patient_id,
                        emergency.patient_name, emergency.birth_date, emergency.sex,
                    ),
                )
            row = conn.execute(
                "SELECT series_count FROM exam_records WHERE worklist_key = ?", (worklist_key,)
            ).fetchone()
            before = _used_series_numbers(conn, worklist_key, row[0]) if row is not None else []
            if series_numbers is None:
                start = 1 + max((number for number, _ in before), default=0)
                series_numbers = [(start + index, False) for index in range(series_count)]
            # 前の版の記録（行が無い）は、自動で使った番号の行を先に作ってから足す
            conn.executemany(
                "INSERT OR IGNORE INTO exam_series_numbers (worklist_key, series_number, explicit)"
                " VALUES (?, ?, ?)",
                [
                    (worklist_key, number, int(explicit))
                    for number, explicit in before + series_numbers
                ],
            )
            updated = conn.execute(
                "UPDATE exam_records SET series_count = series_count + ?,"
                " study_instance_uid = CASE WHEN study_instance_uid = '' THEN ?"
                " ELSE study_instance_uid END,"
                " study_time = CASE WHEN study_date = '' THEN ? ELSE study_time END,"
                " study_description = CASE WHEN study_date = '' THEN ?"
                " ELSE study_description END,"
                " study_date = CASE WHEN study_date = '' THEN ? ELSE study_date END"
                " WHERE worklist_key = ?",
                (
                    series_count,
                    study_instance_uid,
                    study_time,
                    study_description,
                    study_date,
                    worklist_key,
                ),
            )
            if updated.rowcount == 0:
                conn.execute(
                    "INSERT INTO exam_records (worklist_key, study_instance_uid, study_date,"
                    " study_time, study_description, series_count) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        worklist_key,
                        study_instance_uid,
                        study_date,
                        study_time,
                        study_description,
                        series_count,
                    ),
                )

    # --- 撮影に使った装置のプロファイル（docs/spec/13 の 8） ----------------------

    def remember_exam_profile(self, output_dir: str, profile: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO exam_profiles (output_dir, profile) VALUES (?, ?)",
                (_folder_key(output_dir), profile),
            )

    def exam_profile(self, folder: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT profile FROM exam_profiles WHERE output_dir = ?", (_folder_key(folder),)
            ).fetchone()
        return str(row[0]) if row else None

    # --- 保管の確認（Phase 3c。8.3.3） --------------------------------------

    def sent_references(self, job_id: int) -> list[SopReference]:
        """送れた画像の（SOP Class UID, SOP Instance UID）。送ったときに残した値を使う."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT sop_class_uid, sop_instance_uid FROM job_files WHERE job_id = ?"
                " AND status = 'sent' AND sop_class_uid != '' AND sop_instance_uid != ''"
                " ORDER BY path",
                (job_id,),
            ).fetchall()
        return [(str(row[0]), str(row[1])) for row in rows]

    def add_commitment(
        self,
        job_id: int,
        destination: str,
        peer_ae_title: str,
        transaction_uid: str,
        references: Sequence[SopReference],
        timeout_seconds: float,
        own_ae_title: str = "",
    ) -> None:
        """要求を記録する。`own_ae_title` は要求を送った装置の AEタイトル（結果の宛先）."""
        now = datetime.now()
        deadline = (now + timedelta(seconds=timeout_seconds)).isoformat(timespec="seconds")
        stamp = now.isoformat(timespec="seconds")
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO commitments (transaction_uid, job_id, destination, peer_ae_title,"
                " own_ae_title, status, requested_at, updated_at, deadline)"
                " VALUES (?, ?, ?, ?, ?, 'waiting', ?, ?, ?)",
                (
                    transaction_uid,
                    job_id,
                    destination,
                    peer_ae_title,
                    own_ae_title,
                    stamp,
                    stamp,
                    deadline,
                ),
            )
            conn.executemany(
                "INSERT OR IGNORE INTO commitment_items (transaction_uid, sop_class_uid,"
                " sop_instance_uid, status) VALUES (?, ?, ?, 'waiting')",
                [(transaction_uid, cls, inst) for cls, inst in references],
            )

    def fail_commitment(self, transaction_uid: str, reason: str) -> None:
        """N-ACTION を送れなかった要求を「確認の失敗」にする.

        先に結果が届いて状態が変わっていれば、上書きしない（待っている要求だけ）。
        """
        with self._connect() as conn:
            conn.execute(
                "UPDATE commitments SET status = 'failed', error = ?, updated_at = ?"
                " WHERE transaction_uid = ? AND status = 'waiting'",
                (reason, _now(), transaction_uid),
            )

    def commitment_requested(self, transaction_uid: str) -> set[SopReference]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT sop_class_uid, sop_instance_uid FROM commitment_items"
                " WHERE transaction_uid = ?",
                (transaction_uid,),
            ).fetchall()
        return {(str(row[0]), str(row[1])) for row in rows}

    def record_commitment_report(
        self,
        transaction_uid: str,
        confirmed: set[SopReference],
        failed: dict[SopReference, int | None],
    ) -> bool:
        """結果を画像ごとに残し、要求の状態を決める（8.3.2）。受けたら True.

        要求に無い組は捨てる。要求したのに結果のどちらにも無い組は失敗にする（理由「結果に無い」）。
        失敗の側に書いてある組は、成功の側にもあっても失敗にする（書いてある方を信じる）。
        状態の確かめと書き込みは1つの取引で行い、待っている（か時間切れの）要求だけに書く
        （同じ Association と待ち受けから同時に来ても、受けるのは1つ）。
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT status FROM commitments WHERE transaction_uid = ?", (transaction_uid,)
            ).fetchone()
            if row is None or row[0] not in ("waiting", "timed_out"):
                return False
            requested = conn.execute(
                "SELECT sop_class_uid, sop_instance_uid FROM commitment_items"
                " WHERE transaction_uid = ?",
                (transaction_uid,),
            ).fetchall()
            num_failed = 0
            for sop_class_uid, sop_instance_uid in requested:
                reference = (str(sop_class_uid), str(sop_instance_uid))
                code: int | None = None
                note = ""
                if reference in failed:
                    status, code = "failed", failed[reference]
                elif reference in confirmed:
                    status = "confirmed"
                else:
                    status, note = "failed", COMMITMENT_NOT_REPORTED
                num_failed += status == "failed"
                conn.execute(
                    "UPDATE commitment_items SET status = ?, failure_reason = ?, note = ?"
                    " WHERE transaction_uid = ? AND sop_class_uid = ? AND sop_instance_uid = ?",
                    (status, code, note, transaction_uid, *reference),
                )
            overall = "failed" if num_failed else "confirmed"
            error = f"{num_failed} image(s) not committed" if num_failed else ""
            conn.execute(
                "UPDATE commitments SET status = ?, error = ?, updated_at = ?"
                " WHERE transaction_uid = ?",
                (overall, error, _now(), transaction_uid),
            )
        return True

    def commitment_peer(self, transaction_uid: str) -> tuple[str, str, str] | None:
        """要求の（状態, 送信先の AEタイトル, 要求を送った装置の AEタイトル）.

        知らない Transaction UID なら None。
        """
        self.expire_commitments()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status, peer_ae_title, own_ae_title FROM commitments"
                " WHERE transaction_uid = ?",
                (transaction_uid,),
            ).fetchone()
        return (str(row[0]), str(row[1]), str(row[2])) if row else None

    def get_commitment(self, transaction_uid: str) -> CommitmentState:
        self.expire_commitments()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT c.job_id, c.transaction_uid, c.destination, c.peer_ae_title, c.status,"
                " c.error, COUNT(i.sop_instance_uid),"
                " SUM(CASE WHEN i.status = 'confirmed' THEN 1 ELSE 0 END),"
                " SUM(CASE WHEN i.status = 'failed' THEN 1 ELSE 0 END)"
                " FROM commitments c LEFT JOIN commitment_items i"
                " ON i.transaction_uid = c.transaction_uid WHERE c.transaction_uid = ?"
                " GROUP BY c.transaction_uid",
                (transaction_uid,),
            ).fetchone()
        if row is None:
            raise ModalityError(
                f"Storage commitment request not found: {transaction_uid}",
                {"transaction_uid": transaction_uid},
            )
        return CommitmentState(
            job_id=row[0],
            transaction_uid=row[1],
            destination=row[2],
            peer_ae_title=row[3],
            status=row[4],
            error=row[5],
            num_requested=row[6] or 0,
            num_confirmed=row[7] or 0,
            num_failed=row[8] or 0,
        )

    def expire_commitments(self) -> None:
        """決めた時間に結果が来なかった要求を「確認の時間切れ」にする（8.3）."""
        with self._connect() as conn:
            conn.execute(
                "UPDATE commitments SET status = 'timed_out', updated_at = ?"
                " WHERE status = 'waiting' AND deadline < ?",
                (_now(), _now()),
            )

    def _select_jobs(self, where: str, params: tuple[object, ...]) -> list[QueueJob]:
        self.expire_commitments()
        latest = (
            "(SELECT c.{column} FROM commitments c WHERE c.job_id = j.id"
            " ORDER BY c.requested_at DESC, c.rowid DESC LIMIT 1)"
        )
        query = (
            "SELECT j.id, j.created_at, j.updated_at, j.folder, j.destination, j.accession_number,"
            " j.status, j.attempts, j.last_error, COUNT(f.path),"
            " SUM(CASE WHEN f.status = 'sent' THEN 1 ELSE 0 END),"
            f" {latest.format(column='status')}, {latest.format(column='error')},"
            " j.calling_ae_title"
            f" FROM jobs j LEFT JOIN job_files f ON f.job_id = j.id {where}"
            " GROUP BY j.id ORDER BY j.id"
        )
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        cutoff = _stale_cutoff()
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
                stale=row[6] == "sending" and row[2] < cutoff,
                commitment=row[11] or "",
                commitment_error=row[12] or "",
                calling_ae_title=row[13] or "",
            )
            for row in rows
        ]

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self._db_path)) as conn, conn:
            yield conn


def _used_series_numbers(
    conn: sqlite3.Connection, worklist_key: str, series_count: int
) -> list[tuple[int, bool]]:
    """予約で使ったシリーズ番号。行が無い（前の版の記録）なら 1〜series_count を自動とみなす."""
    rows = conn.execute(
        "SELECT series_number, explicit FROM exam_series_numbers WHERE worklist_key = ?"
        " ORDER BY series_number",
        (worklist_key,),
    ).fetchall()
    if not rows:
        return [(number, False) for number in range(1, series_count + 1)]
    return [(int(number), bool(explicit)) for number, explicit in rows]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _add_ae_title_column(
    conn: sqlite3.Connection, table: str, column: str, legacy_ae_title: str
) -> None:
    """AEタイトルの列が無ければ足し、前の行を `legacy_ae_title` で埋める（表と列は定数）."""
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column in columns:
        return
    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")
    conn.execute(f"UPDATE {table} SET {column} = ?", (legacy_ae_title,))


def _folder_key(folder: str) -> str:
    """フォルダの名前をそろえる（同じフォルダを別の書き方で指しても同じ鍵）."""
    return str(Path(folder).resolve())


def _stale_cutoff() -> str:
    """これより前の updated_at の送信中は止まったとみなす（_now と同じ形で比べる）."""
    cutoff = datetime.now() - timedelta(seconds=STALE_SENDING_SECONDS)
    return cutoff.isoformat(timespec="seconds")
