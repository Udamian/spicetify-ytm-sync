# YTM Sync

Keep a Spotify playlist (or your Liked Songs) mirrored, **in the same order**, to a playlist on
YouTube Music. A [Spicetify](https://spicetify.app) custom app with a small local companion.

> **Status: pre-alpha. Nothing syncs yet.** The companion's security layer, credential
> validation and HTTP API are in place, and the custom app can find and pair with the companion.
> The sync engine and the setup wizard are next. See the [roadmap](docs/roadmap.md).

## What it will do

1. **First run:** pick the Spotify playlist (or Liked Songs) and the YouTube Music destination
   playlist; the app copies the existing tracks, preserving order.
2. **Every time Spotify starts:** it checks for new tracks and sends them to the destination.
3. Everything is done from a page inside Spotify. No terminal needed after installation.

## How it works

```
Spotify + Spicetify  ──HTTP, 127.0.0.1──▶  Companion (Python)  ──▶  YouTube Music
 custom app + startup extension              ytmusicapi, SQLite
```

Spicetify apps and extensions are plain JavaScript and cannot run a backend, so the work that
talks to YouTube Music happens in a small companion service on your own computer. Details in
[`docs/architecture.md`](docs/architecture.md).

## Install

Not available yet. The planned installer will set up the companion and add the app to Spicetify
in one step ([roadmap, phase 5](docs/roadmap.md)). Requirements will be: Spotify desktop,
[Spicetify](https://spicetify.app) and a YouTube Music account.

## Development

```bash
# Companion
cd companion
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ytm-sync-companion          # prints a pairing code
pytest && ruff check .

# Spicetify custom app
cd ../app
npm ci
npm run build-local         # output in app/dist
npm run typecheck
```

Everything CI runs: `scripts/check.sh`. To try the app in Spotify, copy `app/dist` into your
Spicetify `CustomApps/ytm-sync` folder, then `spicetify config custom_apps ytm-sync` and
`spicetify apply`. See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Repository layout

| Path | What |
|---|---|
| `app/` | Spicetify custom app + startup extension (TypeScript, built with Spicetify Creator) |
| `companion/` | Local service (Python, Flask, `ytmusicapi`, SQLite) |
| `docs/` | Architecture, roadmap, threat model and the original [viability study](docs/viability-study.md) |
| `spikes/` | Throwaway experiments that validate risky assumptions before building on them |
| `scripts/` | Local checks |
| `manifest.json` | Listing metadata for the Spicetify Marketplace |

## Important notes

- **Unofficial.** YouTube Music has no public API for this; the companion uses
  [`ytmusicapi`](https://github.com/sigma67/ytmusicapi), which imitates the web client and can
  stop working at any time. This project is not affiliated with or endorsed by Spotify, Google,
  YouTube or Spicetify.
- **Your session is sensitive.** The companion stores a copy of your YouTube Music browser
  session on your machine. It never leaves it. Read [`docs/security.md`](docs/security.md).
- Modifying the Spotify client with Spicetify and using unofficial APIs may conflict with those
  services' terms. You use this software at your own risk.

## License

[MIT](LICENSE)
