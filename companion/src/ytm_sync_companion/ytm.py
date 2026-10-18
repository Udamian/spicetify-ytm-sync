"""Thin wrapper around `ytmusicapi`.

`ytmusicapi` is an unofficial API and can break without notice (see docs/roadmap.md, B3).
Keeping every call to it behind this module makes that breakage easy to contain and test.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

SessionStatus = Literal["not_configured", "ok", "expired", "error"]
ClientFactory = Callable[[Path], Any]

# What ytmusicapi raises when YouTube rejects the stored session: "Server returned HTTP 401:
# Unauthorized." / "...403: Forbidden." (ytmusic.py). Matching the status code next to "HTTP"
# avoids mistaking an unrelated number (a count, an id) for an expired session.
_EXPIRED = re.compile(r"HTTP\s+(?:401|403)\b|\bUnauthorized\b|\bForbidden\b", re.I)


def looks_expired(error_text: str) -> bool:
    """True when an error message says YouTube Music rejected our credentials."""
    return bool(_EXPIRED.search(error_text))


# Playlist ids come back from "browse" endpoints with a visual "VL" prefix (VLPL... -> PL...).
# Only the bare id is valid for editing a playlist.
_PLAYLIST_PREFIXES = ("PL", "RD", "OL", "LM")


def normalize_playlist_id(playlist_id: str) -> str:
    if playlist_id.startswith("VL") and playlist_id[2:4] in _PLAYLIST_PREFIXES:
        return playlist_id[2:]
    return playlist_id


def load_client(auth_path: Path) -> Any:
    """Build an authenticated client from the stored browser headers."""
    from ytmusicapi import YTMusic  # imported lazily: keeps unit tests independent of it

    return YTMusic(str(auth_path))


def session_status(auth_path: Path, client_factory: ClientFactory = load_client) -> SessionStatus:
    """Cheap authenticated call to find out whether the stored session still works.

    Detection is heuristic and must be validated against real expiry in spike S1:
    an expired browser session may surface as HTTP 401/403 or as empty results.
    """
    if not auth_path.exists():
        return "not_configured"
    try:
        client_factory(auth_path).get_library_playlists(limit=1)
    except Exception as exc:  # classify any failure, never leak its message
        return "expired" if looks_expired(str(exc)) else "error"
    return "ok"


PRIVACY_VALUES = ("PRIVATE", "UNLISTED", "PUBLIC")


def create_playlist(
    auth_path: Path,
    title: str,
    privacy: str = "PRIVATE",
    client_factory: ClientFactory = load_client,
) -> str:
    """Create an empty playlist and return its id.

    `ytmusicapi` returns the new id as a string, or the raw response when YouTube refuses
    (it does not raise), so anything that is not a plausible id is reported as a failure.
    """
    created = client_factory(auth_path).create_playlist(
        title, "Created by YTM Sync", privacy
    )
    if not isinstance(created, str) or len(created) < 10:
        raise RuntimeError("YouTube Music did not create the playlist")
    return normalize_playlist_id(created)


def list_playlists(auth_path: Path, client_factory: ClientFactory = load_client) -> list[dict]:
    """The user's library playlists as `{id, title, count}`."""
    raw = client_factory(auth_path).get_library_playlists(limit=None)
    return [
        {
            "id": normalize_playlist_id(str(item["playlistId"])),
            "title": item.get("title", ""),
            "count": item.get("count"),
        }
        for item in raw
        if item.get("playlistId")
    ]
