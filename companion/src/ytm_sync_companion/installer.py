"""`install` and `uninstall`: put YTM Sync into Spicetify and set the companion up to run.

install
  1. finds Spicetify,
  2. copies the built app into Spicetify's `CustomApps/ytm-sync`,
  3. registers it (`spicetify config custom_apps ytm-sync`) and runs `spicetify apply`,
  4. Windows, packaged build only: copies the companion to `%LOCALAPPDATA%\\Programs\\ytm-sync`,
     adds a Start Menu shortcut that shows the pairing code and a Startup shortcut that starts the
     companion at login without a window, and starts it now.
Running it again is the update: everything is replaced in place.

uninstall removes all of that. The stored YouTube Music session, the database and the logs are
kept unless `--purge` is given.

Everything that touches the system goes through `Env`, so the tests run it against temporary
folders and a fake `spicetify`.
"""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, runtime
from .config import Settings

APP_FOLDER = "ytm-sync"
APP_FILES = ("index.js", "manifest.json")
PROGRAM_FOLDER = "ytm-sync"
CONSOLE_EXE = "ytm-sync"  # name of the console executable (without ".exe")
CODE_SHORTCUT = "YTM Sync Companion.lnk"
STARTUP_SHORTCUT = "YTM Sync.lnk"
DESKTOP_SHORTCUT = "Start YTM Sync.lnk"
SPICETIFY_HELP = "https://spicetify.app/docs/getting-started"

Runner = Callable[[Sequence[str]], tuple[int, str]]


class InstallError(Exception):
    """A step failed in a way the person can act on; the message says how."""


