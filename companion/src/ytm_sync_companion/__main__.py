"""Entry point: `ytm-sync-companion` or `python -m ytm_sync_companion`."""

from __future__ import annotations

import sys

from . import __version__
from .app import create_app
from .config import HOST, Settings
from .logging_setup import setup_logging


def _announce_code(code: str) -> None:
    print(f"\n  Pairing code: {code}   (valid for 10 minutes)")
    print("  Enter it in the YTM Sync page inside Spotify.\n", flush=True)


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args and args[0] in ("-V", "--version"):
        print(__version__)
        return 0

    settings = Settings.from_env()
    log_path = setup_logging(settings.data_dir)
    app = create_app(settings, on_new_code=_announce_code, worker_enabled=True)

    print(f"YTM Sync companion {__version__} listening on http://{HOST}:{settings.port}")
    print(f"Data directory: {settings.data_dir}")
    print(f"Log file: {log_path}")
    _announce_code(app.extensions["ytm_sync"].pairing.code)

    # Flask's built-in server is enough for a single local user. Revisit when packaging
    # (roadmap phase 5), e.g. waitress.
    try:
        app.run(host=HOST, port=settings.port, debug=False, threaded=True)
    finally:
        app.extensions["ytm_sync"].worker.stop()  # a running job is paused and resumes later
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
