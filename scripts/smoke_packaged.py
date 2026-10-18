"""Smoke test of a built release folder (the real executables, not the Python sources).

    python scripts/smoke_packaged.py build/release/ytm-sync-0.1.0-windows

Checks: --version, `install --dry-run`, `code` (starts the windowless executable and prints a
pairing code), /health, pairing, that the published code changes after pairing, and `stop`.
Uses its own port and data folder, so it never touches a real installation.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ORIGIN = "https://xpui.app.spotify.com"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def check(condition: bool, message: str) -> None:
    print(("ok    " if condition else "FAIL  ") + message, flush=True)
    if not condition:
        raise SystemExit(1)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    folder = Path(sys.argv[1]).resolve()
    exe = folder / ("ytm-sync.exe" if sys.platform == "win32" else "ytm-sync")
    check(exe.is_file(), f"{exe.name} exists")
    check((folder / ("ytm-sync-background.exe" if sys.platform == "win32"
                     else "ytm-sync-background")).is_file(), "windowless executable exists")

    port = free_port()
    data = Path(tempfile.mkdtemp(prefix="ytm-smoke-"))
    env = {**os.environ, "YTM_SYNC_PORT": str(port), "YTM_SYNC_DATA_DIR": str(data)}

    def run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(  # noqa: S603
            [str(exe), *args], env=env, capture_output=True, text=True, timeout=timeout,
            check=False,
        )

    def post(path: str, body: dict) -> tuple[int, dict]:
        request = urllib.request.Request(  # noqa: S310
            f"http://127.0.0.1:{port}{path}", data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json", "Origin": ORIGIN},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as err:
            return err.code, {}

    def current_code() -> str:
        return json.loads((data / "pairing-code.json").read_text())["code"]

    try:
        version = run("--version")
        check(version.returncode == 0 and version.stdout.strip() != "", f"version {version.stdout.strip()}")

        plan = run("install", "--dry-run")
        check(plan.returncode == 0 and "Dry run only" in plan.stdout, "install --dry-run lists the steps")

        status = run("status")
        check(status.returncode == 1 and "not running" in status.stdout, "status: not running yet")

        code = run("code", timeout=90)
        check(code.returncode == 0 and "Pairing code" in code.stdout, "`code` starts it and prints a code")

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=10) as response:  # noqa: S310
            check(json.loads(response.read()).get("ok") is True, "/health answers")

        first = current_code()
        status_code, body = post("/pair", {"code": first})
        check(status_code == 200 and "token" in body, "pairing with the published code works")
        second = current_code()
        check(second != first, "the published code is replaced after pairing")
        check(post("/pair", {"code": first})[0] == 403, "the used code is refused")
        check(post("/pair", {"code": second})[0] == 200, "the new published code works")

        stop = run("stop")
        check(stop.returncode == 0, "stop")
        time.sleep(0.5)
        check(run("status").returncode == 1, "it is no longer running")
        check(not (data / "pairing-code.json").exists(), "the code file is removed on stop")
    finally:
        run("stop")
    print("\nAll smoke checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