def decode_output(data: bytes) -> str:
    """Text of a command's output. Spicetify (written in Go) prints UTF-8 even on Windows, where
    reading it with the console's code page turns "Damián" into "DamiÃ¡n" and breaks paths."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def default_run(command: Sequence[str]) -> tuple[int, str]:
    extra: dict[str, object] = {}
    if sys.platform == "win32":
        # The windowed companion has no console: without this a child would flash one.
        extra["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    try:
        done = subprocess.run(  # noqa: S603
            list(command), capture_output=True, stdin=subprocess.DEVNULL, timeout=300,
            check=False, **extra,  # type: ignore[arg-type]
        )
    except FileNotFoundError:
        return 127, f"command not found: {command[0]}"
    except subprocess.TimeoutExpired:
        return 124, f"timed out: {' '.join(command[:3])}"
    return done.returncode, decode_output((done.stdout or b"") + (done.stderr or b""))


@dataclass
class Env:
    platform: str = sys.platform
    environ: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    home: Path = field(default_factory=Path.home)
    run: Runner = default_run
    which: Callable[[str], str | None] = shutil.which
    frozen: bool = field(default_factory=runtime.is_frozen)
    executable: Path = field(default_factory=lambda: Path(sys.executable))
    start_companion: Callable[[Sequence[str]], None] = runtime.start_detached
    stop_companion: Callable[[Settings], bool] = runtime.request_shutdown
    companion_version: Callable[[Settings], str | None] = runtime.running_version
    sleep: Callable[[float], None] = time.sleep
    out: Callable[[str], None] = print

    @property
    def windows(self) -> bool:
        return self.platform == "win32"


# ---- where things live --------------------------------------------------------------------


def _env_path(env: Env, name: str, fallback: Path) -> Path:
    value = env.environ.get(name)
    return Path(value) if value else fallback


def spicetify_candidates(env: Env) -> list[Path]:
    if env.windows:
        base = _env_path(env, "LOCALAPPDATA", env.home / "AppData" / "Local")
        return [base / "spicetify" / "spicetify.exe"]
    return [env.home / ".spicetify" / "spicetify"]


def find_spicetify(env: Env) -> Path | None:
    on_path = env.which("spicetify")
    if on_path:
        return Path(on_path)
    return next((p for p in spicetify_candidates(env) if p.exists()), None)


def default_userdata(env: Env) -> Path:
    if env.windows:
        return _env_path(env, "APPDATA", env.home / "AppData" / "Roaming") / "spicetify"
    return _env_path(env, "XDG_CONFIG_HOME", env.home / ".config") / "spicetify"


def userdata_dir(env: Env, spicetify: Path) -> Path | None:
    """Spicetify's config folder, or None if it cannot be found.

    Asked of Spicetify itself (`spicetify path userdata`); if that answer is not an existing
    folder (for instance a wrongly decoded name) the default location is tried. Only a folder
    that already exists is returned: nothing here ever creates a path from scratch.
    """
    code, output = env.run([str(spicetify), "path", "userdata"])
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    candidates = [Path(lines[-1])] if code == 0 and lines else []
    candidates.append(default_userdata(env))
    return next((path for path in candidates if path.is_dir()), None)


def require_userdata(env: Env, spicetify: Path) -> Path:
    found = userdata_dir(env, spicetify)
    if found is None:
        raise InstallError(
            f"Spicetify's configuration folder was not found (expected {default_userdata(env)}). "
            "Run `spicetify` once in a terminal, open Spotify, and try again."
        )
    return found


def app_source(env: Env, app_dir: str | None = None) -> Path:
    """Folder with the built app: the one given, the one bundled in the package, or `app/dist`."""
    if app_dir:
        source = Path(app_dir)
    elif env.frozen:
        source = Path(getattr(sys, "_MEIPASS", env.executable.parent)) / "app"
    else:
        source = Path(__file__).resolve().parents[3] / "app" / "dist"
    missing = [name for name in APP_FILES if not (source / name).is_file()]
    if missing:
        raise InstallError(
            f"The built app was not found in {source} (missing {', '.join(missing)}). "
            "Build it with `npm run build-local` in the app folder, or pass --app-dir."
        )
    return source


def program_dir(env: Env) -> Path | None:
    if not env.windows:
        return None
    return _env_path(env, "LOCALAPPDATA", env.home / "AppData" / "Local") / "Programs" / (
        PROGRAM_FOLDER
    )


def _start_menu(env: Env) -> Path:
    base = _env_path(env, "APPDATA", env.home / "AppData" / "Roaming")
    return base / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def startup_dir(env: Env) -> Path:
    return _start_menu(env) / "Startup"


# ---- helpers --------------------------------------------------------------------------------


def ps_quote(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def shortcut_script(
    path: Path, target: str, arguments: str, workdir: str, window_style: int, description: str
) -> str:
    """PowerShell that creates a .lnk (window_style 1 = normal, 7 = minimised)."""
    return (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + ps_quote(str(path)) + "); "
        f"$s.TargetPath = {ps_quote(target)}; $s.Arguments = {ps_quote(arguments)}; "
        f"$s.WorkingDirectory = {ps_quote(workdir)}; $s.WindowStyle = {window_style}; "
        f"$s.Description = {ps_quote(description)}; $s.Save()"
    )


_DESKTOP_LNK = (
    "(Join-Path ([Environment]::GetFolderPath('Desktop')) " + ps_quote(DESKTOP_SHORTCUT) + ")"
)
DESKTOP_REMOVE = f"Remove-Item -LiteralPath {_DESKTOP_LNK} -ErrorAction SilentlyContinue"


def desktop_shortcut_script(target: str, arguments: str, workdir: str, description: str) -> str:
    """Like `shortcut_script`, for the Desktop, whose real location Windows knows (it can be
    moved, for example into OneDrive). Minimised: the program has no window anyway."""
    return (
        f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_DESKTOP_LNK}); "
        f"$s.TargetPath = {ps_quote(target)}; $s.Arguments = {ps_quote(arguments)}; "
        f"$s.WorkingDirectory = {ps_quote(workdir)}; $s.WindowStyle = 7; "
        f"$s.Description = {ps_quote(description)}; $s.Save()"
    )


def write_startup_shortcut(env: Env, exe: Path, workdir: Path) -> None:
    """Create the shortcut that starts the companion, without a window, when the person signs in."""
    command = runtime.background_command(str(exe), env.platform, frozen=True)
    _powershell(env, shortcut_script(
        startup_dir(env) / STARTUP_SHORTCUT, command[0], " ".join(command[1:]),
        str(workdir), 7, "Starts the YTM Sync companion when you sign in",
    ))


def _powershell(env: Env, script: str) -> None:
    code, output = env.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
         "-Command", script]
    )
    if code != 0:
        raise InstallError(f"Could not create a shortcut: {output.strip()[-300:]}")


def _remove_tree(env: Env, path: Path, attempts: int = 6) -> None:
    """rmtree that waits a moment for Windows to release files of a process that just exited."""
    for attempt in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if attempt == attempts - 1:
                raise
            env.sleep(0.5)


def _replace_dir(env: Env, source: Path, dest: Path, *, make_parents: bool = False) -> None:
    """Copy `source` to `dest`, replacing it. The copy is finished before the old one goes.

    Only `dest`'s own parent is created (and its ancestors only with `make_parents`), so a wrong
    path can never make this create folders in places like `C:\\Users`."""
    staging = dest.with_name(dest.name + ".new")
    _remove_tree(env, staging)
    dest.parent.mkdir(parents=make_parents, exist_ok=True)
    shutil.copytree(source, staging)
    _remove_tree(env, dest)
    staging.rename(dest)


def _spicetify(env: Env, spicetify: Path, *args: str) -> tuple[int, str]:
    return env.run([str(spicetify), *args])


def _registered_apps(env: Env, spicetify: Path) -> list[str]:
    """Names in Spicetify's `custom_apps` setting (it prints them separated by `|`)."""
    code, output = _spicetify(env, spicetify, "config", "custom_apps")
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if code != 0 or not lines:
        return []
    return [name.strip() for name in lines[-1].split("|")]


