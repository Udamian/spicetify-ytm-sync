"""In-memory stand-in for ytmusicapi.YTMusic playlists, with injectable failures."""

from __future__ import annotations

from typing import Any

from ytm_sync_companion.matching import SpotifyTrack, build_query


def make_tracks(n: int, start: int = 0) -> list[SpotifyTrack]:
    return [
        SpotifyTrack(
            uri=f"spotify:track:{i}",
            title=f"Song {i}",
            artists=(f"Artist {i}",),
            duration_ms=200_000 + i * 1000,
        )
        for i in range(start, start + n)
    ]


class FakeYTM:
    def __init__(self) -> None:
        self.playlists: dict[str, list[dict[str, str]]] = {}
        self.add_to_top: dict[str, bool] = {}
        self.catalog: dict[str, list[dict[str, Any]]] = {}
        self.search_calls = 0
        self.add_calls: list[tuple[list[str], bool]] = []  # (video ids, add_to_top at the time)
        self.fail_adds = 0  # next N add calls come back STATUS_FAILED
        self.stale_reads = 0  # next N reads return the playlist as it was before the last write
        self.fail_with: Exception | None = None
        self._snapshot: dict[str, list[dict[str, str]]] = {}
        self._counter = 0

    # ---- test setup -----------------------------------------------------------------------
    def register(self, track: SpotifyTrack, video_id: str | None = None,
                 artists: tuple[str, ...] | None = None) -> str:
        vid = video_id or f"v-{track.uri.rsplit(':', 1)[1]}"
        self.catalog[build_query(track)] = [
            {
                "videoId": vid,
                "title": track.title,
                "artists": [{"name": a} for a in (artists or track.artists)],
                "duration_seconds": (track.duration_ms or 0) // 1000,
            }
        ]
        return vid

    def ids(self, playlist_id: str) -> list[str]:
        return [t["videoId"] for t in self.playlists.get(playlist_id, [])]

    # ---- ytmusicapi surface ---------------------------------------------------------------
    def search(self, query: str, filter: str | None = None, limit: int = 20) -> list[dict]:
        self._maybe_fail()
        self.search_calls += 1
        return self.catalog.get(query, []) if filter == "songs" else []

    def get_playlist(self, playlistId: str, limit: int | None = None) -> dict:
        self._maybe_fail()
        if self.stale_reads > 0:
            self.stale_reads -= 1
            return {"tracks": list(self._snapshot.get(playlistId, []))}
        return {"tracks": [dict(t) for t in self.playlists.get(playlistId, [])]}

    def add_playlist_items(self, playlistId: str, videoIds: list[str] | None = None,
                           duplicates: bool = False) -> Any:
        self._maybe_fail()
        ids = list(videoIds or [])
        self.add_calls.append((ids, self.add_to_top.get(playlistId, False)))
        if self.fail_adds > 0:
            self.fail_adds -= 1
            return {"status": "STATUS_FAILED"}
        current = self.playlists.setdefault(playlistId, [])
        existing = {t["videoId"] for t in current}
        if not duplicates and (len(set(ids)) != len(ids) or existing & set(ids)):
            return {"status": "STATUS_FAILED"}  # whole batch refused, like YouTube
        self._snapshot[playlistId] = [dict(t) for t in current]
        new = []
        for vid in ids:
            self._counter += 1
            new.append({"videoId": vid, "setVideoId": f"s{self._counter}"})
        if self.add_to_top.get(playlistId, False):
            current[0:0] = new
        else:
            current.extend(new)
        return {"status": "STATUS_SUCCEEDED", "playlistEditResults": []}

    def edit_playlist(self, playlistId: str, **kwargs: Any) -> Any:
        self._maybe_fail()
        if "addToTop" in kwargs:
            self.add_to_top[playlistId] = bool(kwargs["addToTop"])
        if "moveItem" in kwargs:
            moved, successor = kwargs["moveItem"]
            current = self.playlists[playlistId]
            self._snapshot[playlistId] = [dict(t) for t in current]
            item = next(t for t in current if t["setVideoId"] == moved)
            current.remove(item)
            index = next(i for i, t in enumerate(current) if t["setVideoId"] == successor)
            current.insert(index, item)
        return "STATUS_SUCCEEDED"

    def _maybe_fail(self) -> None:
        if self.fail_with:
            raise self.fail_with
