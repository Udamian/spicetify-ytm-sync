# PyInstaller recipe. Build with:  python scripts/build_release.py
#
# One analysis, two executables in the same folder:
#   ytm-sync.exe             console: `install`, `uninstall`, `code`, `status`, `stop`
#   ytm-sync-background.exe  no window: what starts at login (`run --background`)
# One folder (not one file): starts faster and antivirus programs flag it less often.
# The built Spicetify app (app/dist) is bundled as data and copied by `install`.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
APP_DIST = ROOT / "app" / "dist"
if not (APP_DIST / "index.js").is_file():
    raise SystemExit(f"{APP_DIST} has no index.js: run `npm run build-local` in app/ first.")

analysis = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT / "companion" / "src")],
    datas=[(str(APP_DIST), "app"), *collect_data_files("ytmusicapi")],
    hiddenimports=[*collect_submodules("ytm_sync_companion"), *collect_submodules("ytmusicapi")],
    excludes=["tkinter", "pytest", "ruff"],
)
pyz = PYZ(analysis.pure)

console_exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="ytm-sync", console=True,
)
background_exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="ytm-sync-background", console=False,
)
COLLECT(
    console_exe, background_exe, analysis.binaries, analysis.datas,
    name="ytm-sync", strip=False, upx=False,
)
