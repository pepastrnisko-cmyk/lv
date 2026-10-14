"""Durable action journal and generation-based cooperative cancellation.

The journal is deliberately independent of editor undo. Its caller must compare
the current project fingerprint with the recorded post-edit fingerprint before
restoring a checkpoint. Cancellation leases must be captured when work is
enqueued, and checked immediately before every side effect.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import threading
from typing import Any
import uuid


STATUSES = frozenset({"pending", "proposed", "applied", "verified", "cancelled", "unknown", "undone"})
_TRANSITIONS = {
    "proposed": {"pending", "cancelled", "unknown"},
    "pending": {"applied", "cancelled", "unknown"},
    "applied": {"verified", "unknown"},
    "verified": {"undone", "unknown"},
    "cancelled": set(),
    "unknown": {"verified", "undone", "cancelled"},
    "undone": set(),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _json(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise ValueError("History payloads must be finite JSON values.") from exc


class History:
    """Single-process, thread-safe SQLite journal at a caller-selected path.

    Construction performs startup recovery: pending/applied records from a
    previous process become unknown and are never automatically replayed. Only
    one application instance should open a project's journal at a time.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path) if str(path) != ":memory:" else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self._connection = sqlite3.connect(str(path), timeout=10, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        try:
            with self._lock, self._connection:
                version = self._connection.execute("PRAGMA user_version").fetchone()[0]
                if version not in (0, 1):
                    raise RuntimeError(f"Unsupported history schema version {version}.")
                self._connection.execute("PRAGMA journal_mode=WAL")
                self._connection.execute("PRAGMA synchronous=FULL")
                self._connection.execute("""CREATE TABLE IF NOT EXISTS actions (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    operation TEXT NOT NULL,
                    project_hash TEXT,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('pending','proposed','applied','verified','cancelled','unknown','undone')),
                    result TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )""")
                self._connection.execute("CREATE INDEX IF NOT EXISTS actions_project_status ON actions(project_hash,status,sequence)")
                self._connection.execute("PRAGMA user_version=1")
                incomplete = self._connection.execute("SELECT id,status,result FROM actions WHERE status IN ('pending','applied')").fetchall()
                for row in incomplete:
                    recovery = {"recovery": "Process stopped before verification; inspect the project before retrying or undoing.", "previous_status": row["status"], "previous_result": json.loads(row["result"]) if row["result"] is not None else None}
                    self._connection.execute("UPDATE actions SET status='unknown',result=?,updated_at=? WHERE id=?", (_json(recovery), _now(), row["id"]))
        except Exception:
            self._connection.close()
            self._closed = True
            raise

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("History is closed.")

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        result = dict(row)
        result.pop("sequence", None)
        result["payload"] = json.loads(result["payload"])
        result["result"] = json.loads(result["result"]) if result["result"] is not None else None
        return result

    def record(self, operation: str, project_hash: str | None = None, payload: Any = None, status: str = "proposed") -> str:
        if not isinstance(operation, str) or not operation.strip() or len(operation) > 128 or "\x00" in operation:
            raise ValueError("Operation must be nonempty text of at most 128 characters.")
        if project_hash is not None and (not isinstance(project_hash, str) or not project_hash or len(project_hash) > 4096 or "\x00" in project_hash):
            raise ValueError("Project hash must be nonempty text or None.")
        if status not in STATUSES:
            raise ValueError(f"Invalid history status: {status}.")
        serialized = _json({} if payload is None else payload)
        action_id, timestamp = uuid.uuid4().hex, _now()
        with self._lock:
            self._ensure_open()
            with self._connection:
                self._connection.execute("INSERT INTO actions(id,operation,project_hash,payload,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?)", (action_id, operation, project_hash, serialized, status, timestamp, timestamp))
        return action_id

    def get(self, action_id: str) -> dict[str, Any]:
        with self._lock:
            self._ensure_open()
            row = self._connection.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone()
            if row is None:
                raise KeyError(action_id)
            return self._decode(row)  # type: ignore[return-value]

    def list_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Limit must be an integer between 1 and 1000.")
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute("SELECT * FROM actions ORDER BY sequence DESC LIMIT ?", (limit,)).fetchall()
            return [self._decode(row) for row in rows]  # type: ignore[misc]

    def mark(self, action_id: str, status: str, result: Any = None) -> dict[str, Any]:
        if status not in STATUSES:
            raise ValueError(f"Invalid history status: {status}.")
        serialized = _json(result) if result is not None else None
        with self._lock:
            self._ensure_open()
            with self._connection:
                row = self._connection.execute("SELECT status FROM actions WHERE id=?", (action_id,)).fetchone()
                if row is None:
                    raise KeyError(action_id)
                previous = row["status"]
                if status != previous and status not in _TRANSITIONS[previous]:
                    raise ValueError(f"Invalid history transition: {previous} -> {status}.")
                if serialized is None:
                    self._connection.execute("UPDATE actions SET status=?,updated_at=? WHERE id=?", (status, _now(), action_id))
                else:
                    self._connection.execute("UPDATE actions SET status=?,result=?,updated_at=? WHERE id=?", (status, serialized, _now(), action_id))
            return self.get(action_id)

    def last_verified(self, project_key: str | None = None) -> dict[str, Any] | None:
        with self._lock:
            self._ensure_open()
            if project_key is None:
                row = self._connection.execute("SELECT * FROM actions WHERE status='verified' ORDER BY sequence DESC LIMIT 1").fetchone()
            else:
                row = self._connection.execute("SELECT * FROM actions WHERE status='verified' AND project_hash=? ORDER BY sequence DESC LIMIT 1", (project_key,)).fetchone()
            return self._decode(row)

    def unresolved(self, project_key: str | None = None) -> list[dict[str, Any]]:
        """All unknown outcomes, without a recency limit or implicit clearing."""
        with self._lock:
            self._ensure_open()
            if project_key is None:
                rows = self._connection.execute("SELECT * FROM actions WHERE status='unknown' ORDER BY sequence DESC").fetchall()
            else:
                rows = self._connection.execute("SELECT * FROM actions WHERE status='unknown' AND project_hash=? ORDER BY sequence DESC", (project_key,)).fetchall()
            return [self._decode(row) for row in rows]  # type: ignore[misc]

    def find_verified_output(self, path: str | Path) -> dict[str, Any] | None:
        """Find a verified project-copy transaction even beyond recent UI rows."""
        target = os.path.normcase(str(Path(path).resolve()))
        with self._lock:
            self._ensure_open()
            rows = self._connection.execute("SELECT * FROM actions WHERE status='verified' ORDER BY sequence DESC")
            for row in rows:
                decoded = self._decode(row)
                result = decoded.get("result")
                if isinstance(result, dict) and isinstance(result.get("output"), str):
                    if os.path.normcase(str(Path(result["output"]).resolve())) == target:
                        return decoded
            return None

    def close(self) -> None:
        with self._lock:
            if not self._closed:
                self._connection.close()
                self._closed = True

    def __enter__(self) -> "History":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


