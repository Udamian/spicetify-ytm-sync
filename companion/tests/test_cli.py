from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from ytm_sync_companion import __main__ as cli
from ytm_sync_companion import runtime
from ytm_sync_companion.config import Settings

from .conftest import ORIGIN

SRC = str(Path(__file__).resolve().parents[1] / "src")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Settings for a private port and data folder, also visible to `main()` via the env."""
    port = free_port()
    monkeypatch.setenv("YTM_SYNC_PORT", str(port))
    monkeypatch.setenv("YTM_SYNC_DATA_DIR", str(tmp_path / "data"))
    return Settings(port=port, data_dir=tmp_path / "data")


def test_version(capsys):
    assert cli.main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == cli.__version__


def test_printing_an_unencodable_path_does_not_crash(monkeypatch):
    import io

    ascii_only = io.TextIOWrapper(io.BytesIO(), encoding="ascii")
    monkeypatch.setattr(sys, "stdout", ascii_only)
    cli.safe_streams()
    print("Data directory: C:\\Users\\Damián")  # would raise UnicodeEncodeError before
    ascii_only.flush()
    assert b"Dami" in ascii_only.buffer.getvalue()


def test_parser_accepts_the_documented_commands():
    parser = cli.build_parser()
    assert parser.parse_args([]).command is None
    assert parser.parse_args(["run", "--background"]).background is True
    assert parser.parse_args(["code", "--pause"]).pause is True
    args = parser.parse_args(["install", "--dry-run", "--no-apply", "--app-dir", "x"])
    assert (args.dry_run, args.no_apply, args.app_dir) == (True, True, "x")
    assert parser.parse_args(["uninstall", "--purge"]).purge is True
    with pytest.raises(SystemExit):
        parser.parse_args(["nonsense"])


def test_status_and_stop_when_nothing_runs(isolated, capsys):
    assert cli.main(["status"]) == 1
    assert "not running" in capsys.readouterr().out
    assert cli.main(["stop"]) == 0


def test_code_starts_the_service_and_prints_what_it_publishes(isolated, monkeypatch, capsys):
    started: list[list[str]] = []

    def fake_start(command):
        started.append(list(command))
        runtime.publish_code(isolated, "CAFE0123", 600)

    monkeypatch.setattr(runtime, "start_detached", fake_start)
    runtime.publish_code(isolated, "STALE000", 600)  # left behind by a crash: must not be shown
    assert cli.main(["code"]) == 0
    out = capsys.readouterr().out
    assert "CAFE0123" in out and "STALE000" not in out
    assert started and started[0][-2:] == ["run", "--background"]


def test_code_reports_when_the_service_does_not_come_up(isolated, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "start_detached", lambda _c: None)
    monkeypatch.setattr(runtime, "wait_for_code", lambda *_a, **_k: None)
    assert cli.main(["code"]) == 1
    assert "Could not get a pairing code" in capsys.readouterr().out


def test_run_does_nothing_when_a_companion_already_answers(isolated, monkeypatch, capsys):
    monkeypatch.setattr(runtime, "is_running", lambda *_a, **_k: True)
    assert cli.main(["run"]) == 0
    assert "already running" in capsys.readouterr().out


def _post(url: str, body: dict, port: int) -> tuple[int, dict]:
    request = urllib.request.Request(  # noqa: S310
        url, data=json.dumps(body).encode(), method="POST",
        headers={"Content-Type": "application/json", "Origin": ORIGIN,
                 "Host": f"127.0.0.1:{port}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read() or b"{}")


def test_background_service_end_to_end(isolated, monkeypatch, capsys):
    """The real process: start, publish the code, keep it current after pairing, stop cleanly."""
    env = {**os.environ, "PYTHONPATH": SRC}
    proc = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "ytm_sync_companion", "run", "--background"],
        env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.time() + 20
        while not runtime.is_running(isolated) and time.time() < deadline:
            time.sleep(0.2)
        assert runtime.is_running(isolated), "the service did not come up"
        assert cli.main(["status"]) == 0

        first = runtime.read_code(isolated)
        assert first is not None
        url = f"http://127.0.0.1:{isolated.port}/pair"
        status, body = _post(url, {"code": first[0]}, isolated.port)
        assert status == 200 and body["token"]

        # The code that was just used is gone; the file must hold the new one right away.
        second = runtime.read_code(isolated)
        assert second is not None and second[0] != first[0]
        assert _post(url, {"code": first[0]}, isolated.port)[0] == 403
        assert _post(url, {"code": second[0]}, isolated.port)[0] == 200  # the file's code works

        assert cli.main(["stop"]) == 0
        assert proc.wait(timeout=10) == 0
        assert not runtime.is_running(isolated)
        assert runtime.read_code(isolated) is None  # cleaned up on a clean stop
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(5)
