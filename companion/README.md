# YTM Sync companion

Local service (Python + Flask) that talks to YouTube Music through
[`ytmusicapi`](https://github.com/sigma67/ytmusicapi) on behalf of the Spicetify custom app.
It only listens on `127.0.0.1`.

> **Status: pre-alpha.** In place: the security layer (Host/Origin checks, pairing, bearer token),
> header validation, settings, the SQLite schema and the HTTP API below, all covered by tests.
> **Not implemented yet:** track matching and the sync engine (`/sync/*` and `/status` answer
> `501`; roadmap phase 2).

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
| `YTM_SYNC_ALLOWED_ORIGINS` | `https://xpui.app.spotify.com` | Comma-separated browser origins allowed to call the API (**unconfirmed**, spike S3) |
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
| POST | `/sync/preview`, `/sync/start`; GET `/status` | bearer | `501 not_implemented` until phase 2 |

Anything protected without a valid token answers `401 unauthorized`.

## Layout

| File | Responsibility |
|---|---|
| `app.py` | Flask app factory and request pipeline |
| `security.py` | Host/Origin checks, token store, pairing code |
| `headers.py` | Parse and validate the raw browser headers (never logs values) |
| `ytm.py` | The only module that calls `ytmusicapi` |
| `db.py` | SQLite schema and migrations |
| `config.py` | Settings, ports, data directory |
| `__main__.py` | CLI entry point |

See [`../docs/security.md`](../docs/security.md) for the threat model and
[`../docs/roadmap.md`](../docs/roadmap.md) for what comes next.
