"""A summary of the companion's state that is safe to paste into a bug report.

It contains no credentials, no Spotify or YouTube ids, no song titles and no file paths with the
person's name in them. The log excerpt goes through the same redaction as the log file itself.
"""

from __future__ import annotations

import json
import platform
import sqlite3
from collections import deque
from pathlib import Path
from typing import Any

from . import __version__, jobs, runtime
from .config import API_VERSION, Settings
from .logging_setup import redact

LOG_LINES = 40
LIKED = "spotify:collection:tracks"


def scrub(text: str, settings: Settings) -> str:
    """Redact secrets and hide the person's name (home folder) from a piece of text."""
    text = redact(text)
    for folder in (settings.data_dir, Path.home()):
        for variant in {str(folder), folder.as_posix()}:
            if len(variant) > 3:
                text = text.replace(variant, "~")
    return text


def log_tail(settings: Settings, lines: int = LOG_LINES) -> list[str]:
    path = settings.data_dir / "logs" / "companion.log"
    try:
        with path.open(encoding="utf-8", errors="replace") as handle:
            tail = deque(handle, maxlen=lines)
    except OSError:
        return []
    return [scrub(line.rstrip("\r\n"), settings)[:400] for line in tail]


def collect(
    settings: Settings,
    conn: sqlite3.Connection,
    *,
    youtube: str,
    autostart: dict[str, bool],
    worker_running: bool,
) -> dict[str, Any]:
    pairs = []
    query = "SELECT id, source_uri, mode, last_order, last_synced_at, active FROM pairs"
    for row in conn.execute(query):
        pairs.append({
            "id": row["id"],
            "source": "liked_songs" if row["source_uri"] == LIKED else "playlist",
            "mode": row["mode"],
            "active": bool(row["active"]),
            "synced_count": len(json.loads(row["last_order"] or "[]")),
            "last_synced_at": row["last_synced_at"],
        })
    counts = {
        row["status"]: row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM track_map GROUP BY status")
    }
    recent = [
        {
            "id": job.id, "pair_id": job.pair_id, "kind": job.kind, "state": job.state,
            "done": job.done, "total": job.total, "error_code": job.error_code,
            "error": scrub(job.error, settings) if job.error else None,
            "created_at": job.created_at, "finished_at": job.finished_at,
        }
        for job in jobs.recent(conn)
    ]
    return {
        "companion": {
            "version": __version__,
            "api_version": API_VERSION,
            "python": platform.python_version(),
            "platform": f"{platform.system()} {platform.release()}",
            "packaged": runtime.is_frozen(),
            "worker_running": worker_running,
        },
        "youtube_session": youtube,
        "autostart": autostart,
        "pairs": pairs,
        "tracks": counts,
        "jobs": recent,
        "log_tail": log_tail(settings),
    }
