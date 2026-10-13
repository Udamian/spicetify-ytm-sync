from __future__ import annotations

from pathlib import Path

import pytest

from ytm_sync_companion import ytm

from .conftest import FakeYTMusic


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("VLPLabc123", "PLabc123"),
        ("PLabc123", "PLabc123"),
        ("VLRDCLAK5uy_x", "RDCLAK5uy_x"),
        ("VLOLAK5uy_x", "OLAK5uy_x"),
        ("VLLM", "LM"),
        ("VLxyz", "VLxyz"),  # unknown shape: left untouched
        ("", ""),
    ],
)
def test_normalize_playlist_id(raw, expected):
    assert ytm.normalize_playlist_id(raw) == expected


def test_status_not_configured(tmp_path: Path):
    assert ytm.session_status(tmp_path / "missing.json") == "not_configured"


def test_status_ok(tmp_path: Path):
    auth = tmp_path / "browser.json"
    auth.write_text("{}")
    assert ytm.session_status(auth, lambda _p: FakeYTMusic()) == "ok"


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Server returned HTTP 401: Unauthorized.", "expired"),
        ("Server returned HTTP 403: Forbidden.", "expired"),
        ("Server returned HTTP 400: Bad Request.", "error"),
        ("boom", "error"),
    ],
)
def test_status_classifies_failures(tmp_path: Path, message, expected):
    auth = tmp_path / "browser.json"
    auth.write_text("{}")
    factory = lambda _p: FakeYTMusic(fail_with=RuntimeError(message))  # noqa: E731
    assert ytm.session_status(auth, factory) == expected


def test_list_playlists_normalizes_and_skips_entries_without_id(tmp_path: Path):
    result = ytm.list_playlists(tmp_path / "x.json", lambda _p: FakeYTMusic())
    assert result == [
        {"id": "PLabc123", "title": "Liked mirror", "count": 42},
        {"id": "PLdef456", "title": "Gym", "count": None},
    ]
