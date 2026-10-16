# Roadmap

Estimates assume one person part-time (~8-10 h/week). Total: roughly 3-4 months to a first public
release. Full reasoning and risk matrix (B1-B14): [`viability-study.md`](viability-study.md).

## Where we are

| Phase | Status |
|---|---|
| 0. Validation spikes | **In progress.** S2 and S3 done, S4 almost (check playlist order), S1 running (days), S5 script ready, S6/S7 manual. See [`spikes/README.md`](../spikes/README.md) |
| 1. Solid companion | **Mostly done**: security layer, header validation (plain, PowerShell, cURL), settings, SQLite schema, HTTP skeleton, redacting logs, resumable job queue. Missing: wiring `/sync/*` (phase 2), packaging |
| 2. Sync engine | **Done and tested against a simulated YouTube Music**: matching, ordered resumable dump, incremental on top, duplicate filter, retries, order check and repair, background worker and the `/sync/*`, `/status`, `/review` endpoints. **Next: a real run** into a throw-away playlist |
| 3. Custom app UI | Scaffold (connection, pairing) + Spotify read layer (`app/src/lib/spotify.ts`); wizard not started |
| 4-7 | Not started |

## Design notes for a large Liked Songs library (1,500+ tracks)

- **Order.** Spotify lists Liked Songs newest first. The initial dump *appends* the tracks in
  Spotify order (first row first): appending in order is what spike S2 verified. Later syncs put
  new tracks on top with `addToTop`, **one per call**, oldest of the new ones first, so the newest
  ends up first (S2 only verified single adds with `addToTop`, not batches). If the order check
  finds a mismatch, the engine repairs it with `moveItem`.
- **Time.** About 0.5 s per search and a few batched writes: 1,500 tracks take roughly 15 min.
  The dump is a persistent job with a progress bar that resumes where it stopped (session
  expired, Spotify closed, machine asleep).
- **Cheap check at startup.** Read only the first page of `LibraryAPI.getTracks`, stop at the
  first URI already in `track_map`. A change in `totalLength` without new URIs signals removals.
- **Review list.** Expect roughly 3-5 % of tracks (45-75 of 1,500) to be `not_found` or `review`.
- **Duplicates.** Two Spotify tracks can map to the same `videoId`; the engine writes it once
  and records both URIs. `duplicates=False` is silent in S2, but a mixed batch is still to be
  measured, so the engine filters duplicates itself.

## Phases

| # | Phase | Deliverable | Exit criterion |
|---|---|---|---|
| 0 | Spikes | Written results for S1-S7 | Go/no-go (below) |
| 1 | Solid companion | SQLite, job queue, pairing, restricted CORS, endpoints, logs without secrets, tests with a simulated `ytmusicapi` | Tests green; no open CORS |
| 2 | Sync engine | Scored matching, ordered initial dump, incremental diff, reordering, dedupe, dry run, resume, deletion policy | Dump of 1,500+ Liked Songs with identical order verified by a script; interrupted and resumed once without duplicates |
| 3 | Custom app UI | 6-step wizard, status panel, "needs review" list, clear errors, ES/EN, sync trigger from the startup extension | Whole flow without DevTools or a console |
| 4 | Friendly authentication | 4a: step-by-step guide + validator. 4b (optional): helper browser extension | A new user connects without help |
| 5 | Packaging | One installer: companion + copy app to `CustomApps/` + `spicetify config custom_apps ytm-sync` + `spicetify apply`; uninstall; updates; Releases; README with GIFs; real Marketplace preview image | Clean machine installed in under 5 minutes |
| 6 | Closed beta | 5-10 testers, different OS and library sizes | No blocking bugs; auth failure rate known |
| 7 | Publish and maintain | Announcement in the Spicetify community; follow Spicetify and `ytmusicapi` releases | Written maintenance plan |

## Phase 0: spikes

| Spike | What to prove | Decides |
|---|---|---|
| **S1** Session durability | Capture the headers in an incognito window, close it, then probe with an authenticated call at 1 h, 24 h, 7 d, 14 d and 30 d. Also: can renewed cookies be persisted? Does an expired session fail with 401/403 or return empty results? (`session_status` is a heuristic) | Whether header-based auth is defensible as a product |
| **S2** Writes | With the current `ytmusicapi`: `add_playlist_items` batch size; `edit_playlist` with `addToTop` and `moveItem`; no 401/400 | Ordering strategy; whether writing works at all |
| **S3** Localhost from Spicetify | Real `location.origin` of the Spotify web view (the default allow-list value is a guess); `fetch` to `127.0.0.1` works; Private Network Access preflight | Communication design |
| **S4** Reading playlists | Read an arbitrary playlist in order with the date added, 5,000+ tracks, using only Spicetify internal APIs (`LibraryAPI`, `PlaylistAPI`); the official Spotify Web API is not used (premium-only) | Reading layer |
| **S5** Matching | 200 of your own tracks: % correct, false matches, not found | Score thresholds, size of the "review" list |
| **S6** Packaging | PyInstaller on a clean Windows: SmartScreen? antivirus? (macOS if relevant) | Distribution strategy |
| **S7** Marketplace manifest | Does one root `manifest.json` suffice for a built custom app, or is a `dist` branch needed? | Repo layout for publishing |

**Go/no-go:** the session survives at least 7 days with the capture method; writes work with the
current `ytmusicapi`; matching is acceptable; the companion can be packaged without being blocked.

## Decisions taken as defaults (change them if you disagree)

| Topic | Default | Why |
|---|---|---|
| License | MIT | Permissive, common in the Spicetify ecosystem. Copyright line says "YTM Sync contributors": put your name in `LICENSE` |
| First platform | Windows | Biggest Spicetify audience; macOS needs notarization |
| Scope | Liked Songs **and** any playlist | Matches the original requirement ("playlist to choose") |
| Deletions | Additive by default, mirror mode optional | Safer: a mistake never removes music |
| Companion language | Python now | Reuses the prototype; reconsider Go/Rust if packaging hurts |
| Helper browser extension (4b) | v2 | Keeps v1 smaller |
| Repo language | English | Public, community-facing; the UI will ship ES/EN |
