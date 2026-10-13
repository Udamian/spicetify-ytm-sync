"""Thin wrapper around `ytmusicapi`.

`ytmusicapi` is an unofficial API and can break without notice (see docs/roadmap.md, B3).
Keeping every call to it behind this module makes that breakage easy to contain and test.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

SessionStatus = Literal["not_configured", "ok", "expired", "error"]
ClientFactory = Callable[[Path], Any]

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
        text = str(exc)
        if any(marker in text for marker in ("401", "403", "Unauthorized", "Forbidden")):
            return "expired"
        return "error"
    return "ok"


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
