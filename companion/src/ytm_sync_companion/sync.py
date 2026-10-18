"""Sync engine: dump a Spotify source into a YouTube Music playlist and keep it up to date.

Design, from what spikes S2 and S5 verified (see spikes/README.md):

* Initial dump: the destination is switched to "add to the end" and the tracks are appended in
  Spotify order (first row first), in batches. Appending in order is verified; `addToTop` with a
  multi-track batch is NOT (only single adds were tested), so the dump does not use it.
* Later syncs: new tracks go to the top with `addToTop`, ONE per call, oldest of the new ones
  first, so the newest ends up first. That is the verified case. For Liked Songs new items
  always appear at the top of Spotify's list.
* Duplicates are filtered here: YouTube refuses a whole batch when one track is already there,
  and `duplicates=True` would add it again.
* ytmusicapi does not raise when YouTube refuses a write: every write checks the returned status.
* Reads right after a write can lag: the order check re-reads a few times, and a mismatch is
  repaired with `moveItem` (`plan_moves`).
* Resumable: matches live in `track_map`, so a stopped job re-run only does what is left, and
  tracks already in the destination are skipped.

Nothing here touches the network by itself: the YouTube Music client is injected.
"""

from __future__ import annotations

import json
import logging
import time
from bisect import bisect_left
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from . import matching
from .matching import MatchResult, SpotifyTrack
from .ytm import looks_expired

log = logging.getLogger(__name__)

MAX_FIX_MOVES = 300


class SyncError(Exception):
    """Base class for engine errors. Messages never contain credentials."""


class SessionExpired(SyncError):
    """YouTube Music refused the stored session: the user has to reconnect."""


class WriteFailed(SyncError):
    """YouTube kept refusing a write after the retries."""


class Stopped(SyncError):
    """The job was cancelled or the companion is shutting down. Progress is kept."""