def _apply(env: Env, spicetify: Path) -> None:
    code, output = _spicetify(env, spicetify, "apply")
    if code == 0:
        return
    # A first run needs a backup of Spotify's files before anything can be applied.
    code, output = _spicetify(env, spicetify, "backup", "apply")
    if code != 0:
        raise InstallError(
            "`spicetify apply` failed. Close Spotify and run `spicetify backup apply` "
            f"yourself to see why. Spicetify said: {output.strip()[-400:]}"
        )


# ---- install ----------------------------------------------------------------------------------

Step = tuple[str, Callable[[], None]]


def _install_steps(
    env: Env, settings: Settings, *, apply: bool, app_dir: str | None
) -> list[Step]:
    ctx: dict[str, Path] = {}

    def find() -> None:
        found = find_spicetify(env)
        if not found:
            raise InstallError(
                f"Spicetify was not found. Install it first ({SPICETIFY_HELP}), "
                "open Spotify once, then run this again."
            )
        ctx["spicetify"] = found

    def copy_app() -> None:
        source = app_source(env, app_dir)
        dest = require_userdata(env, ctx["spicetify"]) / "CustomApps" / APP_FOLDER
        _replace_dir(env, source, dest)
        ctx["app"] = dest

    def register() -> None:
        if APP_FOLDER in _registered_apps(env, ctx["spicetify"]):
            return
        code, output = _spicetify(env, ctx["spicetify"], "config", "custom_apps", APP_FOLDER)
        if code != 0:
            raise InstallError(f"`spicetify config` failed: {output.strip()[-300:]}")

    steps: list[Step] = [
        ("Look for Spicetify", find),
        ("Copy the app into Spicetify's CustomApps folder", copy_app),
        ("Register it (spicetify config custom_apps ytm-sync)", register),
    ]
    if apply:
        steps.append(
            ("Apply it to Spotify (spicetify apply)", lambda: _apply(env, ctx["spicetify"]))
        )

    target = program_dir(env)
    if env.windows and env.frozen and target is not None:
        installed_exe = target / env.executable.name

        def background() -> list[str]:
            # Asked when needed, not when planning: the windowed executable only exists in the
            # installed folder once the program has been copied there.
            return runtime.background_command(str(installed_exe), env.platform, frozen=True)

        def startup_shortcut() -> None:
            write_startup_shortcut(env, installed_exe, target)

        def copy_program() -> None:
            source = env.executable.parent
            if source.resolve() == target.resolve():
                return  # already running from the installed copy
            if not env.stop_companion(settings):
                raise InstallError("The companion would not stop. Quit it and try again.")
            _replace_dir(env, source, target, make_parents=True)

        def desktop_shortcut() -> None:
            # On the Desktop (wherever Windows keeps it, OneDrive included): starts the companion
            # without a window, for when it was stopped and the page cannot start it.
            command = background()
            _powershell(env, desktop_shortcut_script(
                command[0], " ".join(command[1:]), str(target),
                "Start the YTM Sync companion (no window)",
            ))

        def check_running() -> None:
            # An old companion that kept running would leave the page newer than the program.
            found = None
            for _ in range(30):
                found = env.companion_version(settings)
                if found == __version__:
                    return
                env.sleep(0.5)
            raise InstallError(
                f"The companion that answers is {'version ' + found if found else 'not running'}, "
                f"not the new version {__version__}. Restart your computer (or end "
                "'ytm-sync-background' in the Task Manager) and run this installer again."
            )

        def start_menu_shortcut() -> None:
            _powershell(env, shortcut_script(
                _start_menu(env) / CODE_SHORTCUT, str(installed_exe), "code --pause", str(target),
                1, "Show the YTM Sync pairing code",
            ))

        steps += [
            (f"Install the companion in {target}", copy_program),
            ("Add the Start Menu shortcut 'YTM Sync Companion'", start_menu_shortcut),
            ("Start the companion when you sign in", startup_shortcut),
            ("Add the Desktop shortcut 'Start YTM Sync'", desktop_shortcut),
            ("Start the companion now", lambda: env.start_companion(background())),
            ("Check that the new companion is the one running", check_running),
        ]
    else:
        steps.append((
            "Companion: not installed as a program here (packaged Windows build only). "
            "Start it with: python -m ytm_sync_companion",
            lambda: None,
        ))
    return steps


