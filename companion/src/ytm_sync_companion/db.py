"""SQLite storage: track matches, source/destination pairs and the (future) job queue.

The schema is versioned with `PRAGMA user_version`. To change it, append a new entry to
`MIGRATIONS`; never edit an existing one.

No secrets live here. YouTube Music credentials are stored separately (see `config.py`).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

MIGRATIONS: tuple[str, ...] = (
    # --- v1 ---------------------------------------------------------------------------
    """
    -- Result of matching one Spotify track to one YouTube Music video.
    CREATE TABLE track_map (
        spotify_uri TEXT PRIMARY KEY,
        video_id    TEXT,
        confidence  REAL,
        status      TEXT NOT NULL CHECK (status IN ('ok', 'not_found', 'review', 'skipped')),
        title       TEXT,
        artists     TEXT,
        duration_ms INTEGER,
        updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
    );

    -- A source (Liked Songs or a Spotify playlist) mirrored into a YouTube Music playlist.
    CREATE TABLE pairs (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        source_uri       TEXT NOT NULL,
        dest_playlist_id TEXT NOT NULL,
        mode             TEXT NOT NULL DEFAULT 'additive' CHECK (mode IN ('additive', 'mirror')),
        last_order       TEXT NOT NULL DEFAULT '[]',  -- JSON list of Spotify URIs, last synced
        last_synced_at   TEXT,
        UNIQUE (source_uri, dest_playlist_id)
    );

    -- Persistent, resumable work queue (used from roadmap phase 2).
    CREATE TABLE jobs (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        pair_id     INTEGER NOT NULL REFERENCES pairs(id) ON DELETE CASCADE,
        kind        TEXT NOT NULL CHECK (kind IN ('initial_dump', 'incremental')),
        state       TEXT NOT NULL DEFAULT 'queued'
                    CHECK (state IN ('queued', 'running', 'done', 'failed', 'cancelled')),
        done        INTEGER NOT NULL DEFAULT 0,
        total       INTEGER NOT NULL DEFAULT 0,
        error       TEXT,
        created_at  TEXT NOT NULL DEFAULT (datetime('now')),
        finished_at TEXT
    );
    """,
    # --- v2: what a job needs to be resumed, and what the user needs to see ---------------
    """
    ALTER TABLE jobs ADD COLUMN payload    TEXT;  -- JSON list of tracks (resume after a restart)
    ALTER TABLE jobs ADD COLUMN error_code TEXT;  -- session_expired, write_failed, ...
    ALTER TABLE jobs ADD COLUMN report     TEXT;  -- JSON summary of a finished job
    """,
)

SCHEMA_VERSION = len(MIGRATIONS)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(path: Path) -> sqlite3.Connection:
    """Open the database and apply any pending migrations. Safe to call repeatedly."""
    conn = connect(path)
    current = conn.execute("PRAGMA user_version").fetchone()[0]
    if current > SCHEMA_VERSION:
        conn.close()
        raise RuntimeError(
            f"Database schema v{current} is newer than this companion (v{SCHEMA_VERSION}). "
            "Update the companion."
        )
    for version in range(current, SCHEMA_VERSION):
        # Statements come from the constant above, never from user input.
        conn.executescript(MIGRATIONS[version])
        conn.execute(f"PRAGMA user_version = {version + 1}")
        conn.commit()
    return conn
