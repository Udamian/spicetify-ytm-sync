from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from ytm_sync_companion.db import SCHEMA_VERSION, init_db


def tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def test_init_creates_schema(tmp_path: Path):
    conn = init_db(tmp_path / "nested" / "db.sqlite3")
    assert {"track_map", "pairs", "jobs"} <= tables(conn)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_init_is_idempotent(tmp_path: Path):
    path = tmp_path / "db.sqlite3"
    init_db(path).close()
    conn = init_db(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION


def test_refuses_newer_schema(tmp_path: Path):
    path = tmp_path / "db.sqlite3"
    conn = sqlite3.connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()
    with pytest.raises(RuntimeError, match="newer"):
        init_db(path)


def test_track_status_is_constrained(tmp_path: Path):
    conn = init_db(tmp_path / "db.sqlite3")
    conn.execute("INSERT INTO track_map (spotify_uri, status) VALUES ('spotify:track:1', 'ok')")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO track_map (spotify_uri, status) VALUES ('spotify:track:2', 'x')")


def test_deleting_a_pair_cascades_to_jobs(tmp_path: Path):
    conn = init_db(tmp_path / "db.sqlite3")
    conn.execute("INSERT INTO pairs (source_uri, dest_playlist_id) VALUES ('liked', 'PL1')")
    conn.execute("INSERT INTO jobs (pair_id, kind) VALUES (1, 'initial_dump')")
    conn.execute("DELETE FROM pairs WHERE id = 1")
    assert conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
