"""Spike S8: run the real sync engine against the real YouTube Music, in a throw-away playlist.

Needs the S1 session (spikes/.s1/browser.json) and a track list exported with s5_export.js
(spikes/.s1/tracks.json). It creates a PRIVATE playlist "YTM Sync spike S8", never touches your
other playlists, and deletes it at the end unless you pass --keep.

What it does, in order:
  1. dump        the first N tracks of the file, in the file's order (the engine appends in order)
  2. order       reads the playlist back and checks it matches the expected order
  3. resume      repeats the dump: nothing may be added twice and no new searches are needed
  4. incremental the next 3 tracks go on top, newest first
  5. repair      moves one track far away on purpose and lets the engine put it back

Run:  python spikes/s8_engine_dump.py spikes/.s1/tracks.json --limit 60
Paste the printed table into spikes/README.md.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

from ytm_sync_companion import jobs
from ytm_sync_companion.db import init_db
from ytm_sync_companion.sync import SyncEngine, SyncReport, to_spotify_tracks

HERE = Path(__file__).resolve().parent
AUTH_FILE = HERE / ".s1" / "browser.json"
DB_FILE = HERE / ".s1" / "s8.sqlite3"

results: list[tuple[str, str, str]] = []


def record(step: str, ok: bool, detail: str = "") -> bool:
    results.append((step, "OK" if ok else "FAIL", detail))
    print(f"  {step:<12} {'OK' if ok else 'FAIL'}  {detail}")
    return ok


def load_tracks(path: Path) -> list[dict[str, Any]]:
    from s5_matching import read_json_list  # same tolerant reader as S5

    return [
        {"uri": i["uri"], "title": i["title"], "artists": i.get("artists") or [],
         "durationMs": i.get("duration_ms"), "album": i.get("album")}
        for i in read_json_list(path)
    ]


def summary(report: SyncReport) -> str:
    return (f"ok {report.matched_ok}, review {report.to_review}, not found {report.not_found}, "
            f"added {report.added}, already there {report.already_present}, "
            f"same-video collapsed {report.duplicates_collapsed}, moves {report.order_moves}")


def run(client: Any, raw_tracks: list[dict[str, Any]], limit: int, keep: bool = False,
        sleep: Any = time.sleep) -> int:
    if len(raw_tracks) < limit + 3:
        print(f"Need at least {limit + 3} tracks in the file (has {len(raw_tracks)}).",
              file=sys.stderr)
        return 1
    main_tracks = to_spotify_tracks(raw_tracks[:limit])
    new_tracks = list(reversed(to_spotify_tracks(raw_tracks[limit : limit + 3])))  # newest first

    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    DB_FILE.unlink(missing_ok=True)
    conn = init_db(DB_FILE)
    engine = SyncEngine(conn, client, sleep=sleep)
    playlist_id = ""
    try:
        created = client.create_playlist("YTM Sync spike S8", "Safe to delete", "PRIVATE")
        playlist_id = created if isinstance(created, str) else ""
        if not record("create", bool(playlist_id), playlist_id or repr(created)[:80]):
            return 2
        pair = jobs.upsert_pair(conn, "spotify:collection:tracks", playlist_id)

        started = time.time()
        report = engine.dump(pair, main_tracks)
        expected, _ = engine.desired_videos(main_tracks)
        record("dump", report.added == len(expected),
               f"{summary(report)}; {time.time() - started:.0f} s")

        actual = [t["videoId"] for t in client.get_playlist(playlist_id, limit=None)["tracks"]]
        record("order", actual == expected and report.order_moves == 0,
               f"{len(actual)}/{len(expected)} tracks; identical order: {actual == expected}; "
               f"repairs needed: {report.order_moves}")

        searches = conn.execute("SELECT COUNT(*) FROM track_map").fetchone()[0]
        again = engine.dump(pair, main_tracks)
        after = [t["videoId"] for t in client.get_playlist(playlist_id, limit=None)["tracks"]]
        record("resume", again.added == 0 and after == actual,
               f"second run added {again.added}; playlist unchanged: {after == actual}; "
               f"matches kept: {searches}")

        inc = engine.incremental(pair, new_tracks)
        want_top, _ = engine.desired_videos(new_tracks)
        top = [t["videoId"] for t in client.get_playlist(playlist_id, limit=None)["tracks"]]
        record("incremental", top[: len(want_top)] == want_top and top[len(want_top):] == actual,
              f"{summary(inc)}; new tracks on top in order: {top[: len(want_top)] == want_top}")

        everything = want_top + expected
        tracks = client.get_playlist(playlist_id, limit=None)["tracks"]
        victim = tracks[len(tracks) // 2]
        client.edit_playlist(playlist_id, moveItem=(victim["setVideoId"], tracks[0]["setVideoId"]))
        sleep(1.5)
        verified, moves = engine.verify_and_fix_order(playlist_id, everything)
        final = [t["videoId"] for t in client.get_playlist(playlist_id, limit=None)["tracks"]]
        record("repair", verified and final == everything,
               f"verified: {verified}; moves used: {moves}; final order correct: "
               f"{final == everything}")
    except Exception as exc:  # report, then still clean up the test playlist
        record("error", False, f"{type(exc).__name__}: {str(exc)[:120]}")
    finally:
        conn.close()
        if playlist_id and not keep:
            try:
                client.delete_playlist(playlist_id)
                print("  (test playlist deleted)")
            except Exception as exc:
                print(f"  could not delete {playlist_id}: {str(exc)[:100]}; delete it by hand.")

    print("\n| Step | Result | Detail |\n|---|---|---|")
    for step, status, detail in results:
        print(f"| {step} | {status} | {detail} |")
    return 0 if all(status == "OK" for _, status, _ in results) else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tracks", type=Path, help="JSON exported with s5_export.js")
    parser.add_argument("--limit", type=int, default=60, help="tracks in the main dump")
    parser.add_argument("--keep", action="store_true", help="do not delete the test playlist")
    args = parser.parse_args()
    if not AUTH_FILE.exists():
        print("No stored session. Run s1_session_durability.py --init first.", file=sys.stderr)
        return 1
    from ytmusicapi import YTMusic

    return run(YTMusic(str(AUTH_FILE)), load_tracks(args.tracks), args.limit, args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
