"""Build the release folder and zip: the packaged companion + the built app + the installers.

    python scripts/build_release.py [--skip-app]

Needs: `pip install pyinstaller "companion/"` and Node (unless --skip-app, when app/dist
already exists). Output: build/release/ytm-sync-<version>-<platform>.zip and a .sha256 file.
Run it on the platform you are releasing for (PyInstaller does not cross-compile).
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
PLATFORM = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def run(command: list[str], cwd: Path = ROOT) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, check=True)  # noqa: S603


def version() -> str:
    sys.path.insert(0, str(ROOT / "companion" / "src"))
    from ytm_sync_companion import __version__

    return __version__


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-app", action="store_true", help="use the existing app/dist")
    args = parser.parse_args()

    if not args.skip_app:
        npm = "npm.cmd" if sys.platform == "win32" else "npm"
        run([npm, "ci"], ROOT / "app")
        run([npm, "run", "build-local"], ROOT / "app")

    shutil.rmtree(BUILD / "dist", ignore_errors=True)
    run([
        sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "ytm-sync.spec"),
        "--noconfirm", "--clean", "--distpath", str(BUILD / "dist"),
        "--workpath", str(BUILD / "work"),
    ])

    name = f"ytm-sync-{version()}-{PLATFORM}"
    staging = BUILD / "release" / name
    shutil.rmtree(staging, ignore_errors=True)
    shutil.copytree(BUILD / "dist" / "ytm-sync", staging)
    for extra in (ROOT / "packaging").glob("*.cmd"):
        shutil.copy2(extra, staging / extra.name)
    shutil.copy2(ROOT / "packaging" / "README.txt", staging / "README.txt")
    shutil.copy2(ROOT / "LICENSE", staging / "LICENSE.txt")

    archive = Path(shutil.make_archive(str(BUILD / "release" / name), "zip",
                                       BUILD / "release", name))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n")
    print(f"\nBuilt {archive} ({archive.stat().st_size / 1e6:.1f} MB)\nsha256 {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
