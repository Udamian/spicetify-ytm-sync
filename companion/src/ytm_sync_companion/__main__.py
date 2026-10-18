"""Command line: `ytm-sync-companion [command]` or `python -m ytm_sync_companion [command]`.

    run [--background]   start the service (default). Background mode shows no console.
    code [--pause]       print the pairing code, starting the service first if needed
    status               say whether the service is running
    stop                 stop the service (a running copy is paused and resumes later)
    install / uninstall  see `installer.py`
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
from collections.abc import Callable
from types import ModuleType

from . import __version__, runtime
from .app import Services, create_app
from .config import HOST, Settings
from .logging_setup import setup_logging


def _announce_code(code: str) -> None:
    print(f"\n  Pairing code: {code}   (valid for 10 minutes)")
    print("  Enter it in the YTM Sync page inside Spotify.\n", flush=True)


def cmd_run(settings: Settings, background: bool) -> int:
    if runtime.is_running(settings):
        if not background:
            print("YTM Sync companion is already running. Use `code` to see the pairing code.")
        return 0
    if background:
        runtime.quiet_streams()
    log_path = setup_logging(settings.data_dir, console=not background)

    def on_new_code(code: str) -> None:
        # The code rotates after a successful pairing and when it expires: keep the file current.
        runtime.publish_code(settings, code, app.extensions["ytm_sync"].pairing.seconds_left())
        if not background:
            _announce_code(code)

    def on_shutdown() -> None:
        services.worker.stop()  # a running job is paused and resumes at the next start
        runtime.remove_code(settings)
        os._exit(0)  # noqa: SLF001 (stop the server thread too; everything is flushed)

    app = create_app(
        settings, on_new_code=on_new_code, on_shutdown=on_shutdown, worker_enabled=True
    )
    services = app.extensions["ytm_sync"]
    runtime.publish_code(settings, services.pairing.code, services.pairing.seconds_left())
    stop = _start_code_refresh(settings, services)

    if not background:
        print(f"YTM Sync companion {__version__} listening on http://{HOST}:{settings.port}")
        print(f"Data directory: {settings.data_dir}")
        print(f"Log file: {log_path}")
        _announce_code(services.pairing.code)

    # Flask's built-in server is enough for a single local user.
    try:
        app.run(host=HOST, port=settings.port, debug=False, threaded=True)
    finally:
        stop.set()
        services.worker.stop()
        runtime.remove_code(settings)
    return 0


def _start_code_refresh(settings: Settings, services: Services) -> threading.Event:
    stop = threading.Event()
    runtime.keep_code_fresh(
        services.pairing,
        lambda code, left: runtime.publish_code(settings, code, left),
        stop,
    )
    return stop


def cmd_code(settings: Settings, pause: bool) -> int:
    if not runtime.is_running(settings):
        print("Starting the YTM Sync companion...")
        runtime.remove_code(settings)  # a file left by a crash would show a code that is gone
        runtime.start_detached(runtime.background_command())
    found = runtime.wait_for_code(settings)
    if found is None:
        print("Could not get a pairing code. Look at the log file in:")
        print(f"  {settings.data_dir / 'logs'}")
        status = 1
    else:
        code, left = found
        print(f"\n  Pairing code: {code}   (valid for about {max(1, left // 60)} min)")
        print("  Enter it in the YTM Sync page inside Spotify.\n")
        status = 0
    if pause:
        input("Press Enter to close this window...")
    return status


def cmd_status(settings: Settings) -> int:
    running = runtime.is_running(settings)
    print(f"YTM Sync companion {__version__}: {'running' if running else 'not running'}")
    print(f"Data directory: {settings.data_dir}")
    return 0 if running else 1


def cmd_stop(settings: Settings) -> int:
    if not runtime.is_running(settings):
        print("The companion is not running.")
        return 0
    if runtime.request_shutdown(settings):
        print("Stopped.")
        return 0
    print("Could not stop it. Close it from the Task Manager (ytm-sync-background).")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ytm-sync-companion", description=__doc__.split("\n")[0])
    parser.add_argument("-V", "--version", action="store_true", help="print the version")
    sub = parser.add_subparsers(dest="command")
    run = sub.add_parser("run", help="start the service (default)")
    run.add_argument("--background", action="store_true", help="no console output or window")
    code = sub.add_parser("code", help="show the pairing code")
    code.add_argument("--pause", action="store_true", help="wait for Enter before closing")
    sub.add_parser("status", help="is it running?")
    sub.add_parser("stop", help="stop the service")
    install = sub.add_parser("install", help="add the app to Spicetify and set up the companion")
    install.add_argument("--dry-run", action="store_true", help="only list what would be done")
    install.add_argument("--no-apply", action="store_true", help="do not run `spicetify apply`")
    install.add_argument("--app-dir", help="folder with the built app (default: the bundled one)")
    uninstall = sub.add_parser("uninstall", help="remove what `install` added")
    uninstall.add_argument("--dry-run", action="store_true", help="only list what would be done")
    uninstall.add_argument("--purge", action="store_true",
                           help="also delete the stored YouTube Music session and the database")
    return parser


def safe_streams() -> None:
    """Never let a character the console cannot encode (an accented user name in a path, say)
    crash a command half way through: print a replacement character instead."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(errors="replace")


def main(argv: list[str] | None = None) -> int:
    safe_streams()
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    if args.version:
        print(__version__)
        return 0
    settings = Settings.from_env()
    handlers: dict[str | None, Callable[[], int]] = {
        None: lambda: cmd_run(settings, background=False),
        "run": lambda: cmd_run(settings, background=getattr(args, "background", False)),
        "code": lambda: cmd_code(settings, getattr(args, "pause", False)),
        "status": lambda: cmd_status(settings),
        "stop": lambda: cmd_stop(settings),
        "install": lambda: _installer().install(
            settings, dry_run=args.dry_run, apply=not args.no_apply, app_dir=args.app_dir
        ),
        "uninstall": lambda: _installer().uninstall(
            settings, dry_run=args.dry_run, purge=args.purge
        ),
    }
    return handlers[args.command]()


def _installer() -> ModuleType:
    from . import installer  # imported late: only these two commands need it

    return installer


if __name__ == "__main__":
    raise SystemExit(main())
