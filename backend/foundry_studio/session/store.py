"""SQLite-backed multi-turn session store (synchronous, thread-safe).

Uses the built-in sqlite3 module so no additional dependencies are required.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Thread-local session context — ensures concurrent requests don't clobber each other.
_CURRENT_SESSION_ID: ContextVar[str | None] = ContextVar("_current_session_id", default=None)


@dataclass
class SessionMessage:
    role: str  # "user" | "assistant" | "system" | "tool"
    content: str
    parts: list[dict] = field(default_factory=list)
    created_at: str = ""


class SessionStore:
    """SQLite-backed session store (synchronous).

    Tables
    ------
    sessions(session_id TEXT PRIMARY KEY, created_at TEXT, updated_at TEXT)
    messages(session_id TEXT, seq INTEGER, role TEXT, content TEXT, parts TEXT, created_at TEXT)
      FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
    """

    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._lock = threading.Lock()
        self._initialized = False

    def init(self) -> None:
        """Create tables if they don't exist. Thread-safe and idempotent."""
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    session_id TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL DEFAULT '',
                    parts TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id) ON DELETE CASCADE
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, seq)"
            )
            conn.commit()
            conn.close()
            self._initialized = True

    # ------------------------------------------------------------------ #
    # Session CRUD                                                          #
    # ------------------------------------------------------------------ #

    def create_session(self, user_id: str | None = None) -> str:
        """Create a new session. Returns the session_id. Thread-safe."""
        session_id = str(uuid.uuid4())
        now = _now()
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT INTO sessions (session_id, created_at, updated_at) VALUES (?, ?, ?)",
                (session_id, now, now),
            )
            conn.commit()
            conn.close()
        return session_id

    def get_session(self, session_id: str) -> dict | None:
        """Return session metadata (not messages). Thread-safe."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?", (session_id,)
            )
            row = cur.fetchone()
            conn.close()
        if not row:
            return None
        return dict(row)

    def list_sessions(self, limit: int = 20) -> list[dict]:
        """Return recent sessions ordered by updated_at desc. Thread-safe."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            )
            rows = cur.fetchall()
            conn.close()
        return [dict(r) for r in rows]

    def touch_session(self, session_id: str) -> None:
        """Update the updated_at timestamp. Thread-safe."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (_now(), session_id),
            )
            conn.commit()
            conn.close()

    def delete_session(self, session_id: str) -> None:
        """Delete a session and all its messages. Thread-safe."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            conn.commit()
            conn.close()

    # ------------------------------------------------------------------ #
    # Message CRUD                                                          #
    # ------------------------------------------------------------------ #

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str = "",
        parts: list[dict] | None = None,
    ) -> int:
        """Append a message. Returns the sequence number. Thread-safe."""
        now = _now()
        parts_json = json.dumps(parts or [])
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            cur = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) + 1 FROM messages WHERE session_id = ?",
                (session_id,),
            )
            (seq,) = cur.fetchone()
            conn.execute(
                "INSERT INTO messages (session_id, seq, role, content, parts, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (session_id, seq, role, content, parts_json, now),
            )
            conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            conn.commit()
            conn.close()
        return seq

    def get_messages(self, session_id: str) -> list[SessionMessage]:
        """Return all messages for a session in chronological order. Thread-safe."""
        with self._lock:
            conn = sqlite3.connect(self._db_path)
            conn.row_factory = sqlite3.Row
            cur = conn.execute(
                "SELECT role, content, parts, created_at FROM messages WHERE session_id = ? ORDER BY seq ASC",
                (session_id,),
            )
            rows = cur.fetchall()
            conn.close()
        messages = []
        for row in rows:
            parts_data = json.loads(row["parts"]) if row["parts"] else []
            messages.append(
                SessionMessage(
                    role=row["role"],
                    content=row["content"],
                    parts=parts_data,
                    created_at=row["created_at"],
                )
            )
        return messages

    def get_messages_dict(self, session_id: str) -> list[dict]:
        """Return all messages as plain dicts."""
        msgs = self.get_messages(session_id)
        return [
            {
                "role": m.role,
                "content": m.content,
                "parts": m.parts,
                "created_at": m.created_at,
            }
            for m in msgs
        ]

    # ------------------------------------------------------------------ #
    # ContextVar helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def set_current_session(session_id: str | None) -> None:
        _CURRENT_SESSION_ID.set(session_id)

    @staticmethod
    def get_current_session() -> str | None:
        return _CURRENT_SESSION_ID.get()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
