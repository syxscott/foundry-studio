"""SQLite persistence for jobs and worker heartbeats.

The database is the single source of truth for the job queue: API processes
write jobs, worker processes claim and update them.  SQLite WAL mode makes
concurrent readers/writers safe for a single-machine deployment.

Schema versioning is handled with a small ``schema_version`` pragma table.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

# Job statuses (kept as plain strings for easy SQL, validated in one place).
STATUS_QUEUED = "queued"
STATUS_DRAFT = "draft"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELED = "canceled"

TERMINAL_STATUSES = {STATUS_SUCCEEDED, STATUS_FAILED, STATUS_CANCELED}
ACTIVE_STATUSES = {STATUS_QUEUED, STATUS_RUNNING}

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    name TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    input_files_json TEXT NOT NULL DEFAULT '[]',
    engine_mode TEXT NOT NULL DEFAULT 'auto',
    progress INTEGER,
    error_code TEXT,
    error_detail TEXT,
    log_path TEXT,
    outputs_dir TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    remote_job_id TEXT,
    backend TEXT,
    scheduler TEXT,
    job_spec_json TEXT,
    spec_overrides_json TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at);

CREATE TABLE IF NOT EXISTS workers (
    model TEXT PRIMARY KEY,
    pid INTEGER,
    status TEXT NOT NULL DEFAULT 'stopped',
    heartbeat_at TEXT,
    started_at TEXT,
    last_error TEXT
);
"""


