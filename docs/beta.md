# Closed beta guide

Thanks for testing YTM Sync. It copies Spotify Liked Songs or a playlist to a YouTube Music
playlist, in the same order, and keeps adding new songs. This guide is for the first 5-10 testers.
You need Windows, Spotify desktop, [Spicetify](https://spicetify.app/docs/getting-started)
and a YouTube Music account. Nothing here touches your Spotify account's data except reading
your library through Spotify's own app.

## Before you start

- Use a throw-away YouTube Music playlist for the first copy ("Create a new playlist" in the wizard
  does that). The app only writes to the playlist you choose.
- The release is not code-signed yet: Windows SmartScreen may warn. Choose *More info*, then
  *Run anyway*, and check the `.sha256` file if you want.
- Do not share cookies, headers or the pairing code with anyone, including in bug reports.

## What to do (about 30 minutes, plus waiting for the copy)

| # | Step | What we want to know |
|---|---|---|
| 1 | Install from the release zip (`Install YTM Sync.cmd`), restart Spotify, open **YTM Sync** | Did the installer work first time? How long did it take? |
| 2 | Pair: open **YTM Sync Companion** from the Start Menu, type the code | Was it clear where to get the code? |
| 3 | Connect YouTube Music with the step-by-step guide | Could you do it **without help**? Where did you get stuck? |
| 4 | Copy a small playlist (20-50 songs) | Same order on both sides? Songs sent to "review" |
| 5 | Copy your Liked Songs (any size; 1,500 songs takes about 20 minutes) | Time, errors, order check result |
| 6 | Resolve the "needs review" list | Were the suggestions right? |
| 7 | Add 2-3 songs in Spotify, restart Spotify | Did they appear on top of the YouTube Music playlist? |
| 8 | Use the **Helper app** card: *Sync now*, *Start with Windows*, *Copy diagnostics* | Anything confusing? |
| 9 | After 3, 7 and 14 days, open YTM Sync again and restart Spotify | Does the YouTube Music session still work? |

Step 9 matters most: the YouTube Music session is captured from your browser and we do not yet
know how long it lasts. If the app says the session expired, note **how many days** it had been
and reconnect (your progress is kept).

## Reporting

- Bugs: use the *Bug report* issue form. Press **Copy diagnostics** in the Helper app card and
  paste the result: it has no passwords, links or song names.
- Everything else: fill in the *Beta feedback* issue form once you finish step 8, and again after
  step 9.

## Numbers we collect (by hand, from your reports)

| Metric | Goal |
|---|---|
| Testers who connected YouTube Music without help | 80 % or more |
| Songs matched automatically | 95 % or more |
| Copies with identical order | 100 % |
| Days until a session expired | Know the median |
| Blocking bugs open | 0 before going public |

## Leaving

Run *Uninstall YTM Sync.cmd* from the release folder. To also delete the stored session and
progress, run `ytm-sync.exe uninstall --purge` there. Sign out of YouTube Music in your browser
if you want the captured session to stop working.
