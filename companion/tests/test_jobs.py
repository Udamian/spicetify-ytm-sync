from __future__ import annotations

import pytest

from ytm_sync_companion import jobs
from ytm_sync_companion.db import init_db


@pytest.fixture
def conn(tmp_path):
    connection = init_db(tmp_path / "t.sqlite3")
    yield connection
    connection.close()


@pytest.fixture
def pair_id(conn):
    return jobs.upsert_pair(conn, "spotify:collection:tracks", "PLdest")


def test_upsert_pair_is_idempotent_and_updates_mode(conn):
    first = jobs.upsert_pair(conn, "src", "dst")
    second = jobs.upsert_pair(conn, "src", "dst", mode="mirror")
    assert first == second
    assert conn.execute("SELECT mode FROM pairs WHERE id = ?", (first,)).fetchone()[0] == "mirror"


def test_enqueue_claim_progress_finish(conn, pair_id):
    job = jobs.enqueue(conn, pair_id, "initial_dump", total=1500)
    assert (job.state, job.done, job.total) == ("queued", 0, 1500)

    claimed = jobs.claim_next(conn)
    assert claimed is not None and claimed.id == job.id and claimed.state == "running"
    assert jobs.claim_next(conn) is None  # nothing else queued

    jobs.set_progress(conn, job.id, 750)
    assert jobs.get(conn, job.id).progress == 0.5

    jobs.finish(conn, job.id, "done")
    done = jobs.get(conn, job.id)
    assert done.state == "done"
    assert jobs.active_for_pair(conn, pair_id) is None


def test_no_overlapping_jobs_for_a_pair(conn, pair_id):
    first = jobs.enqueue(conn, pair_id, "initial_dump")
    again = jobs.enqueue(conn, pair_id, "incremental")
    assert again.id == first.id
    jobs.claim_next(conn)
    assert jobs.enqueue(conn, pair_id, "incremental").id == first.id  # still running
    jobs.finish(conn, first.id, "done")
    assert jobs.enqueue(conn, pair_id, "incremental").id != first.id


def test_recover_interrupted_requeues_and_keeps_progress(conn, pair_id):
    job = jobs.enqueue(conn, pair_id, "initial_dump", total=100)
    jobs.claim_next(conn)
    jobs.set_progress(conn, job.id, 40)
    assert jobs.recover_interrupted(conn) == 1
    resumed = jobs.claim_next(conn)
    assert resumed is not None and resumed.id == job.id and resumed.done == 40


def test_cancel(conn, pair_id):
    job = jobs.enqueue(conn, pair_id, "initial_dump")
    jobs.claim_next(conn)
    assert jobs.cancel(conn, job.id) is True
    assert jobs.is_cancelled(conn, job.id)
    jobs.set_progress(conn, job.id, 10)  # a late update must not revive it
    assert jobs.get(conn, job.id).state == "cancelled"
    assert jobs.cancel(conn, job.id) is False


def test_finish_redacts_error_and_rejects_non_final_state(conn, pair_id):
    job = jobs.enqueue(conn, pair_id, "initial_dump")
    jobs.claim_next(conn)
    jobs.finish(conn, job.id, "failed", "boom Cookie: SAPISID=TOPSECRET")
    assert "TOPSECRET" not in (jobs.get(conn, job.id).error or "")
    with pytest.raises(ValueError):
        jobs.finish(conn, job.id, "running")


def test_finishing_a_cancelled_job_does_not_revive_it(conn, pair_id):
    job = jobs.enqueue(conn, pair_id, "initial_dump")
    jobs.claim_next(conn)
    jobs.cancel(conn, job.id)
    jobs.finish(conn, job.id, "done", report={"added": 1})  # the worker finishing a moment late
    assert jobs.get(conn, job.id).state == "cancelled"


def test_report_and_error_code_roundtrip(conn, pair_id):
    job = jobs.enqueue(conn, pair_id, "initial_dump", payload="[]")
    jobs.claim_next(conn)
    jobs.finish(conn, job.id, "failed", "x", error_code="session_expired", report={"a": 1})
    saved = jobs.get(conn, job.id)
    assert (saved.error_code, saved.report) == ("session_expired", {"a": 1})
    assert jobs.payload(conn, job.id) == "[]"
    assert [j.id for j in jobs.recent(conn)] == [job.id]
