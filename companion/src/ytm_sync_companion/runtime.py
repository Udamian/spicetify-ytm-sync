"""Running the companion as a background service: pairing code file, liveness, detached start.

When the companion starts at login there is no console to read the pairing code from. It
therefore keeps the current code in a file only the current user can read, refreshed before it
expires, and `ytm-sync-companion code` prints it. That is no weaker than a console window: any
process of the same user could already read the stored YouTube Music session.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path

from .config import HOST, Settings
from .security import Pairing, write_private

# Calls to 127.0.0.1 must never go through a system or corporate proxy.
_DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))

CODE_FILE = "pairing-code.json"
REFRESH_MARGIN_SECONDS = 90  # a code is replaced when less than this is left
REFRESH_INTERVAL_SECONDS = 15


def code_path(settings: Settings) -> Path:
    return settings.data_dir / CODE_FILE


def publish_code(
    settings: Settings, code: str, seconds_left: float, now: Callable[[], float] = time.time
) -> None:
    payload = {"code": code, "expires_at": now() + seconds_left}
    write_private(code_path(settings), json.dumps(payload))


def read_code(
    settings: Settings, now: Callable[[], float] = time.time
) -> tuple[str, int] | None:
    """(code, seconds left) of the published code, or None if missing, damaged or expired."""
    try:
        data = json.loads(code_path(settings).read_text(encoding="utf-8"))
        code, expires_at = str(data["code"]), float(data["expires_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    left = int(expires_at - now())
    return (code, left) if code and left > 0 else None


def remove_code(settings: Settings) -> None:
    try:
        code_path(settings).unlink()
    except OSError:
        pass


def keep_code_fresh(
    pairing: Pairing,
    publish: Callable[[str, float], None],
    stop: threading.Event,
    *,
    margin: float = REFRESH_MARGIN_SECONDS,
    interval: float = REFRESH_INTERVAL_SECONDS,
) -> threading.Thread:
    """Rotate the code shortly before it expires and publish the new one."""

    def loop() -> None:
        while not stop.wait(interval):
            if pairing.seconds_left() < margin:
                pairing.rotate()
                publish(pairing.code, pairing.seconds_left())

    thread = threading.Thread(target=loop, name="ytm-sync-code", daemon=True)
    thread.start()
    return thread


def is_running(settings: Settings, timeout: float = 1.0) -> bool:
    """True when a YTM Sync companion answers on this port."""
    url = f"http://{HOST}:{settings.port}/health"
    request = urllib.request.Request(url, headers={"Host": f"{HOST}:{settings.port}"})  # noqa: S310
    try:
        with _DIRECT.open(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return False
    return isinstance(body, dict) and "api_version" in body


def running_version(settings: Settings, timeout: float = 1.0) -> str | None:
    """The version a running YTM Sync companion reports, or None when none answers."""
    url = f"http://{HOST}:{settings.port}/health"
    request = urllib.request.Request(url, headers={"Host": f"{HOST}:{settings.port}"})  # noqa: S310
    try:
        with _DIRECT.open(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if isinstance(body, dict) and "api_version" in body:
        return str(body.get("version", ""))
    return None


BACKGROUND_EXE = "ytm-sync-background"  # windowed build next to the console one (Windows)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def background_command(
    python: str = sys.executable,
    platform: str = sys.platform,
    frozen: bool | None = None,
) -> list[str]:
    """Command that runs the companion with no console window.

    Packaged build: the windowed executable that sits next to the console one (a console
    executable started from a shortcut would flash a window). From source: `pythonw.exe` on
    Windows, otherwise the same interpreter.
    """
    frozen = is_frozen() if frozen is None else frozen
    if frozen:
        suffix = ".exe" if platform == "win32" else ""
        windowed = Path(python).with_name(BACKGROUND_EXE + suffix)
        return [str(windowed if windowed.exists() else python), "run", "--background"]
    if platform == "win32":
        candidate = Path(python).with_name("pythonw.exe")
        if candidate.exists():
            python = str(candidate)
    return [python, "-m", "ytm_sync_companion", "run", "--background"]


def start_detached(
    command: Sequence[str],
    platform: str = sys.platform,
    popen: Callable[..., object] = subprocess.Popen,
) -> None:
    """Start the companion so that it outlives this process and shows no window."""
    kwargs: dict[str, object] = {
        "stdin": subprocess.DEVNULL, "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if platform == "win32":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
        kwargs["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000
    else:
        kwargs["start_new_session"] = True
    popen(list(command), **kwargs)  # noqa: S603


def wait_for_code(
    settings: Settings,
    timeout: float = 15.0,
    *,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.time,
) -> tuple[str, int] | None:
    deadline = now() + timeout
    while True:
        found = read_code(settings, now)
        if found:
            return found
        if now() >= deadline:
            return None
        sleep(0.3)


def request_shutdown(settings: Settings, timeout: float = 10.0) -> bool:
    """Ask a running companion to stop (it pauses a running job first). True when it is gone.

    Uses the bearer token the companion itself stored for the current user, so only that user
    (or a process of theirs) can do this.
    """
    if not is_running(settings):
        return True
    try:
        token = settings.token_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    url = f"http://{HOST}:{settings.port}/shutdown"
    request = urllib.request.Request(  # noqa: S310
        url, data=b"{}", method="POST",
        headers={"Host": f"{HOST}:{settings.port}", "Authorization": f"Bearer {token}",
                 "Content-Type": "application/json"},
    )
    try:
        _DIRECT.open(request, timeout=timeout).close()
    except (urllib.error.URLError, OSError):
        return not is_running(settings)
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not is_running(settings, timeout=0.5):
            return True
        time.sleep(0.2)
    return False


def quiet_streams() -> None:
    """Background mode: nothing may write to a console that does not exist."""
    # A windowed build has no stdout/stderr at all (they are None), so always replace them.
    devnull = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    sys.stdout = devnull
    sys.stderr = devnull