def _run_steps(env: Env, steps: list[Step], dry_run: bool, done_message: str) -> int:
    for index, (label, action) in enumerate(steps, 1):
        env.out(f"[{index}/{len(steps)}] {label}")
        if dry_run:
            continue
        try:
            action()
        except InstallError as exc:
            env.out(f"\nError: {exc}")
            return 1
        except OSError as exc:
            env.out(f"\nError: {exc}")
            return 1
    env.out("\n" + ("Dry run only: nothing was changed." if dry_run else done_message))
    return 0


def install(
    settings: Settings,
    *,
    dry_run: bool = False,
    apply: bool = True,
    app_dir: str | None = None,
    env: Env | None = None,
) -> int:
    env = env or Env()
    steps = _install_steps(env, settings, apply=apply, app_dir=app_dir)
    pairing = (
        "To pair, open the 'YTM Sync Companion' shortcut in the Start Menu and type its code."
        if env.windows and env.frozen
        else "To pair, run `python -m ytm_sync_companion` and type the code it prints."
    )
    return _run_steps(
        env, steps, dry_run,
        "Done. Restart Spotify, open 'YTM Sync' in the left sidebar and follow the steps.\n"
        + pairing,
    )


# ---- uninstall --------------------------------------------------------------------------------


def _uninstall_steps(env: Env, settings: Settings, *, purge: bool) -> list[Step]:
    ctx: dict[str, Path | None] = {"spicetify": None}

    def stop() -> None:
        if not env.stop_companion(settings):
            raise InstallError("The companion would not stop. Quit it from the Task Manager.")

    def remove_shortcuts() -> None:
        for path in (_start_menu(env) / CODE_SHORTCUT, startup_dir(env) / STARTUP_SHORTCUT):
            path.unlink(missing_ok=True)

    def remove_desktop_shortcut() -> None:
        if env.windows:  # a PowerShell hiccup here is not worth failing the uninstall for
            env.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", DESKTOP_REMOVE])

    def unregister() -> None:
        found = find_spicetify(env)
        ctx["spicetify"] = found
        if not found:
            env.out("    Spicetify was not found: nothing to unregister.")
            return
        if APP_FOLDER in _registered_apps(env, found):
            code, output = _spicetify(env, found, "config", "custom_apps", APP_FOLDER + "-")
            if code != 0:
                raise InstallError(f"`spicetify config` failed: {output.strip()[-300:]}")
        userdata = userdata_dir(env, found)
        folder = userdata / "CustomApps" / APP_FOLDER if userdata else None
        if folder is not None and folder.exists():
            _remove_tree(env, folder)
        _apply(env, found)

    def remove_program() -> None:
        target = program_dir(env)
        if target is None or not target.exists():
            return
        try:
            _remove_tree(env, target)
        except OSError:
            env.out(f"    Could not remove {target} (in use). Delete that folder by hand.")

    def purge_data() -> None:
        if settings.data_dir.exists():
            _remove_tree(env, settings.data_dir)

    steps: list[Step] = [
        ("Stop the companion", stop),
        ("Remove the shortcuts", remove_shortcuts),
        ("Remove the Desktop shortcut", remove_desktop_shortcut),
        ("Remove the app from Spicetify and apply", unregister),
        ("Remove the installed companion", remove_program),
    ]
    steps.append(
        ("Delete the stored YouTube Music session, database and logs", purge_data) if purge
        else (f"Keep your data in {settings.data_dir} (use --purge to delete it)", lambda: None)
    )
    return steps


def uninstall(
    settings: Settings, *, dry_run: bool = False, purge: bool = False, env: Env | None = None
) -> int:
    env = env or Env()
    steps = _uninstall_steps(env, settings, purge=purge)
    return _run_steps(env, steps, dry_run, "YTM Sync was removed. Restart Spotify.")
