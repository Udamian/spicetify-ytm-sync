# Spikes

Short, throwaway experiments that settle risky assumptions *before* the product is built on
them. The reasoning behind each is in [`../docs/roadmap.md`](../docs/roadmap.md#phase-0-spikes).
Record each result in this table (and date it) when you finish.

| Spike | Question | How | Result |
|---|---|---|---|
| **S1** Session durability | How long does a captured session keep working? | [`s1_session_durability.py`](s1_session_durability.py) | _pending_ |
| **S2** Writes | Do `add_playlist_items`, `addToTop` and `moveItem` work with the current `ytmusicapi`? | _script to write_ | _pending_ |
| **S3** Localhost from Spicetify | What is the real `location.origin`? Can the web view `fetch` `127.0.0.1`? | Spotify DevTools console | _pending_ |
| **S4** Reading playlists | Order and date added for 5,000+ tracks | _script to write_ | _pending_ |
| **S5** Matching | Accuracy over 200 of your own tracks | _script to write_ | _pending_ |
| **S6** Packaging | Does PyInstaller trigger SmartScreen/antivirus on a clean Windows? | Manual | _pending_ |
| **S7** Marketplace manifest | Is one root `manifest.json` enough for a built app? | Manual | _pending_ |

Spike scripts import the companion, so install it first (`pip install -e "companion[dev]"`).
Credentials captured here live in `spikes/.s1/`, which is git-ignored. **Never commit them.**
