"""Sanity checks for the two manifests this project depends on.

* `manifest.json` (repo root): read by the Spicetify Marketplace. For a custom app it needs
  name, description, preview and readme; the referenced files must exist.
* `app/src/settings.json`: read by Spicetify Creator to produce the app's own manifest.

Run from anywhere: `python scripts/check_manifests.py`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MARKETPLACE_REQUIRED = ("name", "description", "preview", "readme")
SETTINGS_REQUIRED = ("displayName", "nameId", "icon", "activeIcon")
# Same rule Create Spicetify App enforces for the app's folder name.
NAME_ID = re.compile(r"^[a-z,\-,_]*[a-z,_]$")


def load(path: Path, errors: list[str]) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"{path.relative_to(ROOT)}: cannot read as JSON ({exc})")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.relative_to(ROOT)}: expected a JSON object")
        return {}
    return data


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://"))


def main() -> int:
    errors: list[str] = []

    market = load(ROOT / "manifest.json", errors)
    for key in MARKETPLACE_REQUIRED:
        value = market.get(key)
        if not isinstance(value, str) or not value.strip():
            errors.append(f"manifest.json: missing or empty '{key}'")
        elif key in ("preview", "readme") and not is_url(value) and not (ROOT / value).is_file():
            errors.append(f"manifest.json: '{key}' points to a missing file: {value}")

    app_src = ROOT / "app" / "src"
    settings = load(app_src / "settings.json", errors)
    for key in SETTINGS_REQUIRED:
        if not isinstance(settings.get(key), str) or not settings[key].strip():
            errors.append(f"app/src/settings.json: missing or empty '{key}'")
    name_id = settings.get("nameId", "")
    if name_id and not NAME_ID.match(name_id):
        errors.append(f"app/src/settings.json: invalid nameId '{name_id}'")
    for key in ("icon", "activeIcon"):
        value = settings.get(key)
        if isinstance(value, str) and value and not (app_src / value).is_file():
            errors.append(f"app/src/settings.json: '{key}' points to a missing file: {value}")

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("manifests OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