class StudioDB:
    """Thin, thread-safe wrapper around a SQLite database file."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_schema()

    # --- connection management -------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=30000;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = self._connect()
            self._local.conn = conn
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA_SQL)
            row = conn.execute("SELECT version FROM schema_version").fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,)
                )
            self._migrate(conn)

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Add columns introduced after schema v1 without dropping data."""
        existing = {
            r["name"] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        added: list[str] = []
        for col, ctype in (
            ("remote_job_id", "TEXT"),
            ("backend", "TEXT"),
            ("scheduler", "TEXT"),
            ("job_spec_json", "TEXT"),
            ("spec_overrides_json", "TEXT"),
        ):
            if col not in existing:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {ctype}")
                added.append(col)
        if added:
            logger = logging.getLogger("foundry_studio.db")
            logger.info("Migrated jobs table: added columns %s", added)

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        """Context manager committing on success, rolling back on error."""
        conn = self._conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None

    # --- jobs ------------------------------------------------------------------
    def create_job(
        self,
        *,
        model: str,
        name: str,
        params: dict[str, Any],
        input_files: list[dict[str, str]],
        engine_mode: str,
    ) -> dict[str, Any]:
        job_id = uuid.uuid4().hex
        created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        serialized_params = json.dumps(params, ensure_ascii=False)
        serialized_input_files = json.dumps(input_files, ensure_ascii=False)
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO jobs
                (id, model, name, status, params_json, input_files_json,
                 engine_mode, created_at, cancel_requested)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    job_id,
                    model,
                    name,
                    STATUS_DRAFT,
                    serialized_params,
                    serialized_input_files,
                    engine_mode,
                    created,
                ),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self.tx() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None

    def list_jobs(self, limit: int = 200, offset: int = 0) -> list[dict[str, Any]]:
        with self.tx() as conn:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [dict(r) for r in rows]

    def claim_next_job(self, model: str) -> dict[str, Any] | None:
        """Atomically claim the oldest queued job for ``model``.

        The UPDATE carries ``status = 'queued'`` in its WHERE clause so two
        workers polling concurrently can never claim the same job: SQLite
        serializes writers, and the second UPDATE matches zero rows.
        """
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.tx() as conn:
            row = conn.execute(
                """
                UPDATE jobs SET status = ?, started_at = ?
                WHERE id = (
                    SELECT id FROM jobs
                    WHERE model = ? AND status = ?
                    ORDER BY created_at ASC LIMIT 1
                ) AND status = ?
                RETURNING *
                """,
                (STATUS_RUNNING, now, model, STATUS_QUEUED, STATUS_QUEUED),
            ).fetchone()
        return dict(row) if row else None

    def update_job(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        error_code: str | None = None,
        error_detail: str | None = None,
        outputs_dir: str | None = None,
        log_path: str | None = None,
        started_at: str | None = None,
        cancel_requested: bool | None = None,
        remote_job_id: str | None = None,
        backend: str | None = None,
        scheduler: str | None = None,
        job_spec_json: str | None = None,
    ) -> dict[str, Any] | None:
        sets: list[str] = []
        values: list[Any] = []
        if status is not None:
            sets.append("status = ?")
            values.append(status)
            if status in TERMINAL_STATUSES:
                sets.append("finished_at = ?")
                values.append(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        if progress is not None:
            sets.append("progress = ?")
            values.append(int(progress))
        if error_code is not None:
            sets.append("error_code = ?")
            values.append(error_code)
        if error_detail is not None:
            sets.append("error_detail = ?")
            values.append(error_detail)
        if outputs_dir is not None:
            sets.append("outputs_dir = ?")
            values.append(outputs_dir)
        if log_path is not None:
            sets.append("log_path = ?")
            values.append(log_path)
        if started_at is not None:
            sets.append("started_at = ?")
            values.append(started_at)
        if cancel_requested is not None:
            sets.append("cancel_requested = ?")
            values.append(1 if cancel_requested else 0)
        if remote_job_id is not None:
            sets.append("remote_job_id = ?")
            values.append(remote_job_id)
        if backend is not None:
            sets.append("backend = ?")
            values.append(backend)
        if scheduler is not None:
            sets.append("scheduler = ?")
            values.append(scheduler)
        if job_spec_json is not None:
            sets.append("job_spec_json = ?")
            values.append(job_spec_json)
        if not sets:
            return self.get_job(job_id)
        sets_sql = ", ".join(sets)
        values.append(job_id)
        with self.tx() as conn:
            conn.execute(f"UPDATE jobs SET {sets_sql} WHERE id = ?", values)
        return self.get_job(job_id)  # type: ignore[return-value]

    def request_cancel(self, job_id: str) -> dict[str, Any] | None:
        # Atomic read-check-write using the existing tx() context
        with self.tx() as conn:
            row = conn.execute(
                "SELECT status FROM jobs WHERE id = ?", (job_id,)
            ).fetchone()
            if row is None:
                return None
            if row["status"] in TERMINAL_STATUSES:
                return dict(row)
            conn.execute(
                "UPDATE jobs SET cancel_requested = 1 WHERE id = ? AND status = ?",
                (job_id, row["status"]),
            )
        return self.get_job(job_id)

    def set_input_files(
        self, job_id: str, input_files: list[dict[str, str]]
    ) -> dict[str, Any] | None:
        with self.tx() as conn:
            try:
                serialized = json.dumps(input_files, ensure_ascii=False)
            except (TypeError, ValueError):
                serialized = json.dumps([{"_serialization_error": str(input_files)}], ensure_ascii=False)
            conn.execute(
                "UPDATE jobs SET input_files_json = ? WHERE id = ?",
                (serialized, job_id),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def set_spec_overrides(
        self, job_id: str, overrides: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Persist per-job environment overrides (agent-tuned resources/invocation)."""
        with self.tx() as conn:
            try:
                serialized = json.dumps(overrides, ensure_ascii=False)
            except (TypeError, ValueError):
                serialized = json.dumps({"_serialization_error": str(overrides)}, ensure_ascii=False)
            conn.execute(
                "UPDATE jobs SET spec_overrides_json = ? WHERE id = ?",
                (serialized, job_id),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def submit_job(self, job_id: str) -> dict[str, Any] | None:
        """DB-level primitive: move a ``draft`` job into the queue.

        Note: production HTTP submission goes through
        :meth:`foundry_studio.joblifecycle.JobOrchestrator.submit` which
        performs the same state transition as part of building the
        ``JobSpec`` and dispatching to the active backend. This primitive
        is kept as a tested, in-process API (used by the unit tests and
        any future bulk-submit code paths) so the draft → queued
        transition lives in exactly one place.
        """
        with self.tx() as conn:
            row = conn.execute(
                "SELECT * FROM jobs WHERE id = ? AND status = ?",
                (job_id, STATUS_DRAFT),
            ).fetchone()
            if row is None:
                return self.get_job(job_id)
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (STATUS_QUEUED, job_id),
            )
        return self.get_job(job_id)  # type: ignore[return-value]

    def delete_job(self, job_id: str) -> bool:
        with self.tx() as conn:
            cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        return cur.rowcount > 0

    def requeue_stale_running(self, stale_seconds: int = 300) -> int:
        """Reset running jobs whose worker died without a terminal update.

        Called by worker managers on startup. Returns the number of jobs
        reset back to ``queued``.
        """
        cutoff = time.time() - stale_seconds
        cutoff_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(cutoff))
        with self.tx() as conn:
            cur = conn.execute(
                "UPDATE jobs SET status = ?, started_at = NULL "
                "WHERE status = ? AND started_at IS NOT NULL AND started_at < ?",
                (STATUS_QUEUED, STATUS_RUNNING, cutoff_iso),
            )
        return cur.rowcount

    # --- workers ----------------------------------------------------------------
    def upsert_worker(
        self,
        model: str,
        *,
        pid: int | None = None,
        status: str = "running",
        last_error: str | None = None,
    ) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.tx() as conn:
            conn.execute(
                """
                INSERT INTO workers(model, pid, status, heartbeat_at, started_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(model) DO UPDATE SET
                    pid = excluded.pid,
                    status = excluded.status,
                    heartbeat_at = excluded.heartbeat_at,
                    started_at = COALESCE(workers.started_at, excluded.started_at),
                    last_error = excluded.last_error
                """,
                (model, pid, status, now, now, last_error),
            )

    def heartbeat(self, model: str, pid: int) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.tx() as conn:
            conn.execute(
                "UPDATE workers SET heartbeat_at = ?, status = 'running' WHERE model = ?",
                (now, model),
            )

    def mark_worker_stopped(self, model: str, last_error: str | None = None) -> None:
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        with self.tx() as conn:
            conn.execute(
                "UPDATE workers SET status = 'stopped', heartbeat_at = ?, "
                "last_error = ? WHERE model = ?",
                (now, last_error, model),
            )

    def get_worker(self, model: str) -> dict[str, Any] | None:
        with self.tx() as conn:
            row = conn.execute(
                "SELECT * FROM workers WHERE model = ?", (model,)
            ).fetchone()
        return dict(row) if row else None

    def list_workers(self) -> list[dict[str, Any]]:
        with self.tx() as conn:
            rows = conn.execute("SELECT * FROM workers ORDER BY model").fetchall()
        return [dict(r) for r in rows]
