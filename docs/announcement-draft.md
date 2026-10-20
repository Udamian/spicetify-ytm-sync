# Announcement draft (do not publish before the beta goals in `beta.md` are met)

**Title:** YTM Sync - mirror Spotify Liked Songs and playlists to YouTube Music, in the same order

**Post:**

Hi everyone. I built YTM Sync, a Spicetify custom app that copies your Liked Songs (tested with
1,500+) or any playlist to a YouTube Music playlist with the same order, and then sends new songs
every time Spotify starts.

- Everything is driven from a tab in Spotify: pairing, connecting YouTube Music, copy progress,
  a list for songs it could not match with confidence, "Sync now".
- A small helper app on your computer talks to YouTube Music. It listens only on `127.0.0.1`,
  needs a one-time pairing code and never sends your data anywhere else.
- Uses only Spicetify's internal APIs for Spotify data, so no Spotify Premium Web API needed.
- Windows installer included (no admin rights). macOS and Linux: from source for now.

Limits, honestly: YouTube Music has no official API, so the session is captured from your browser
and can expire (the app tells you and resumes where it stopped). Songs are matched by title,
artists and duration; doubtful ones go to a review list instead of being guessed. The release
is not code-signed yet, so Windows SmartScreen will warn.

Repo: https://github.com/Udamian/spicetify-ytm-sync  ·  feedback and bug reports welcome.

**Checklist before posting:** repository public; release published (not draft); real preview image
in `docs/assets/preview.png`; `manifest.json` tags and README checked; Marketplace listing PR
prepared; beta numbers written in the roadmap.
