from __future__ import annotations

import random

import pytest

from ytm_sync_companion import jobs
from ytm_sync_companion.db import init_db
from ytm_sync_companion.sync import (
    SessionExpired,
    Stopped,
    SyncEngine,
    WriteFailed,
    plan_moves,
    to_spotify_tracks,
)

from .fakes import FakeYTM, make_tracks

DEST = "PLdest"


@pytest.fixture
def conn(tmp_path):
    connection = init_db(tmp_path / "t.sqlite3")
    yield connection
    connection.close()


@pytest.fixture
def pair_id(conn):
    return jobs.upsert_pair(conn, "spotify:collection:tracks", DEST)


@pytest.fixture
def fake():
    return FakeYTM()


@pytest.fixture
def sleeps():
    return []


@pytest.fixture
def engine(conn, fake, sleeps):
    return SyncEngine(conn, fake, sleep=sleeps.append, batch_size=25)


def register_all(fake, tracks):
    return [fake.register(t) for t in tracks]


def test_dump_keeps_spotify_order_across_batches(engine, fake, conn, pair_id):
    tracks = make_tracks(60)
    expected = register_all(fake, tracks)
    report = engine.dump(pair_id, tracks)

    assert fake.ids(DEST) == expected
    assert (report.matched_ok, report.added, report.order_verified) == (60, 60, True)
    assert report.order_moves == 0  # right from the writes, not repaired afterwards
    assert [len(ids) for ids, _ in fake.add_calls] == [25, 25, 10]
    assert all(not on_top for _, on_top in fake.add_calls)  # the dump appends in order
    saved = conn.execute("SELECT last_order FROM pairs WHERE id = ?", (pair_id,)).fetchone()[0]
    assert saved.count("spotify:track:") == 60


def test_same_video_for_two_tracks_is_written_once(engine, fake, pair_id):
    tracks = make_tracks(6)
    register_all(fake, tracks)
    fake.register(tracks[5], video_id="v-0")  # track 5 resolves to the same video as track 0
    report = engine.dump(pair_id, tracks)
    assert report.duplicates_collapsed == 1
    assert fake.ids(DEST) == ["v-0", "v-1", "v-2", "v-3", "v-4"]


def test_resume_after_stop_completes_without_duplicates_or_new_searches(
    engine, fake, pair_id
):
    tracks = make_tracks(80)
    expected = register_all(fake, tracks)
    with pytest.raises(Stopped):
        engine.dump(pair_id, tracks, should_stop=lambda: len(fake.add_calls) >= 2)
    assert len(fake.ids(DEST)) == 50

    searches_before = fake.search_calls
    report = engine.dump(pair_id, tracks)
    assert fake.search_calls == searches_before  # matches were kept
    assert fake.ids(DEST) == expected
    assert report.already_present == 50 and report.added == 30


def test_review_tracks_wait_for_the_user_and_are_then_placed_in_order(engine, fake, pair_id):
    tracks = make_tracks(6)
    register_all(fake, tracks)
    fake.register(tracks[2], artists=("Somebody Else",))  # artist mismatch -> not ok
    first = engine.dump(pair_id, tracks)
    assert first.matched_ok == 5 and first.to_review + first.not_found == 1
    assert "v-2" not in fake.ids(DEST)

    engine.resolve_review(tracks[2].uri, "v-2")  # the user accepts the match
    second = engine.dump(pair_id, tracks)
    assert second.order_verified is True
    assert fake.ids(DEST) == [f"v-{i}" for i in range(6)]  # moved from the end to its place


def test_skipped_review_track_stays_out(engine, fake, pair_id):
    tracks = make_tracks(3)
    register_all(fake, tracks)
    fake.register(tracks[1], artists=("Somebody Else",))
    engine.dump(pair_id, tracks)
    engine.resolve_review(tracks[1].uri, None)
    engine.dump(pair_id, tracks)
    assert fake.ids(DEST) == ["v-0", "v-2"]


def test_transient_refusal_is_retried(engine, fake, sleeps, pair_id):
    tracks = make_tracks(5)
    expected = register_all(fake, tracks)
    fake.fail_adds = 1
    engine.dump(pair_id, tracks)
    assert fake.ids(DEST) == expected
    assert 1 in sleeps  # backed off once


def test_persistent_refusal_raises_and_keeps_progress(engine, fake, conn, pair_id):
    tracks = make_tracks(5)
    register_all(fake, tracks)
    fake.fail_adds = 99
    with pytest.raises(WriteFailed):
        engine.dump(pair_id, tracks)
    assert conn.execute("SELECT COUNT(*) FROM track_map").fetchone()[0] == 5


