"""Spike S5, step 2: print what you need to check by hand, side by side.

Shows 30 random 'ok' rows (to estimate the false-match rate) and every 'review' / 'not_found'
row, from the CSV written by s5_matching.py. For each row compare S (Spotify) with Y (YouTube
Music): same song and artist? Count the wrong ones.

Run:  python spikes/s5_review.py            (add --seed 1 to reproduce the same sample)
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

from ytm_sync_companion.matching import (
    Candidate,
    SpotifyTrack,
    artist_similarity,
    decide,
    duration_similarity,
    title_similarity,
    version_markers,
)

CSV_FILE = Path(__file__).resolve().parent / ".s1" / "s5_results.csv"


def mmss(ms: str) -> str:
    if not ms:
        return "?:??"
    seconds = int(float(ms)) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def why(row: dict[str, str]) -> str:
    """Recompute the scoring parts offline, to see WHY a row was not accepted."""
    if not row["video_id"]:
        return "no candidate"
    wanted = tuple(a.strip() for a in row["spotify_artists"].split(";") if a.strip())
    found = tuple(a.strip() for a in row["ytm_artists"].split(";") if a.strip())
    dur = duration_similarity(
        int(float(row["spotify_ms"])) if row["spotify_ms"] else None,
        int(float(row["ytm_ms"])) if row["ytm_ms"] else None,
    )
    extra = version_markers(row["ytm_title"]) - version_markers(row["spotify_title"])
    return (
        f"title {title_similarity(row['spotify_title'], row['ytm_title']):.2f}  "
        f"artist {artist_similarity(wanted, found):.2f}  "
        f"duration {'n/a' if dur is None else f'{dur:.2f}'}  "
        f"extra version words: {sorted(extra) or '-'}"
    )


def rescore(row: dict[str, str]) -> str:
    """Status the CURRENT matching code gives to the stored best candidate (offline)."""
    if not row["video_id"]:
        return "not_found"
    split = lambda text: tuple(a.strip() for a in text.split(";") if a.strip())  # noqa: E731
    ms = lambda text: int(float(text)) if text else None  # noqa: E731
    track = SpotifyTrack("", row["spotify_title"], split(row["spotify_artists"]),
                         ms(row["spotify_ms"]))
    cand = Candidate(row["video_id"], row["ytm_title"], split(row["ytm_artists"]), ms(row["ytm_ms"]))
    return decide(track, [cand]).status


def show(rows: list[dict[str, str]], explain: bool = False) -> None:
    for row in rows:
        print(f"[{row['status']} {row['confidence']}]")
        print(f"  S: {row['spotify_title']} | {row['spotify_artists']} | {mmss(row['spotify_ms'])}")
        if row["video_id"]:
            print(f"  Y: {row['ytm_title']} | {row['ytm_artists']} | {mmss(row['ytm_ms'])}")
        else:
            print("  Y: (nothing)")
        if explain:
            print(f"  why: {why(row)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--sample", type=int, default=30)
    args = parser.parse_args()

    with CSV_FILE.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    ok = [r for r in rows if r["status"] == "ok"]
    rest = [r for r in rows if r["status"] != "ok"]
    rng = random.Random(args.seed)
    sample = rng.sample(ok, min(args.sample, len(ok)))

    print(f"=== {len(sample)} random 'ok' rows (how many are WRONG?) ===")
    show(sample)
    print(f"\n=== {len(rest)} 'review' / 'not_found' rows (how many are actually right?) ===")
    show(sorted(rest, key=lambda r: -float(r["confidence"])), explain=True)

    changes = [(r, rescore(r)) for r in rows if rescore(r) != r["status"]]
    counts = {s: sum(1 for r in rows if rescore(r) == s) for s in ("ok", "review", "not_found")}
    print("\n=== with the CURRENT matching code (offline re-score of the stored candidates) ===")
    print(f"ok {counts['ok']}  review {counts['review']}  not_found {counts['not_found']}"
          f"   ({len(changes)} rows change status)")
    for row, new in changes:
        print(f"  {row['status']} -> {new}: {row['spotify_title']} | {row['spotify_artists']}"
              f"  ==  {row['ytm_title']} | {row['ytm_artists']}")

    ok_conf = sorted(float(r["confidence"]) for r in ok)
    review_conf = sorted(float(r["confidence"]) for r in rest if r["status"] == "review")
    print("\n=== confidence summary ===")
    print(f"lowest 10 'ok':   {ok_conf[:10]}")
    if review_conf:
        print(f"'review' range:   {review_conf[0]} .. {review_conf[-1]}  (n={len(review_conf)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())