class YTMClient(Protocol):
    """The part of `ytmusicapi.YTMusic` the engine uses."""

    def search(self, query: str, filter: str | None = None, limit: int = 20) -> list[dict]: ...

    def get_playlist(self, playlistId: str, limit: int | None = None) -> dict: ...

    def add_playlist_items(
        self, playlistId: str, videoIds: list[str] | None = None, duplicates: bool = False
    ) -> Any: ...

    def edit_playlist(self, playlistId: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class SyncReport:
    matched_ok: int
    to_review: int
    not_found: int
    added: int
    already_present: int
    duplicates_collapsed: int
    order_verified: bool
    order_moves: int = 0


def is_success(response: object) -> bool:
    if isinstance(response, str):
        return "SUCCEEDED" in response
    if isinstance(response, dict):
        return "SUCCEEDED" in str(response.get("status", ""))
    return False


def resolve_review(conn: Any, spotify_uri: str, video_id: str | None) -> bool:
    """The user's decision on a `review`/`not_found` track: accept `video_id` or skip it."""
    status, vid = ("ok", video_id) if video_id else ("skipped", None)
    cursor = conn.execute(
        "UPDATE track_map SET status = ?, video_id = ?, confidence = 1.0, "
        "updated_at = datetime('now') WHERE spotify_uri = ?",
        (status, vid, spotify_uri),
    )
    conn.commit()
    return cursor.rowcount > 0


def plan_moves(current: list[tuple[str, str]], desired: list[str]) -> list[tuple[str, str]]:
    """Moves `(setVideoId, successor_setVideoId)` that put `desired` in order.

    `current` is the destination as `(setVideoId, videoId)` pairs; videos not in `desired` are
    ignored (left wherever they are). Each move means "put this item right before that one".
    Items already in a longest correct run stay still, so a few misplaced tracks cost a few moves.
    """
    wanted = {v: i for i, v in enumerate(dict.fromkeys(desired))}
    sim: list[tuple[str, str]] = []  # first occurrence of each wanted video, current order
    seen: set[str] = set()
    for set_id_, video in current:
        if video in wanted and video not in seen:
            seen.add(video)
            sim.append((set_id_, video))
    order = [v for v in wanted if v in seen]  # desired order, restricted to what is present
    set_id = {v: s for s, v in sim}
    if len(order) < 2:
        return []

    positions = [wanted[v] for _, v in sim]
    keep = _longest_increasing(positions)
    stay = {sim[i][1] for i in keep}
    moves: list[tuple[str, str]] = []
    work = [v for _, v in sim]

    def move_before(item: str, successor: str) -> None:
        work.remove(item)
        work.insert(work.index(successor), item)
        moves.append((set_id[item], set_id[successor]))

    if order[-1] in stay:
        for i in range(len(order) - 2, -1, -1):
            if order[i] not in stay:
                move_before(order[i], order[i + 1])
    else:  # the last item would need "move to the end": chain everything before it instead
        for i in range(len(order) - 2, -1, -1):
            if work.index(order[i]) + 1 != work.index(order[i + 1]):
                move_before(order[i], order[i + 1])
    return moves


def _longest_increasing(values: list[int]) -> list[int]:
    """Indices of one longest strictly increasing subsequence (patience sorting)."""
    tails: list[int] = []
    tail_idx: list[int] = []
    prev = [-1] * len(values)
    for i, value in enumerate(values):
        pos = bisect_left(tails, value)
        if pos == len(tails):
            tails.append(value)
            tail_idx.append(i)
        else:
            tails[pos] = value
            tail_idx[pos] = i
        prev[i] = tail_idx[pos - 1] if pos else -1
    result: list[int] = []
    k = tail_idx[-1] if tail_idx else -1
    while k != -1:
        result.append(k)
        k = prev[k]
    return result[::-1]


class SyncEngine:
    def __init__(
        self,
        conn: Any,
        client: YTMClient,
        *,
        sleep: Callable[[float], None] = time.sleep,
        batch_size: int = 25,
        search_pause: float = 0.35,
        write_pause: float = 0.5,
        retries: int = 3,
    ) -> None:
        self.conn = conn
        self.client = client
        self.sleep = sleep
        self.batch_size = batch_size
        self.search_pause = search_pause
        self.write_pause = write_pause
        self.retries = retries

    # ---- helpers --------------------------------------------------------------------------

    def _pair(self, pair_id: int) -> Any:
        row = self.conn.execute("SELECT * FROM pairs WHERE id = ?", (pair_id,)).fetchone()
        if row is None:
            raise SyncError(f"unknown pair {pair_id}")
        return row

    def _guard(self, call: Callable[[], Any]) -> Any:
        """Run a client call, turning auth failures into `SessionExpired`."""
        try:
            return call()
        except SyncError:
            raise
        except Exception as exc:
            if looks_expired(str(exc)):
                raise SessionExpired("YouTube Music rejected the session") from exc
            raise SyncError(f"YouTube Music call failed: {type(exc).__name__}") from exc

    def _write(self, call: Callable[[], Any], what: str) -> None:
        """A write with retries; checks the returned status (ytmusicapi does not raise)."""
        last = ""
        for attempt in range(self.retries):
            response = self._guard(call)
            if is_success(response):
                return
            last = str(response)[:80]
            log.warning("%s refused (attempt %d/%d): %s", what, attempt + 1, self.retries, last)
            self.sleep(2**attempt)
        raise WriteFailed(f"{what} failed after {self.retries} attempts: {last}")

    def _set_add_to_top(self, playlist_id: str, value: bool) -> None:
        self._write(
            lambda: self.client.edit_playlist(playlist_id, addToTop=value), "set add-to-top"
        )

    def _dest(self, playlist_id: str) -> list[tuple[str, str]]:
        data = self._guard(lambda: self.client.get_playlist(playlist_id, limit=None))
        return [
            (t.get("setVideoId") or "", t["videoId"])
            for t in data.get("tracks", [])
            if t.get("videoId")
        ]

    # ---- matching -------------------------------------------------------------------------

    def match_one(self, track: SpotifyTrack) -> MatchResult:
        query = matching.build_query(track)
        candidates: list[matching.Candidate] = []
        for kind in ("songs", "videos"):
            hits = self._guard(lambda k=kind: self.client.search(query, filter=k, limit=5))
            candidates += [c for c in map(matching.candidate_from_ytm, hits) if c]
            if kind == "songs" and matching.decide(track, candidates).status == "ok":
                break  # a clean song match: no need to look at videos
            self.sleep(self.search_pause)
        return matching.decide(track, candidates)

    def ensure_matches(
        self,
        tracks: list[SpotifyTrack],
        progress: Callable[[int, int], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, int]:
        """Match every track that has no `track_map` row yet. Safe to re-run (resumable)."""
        known = {r[0] for r in self.conn.execute("SELECT spotify_uri FROM track_map")}
        for index, track in enumerate(tracks, 1):
            if track.uri not in known:
                if should_stop and should_stop():
                    self.conn.commit()
                    raise Stopped("stopped while matching")
                result = self.match_one(track)
                self.conn.execute(
                    "INSERT OR REPLACE INTO track_map "
                    "(spotify_uri, video_id, confidence, status, title, artists, duration_ms) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        track.uri, result.video_id, result.confidence, result.status,
                        track.title, "; ".join(track.artists), track.duration_ms,
                    ),
                )
                known.add(track.uri)
                if index % 20 == 0:
                    self.conn.commit()
            if progress:
                progress(index, len(tracks))
        self.conn.commit()
        return self.match_counts(tracks)

    def match_counts(self, tracks: list[SpotifyTrack]) -> dict[str, int]:
        counts = {"ok": 0, "review": 0, "not_found": 0, "skipped": 0}
        for track in tracks:
            row = self.conn.execute(
                "SELECT status FROM track_map WHERE spotify_uri = ?", (track.uri,)
            ).fetchone()
            if row:
                counts[row["status"]] += 1
        return counts

    def resolve_review(self, spotify_uri: str, video_id: str | None) -> None:
        resolve_review(self.conn, spotify_uri, video_id)

    def desired_videos(self, tracks: list[SpotifyTrack]) -> tuple[list[str], int]:
        """Video ids in Spotify order, one per video, only for tracks with status ok."""
        ids: list[str] = []
        seen: set[str] = set()
        collapsed = 0
        for track in tracks:
            row = self.conn.execute(
                "SELECT video_id FROM track_map WHERE spotify_uri = ? AND status = 'ok'",
                (track.uri,),
            ).fetchone()
            if not row or not row["video_id"]:
                continue
            if row["video_id"] in seen:
                collapsed += 1
                continue
            seen.add(row["video_id"])
            ids.append(row["video_id"])
        return ids, collapsed

    # ---- writing --------------------------------------------------------------------------

    def dump(
        self,
        pair_id: int,
        tracks: list[SpotifyTrack],
        progress: Callable[[int, int], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> SyncReport:
        """Initial copy of `tracks` (Spotify order, first row first) into the destination."""
        pair = self._pair(pair_id)
        playlist_id = pair["dest_playlist_id"]
        n = max(len(tracks), 1)

        def match_progress(done: int, _total: int) -> None:
            if progress:
                progress(done, 2 * n)

        counts = self.ensure_matches(tracks, match_progress, should_stop)
        desired, collapsed = self.desired_videos(tracks)

        present = {v for _, v in self._dest(playlist_id)}
        todo = [v for v in desired if v not in present]
        already = len(desired) - len(todo)

        self._set_add_to_top(playlist_id, False)  # append in order (verified in S2)
        added = 0
        for start in range(0, len(todo), self.batch_size):
            if should_stop and should_stop():
                raise Stopped("stopped while writing")
            batch = todo[start : start + self.batch_size]
            self._write(
                lambda b=batch: self.client.add_playlist_items(playlist_id, b, duplicates=False),
                f"add batch of {len(batch)}",
            )
            added += len(batch)
            if progress:
                progress(n + int(n * added / len(todo)), 2 * n)
            self.sleep(self.write_pause)

        self.conn.execute(
            "UPDATE pairs SET last_order = ?, last_synced_at = datetime('now') WHERE id = ?",
            (json.dumps([t.uri for t in tracks]), pair_id),
        )
        self.conn.commit()
        verified, moves = self.verify_and_fix_order(playlist_id, desired)
        return SyncReport(
            counts["ok"], counts["review"], counts["not_found"], added, already, collapsed,
            verified, moves,
        )

    def incremental(
        self,
        pair_id: int,
        fresh: list[SpotifyTrack],
        progress: Callable[[int, int], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> SyncReport:
        """Add tracks that are new in Spotify (`fresh`, newest first) to the top."""
        pair = self._pair(pair_id)
        playlist_id = pair["dest_playlist_id"]
        counts = self.ensure_matches(fresh, None, should_stop)
        desired, collapsed = self.desired_videos(fresh)

        present = {v for _, v in self._dest(playlist_id)}
        todo = [v for v in desired if v not in present]

        self._set_add_to_top(playlist_id, True)
        added = 0
        for video_id in reversed(todo):  # oldest of the new ones first: newest ends on top
            if should_stop and should_stop():
                raise Stopped("stopped while writing")
            self._write(
                lambda v=video_id: self.client.add_playlist_items(
                    playlist_id, [v], duplicates=False
                ),
                "add track on top",
            )
            added += 1
            if progress:
                progress(added, len(todo))
            self.sleep(self.write_pause)

        # Only a complete run moves the "already synced" marker; a stopped one is simply redone
        # (tracks already in the destination are skipped).
        old = json.loads(pair["last_order"] or "[]")
        self.conn.execute(
            "UPDATE pairs SET last_order = ?, last_synced_at = datetime('now') WHERE id = ?",
            (json.dumps([t.uri for t in fresh] + old), pair_id),
        )
        self.conn.commit()

        if todo:
            verified, moves = self.verify_and_fix_order(playlist_id, todo, top_only=True)
        else:
            verified, moves = True, 0
        return SyncReport(
            counts["ok"], counts["review"], counts["not_found"], added,
            len(desired) - len(todo), collapsed, verified, moves,
        )

    # ---- order check ----------------------------------------------------------------------

    def _order_mismatch(self, dest: list[tuple[str, str]], desired: list[str]) -> bool:
        wanted = set(desired)
        actual = [v for _, v in dest if v in wanted]
        expected = [v for v in dict.fromkeys(desired) if v in set(actual)]
        return actual != expected

    def verify_and_fix_order(
        self, playlist_id: str, desired: list[str], top_only: bool = False
    ) -> tuple[bool, int]:
        """Check the relative order of `desired` in the destination; repair with moveItem.

        Re-reads a few times first (YouTube can lag after a write). `top_only` is for the
        incremental case: the new tracks must be the first items, in the given order.
        """
        dest: list[tuple[str, str]] = []
        for attempt in range(4):
            dest = self._dest(playlist_id)
            if top_only:
                ok = [v for _, v in dest[: len(desired)]] == desired
            else:
                ok = not self._order_mismatch(dest, desired)
            if ok:
                log.info("order check ok (top_only=%s, attempt %d)", top_only, attempt + 1)
                return True, 0
            if attempt < 3:
                self.sleep(1.5)

        if top_only:  # put the new tracks, in order, right before the first other item
            by_video = {v: s for s, v in dest}
            first_other = next((s for s, v in dest if v not in set(desired)), None)
            moves = [(by_video[v], first_other) for v in desired if v in by_video and first_other]
        else:
            moves = plan_moves(dest, desired)
        log.warning(
            "order check failed (top_only=%s): %d moves planned, first new item at position %s",
            top_only, len(moves),
            next((i for i, (_, v) in enumerate(dest) if v in set(desired)), None),
        )
        if not moves or len(moves) > MAX_FIX_MOVES:
            return False, 0
        applied = 0
        for set_id, successor in moves:
            self._write(
                lambda a=set_id, b=successor: self.client.edit_playlist(
                    playlist_id, moveItem=(a, b)
                ),
                "move item",
            )
            applied += 1
            self.sleep(self.write_pause)
        dest = self._dest(playlist_id)
        fixed = (
            [v for _, v in dest[: len(desired)]] == desired
            if top_only
            else not self._order_mismatch(dest, desired)
        )
        return fixed, applied


def to_spotify_tracks(items: list[dict[str, Any]]) -> list[SpotifyTrack]:
    """Tracks as the Spicetify app sends them: {uri, title, artists, durationMs, album}."""
    return [
        SpotifyTrack(
            uri=str(i["uri"]),
            title=str(i.get("title", "")),
            artists=tuple(str(a) for a in i.get("artists") or ()),
            duration_ms=i.get("durationMs"),
            album=i.get("album"),
        )
        for i in items
    ]
