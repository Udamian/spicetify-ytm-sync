# Publishing a release

1. **Preview image:** put a real screenshot at `docs/assets/preview.png` (the YTM Sync page after
   a finished copy; no personal playlists or account names visible).
2. **Icons:** `python scripts/make_icons.py` regenerates `packaging/ytm-sync.ico`, `docs/assets/logo.*`
   and `docs/assets/social-preview.png`. Upload the latter in the repository's *Settings > Social
   preview* (it is what shows when the link is shared).
3. **Version:** `companion/src/ytm_sync_companion/__init__.py` (`__version__`) must match the tag.
   The release workflow fails otherwise.
4. **Checks:** `pytest` and `ruff check .` in `companion/`, `npm run typecheck` in `app/`, CI green
   on `main`.
5. **Tag:** `git tag v0.1.4 && git push origin v0.1.4`. The *Release* workflow builds the Windows
   zip, runs the smoke test and creates a **draft** release with the zip and its `.sha256`.
6. **Review the draft** on GitHub, download the zip, install it on a clean-ish machine, then
   **Publish**. Mark it *pre-release* while the beta runs.
7. **Make the repository public** (Settings > General > Danger Zone > Change visibility). Check first
   that no `browser.json`, `headers.txt`, `.env` or tokens are in the history.
8. **Marketplace:** add the topic `spicetify-apps` to the repository (the gear next to *About*).
   The Marketplace finds apps by that topic and reads `manifest.json` from the repository root
   (`name`, `description`, `main`, `authors`, `preview`, `readme` are required). It does **not**
   install apps: the card links to the repository, so the README's *Install* section is what
   people follow. It can take a while for a new repository to show up.
