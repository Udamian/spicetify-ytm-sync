"""Spike S5: how accurate is the Spotify -> YouTube Music matching on YOUR tracks?

Input: a JSON file exported from Spotify with the snippet in spikes/s5_export.js
(a list of {uri, title, artists, duration_ms, album}). Output: a CSV you can open in Excel
and a summary with the % of ok / review / not_found.

Run:  python spikes/s5_matching.py spikes/.s1/tracks.json
      (uses the session stored by S1; read-only: it only searches, never writes)

Then open spikes/.s1/s5_results.csv and check by hand ~30 rows marked "ok" and all "review"
rows: a wrong "ok" is the number that matters (false match rate).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

from ytmusicapi import YTMusic

from ytm_sync_companion.matching import (
    SpotifyTrack,
    build_query,
    candidate_from_ytm,
    decide,
)

AUTH_FILE = Path(__file__).resolve().parent / ".s1" / "browser.json"
OUT_FILE = Path(__file__).resolve().parent / ".s1" / "s5_results.csv"
PAUSE = 0.35


def read_json_list(path: Path) -> list[dict]:
    """Read the exported JSON, tolerating BOM, UTF-16 (PowerShell) and text around the list."""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise SystemExit(f"{path} is not readable text.")
    if not text.strip():
        raise SystemExit(f"{path} is empty: paste the clipboard content into it and save.")
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end <= start:
        raise SystemExit(
            f"{path} does not contain a JSON list (it starts with: {text.strip()[:40]!r}).\n"
            "Run spikes/s5_export.js again and paste what it copies, not the console messages."
        )
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} has invalid JSON ({exc}). The paste may be cut off.") from exc


def load_tracks(path: Path) -> list[SpotifyTrack]:
    raw = read_json_list(path)
    return [
        SpotifyTrack(
            uri=item["uri"],
            title=item["title"],
            artists=tuple(item.get("artists") or ()),
            duration_ms=item.get("duration_ms"),
            album=item.get("album"),
        )
        for item in raw
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("tracks", type=Path, help="JSON exported from Spotify")
    parser.add_argument("--limit", type=int, default=200, help="how many tracks to test")
    args = parser.parse_args()

    if not AUTH_FILE.exists():
        print("No stored session. Run s1_session_durability.py --init first.", file=sys.stderr)
        return 1
    tracks = load_tracks(args.tracks)[: args.limit]
    yt = YTMusic(str(AUTH_FILE))
    counts: Counter[str] = Counter()

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with OUT_FILE.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["status", "confidence", "spotify_title", "spotify_artists", "ytm_title",
             "ytm_artists", "video_id", "spotify_ms", "ytm_ms"]
        )
        for index, track in enumerate(tracks, 1):
            candidates = []
            for kind in ("songs", "videos"):
                try:
                    hits = yt.search(build_query(track), filter=kind, limit=5)
                except Exception as exc:
                    print(f"  search failed ({str(exc)[:80]}); stopping.", file=sys.stderr)
                    return 2
                candidates += [c for c in map(candidate_from_ytm, hits) if c]
                if kind == "songs" and decide(track, candidates).status == "ok":
                    break  # a clean song match: no need to look at videos
                time.sleep(PAUSE)
            result = decide(track, candidates)
            best = next((c for c in candidates if c.video_id == result.video_id), None)
            counts[result.status] += 1
            writer.writerow([
                result.status, f"{result.confidence:.2f}", track.title, "; ".join(track.artists),
                best.title if best else "", "; ".join(best.artists) if best else "",
                result.video_id or "", track.duration_ms or "",
                best.duration_ms if best and best.duration_ms else "",
            ])
            if index % 20 == 0:
                print(f"  {index}/{len(tracks)}")

    total = sum(counts.values()) or 1
    print("\n| Result | Tracks | % |\n|---|---|---|")
    for status in ("ok", "review", "not_found"):
        print(f"| {status} | {counts[status]} | {100 * counts[status] / total:.1f} |")
    print(f"\nDetails: {OUT_FILE}")
    print("Now check by hand ~30 'ok' rows and every 'review' row; count the wrong 'ok's.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())