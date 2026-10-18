from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest
from werkzeug.serving import make_server

from ytm_sync_companion import runtime
from ytm_sync_companion.app import create_app
from ytm_sync_companion.config import Settings
from ytm_sync_companion.security import Pairing


def test_code_file_round_trip_and_expiry(settings):
    runtime.publish_code(settings, "ABCD1234", 600, now=lambda: 1000.0)
    assert runtime.read_code(settings, now=lambda: 1100.0) == ("ABCD1234", 500)
    assert runtime.read_code(settings, now=lambda: 1601.0) is None  # expired
    runtime.remove_code(settings)
    assert runtime.read_code(settings) is None
    runtime.remove_code(settings)  # removing twice is fine


def test_damaged_code_file_is_ignored(settings):
    runtime.code_path(settings).parent.mkdir(parents=True, exist_ok=True)
    for text in ("", "not json", json.dumps({"code": "X"}), json.dumps([1, 2])):
        runtime.code_path(settings).write_text(text)
        assert runtime.read_code(settings) is None


def test_wait_for_code_polls_until_it_appears(settings):
    clock = {"t": 0.0}
    calls = {"n": 0}

    def sleep(seconds: float) -> None:
        clock["t"] += seconds
        calls["n"] += 1
        if calls["n"] == 3:
            runtime.publish_code(settings, "FEEDBEEF", 600, now=lambda: clock["t"])

    found = runtime.wait_for_code(settings, timeout=10, sleep=sleep, now=lambda: clock["t"])
    assert found and found[0] == "FEEDBEEF"
    assert runtime.wait_for_code(
        Settings(data_dir=settings.data_dir / "elsewhere"), timeout=1,
        sleep=lambda s: clock.__setitem__("t", clock["t"] + s), now=lambda: clock["t"],
    ) is None


def test_keep_code_fresh_rotates_before_expiry_and_publishes():
    now = {"t": 0.0}
    pairing = Pairing(clock=lambda: now["t"])
    first = pairing.code
    published: list[tuple[str, float]] = []
    seen = threading.Event()

    def publish(code: str, left: float) -> None:
        published.append((code, left))
        seen.set()

    stop = threading.Event()
    now["t"] = 600 - 10  # 10 s left: inside the refresh margin
    runtime.keep_code_fresh(pairing, publish, stop, margin=90, interval=0.01)
    assert seen.wait(2)
    stop.set()
    assert published[0][0] == pairing.code
    assert published[0][0] != first
    assert published[0][1] > 500  # the new code starts a fresh 10 minutes


def test_background_command_from_source(tmp_path: Path):
    python = tmp_path / "python.exe"
    python.touch()
    assert runtime.background_command(str(python), "linux", frozen=False) == [
        str(python), "-m", "ytm_sync_companion", "run", "--background"]
    (tmp_path / "pythonw.exe").touch()
    assert runtime.background_command(str(python), "win32", frozen=False)[0].endswith("pythonw.exe")


def test_background_command_packaged_uses_the_windowed_exe_when_present(tmp_path: Path):
    console = tmp_path / "ytm-sync.exe"
    console.touch()
    assert runtime.background_command(str(console), "win32", frozen=True) == [
        str(console), "run", "--background"]  # no windowed build next to it: fall back
    (tmp_path / "ytm-sync-background.exe").touch()
    assert runtime.background_command(str(console), "win32", frozen=True) == [
        str(tmp_path / "ytm-sync-background.exe"), "run", "--background"]


def test_start_detached_flags():
    seen: list[dict] = []
    runtime.start_detached(["x"], "win32", lambda cmd, **kw: seen.append(kw))
    runtime.start_detached(["x"], "linux", lambda cmd, **kw: seen.append(kw))
    assert seen[0]["creationflags"] == 0x08000000 | 0x00000008 | 0x00000200
    assert seen[1]["start_new_session"] is True and "creationflags" not in seen[1]


@pytest.fixture
def server(tmp_path: Path):
    """A real companion bound to a free port, with a shutdown handler we can observe."""
    stopped = threading.Event()
    probe = make_server("127.0.0.1", 0, lambda *_: [])
    port = probe.port
    probe.server_close()
    settings = Settings(port=port, data_dir=tmp_path / "data")
    app = create_app(settings, on_shutdown=stopped.set)
    http = make_server("127.0.0.1", port, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield settings, app, stopped
    http.shutdown()
    thread.join(5)


def test_is_running_and_shutdown_through_the_api(server):
    settings, app, stopped = server
    assert runtime.is_running(settings)
    assert not runtime.is_running(Settings(port=settings.port + 1, data_dir=settings.data_dir))

    client = app.test_client()
    host = {"Host": f"127.0.0.1:{settings.port}"}
    assert client.post("/shutdown", headers=host).status_code == 401  # needs the token
    token = settings.token_path.read_text().strip()
    ok = client.post("/shutdown", headers={**host, "Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert stopped.wait(3)


def test_request_shutdown_uses_the_stored_token(server):
    settings, _app, stopped = server
    # The test server keeps running (the handler only sets an event), so it reports "not gone".
    assert runtime.request_shutdown(settings, timeout=1.0) is False
    assert stopped.wait(3)


def test_shutdown_is_not_supported_without_a_handler(settings):
    app = create_app(settings)
    token = settings.token_path.read_text().strip()
    headers = {"Host": f"127.0.0.1:{settings.port}", "Authorization": f"Bearer {token}"}
    response = app.test_client().post("/shutdown", headers=headers)
    assert response.status_code == 501


def test_request_shutdown_when_nothing_runs(settings):
    assert runtime.request_shutdown(settings) is True  # already gone
