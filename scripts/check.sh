#!/usr/bin/env bash
# Local equivalent of CI. Run from anywhere; needs the companion's dev dependencies installed
# (pip install -e "companion[dev]") and `npm ci` done in app/.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== manifests ==";  python scripts/check_manifests.py
echo "== companion ==";  (cd companion && ruff check . && pytest -q)
echo "== app ==";        (cd app && npm run -s typecheck && npm run -s build-local)
echo "All checks passed."