class CancelledOperation(RuntimeError):
    """A captured operation was revoked; it must not perform further changes."""


class CancellationLease:
    def __init__(self, supervisor: "CancellationSupervisor", generation: int, event: threading.Event):
        self._supervisor = supervisor
        self.generation = generation
        self.event = event
        self.cancel_event = event

    def is_active(self) -> bool:
        return self._supervisor.is_active(self)

    def assert_active(self) -> None:
        if not self.is_active():
            raise CancelledOperation("Operation cancelled; inspect any in-flight editor change before continuing.")

    def wait(self, timeout: float | None = None) -> bool:
        """Wait until cancelled; return True if this lease has been revoked."""
        return self.event.wait(timeout)


class CancellationSupervisor:
    """Revoke all queued/running leases without blocking the stop action.

    This is cooperative cancellation. It cannot undo an editor API operation
    already in flight; the caller must verify that operation and journal its
    outcome. It injects no keyboard or mouse input.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._generation = 0
        self._event = threading.Event()

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def capture(self) -> CancellationLease:
        with self._lock:
            return CancellationLease(self, self._generation, self._event)

    acquire = capture

    def is_active(self, lease: CancellationLease) -> bool:
        with self._lock:
            return lease._supervisor is self and lease.generation == self._generation and not lease.event.is_set()

    def stop(self) -> int:
        with self._lock:
            self._event.set()
            self._generation += 1
            self._event = threading.Event()
            return self._generation

    cancel = stop
