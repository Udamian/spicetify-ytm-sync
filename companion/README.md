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
| POST | `/pair` | allowed `Origin` + pairing code | Body `{"code": "..."}`. Returns `{token}`. `403 invalid_code`, `410 expired`, `429 locked` |
| GET | `/auth/status` | bearer | `{status}`: `not_configured` / `ok` / `expired` / `error` |
| POST | `/auth/headers` | bearer | Body `{"headers": "<raw request headers>"}`. `400 missing_headers` lists header *names* only |
| DELETE | `/auth` | bearer | Deletes the stored YouTube Music credentials (`204`, idempotent) |
| GET | `/playlists` | bearer | `{playlists: [{id, title, count}]}`. `409 not_configured` without credentials; `502 youtube_error` on upstream failure |
| POST | `/sync/preview` | bearer | Body `{tracks}`. Returns `{total, already_matched, to_search, estimated_seconds}`. No network |
| POST | `/sync/start` | bearer | Body `{source_uri, dest_playlist_id, kind, tracks, mode?}`. `kind`: `initial_dump` / `incremental`. `202 {job_id}`; `409 already_running` (with `job_id`) or `not_configured`; `400 bad_tracks` (with `index`), `bad_source`, `bad_destination` |
| POST | `/sync/cancel` | bearer | Body `{job_id}`. `{cancelled}` |
| GET | `/status` | bearer | `{jobs: [last 5], worker_running, review_count, not_found_count}`; with `?job_id=N`: `{job}` or `404`. A job has `state`, `done`, `total`, `progress`, `error_code` (`session_expired`, `write_failed`, ...) and, when finished, `report` |
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
