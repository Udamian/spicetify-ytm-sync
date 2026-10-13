"""Spike S1: how long does a captured YouTube Music browser session keep working?

Steps
  1. Open https://music.youtube.com in an INCOGNITO window and sign in.
  2. DevTools (F12) > Network > pick a POST request to music.youtube.com > right click >
     Copy > Copy request headers. Paste them into a text file (for example
     spikes/.s1/headers.txt; the folder is git-ignored).
  3. CLOSE the incognito window, so the browser never rotates these cookies.
  4. Store the session:   python spikes/s1_session_durability.py --init spikes/.s1/headers.txt
     then delete headers.txt.
  5. Probe it later (about 1 h, 24 h, 7 d, 14 d, 30 d):
                          python spikes/s1_session_durability.py

Every probe appends a row to spikes/.s1/log.csv. A probe that says "ok" but finds 0 playlists
is suspicious: stale sessions may return empty results instead of an error (this is one of the
things the spike is meant to find out).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from ytm_sync_companion import ytm
from ytm_sync_companion.headers import check_headers
from ytm_sync_companion.security import write_private

STATE_DIR = Path(__file__).resolve().parent / ".s1"
AUTH_FILE = STATE_DIR / "browser.json"
LOG_FILE = STATE_DIR / "log.csv"


def init(headers_file: Path) -> int:
    check = check_headers(headers_file.read_text(encoding="utf-8"))
    if not check.ok:
        print(f"Missing from the pasted headers: {', '.join(check.missing)}", file=sys.stderr)
        return 1
    for warning in check.warnings:
        print(f"Warning: {warning}")
    write_private(AUTH_FILE, json.dumps(check.headers))
    print(f"Session stored in {AUTH_FILE}.")
    print("Now delete the headers file and make sure the incognito window is closed.")
    return 0


def probe() -> int:
    if not AUTH_FILE.exists():
        print("No stored session. Run with --init first.", file=sys.stderr)
        return 1
    status = ytm.session_status(AUTH_FILE)
    playlists = len(ytm.list_playlists(AUTH_FILE)) if status == "ok" else ""
    row = [datetime.now(timezone.utc).isoformat(timespec="seconds"), status, playlists]

    new_file = not LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(["utc_time", "status", "playlists_found"])
        writer.writerow(row)
    print(f"{row[0]}  status={status}  playlists={playlists or '-'}")
    return 0 if status == "ok" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--init", metavar="HEADERS_FILE", type=Path, help="store a session")
    args = parser.parse_args()
    return init(args.init) if args.init else probe()


if __name__ == "__main__":
    raise SystemExit(main())
