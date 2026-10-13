# Architecture

> Supersedes sections 4 and 6 of [`viability-study.md`](viability-study.md), which assumed a
> single Spicetify *extension*. The study remains the reference for research, risks and sync
> design. Items marked **(to validate)** are open and tracked as spikes in
> [`roadmap.md`](roadmap.md).

## Components

```
Spotify desktop + Spicetify                 Your computer                         Internet
┌──────────────────────────────┐   HTTP    ┌──────────────────────────┐  HTTPS  ┌───────────────┐
│ Custom app  (app/)           │ 127.0.0.1 │ Companion  (companion/)  │ ──────▶ │ YouTube Music │
│  · page in the sidebar:      │ ────────▶ │  · Flask HTTP API        │ ◀────── │ (unofficial   │
│    wizard, status, review    │ ◀──────── │  · ytmusicapi            │         │  API)         │
│  · reads Spotify playlists   │  bearer   │  · SQLite: matches,      │         └───────────────┘
│ Startup extension            │  token    │    pairs, job queue      │
│  · runs when Spotify starts  │           │  · credentials (0600)    │
│  · triggers the sync         │           └──────────────────────────┘
└──────────────────────────────┘
```

| Component | Language | Role |
|---|---|---|
| **Custom app** (`app/src/app.tsx`) | TypeScript + React | The UI: a page in Spotify's sidebar. Built with Spicetify Creator. |
| **Startup extension** (`app/src/extensions/`) | TypeScript | Declared in the app's `subfiles_extension`, so it runs at every Spotify start. A custom app's own code runs only while its page is open. |
| **Companion** (`companion/`) | Python 3.10+ | Talks to YouTube Music, matches tracks, keeps state, and holds the credentials. |

### Why a companion at all

- A Spicetify extension or app is only JavaScript files; it cannot ship a backend.
- Calling YouTube Music directly from Spotify's web view would mean sending Google cookies through
  Spicetify's CORS proxy (`CosmosAsync` routes external URLs through a third-party proxy).
- The credentials and the sync state should live outside Spotify's cache, which can be cleared.

### Why a Custom App plus an extension

- The Marketplace installs *extensions* in one click, but only offers a link for *apps*; apps are
  installed by hand (`spicetify config custom_apps ytm-sync`, `spicetify apply`). Since the
  companion already needs its own installer, a single installer will do all of it
  (roadmap phase 5).
- An app gives a full page for the wizard, the "needs review" list and the history, instead of a
  modal.
- The sync-on-start requirement is met by the extension bundled with the app.

## Distribution

| Piece | How it reaches the user |
|---|---|
| Companion | Installer / executable from GitHub Releases (roadmap phase 5) |
| Custom app + startup extension | Copied into Spicetify's `CustomApps/` folder by the same installer |
| Marketplace listing | Public repo with the `spicetify-apps` topic and the root [`manifest.json`](../manifest.json) (`name`, `description`, `preview`, `readme`). The card links to the repo; installation is manual. |

**(to validate, spike S7)** Whether the root `manifest.json` is enough for an app whose built
files are produced by a build step, or whether the Marketplace needs a `dist` branch (as other
published apps do).

## HTTP contract (v1)

Defined in [`companion/README.md`](../companion/README.md). Summary of the rules:

- The server binds to `127.0.0.1` only (default port `48215`).
- Every request passes: `Host` allow-list → `Origin` allow-list → bearer token.
- `/health` and `/pair` are the only unauthenticated endpoints; `/pair` requires a browser
  `Origin` and a one-time code.
- `API_VERSION` is incremented on incompatible changes; the app refuses to run against a
  companion that speaks another version.

## Data model

SQLite, versioned with `PRAGMA user_version` (`companion/src/ytm_sync_companion/db.py`):

- `track_map`: Spotify URI → YouTube Music `video_id`, confidence, and a status (`ok`,
  `not_found`, `review`, `skipped`).
- `pairs`: a source (Liked Songs or a playlist) mirrored into a destination playlist, plus the
  last synced order.
- `jobs`: a persistent, resumable queue (initial dump, incremental).

## Where things live on disk

Under the OS app-data directory (`%APPDATA%\ytm-sync`, `~/Library/Application Support/ytm-sync`,
`$XDG_DATA_HOME/ytm-sync`), overridable with `YTM_SYNC_DATA_DIR`:

| File | Content | Sensitive |
|---|---|---|
| `token` | Bearer token the app uses | Yes (0600) |
| `browser.json` | Parsed YouTube Music request headers | **Yes** (0600) |
| `ytm-sync.sqlite3` | Matches, pairs, jobs | No |

## Synchronization

Unchanged from the study (section 5): Spotify is the source of truth and the visible order is
canonical; everything is idempotent; additive mode by default; a "review" list for uncertain
matches; a 5,000-item limit per YouTube Music playlist to warn about. The engine is **not
implemented yet** (roadmap phase 2); the `/sync/*` endpoints answer `501`.
