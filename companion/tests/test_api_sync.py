from __future__ import annotations

import time

import pytest

from ytm_sync_companion import jobs
from ytm_sync_companion.app import create_app
from ytm_sync_companion.db import connect

from .conftest import HOST_HEADER, ORIGIN
from .fakes import FakeYTM, make_tracks

DEST = "PLabcdefghij"
SOURCE = "spotify:collection:tracks"


def payload(tracks):
    return [
        {"uri": t.uri, "title": t.title, "artists": list(t.artists), "durationMs": t.duration_ms}
        for t in tracks
    ]


@pytest.fixture
def fake():
    return FakeYTM()


@pytest.fixture
def app(settings, fake):
    return create_app(
        settings, client_factory=lambda _p: fake,
        engine_kwargs={"sleep": lambda _s: None},
    )


@pytest.fixture
def worker(app):
    return app.extensions["ytm_sync"].worker


@pytest.fixture
def connected(settings):
    """A stored YouTube Music session (content is irrelevant: the client is faked)."""
    settings.auth_path.parent.mkdir(parents=True, exist_ok=True)
    settings.auth_path.write_text("{}")


def start(client, auth, tracks, **extra):
    body = {"source_uri": SOURCE, "dest_playlist_id": DEST, "kind": "initial_dump",
            "tracks": payload(tracks), **extra}
    return client.post("/sync/start", json=body, headers=auth)


def test_start_needs_a_stored_youtube_session(client, auth):
    response = start(client, auth, make_tracks(2))
    assert (response.status_code, response.get_json()["error"]) == (409, "not_configured")


def test_full_dump_through_the_api(client, auth, connected, fake, worker):
    tracks = make_tracks(30)
    for t in tracks:
        fake.register(t)
    response = start(client, auth, tracks)
    assert response.status_code == 202
    job_id = response.get_json()["job_id"]

    assert worker.run_once() is True
    job = client.get(f"/status?job_id={job_id}", headers=auth).get_json()["job"]
    assert job["state"] == "done" and job["progress"] == 1.0
    assert job["report"]["added"] == 30 and job["report"]["order_verified"] is True
    assert fake.ids(DEST) == [f"v-{i}" for i in range(30)]

    overview = client.get("/status", headers=auth).get_json()
    assert overview["jobs"][0]["id"] == job_id and overview["review_count"] == 0


def test_second_start_while_one_is_active_is_refused(client, auth, connected):
    first = start(client, auth, make_tracks(3)).get_json()["job_id"]
    again = start(client, auth, make_tracks(3))
    assert (again.status_code, again.get_json()["job_id"]) == (409, first)


def test_cancel_before_it_runs(client, auth, connected, worker):
    job_id = start(client, auth, make_tracks(3)).get_json()["job_id"]
    response = client.post("/sync/cancel", json={"job_id": job_id}, headers=auth)
    assert response.get_json() == {"cancelled": True}
    assert worker.run_once() is False
    state = client.get(f"/status?job_id={job_id}", headers=auth).get_json()["job"]["state"]
    assert state == "cancelled"


@pytest.mark.parametrize(
    "change",
    [
        {"source_uri": "spotify:artist:abc"},
        {"dest_playlist_id": "x"},
        {"kind": "everything"},
        {"mode": "delete-all"},
        {"tracks": "nope"},
        {"tracks": [{"uri": "http://evil", "title": "t", "artists": []}]},
        {"tracks": [{"uri": "spotify:track:1", "title": "t" * 400, "artists": []}]},
    ],
)
def test_start_validates_input(client, auth, connected, change):
    body = {"source_uri": SOURCE, "dest_playlist_id": DEST, "kind": "initial_dump",
            "tracks": payload(make_tracks(1)), **change}
    assert client.post("/sync/start", json=body, headers=auth).status_code == 400


def test_dump_with_no_tracks_is_rejected_but_empty_incremental_is_fine(client, auth, connected):
    assert start(client, auth, []).status_code == 400
    response = start(client, auth, [], kind="incremental")
    assert response.get_json() == {"job_id": None, "nothing_to_do": True}


def test_vid_prefix_in_destination_is_accepted(client, auth, connected):
    assert start(client, auth, make_tracks(1), dest_playlist_id="VL" + DEST).status_code == 202


