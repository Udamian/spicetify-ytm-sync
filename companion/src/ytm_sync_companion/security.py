"""Local-server hardening: Host/Origin checks, one-time pairing and bearer-token auth.

Why this exists: the companion holds YouTube Music credentials and listens on localhost.
Without these checks, any web page open in the user's normal browser could talk to it.
See docs/security.md.
"""

from __future__ import annotations

import contextlib
import hmac
import os
import secrets
import time
from collections.abc import Callable, Iterable
from pathlib import Path

PAIRING_CODE_TTL_SECONDS = 600
MAX_PAIRING_FAILURES = 5
LOCKOUT_SECONDS = 60


def write_private(path: Path, text: str) -> None:
    """Write a file readable only by the current user (best effort on Windows)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    with contextlib.suppress(OSError):
        os.chmod(path, 0o600)


def host_allowed(host_header: str | None, allowed_hosts: Iterable[str]) -> bool:
    return bool(host_header) and host_header in set(allowed_hosts)


def origin_allowed(
    origin: str | None, allowed_origins: Iterable[str], *, required: bool = False
) -> bool:
    """A missing Origin is fine for non-browser clients unless `required` is set.

    A present Origin must be in the allow-list (the literal string "null" is rejected).
    """
    if origin is None:
        return not required
    return origin in set(allowed_origins)


def extract_bearer(auth_header: str | None) -> str | None:
    if not auth_header:
        return None
    scheme, _, value = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


class TokenStore:
    """Persistent bearer token, created on first run and stored with 0600 permissions."""

    def __init__(self, path: Path) -> None:
        self._path = path
        if path.exists():
            self._token = path.read_text(encoding="utf-8").strip()
        else:
            self._token = secrets.token_urlsafe(32)
            write_private(path, self._token)

    @property
    def token(self) -> str:
        return self._token

    def verify(self, candidate: str | None) -> bool:
        if not candidate:
            return False
        return hmac.compare_digest(candidate.encode(), self._token.encode())


class Pairing:
    """One-time pairing code the user copies from the companion into the Spicetify app.

    The code expires, rotates after every successful use and locks out brute force.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._failures = 0
        self._locked_until = 0.0
        self._code = ""
        self._expires_at = 0.0
        self.rotate()

    @property
    def code(self) -> str:
        return self._code

    def rotate(self) -> str:
        self._code = secrets.token_hex(4).upper()  # 8 hex chars
        self._expires_at = self._clock() + PAIRING_CODE_TTL_SECONDS
        return self._code

    def redeem(self, candidate: str | None) -> str:
        """Return one of: "ok", "invalid", "expired", "locked"."""
        now = self._clock()
        if now < self._locked_until:
            return "locked"
        if now > self._expires_at:
            self.rotate()
            return "expired"
        normalized = (candidate or "").strip().upper().replace("-", "")
        if normalized and hmac.compare_digest(normalized.encode(), self._code.encode()):
            self._failures = 0
            self.rotate()
            return "ok"
        self._failures += 1
        if self._failures >= MAX_PAIRING_FAILURES:
            self._locked_until = now + LOCKOUT_SECONDS
            self._failures = 0
        return "invalid"
