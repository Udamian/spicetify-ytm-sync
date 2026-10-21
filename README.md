<p align="center"><img src="docs/assets/logo.png" alt="YTM Sync logo" width="96"></p>

# YTM Sync

Keep a Spotify playlist (or your Liked Songs) mirrored, **in the same order**, to a playlist on
YouTube Music. A [Spicetify](https://spicetify.app) custom app with a small local helper app.

<p align="center"><img src="docs/assets/preview.png" alt="The YTM Sync page inside Spotify" width="420"></p>

> **Status: beta (0.1.x), Windows.** Tested by its author with about 2,000 liked songs. The
> release is not code-signed yet and YouTube Music has no official API, so expect rough edges and
> please [report them](../../issues/new/choose). macOS and Linux have no installer yet.

## What it does

1. **First run:** pick Liked Songs or a Spotify playlist and a YouTube Music playlist (new or
   existing). The app copies the songs, in the same order. A 1,500-song library takes about 20
   minutes.
2. **Every time Spotify starts:** new songs are sent to the top of the YouTube Music playlist, and
   changes to a copied playlist are applied.
3. **Songs it is not sure about** go to a *review* list with a suggestion you can accept, replace
   or skip, instead of being guessed.
4. Everything is done from a page inside Spotify. No terminal needed.

## Install (Windows)

You need Spotify desktop, [Spicetify](https://spicetify.app/docs/getting-started) (installed, with
Spotify opened once) and a YouTube Music account.

1. Download `ytm-sync-<version>-windows.zip` from the [Releases](../../releases) page (under
   **Assets**, not "Source code") and **unzip it** (right-click, *Extract all*).
2. Double-click **Install YTM Sync.cmd**. It adds the app to Spicetify, runs `spicetify apply`,
   installs the helper app for your user (no administrator rights) and starts it at every login,
   without a window. It also puts a **Start YTM Sync** shortcut on your Desktop.
3. Restart Spotify and open **YTM Sync** in the left sidebar.

Windows may warn that the program is from an unknown publisher: the release is not code-signed
yet. Choose *More info* and *Run anyway*. The zip comes with a `.sha256` file to check it.

**Update:** download the new release and run *Install YTM Sync.cmd* again. Your session and
progress are kept. **Uninstall:** run *Uninstall YTM Sync.cmd*. To also delete the stored YouTube
Music session and copy progress, run `ytm-sync.exe uninstall --purge` in that folder.

macOS and Linux: run the helper app from source (see Development) and copy `app/dist` into
Spicetify's `CustomApps/ytm-sync` folder.

## First use

The page walks you through four steps:

1. **Helper app:** found automatically.
2. **Pair:** open **YTM Sync Companion** from the Windows search (Start Menu); it shows a code for
   a few minutes. Type it in the page. You only do this once.
3. **YouTube Music:** follow the step-by-step guide to copy your browser's request headers. They
   are stored on your computer only. See [`docs/security.md`](docs/security.md).
4. **Playlist:** choose what to copy and where, press *Check and preview*, then *Start copying*.

The **Helper app** card at the bottom of the page shows its status and has *Sync now*, *Start with
Windows*, *Copy diagnostics* (a summary with no passwords or song names, for bug reports) and
*Stop*.

## Troubleshooting

| What you see | What to do |
|---|---|
| "The helper app is not running" | It starts with Windows. Otherwise type **YTM Sync Companion** in the Windows search, or double-click **Start YTM Sync** on your Desktop, then press *Try again*. A web page cannot start it for you. |
| "Your YouTube Music session expired" | Reconnect with the guide. Your copies and progress are kept; an interrupted copy resumes. |
| The YouTube Music playlist has fewer songs than Spotify | Press **Check the order now**: it adds missing songs and puts them in Spotify's order. Songs listed under *review* or *not found* are not added until you decide. |
| Windows says "unknown publisher" | The release is not signed yet: *More info*, then *Run anyway*. |
| Anything else | Press **Copy diagnostics** and open an [issue](../../issues/new/choose) with it. Never paste cookies, headers or `browser.json`. |

## How it works

```
Spotify + Spicetify  ──HTTP, 127.0.0.1──▶  Helper app (Python)  ──▶  YouTube Music
 custom app + startup extension              ytmusicapi, SQLite
```

Spicetify apps and extensions are plain JavaScript and cannot run a backend, so the work that
talks to YouTube Music happens in a small service on your own computer. Spotify data is read only
through Spicetify's internal APIs (no Spotify Web API, no Premium needed). Details in
[`docs/architecture.md`](docs/architecture.md).

## Development

```bash
# Companion
cd companion
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
ytm-sync-companion          # runs in the foreground and prints a pairing code
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