def test_preview_counts_what_still_needs_searching(client, auth, connected, fake, worker):
    tracks = make_tracks(10)
    for t in tracks:
        fake.register(t)
    start(client, auth, tracks[:4])
    worker.run_once()
    preview = client.post("/sync/preview", json={"tracks": payload(tracks)}, headers=auth)
    data = preview.get_json()
    assert (data["total"], data["already_matched"], data["to_search"]) == (10, 4, 6)
    assert data["estimated_seconds"] > 0


def test_a_whole_library_fits_but_other_endpoints_keep_the_small_limit(client, auth):
    big = payload(make_tracks(3000))  # well over 256 KB of JSON
    assert client.post("/sync/preview", json={"tracks": big}, headers=auth).status_code == 200
    too_big = client.post("/auth/headers", json={"headers": "x" * 300_000}, headers=auth)
    assert too_big.status_code == 413


def test_session_expiry_is_reported_without_leaking_secrets(
    client, auth, connected, fake, worker
):
    tracks = make_tracks(3)
    for t in tracks:
        fake.register(t)
    fake.fail_with = Exception("HTTP 403 Forbidden cookie=super-secret-value")
    job_id = start(client, auth, tracks).get_json()["job_id"]
    worker.run_once()
    response = client.get(f"/status?job_id={job_id}", headers=auth)
    job = response.get_json()["job"]
    assert (job["state"], job["error_code"]) == ("failed", "session_expired")
    assert "super-secret-value" not in response.get_data(as_text=True)


def test_review_flow_through_the_api(client, auth, connected, fake, worker):
    tracks = make_tracks(4)
    for t in tracks:
        fake.register(t)
    fake.register(tracks[1], artists=("Somebody Else",))
    start(client, auth, tracks)
    worker.run_once()

    items = client.get("/review", headers=auth).get_json()["items"]
    assert [i["uri"] for i in items] == ["spotify:track:1"]
    assert client.get("/status", headers=auth).get_json()["review_count"] + \
        client.get("/status", headers=auth).get_json()["not_found_count"] == 1

    bad = client.post("/review/resolve", json={"uri": items[0]["uri"], "video_id": "short"},
                      headers=auth)
    assert bad.status_code == 400
    missing = client.post("/review/resolve", json={"uri": "spotify:track:999", "video_id": None},
                          headers=auth)
    assert missing.status_code == 404

    ok = client.post("/review/resolve", json={"uri": items[0]["uri"], "video_id": "abcdefghijk"},
                     headers=auth)
    assert ok.status_code == 200
    assert client.get("/review", headers=auth).get_json()["items"] == []


def test_running_jobs_go_back_to_the_queue_when_the_companion_starts(settings, fake):
    first = create_app(settings, client_factory=lambda _p: fake)
    assert first is not None
    conn = connect(settings.db_path)
    pair_id = jobs.upsert_pair(conn, SOURCE, DEST)
    job = jobs.enqueue(conn, pair_id, "initial_dump", 5, "[]")
    jobs.claim_next(conn)
    conn.close()

    create_app(settings, client_factory=lambda _p: fake)  # a restart
    conn = connect(settings.db_path)
    assert jobs.get(conn, job.id).state == "queued"
    conn.close()


def test_background_thread_picks_up_a_job(settings, fake):
    app = create_app(settings, client_factory=lambda _p: fake, worker_enabled=True,
                     engine_kwargs={"sleep": lambda _s: None})
    services = app.extensions["ytm_sync"]
    try:
        settings.auth_path.parent.mkdir(parents=True, exist_ok=True)
        settings.auth_path.write_text("{}")
        client = app.test_client()
        code = services.pairing.code
        token = client.post("/pair", json={"code": code},
                            headers={**HOST_HEADER, "Origin": ORIGIN}).get_json()["token"]
        auth = {**HOST_HEADER, "Authorization": f"Bearer {token}"}
        tracks = make_tracks(12)
        for t in tracks:
            fake.register(t)
        job_id = start(client, auth, tracks).get_json()["job_id"]

        deadline = time.time() + 10
        state = ""
        while time.time() < deadline and state != "done":
            state = client.get(f"/status?job_id={job_id}", headers=auth).get_json()["job"]["state"]
            time.sleep(0.05)
        assert state == "done"
        assert fake.ids(DEST) == [f"v-{i}" for i in range(12)]
    finally:
        services.worker.stop()
    assert not services.worker.running
