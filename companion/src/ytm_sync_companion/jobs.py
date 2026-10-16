"""Persistent, resumable job queue on top of the `jobs` table.

A job is one run of "dump" or "incremental sync" for a pair (source -> destination playlist).
The queue only tracks *state and progress*. What is already done lives in `track_map`
(matches) and in the destination playlist, so a resumed job skips finished tracks and never
duplicates work: after a crash, `recover_interrupted` puts `running` jobs back in `queued`.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

from .logging_setup import redact

ACTIVE_STATES = ("queued", "running")
FINAL_STATES = ("done", "failed", "cancelled")


@dataclass(frozen=True)
class Job:
    id: int
    pair_id: int
    kind: str
    state: str
    done: int
    total: int
    error: str | None
    error_code: str | None = None
    report: dict[str, Any] | None = None
    created_at: str | None = None
    finished_at: str | None = None

    @property
    def progress(self) -> float:
        return self.done / self.total if self.total else 0.0


def _job(row: sqlite3.Row | None) -> Job | None:
    if row is None:
        return None
    return Job(
        id=row["id"], pair_id=row["pair_id"], kind=row["kind"], state=row["state"],
        done=row["done"], total=row["total"], error=row["error"],
        error_code=row["error_code"],
        report=json.loads(row["report"]) if row["report"] else None,
        created_at=row["created_at"], finished_at=row["finished_at"],
    )


def upsert_pair(conn: sqlite3.Connection, source_uri: str, dest_playlist_id: str,
                mode: str = "additive") -> int:
    conn.execute(
        "INSERT INTO pairs (source_uri, dest_playlist_id, mode) VALUES (?, ?, ?) "
        "ON CONFLICT (source_uri, dest_playlist_id) DO UPDATE SET mode = excluded.mode",
        (source_uri, dest_playlist_id, mode),
    )
    conn.commit()
    row = conn.execute(
        "SELECT id FROM pairs WHERE source_uri = ? AND dest_playlist_id = ?",
        (source_uri, dest_playlist_id),
    ).fetchone()
    return int(row["id"])


def get(conn: sqlite3.Connection, job_id: int) -> Job | None:
    return _job(conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone())


def active_for_pair(conn: sqlite3.Connection, pair_id: int) -> Job | None:
    return _job(
        conn.execute(
            "SELECT * FROM jobs WHERE pair_id = ? AND state IN ('queued', 'running') "
            "ORDER BY id LIMIT 1",
            (pair_id,),
        ).fetchone()
    )


def enqueue(
    conn: sqlite3.Connection, pair_id: int, kind: str, total: int = 0, payload: str | None = None
) -> Job:
    """Queue a job. If the pair already has an active one, return that instead (no overlap)."""
    existing = active_for_pair(conn, pair_id)
    if existing:
        return existing
    cursor = conn.execute(
        "INSERT INTO jobs (pair_id, kind, total, payload) VALUES (?, ?, ?, ?)",
        (pair_id, kind, total, payload),
    )
    conn.commit()
    job = get(conn, int(cursor.lastrowid or 0))
    if job is None:  # cannot happen right after an INSERT; keeps the type honest
        raise RuntimeError("job was not created")
    return job


def claim_next(conn: sqlite3.Connection) -> Job | None:
    """Take the oldest queued job and mark it running (single worker, so no race)."""
    row = conn.execute("SELECT id FROM jobs WHERE state = 'queued' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        return None
    conn.execute("UPDATE jobs SET state = 'running' WHERE id = ?", (row["id"],))
    conn.commit()
    return get(conn, int(row["id"]))


def set_progress(
    conn: sqlite3.Connection, job_id: int, done: int, total: int | None = None
) -> None:
    if total is None:
        conn.execute(
            "UPDATE jobs SET done = ? WHERE id = ? AND state = 'running'", (done, job_id)
        )
    else:
        conn.execute(
            "UPDATE jobs SET done = ?, total = ? WHERE id = ? AND state = 'running'",
            (done, total, job_id),
        )
    conn.commit()


def finish(
    conn: sqlite3.Connection,
    job_id: int,
    state: str,
    error: str | None = None,
    *,
    error_code: str | None = None,
    report: dict[str, Any] | None = None,
) -> None:
    """Close a running job. A job cancelled meanwhile stays cancelled."""
    if state not in FINAL_STATES:
        raise ValueError(f"not a final state: {state}")
    message = redact(error)[:500] if error else None
    conn.execute(
        "UPDATE jobs SET state = ?, error = ?, error_code = ?, report = ?, "
        "finished_at = datetime('now') WHERE id = ? AND state = 'running'",
        (state, message, error_code, json.dumps(report) if report else None, job_id),
    )
    conn.commit()


def payload(conn: sqlite3.Connection, job_id: int) -> str | None:
    row = conn.execute("SELECT payload FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return row["payload"] if row else None


def recent(conn: sqlite3.Connection, limit: int = 5) -> list[Job]:
    rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [job for job in map(_job, rows) if job]


def requeue(conn: sqlite3.Connection, job_id: int) -> None:
    """Put a running job back in the queue (companion shutting down: it resumes next start)."""
    conn.execute("UPDATE jobs SET state = 'queued' WHERE id = ? AND state = 'running'", (job_id,))
    conn.commit()


def cancel(conn: sqlite3.Connection, job_id: int) -> bool:
    """Cancel an active job. A running worker must check `is_cancelled` between steps."""
    cursor = conn.execute(
        "UPDATE jobs SET state = 'cancelled', finished_at = datetime('now') "
        "WHERE id = ? AND state IN ('queued', 'running')",
        (job_id,),
    )
    conn.commit()
    return cursor.rowcount > 0


def is_cancelled(conn: sqlite3.Connection, job_id: int) -> bool:
    job = get(conn, job_id)
    return job is not None and job.state == "cancelled"


def recover_interrupted(conn: sqlite3.Connection) -> int:
    """At startup: jobs left `running` by a crash or a closed companion go back to the queue."""
    cursor = conn.execute("UPDATE jobs SET state = 'queued' WHERE state = 'running'")
    conn.commit()
    return cursor.rowcount
