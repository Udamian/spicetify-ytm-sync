# YTM Sync companion

Local service (Python + Flask) that talks to YouTube Music through
[`ytmusicapi`](https://github.com/sigma67/ytmusicapi) on behalf of the Spicetify custom app.
It only listens on `127.0.0.1`.

> **Status: pre-alpha.** In place: the security layer, header validation (plain, PowerShell and
> cURL formats), settings, SQLite schema, track matching, the sync engine and a background worker,
> exposed through the HTTP API below, all covered by tests against a simulated YouTube Music.
> **Not yet run against the real service** end to end: do a dump into a throw-away playlist first.

## Run it (development)

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ytm-sync-companion                 # prints a one-time pairing code
pytest
ruff check .
```

## Commands

| Command | What it does |
|---|---|
| `ytm-sync-companion` or `... run` | Run in the foreground and print the pairing code |
| `... run --background` | Run with no console or window (what starts at login). Publishes the pairing code in `<data dir>/pairing-code.json` (readable by your user only) |
| `... code [--pause]` | Print the current pairing code, starting the background service first if needed |
| `... status` | Say whether it is running (exit code 0/1) |
| `... stop` | Stop it cleanly: a running copy is paused and resumes at the next start |
| `... install [--dry-run] [--no-apply] [--app-dir DIR]` | Add the app to Spicetify and, in the packaged Windows build, install the companion with a Start Menu shortcut and a startup entry. Running it again updates |
| `... uninstall [--dry-run] [--purge]` | Remove all of that; `--purge` also deletes the session, database and logs |

Packaged build: `python scripts/build_release.py` (needs PyInstaller; builds for the platform it
runs on) and `python scripts/smoke_packaged.py <release folder>` to test the real executables.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `YTM_SYNC_PORT` | `48215` | Listening port (always on `127.0.0.1`) |
| `YTM_SYNC_ALLOWED_ORIGINS` | `https://xpui.app.spotify.com` | Comma-separated browser origins allowed to call the API (confirmed in spike S3) |
| `YTM_SYNC_DATA_DIR` | OS app-data dir + `ytm-sync` | Where the token, credentials and database are stored |

## API (v1)

Every request must carry a `Host` of `127.0.0.1:<port>` or `localhost:<port>`, and any `Origin`
must be on the allow-list. Errors are JSON: `{"error": "<code>"}`.

| Method | Path | Auth | Notes |
|---|---|---|---|
| GET | `/health` | none | `{ok, version, api_version}` |
| POST | `/shutdown` | bearer | Stops the companion cleanly (used by `stop`, install and uninstall). `501` when not run by the command line |
| GET | `/autostart` | bearer | `{supported, enabled}`: the start-with-Windows switch. `supported` is true only for the installed Windows program |
| POST | `/autostart` | bearer | Body `{"enabled": true|false}`. Creates or removes the Startup shortcut. `409` when not supported |
| GET | `/diagnostics` | bearer | State summary for bug reports: versions, pairs, counts, recent jobs and a redacted log tail. No secrets, ids, titles or personal paths |
| POST | `/pair` | allowed `Origin` + pairing code | Body `{"code": "..."}`. Returns `{token}`. `403 invalid_code`, `410 expired`, `429 locked` |
| GET | `/auth/status` | bearer | `{status}`: `not_configured` / `ok` / `expired` / `error` |
| POST | `/auth/headers` | bearer | Body `{"headers": "<raw request headers>"}`. `400 missing_headers` lists header *names* only |
| DELETE | `/auth` | bearer | Deletes the stored YouTube Music credentials (`204`, idempotent) |
| GET | `/playlists` | bearer | `{playlists: [{id, title, count}]}`. `409 not_configured` without credentials; `502 youtube_error` on upstream failure |
| POST | `/playlists` | bearer | Body `{title, privacy?}` (`PRIVATE` default). `201 {id, title, count: 0}`; `400 bad_title`, `409 not_configured`, `502 youtube_error` |
| POST | `/sync/preview` | bearer | Body `{tracks}`. Returns `{total, already_matched, to_search, estimated_seconds}`. No network |
| POST | `/sync/start` | bearer | Body `{source_uri, dest_playlist_id, kind, tracks, mode?}`. `kind`: `initial_dump` / `incremental`. `202 {job_id}`; `409 already_running` (with `job_id`) or `not_configured`; `400 bad_tracks` (with `index`), `bad_source`, `bad_destination` |
| POST | `/sync/cancel` | bearer | Body `{job_id}`. `{cancelled}` |
| POST | `/sync/retry` | bearer | Body `{job_id}`: queue a failed job again with the data it already stored (`202 {job_id}`); `409 cannot_retry` if it is not failed, has no stored data, or its pair is busy |
| GET | `/status` | bearer | `{jobs: [last 5], worker_running, review_count, not_found_count}`; with `?job_id=N`: `{job}` or `404`. A job has `state`, `done`, `total`, `progress`, `error_code` (`session_expired`, `write_failed`, ...) and, when finished, `report` |
| GET | `/pairs` | bearer | `{pairs: [{id, source_uri, dest_playlist_id, mode, last_synced_at, synced_count}]}`; `last_synced_at` is null until the first copy finishes |
| GET | `/pairs/<id>/synced` | bearer | `{uris}`: Spotify URIs of the last completed copy, in Spotify order (the startup check stops at the first one it finds there) |
| GET | `/review` | bearer | Tracks the matcher was unsure about: `{items: [{uri, title, artists, duration_ms, status, video_id, confidence}]}` |
| POST | `/review/resolve` | bearer | Body `{uri, video_id}`: accept that YouTube Music video, or `video_id: null` to skip the track |

`tracks` is a list of `{uri, title, artists[], durationMs, album?}` (up to 20,000; `/sync/*` accept
bodies up to 8 MB, everything else 256 KB). `source_uri` is `spotify:collection:tracks` or
`spotify:playlist:<id>`. Jobs are persisted with their track list, so a job interrupted by a
restart goes back to the queue and resumes.

Anything protected without a valid token answers `401 unauthorized`.

## Layout

| File | Responsibility |
|---|---|
| `app.py` | Flask app factory and request pipeline |
| `security.py` | Host/Origin checks, token store, pairing code |
| `headers.py` | Parse and validate the raw browser headers (never logs values) |
| `ytm.py` | Builds the `ytmusicapi` client and wraps the simple library calls |
| `matching.py` | Scores Spotify tracks against YouTube Music results (pure, no network) |
| `sync.py` | Sync engine: ordered resumable dump, incremental, duplicates, retries, order repair |
| `jobs.py`, `worker.py` | Persistent job queue and the background worker that runs the engine |
| `logging_setup.py` | Log files that redact cookies and tokens |
| `db.py` | SQLite schema and migrations |
| `config.py` | Settings, ports, data directory |
| `__main__.py` | CLI entry point |

See [`../docs/security.md`](../docs/security.md) for the threat model and
[`../docs/roadmap.md`](../docs/roadmap.md) for what comes next.