def test_expired_session_is_reported(engine, fake, pair_id):
    tracks = make_tracks(2)
    register_all(fake, tracks)
    fake.fail_with = Exception("HTTP 403 Forbidden: secret-cookie-value")
    with pytest.raises(SessionExpired) as info:
        engine.dump(pair_id, tracks)
    assert "secret-cookie-value" not in str(info.value)


def test_stale_reads_after_a_write_do_not_trigger_needless_moves(
    engine, fake, sleeps, pair_id
):
    old = make_tracks(5)
    register_all(fake, old)
    engine.dump(pair_id, old)
    fresh = [make_tracks(1, start=5)[0]]
    register_all(fake, fresh)
    engine.incremental(pair_id, fresh)

    # Two reads still show the playlist from before the new track was added.
    fake.stale_reads = 2
    sleeps.clear()
    assert engine.verify_and_fix_order(DEST, ["v-5"], top_only=True) == (True, 0)
    assert sleeps.count(1.5) == 2  # it waited and re-read instead of "repairing"


def test_misordered_destination_is_repaired_with_moves(engine, fake, pair_id):
    tracks = make_tracks(12)
    expected = register_all(fake, tracks)
    engine.dump(pair_id, tracks)
    playlist = fake.playlists[DEST]
    playlist.insert(0, playlist.pop(7))  # someone moved a track
    verified, moves = engine.verify_and_fix_order(DEST, expected)
    assert verified is True and moves >= 1
    assert fake.ids(DEST) == expected


def test_incremental_puts_new_tracks_on_top_newest_first(engine, fake, conn, pair_id):
    old = make_tracks(10)
    register_all(fake, old)
    engine.dump(pair_id, old)

    fresh = list(reversed(make_tracks(3, start=10)))  # Spotify lists the newest first
    register_all(fake, fresh)
    fake.add_calls.clear()
    report = engine.incremental(pair_id, fresh)

    assert fake.ids(DEST)[:3] == ["v-12", "v-11", "v-10"]
    assert fake.ids(DEST)[3:] == [f"v-{i}" for i in range(10)]
    assert report.added == 3 and report.order_verified
    assert report.order_moves == 0  # right from the writes, not repaired afterwards
    assert all(len(ids) == 1 and on_top for ids, on_top in fake.add_calls)
    saved = conn.execute("SELECT last_order FROM pairs WHERE id = ?", (pair_id,)).fetchone()[0]
    assert saved.startswith('["spotify:track:12"')


def test_incremental_skips_what_is_already_there(engine, fake, pair_id):
    tracks = make_tracks(4)
    register_all(fake, tracks)
    engine.dump(pair_id, tracks)
    report = engine.incremental(pair_id, [tracks[0]])
    assert report.added == 0
    assert fake.ids(DEST) == [f"v-{i}" for i in range(4)]


def test_cancelled_job_state_is_visible_to_should_stop(engine, fake, conn, pair_id):
    tracks = make_tracks(30)
    register_all(fake, tracks)
    job = jobs.enqueue(conn, pair_id, "initial_dump", total=30)
    jobs.claim_next(conn)
    jobs.cancel(conn, job.id)
    with pytest.raises(Stopped):
        engine.dump(pair_id, tracks, should_stop=lambda: jobs.is_cancelled(conn, job.id))


def apply_moves(current, moves):
    sim = list(current)
    for moved, successor in moves:
        item = next(x for x in sim if x[0] == moved)
        sim.remove(item)
        sim.insert(next(i for i, x in enumerate(sim) if x[0] == successor), item)
    return sim


def test_plan_moves_sorts_any_permutation_even_with_foreign_items():
    rng = random.Random(7)  # noqa: S311 - deterministic test data, not security
    for _ in range(300):
        n = rng.randint(2, 14)
        desired = [f"v{i}" for i in range(n)]
        foreign = [(f"sx{i}", f"x{i}") for i in range(rng.randint(0, 3))]
        current = [(f"s{v}", v) for v in desired] + foreign
        rng.shuffle(current)
        result = apply_moves(current, plan_moves(current, desired))
        assert [v for _, v in result if v in set(desired)] == desired


def test_plan_moves_is_empty_when_already_in_order_and_small_for_one_displaced_item():
    desired = [f"v{i}" for i in range(20)]
    ordered = [(f"s{v}", v) for v in desired]
    assert plan_moves(ordered, desired) == []
    displaced = ordered[:]
    displaced.insert(0, displaced.pop(10))
    assert len(plan_moves(displaced, desired)) == 1


def test_to_spotify_tracks_accepts_app_payload():
    tracks = to_spotify_tracks(
        [{"uri": "spotify:track:1", "title": "T", "artists": ["A", "B"], "durationMs": 1000}]
    )
    assert tracks[0].artists == ("A", "B") and tracks[0].duration_ms == 1000