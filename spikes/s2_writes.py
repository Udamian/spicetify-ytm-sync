"""Spike S2: do writes and ordering work with the current ytmusicapi?

Uses the session stored by S1 (spikes/.s1/browser.json, see s1_session_durability.py).
It only ever touches ONE playlist that it creates itself (private, named "YTM Sync spike S2"),
and deletes it at the end unless you pass --keep. Your other playlists are never modified.

Checks, in order:
  create      create the private test playlist
  search      find video ids (unauthenticated-style search)
  add_batch   add 3 tracks, then 3 more in a second batch
  duplicate   add an existing track again with duplicates=False: the CALL STATUS is reported
  read_order  read the playlist back: order and setVideoId present?
  move        moveItem: move the last item to the top
  add_to_top  edit_playlist(addToTop=True), then add a track: does it land first?
  mixed_false [duplicate, new track] with duplicates=False: is the new one kept?
  mixed_true  [duplicate, new track] with duplicates=True: new kept? duplicate added again?
  big         (only with --big) 30 new tracks in chunks of 5, 10 and 15: which sizes work?

Note: ytmusicapi does NOT raise when YouTube refuses a write; it returns the response. Every
step below therefore checks the returned status as well as re-reading the playlist.

Run:  python spikes/s2_writes.py        (needs: pip install -e companion[dev])
Paste the printed table into spikes/README.md as the S2 result.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ytmusicapi import YTMusic

AUTH_FILE = Path(__file__).resolve().parent / ".s1" / "browser.json"
QUERIES = [
    "Daft Punk One More Time",
    "Radiohead Karma Police",
    "Queen Bohemian Rhapsody",
    "Adele Hello",
    "Nirvana Smells Like Teen Spirit",
    "Coldplay Yellow",
    "Oasis Wonderwall",
    "Michael Jackson Billie Jean",
    "ABBA Dancing Queen",
]
BIG_QUERIES = [
    "Beatles Hey Jude", "Pink Floyd Time", "Led Zeppelin Kashmir", "Prince Kiss",
    "David Bowie Heroes", "Fleetwood Mac Dreams", "Eagles Hotel California",
    "Bob Marley Three Little Birds", "Madonna Vogue", "U2 One", "Metallica One",
    "AC/DC Thunderstruck", "Rihanna Umbrella", "Eminem Lose Yourself", "Shakira Hips Don't Lie",
    "Bruno Mars Uptown Funk", "Ed Sheeran Shape of You", "The Weeknd Blinding Lights",
    "Dua Lipa Levitating", "Billie Eilish Bad Guy", "Rosalia Malamente", "Bad Bunny Titi Me Pregunto",
    "Estopa Como Camarón", "Extremoduro So Payaso", "Mecano Hijo de la Luna",
    "Enrique Iglesias Bailando", "Maluma Felices los 4", "Daddy Yankee Gasolina",
    "Juanes La Camisa Negra", "Manu Chao Me Gustas Tu",
]
PAUSE = 0.5  # seconds between write calls, as in the prototype

results: list[tuple[str, str, str]] = []


def record(step: str, ok: bool, detail: str = "") -> bool:
    results.append((step, "OK" if ok else "FAIL", detail))
    print(f"  {step:<11} {'OK' if ok else 'FAIL'}  {detail}")
    return ok


def status_of(response: object) -> str:
    """'SUCCEEDED', or a short description of what came back instead."""
    if isinstance(response, str):
        return "SUCCEEDED" if "SUCCEEDED" in response else response[:80]
    if isinstance(response, dict):
        status = str(response.get("status", ""))
        return "SUCCEEDED" if "SUCCEEDED" in status else (status or str(response)[:120])
    return repr(response)[:80]


def titles(yt: YTMusic, playlist_id: str) -> list[dict]:
    return yt.get_playlist(playlist_id, limit=None)["tracks"]


def settled(yt: YTMusic, playlist_id: str, check, tries: int = 4, delay: float = 1.5) -> list[dict]:
    """Re-read the playlist until `check(tracks)` is true (YouTube can lag a moment)."""
    tracks = titles(yt, playlist_id)
    for _ in range(tries - 1):
        if check(tracks):
            break
        time.sleep(delay)
        tracks = titles(yt, playlist_id)
    return tracks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", action="store_true", help="do not delete the test playlist")
    parser.add_argument("--big", action="store_true", help="also test batches of 5, 10 and 15")
    args = parser.parse_args()

    if not AUTH_FILE.exists():
        print("No stored session. Run s1_session_durability.py --init first.", file=sys.stderr)
        return 1
    yt = YTMusic(str(AUTH_FILE))
    playlist_id = ""

    try:
        # create
        try:
            created = yt.create_playlist("YTM Sync spike S2", "Safe to delete", "PRIVATE")
            playlist_id = created if isinstance(created, str) else ""
            record("create", bool(playlist_id), playlist_id or f"unexpected reply: {created!r}")
        except Exception as exc:
            record("create", False, str(exc)[:160])
        if not playlist_id:
            return 2

        # search
        video_ids: list[str] = []
        for query in QUERIES:
            hits = yt.search(query, filter="songs", limit=1)
            if hits and hits[0].get("videoId"):
                video_ids.append(hits[0]["videoId"])
        video_ids = list(dict.fromkeys(video_ids))
        if not record("search", len(video_ids) >= 9, f"{len(video_ids)} distinct of {len(QUERIES)}"):
            return 2

        # add in two batches
        try:
            s1 = status_of(yt.add_playlist_items(playlist_id, video_ids[:3]))
            time.sleep(PAUSE)
            s2 = status_of(yt.add_playlist_items(playlist_id, video_ids[3:6]))
            time.sleep(PAUSE)
            tracks = settled(yt, playlist_id, lambda t: len(t) == 6)
            record("add_batch", len(tracks) == 6 and s1 == s2 == "SUCCEEDED",
                   f"{len(tracks)}/6 tracks; status {s1} / {s2}")
        except Exception as exc:
            record("add_batch", False, str(exc)[:160])

        # duplicate with duplicates=False: ytmusicapi RETURNS the failure instead of raising
        try:
            status = status_of(yt.add_playlist_items(playlist_id, [video_ids[0]], duplicates=False))
            count = len(titles(yt, playlist_id))
            record("duplicate", status != "SUCCEEDED" and count == 6,
                   f"refused without raising: {status != 'SUCCEEDED'}; status: {status}; "
                   f"tracks now: {count}")
        except Exception as exc:
            record("duplicate", True, f"raised: {str(exc)[:100]}")

        # read order
        tracks = titles(yt, playlist_id)
        ids = [t["videoId"] for t in tracks]
        has_set_ids = all(t.get("setVideoId") for t in tracks)
        record("read_order", ids[:6] == video_ids[:6] and has_set_ids,
               f"order matches insertion: {ids[:6] == video_ids[:6]}; "
               f"setVideoId present: {has_set_ids}")

        # move last to top
        try:
            last, first = tracks[-1], tracks[0]
            status = status_of(
                yt.edit_playlist(playlist_id, moveItem=(last["setVideoId"], first["setVideoId"]))
            )
            after = settled(yt, playlist_id, lambda t: t[0]["videoId"] == last["videoId"])
            moved = after[0]["videoId"] == last["videoId"]
            record("move", moved, f"top is now the former last item: {moved}; status: {status}")
        except Exception as exc:
            record("move", False, str(exc)[:160])

        # addToTop
        try:
            yt.edit_playlist(playlist_id, addToTop=True)
            time.sleep(PAUSE)
            status = status_of(yt.add_playlist_items(playlist_id, [video_ids[6]]))
            top = settled(yt, playlist_id, lambda t: t[0]["videoId"] == video_ids[6])[0]["videoId"]
            record("add_to_top", top == video_ids[6],
                   f"new track landed first: {top == video_ids[6]}; status: {status}")
        except Exception as exc:
            record("add_to_top", False, str(exc)[:160])

        # mixed batches: [duplicate, new] with each value of `duplicates`
        for step, flag, new_id in (
            ("mixed_false", False, video_ids[7]),
            ("mixed_true", True, video_ids[8]),
        ):
            try:
                before = [t["videoId"] for t in titles(yt, playlist_id)]
                status = status_of(
                    yt.add_playlist_items(playlist_id, [video_ids[1], new_id], duplicates=flag)
                )
                after = settled(yt, playlist_id, lambda t, n=new_id: n in [x["videoId"] for x in t])
                after_ids = [t["videoId"] for t in after]
                kept = new_id in after_ids
                dup_again = after_ids.count(video_ids[1]) > 1
                # Informative step: both outcomes are a valid answer, so it is always "OK".
                record(step, True,
                       f"new track kept: {kept}; duplicate added again: {dup_again}; "
                       f"size {len(before)} -> {len(after_ids)}; status: {status}")
            except Exception as exc:
                record(step, True, f"raised (whole batch refused?): {str(exc)[:120]}")
            time.sleep(PAUSE)

        # batch sizes
        if args.big:
            try:
                pool: list[str] = []
                for query in BIG_QUERIES:
                    hits = yt.search(query, filter="songs", limit=1)
                    if hits and hits[0].get("videoId"):
                        pool.append(hits[0]["videoId"])
                present = {t["videoId"] for t in titles(yt, playlist_id)}
                pool = [v for v in dict.fromkeys(pool) if v not in present]
                outcomes = []
                cursor = 0
                for size in (5, 10, 15):
                    chunk = pool[cursor:cursor + size]
                    cursor += size
                    if not chunk:
                        break
                    status = status_of(yt.add_playlist_items(playlist_id, chunk))
                    time.sleep(PAUSE)
                    outcomes.append(f"{len(chunk)}: {status}")
                total = len(titles(yt, playlist_id))
                record("big", all(o.endswith("SUCCEEDED") for o in outcomes),
                       f"{'; '.join(outcomes)}; playlist size now {total}")
            except Exception as exc:
                record("big", False, str(exc)[:160])
    finally:
        if playlist_id and not args.keep:
            try:
                yt.delete_playlist(playlist_id)
                print("  (test playlist deleted)")
            except Exception as exc:
                print(f"  could not delete the test playlist {playlist_id}: {str(exc)[:100]}")
                print("  delete it by hand in YouTube Music.")

    print("\n| Step | Result | Detail |\n|---|---|---|")
    for step, status, detail in results:
        print(f"| {step} | {status} | {detail} |")
    return 0 if all(status == "OK" for _, status, _ in results) else 2


if __name__ == "__main__":
    raise SystemExit(main())