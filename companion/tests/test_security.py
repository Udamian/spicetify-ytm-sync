from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from ytm_sync_companion.security import (
    LOCKOUT_SECONDS,
    MAX_PAIRING_FAILURES,
    PAIRING_CODE_TTL_SECONDS,
    Pairing,
    TokenStore,
    extract_bearer,
    host_allowed,
    origin_allowed,
    write_private,
)

HOSTS = {"127.0.0.1:48215", "localhost:48215"}
ORIGINS = {"https://xpui.app.spotify.com"}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_host_allowed():
    assert host_allowed("127.0.0.1:48215", HOSTS)
    assert host_allowed("localhost:48215", HOSTS)
    assert not host_allowed("evil.example:48215", HOSTS)  # DNS rebinding
    assert not host_allowed("127.0.0.1:9999", HOSTS)
    assert not host_allowed(None, HOSTS)
    assert not host_allowed("", HOSTS)


def test_origin_allowed():
    assert origin_allowed("https://xpui.app.spotify.com", ORIGINS)
    assert not origin_allowed("https://evil.example", ORIGINS)
    assert not origin_allowed("null", ORIGINS)
    assert origin_allowed(None, ORIGINS)  # non-browser client
    assert not origin_allowed(None, ORIGINS, required=True)


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("Bearer abc", "abc"),
        ("bearer abc", "abc"),
        ("Bearer   abc  ", "abc"),
        ("Basic abc", None),
        ("Bearer", None),
        ("Bearer ", None),
        ("", None),
        (None, None),
    ],
)
def test_extract_bearer(header, expected):
    assert extract_bearer(header) == expected


def test_token_store_creates_and_reuses(tmp_path: Path):
    path = tmp_path / "sub" / "token"
    first = TokenStore(path)
    assert len(first.token) >= 40
    assert TokenStore(path).token == first.token  # persisted
    assert first.verify(first.token)
    assert not first.verify("wrong")
    assert not first.verify("")
    assert not first.verify(None)


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_write_private_is_user_only(tmp_path: Path):
    path = tmp_path / "secret"
    write_private(path, "x")
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_pairing_success_rotates_code():
    pairing = Pairing()
    old = pairing.code
    assert pairing.redeem(old) == "ok"
    assert pairing.code != old
    assert pairing.redeem(old) == "invalid"  # one-time use


def test_pairing_normalizes_input():
    pairing = Pairing()
    code = pairing.code
    dashed = f"{code[:4]}-{code[4:]}".lower()
    assert pairing.redeem(f"  {dashed} ") == "ok"


def test_pairing_rejects_empty_and_wrong():
    pairing = Pairing()
    assert pairing.redeem(None) == "invalid"
    assert pairing.redeem("") == "invalid"
    assert pairing.redeem("ZZZZZZZZ") == "invalid"


def test_pairing_expires_and_rotates():
    clock = FakeClock()
    pairing = Pairing(clock=clock)
    old = pairing.code
    clock.now += PAIRING_CODE_TTL_SECONDS + 1
    assert pairing.redeem(old) == "expired"
    assert pairing.code != old


def test_pairing_locks_out_brute_force():
    clock = FakeClock()
    pairing = Pairing(clock=clock)
    for _ in range(MAX_PAIRING_FAILURES):
        assert pairing.redeem("WRONG000") == "invalid"
    # Even the right code is refused while locked.
    assert pairing.redeem(pairing.code) == "locked"
    clock.now += LOCKOUT_SECONDS + 1
    assert pairing.redeem(pairing.code) == "ok"
