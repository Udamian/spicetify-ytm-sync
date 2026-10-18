from __future__ import annotations

from pathlib import Path

import pytest

from ytm_sync_companion import installer
from ytm_sync_companion.config import Settings
from ytm_sync_companion.installer import Env


class FakeSpicetify:
    """Answers the few `spicetify` commands the installer uses and records every call."""

    def __init__(self, userdata: Path) -> None:
        self.userdata = userdata
        self.apps: list[str] = []
        self.calls: list[list[str]] = []
        self.apply_fails = 0  # next N `apply` calls fail (a first run has no backup yet)
        self.backup_fails = False
        self.powershell: list[str] = []

    def __call__(self, command):
        command = list(command)
        self.calls.append(command)
        if command[0] == "powershell":
            self.powershell.append(command[-1])
            return 0, ""
        args = command[1:]
        if args == ["path", "userdata"]:
            return 0, f"{self.userdata}\n"
        if args == ["config", "custom_apps"]:
            return 0, "|".join(self.apps) + "\n"
        if args[:2] == ["config", "custom_apps"]:
            name = args[2]
            if name.endswith("-"):
                self.apps = [a for a in self.apps if a != name[:-1]]
            elif name not in self.apps:
                self.apps.append(name)
            return 0, ""
        if args == ["apply"]:
            if self.apply_fails:
                self.apply_fails -= 1
                return 1, "You haven't backed up"
            return 0, ""
        if args == ["backup", "apply"]:
            return (1, "backup failed") if self.backup_fails else (0, "")
        return 1, f"unexpected: {args}"

    def verbs(self) -> list[str]:
        return [" ".join(c[1:]) for c in self.calls if c[0] != "powershell"]


@pytest.fixture
def built_app(tmp_path: Path) -> Path:
    app = tmp_path / "built"
    app.mkdir()
    (app / "index.js").write_text("// app")
    (app / "manifest.json").write_text("{}")
    (app / "style.css").write_text("")
    return app


@pytest.fixture
def linux(tmp_path: Path):
    """A Linux-like environment with Spicetify installed in a temporary home."""
    home = tmp_path / "home"
    spicetify_bin = home / ".spicetify" / "spicetify"
    spicetify_bin.parent.mkdir(parents=True)
    spicetify_bin.touch()
    fake = FakeSpicetify(home / ".config" / "spicetify")
    fake.userdata.mkdir(parents=True)
    lines: list[str] = []
    env = Env(platform="linux", environ={}, home=home, run=fake, which=lambda _n: None,
              frozen=False, out=lines.append, sleep=lambda _s: None)
    return env, fake, lines


def settings_in(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data")


def test_install_copies_the_app_registers_and_applies(tmp_path, built_app, linux):
    env, fake, _ = linux
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 0
    target = fake.userdata / "CustomApps" / "ytm-sync"
    assert (target / "index.js").read_text() == "// app"
    assert (target / "style.css").exists()
    assert fake.verbs() == [
        "path userdata", "config custom_apps", "config custom_apps ytm-sync", "apply"]
    assert fake.apps == ["ytm-sync"]


def test_installing_again_updates_in_place_without_registering_twice(tmp_path, built_app, linux):
    env, fake, _ = linux
    installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env)
    target = fake.userdata / "CustomApps" / "ytm-sync"
    (target / "stale.js").write_text("old")  # something an older version had
    (built_app / "index.js").write_text("// new")

    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 0
    assert (target / "index.js").read_text() == "// new"
    assert not (target / "stale.js").exists()
    assert fake.apps == ["ytm-sync"]
    assert sum(v == "config custom_apps ytm-sync" for v in fake.verbs()) == 1
    assert not target.with_name("ytm-sync.new").exists()  # no staging folder left behind


def test_other_registered_apps_are_left_alone(tmp_path, built_app, linux):
    env, fake, _ = linux
    fake.apps = ["lyrics-plus", "reddit"]
    installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env)
    assert fake.apps == ["lyrics-plus", "reddit", "ytm-sync"]


def test_missing_spicetify_says_how_to_get_it(tmp_path, built_app, linux):
    env, _fake, lines = linux
    (env.home / ".spicetify" / "spicetify").unlink()
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 1
    assert "Spicetify was not found" in "\n".join(lines)
    assert "spicetify.app" in "\n".join(lines)


def test_spicetify_found_on_the_path(tmp_path, built_app, linux):
    env, fake, _ = linux
    (env.home / ".spicetify" / "spicetify").unlink()
    env.which = lambda name: "/usr/bin/spicetify" if name == "spicetify" else None
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 0
    assert fake.calls[0][0] == "/usr/bin/spicetify"


def test_a_first_run_without_backup_falls_back_to_backup_apply(tmp_path, built_app, linux):
    env, fake, _ = linux
    fake.apply_fails = 1
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 0
    assert fake.verbs()[-2:] == ["apply", "backup apply"]


def test_failing_apply_reports_spicetifys_message(tmp_path, built_app, linux):
    env, fake, lines = linux
    fake.apply_fails, fake.backup_fails = 2, True
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 1
    assert "backup failed" in "\n".join(lines)


def test_no_apply_flag_skips_apply(tmp_path, built_app, linux):
    env, fake, _ = linux
    installer.install(settings_in(tmp_path), apply=False, app_dir=str(built_app), env=env)
    assert "apply" not in fake.verbs()


def test_an_incomplete_app_folder_is_refused_before_touching_spicetify(tmp_path, linux):
    env, fake, lines = linux
    empty = tmp_path / "empty"
    empty.mkdir()
    assert installer.install(settings_in(tmp_path), app_dir=str(empty), env=env) == 1
    assert "index.js" in "\n".join(lines)
    assert fake.apps == [] and not (fake.userdata / "CustomApps" / "ytm-sync").exists()


def test_dry_run_lists_steps_and_changes_nothing(tmp_path, built_app, linux):
    env, fake, lines = linux
    assert installer.install(settings_in(tmp_path), dry_run=True, app_dir=str(built_app),
                             env=env) == 0
    assert fake.calls == [] and not (fake.userdata / "CustomApps").exists()
    text = "\n".join(lines)
    assert "[1/" in text and "Dry run only" in text


def test_userdata_falls_back_to_the_default_when_spicetify_cannot_say(tmp_path, linux):
    env, fake, _ = linux
    env.run = lambda _c: (1, "boom")
    assert installer.userdata_dir(env, Path("spicetify")) == env.home / ".config" / "spicetify"
    roaming = tmp_path / "roaming" / "spicetify"
    roaming.mkdir(parents=True)
    env.platform, env.environ = "win32", {"APPDATA": str(tmp_path / "roaming")}
    assert installer.userdata_dir(env, Path("spicetify")) == roaming


def test_a_wrongly_decoded_path_is_ignored_and_never_created(tmp_path, built_app, linux):
    """Regression: Windows user "Damian" with an accent: the reported path came out as
    "DamiÃ¡n" (UTF-8 read as cp1252), which does not exist; the installer then tried to create
    it inside C:\\Users and failed with 'access denied'."""
    env, fake, _ = linux
    bogus = tmp_path / "Users" / "DamiÃ¡n" / "spicetify"
    fake.userdata = bogus  # what `spicetify path userdata` (mis)reports
    default = env.home / ".config" / "spicetify"
    default.mkdir(parents=True, exist_ok=True)

    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 0
    assert (default / "CustomApps" / "ytm-sync" / "index.js").exists()
    assert not (tmp_path / "Users").exists()  # nothing was created at the bogus location


def test_without_any_spicetify_folder_nothing_is_created(tmp_path, built_app, linux):
    env, fake, lines = linux
    fake.userdata = tmp_path / "nowhere" / "spicetify"
    (env.home / ".config" / "spicetify").rmdir()
    (env.home / ".config").rmdir()
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 1
    assert "configuration folder was not found" in "\n".join(lines)
    assert not (tmp_path / "nowhere").exists() and not (env.home / ".config").exists()
    assert fake.apps == []


def test_decode_output_reads_utf8_and_falls_back_to_the_local_code_page(monkeypatch):
    assert installer.decode_output("C:\\Users\\Damián".encode()) == "C:\\Users\\Damián"
    monkeypatch.setattr(
        installer.locale, "getpreferredencoding", lambda _do_setlocale=True: "cp1252"
    )
    assert installer.decode_output("Damián".encode("cp1252")) == "Damián"


def test_default_run_decodes_a_child_process_as_utf8():
    import sys

    code, output = installer.default_run(
        [sys.executable, "-c",
         "import sys; sys.stdout.buffer.write('Dami\\u00e1n'.encode('utf-8'))"]
    )
    assert (code, output) == (0, "Damián")
    assert installer.default_run(["definitely-not-a-command-xyz"])[0] == 127


def test_the_program_folder_is_created_with_its_parents_but_the_app_folder_is_not(tmp_path):
    env = Env(platform="linux", environ={}, home=tmp_path, sleep=lambda _s: None)
    source = tmp_path / "src"
    source.mkdir()
    (source / "f").write_text("x")
    installer._replace_dir(env, source, tmp_path / "a" / "b" / "prog", make_parents=True)
    assert (tmp_path / "a" / "b" / "prog" / "f").exists()
    with pytest.raises(FileNotFoundError):  # a missing grandparent is an error, not a mkdir -p
        installer._replace_dir(env, source, tmp_path / "x" / "y" / "app")
    assert not (tmp_path / "x").exists()


def test_powershell_quoting_survives_apostrophes():
    assert installer.ps_quote("C:\\Users\\O'Brien") == "'C:\\Users\\O''Brien'"
    script = installer.shortcut_script(Path("a.lnk"), "t.exe", "x y", "w", 7, "it's")
    assert "'it''s'" in script and "$s.WindowStyle = 7" in script


# ---- Windows, packaged build ------------------------------------------------------------------


@pytest.fixture
def windows(tmp_path: Path, built_app):
    """Windows-like paths under tmp, running from an unpacked release folder."""
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    spicetify_bin = local / "spicetify" / "spicetify.exe"
    spicetify_bin.parent.mkdir(parents=True)
    spicetify_bin.touch()
    release = tmp_path / "release"
    release.mkdir()
    for name in ("ytm-sync.exe", "ytm-sync-background.exe", "Install YTM Sync.cmd"):
        (release / name).write_text("x")
    fake = FakeSpicetify(roaming / "spicetify")
    fake.userdata.mkdir(parents=True)
    started: list[list[str]] = []
    stopped: list[Settings] = []
    lines: list[str] = []
    env = Env(
        platform="win32",
        environ={"LOCALAPPDATA": str(local), "APPDATA": str(roaming)},
        home=tmp_path / "home", run=fake, which=lambda _n: None, frozen=True,
        executable=release / "ytm-sync.exe",
        start_companion=started.append,
        stop_companion=lambda s: stopped.append(s) or True,
        sleep=lambda _s: None, out=lines.append,
    )
    return env, fake, started, stopped, lines, local, roaming


def test_windows_install_sets_up_the_companion_and_shortcuts(tmp_path, built_app, windows):
    env, fake, started, stopped, _lines, local, roaming = windows
    settings = settings_in(tmp_path)
    assert installer.install(settings, app_dir=str(built_app), env=env) == 0

    program = local / "Programs" / "ytm-sync"
    assert (program / "ytm-sync.exe").exists() and (program / "ytm-sync-background.exe").exists()
    assert stopped == [settings]  # the old companion is stopped before its files are replaced

    menu, startup = fake.powershell
    assert "YTM Sync Companion.lnk" in menu and "code --pause" in menu
    assert str(program / "ytm-sync.exe") in menu and "$s.WindowStyle = 1" in menu
    assert "Startup" in startup and "YTM Sync.lnk" in startup
    assert str(program / "ytm-sync-background.exe") in startup
    assert "run --background" in startup and "$s.WindowStyle = 7" in startup
    assert started == [[str(program / "ytm-sync-background.exe"), "run", "--background"]]
    assert (roaming / "spicetify" / "CustomApps" / "ytm-sync" / "index.js").exists()


def test_windows_install_from_the_installed_copy_does_not_copy_onto_itself(
    tmp_path, built_app, windows
):
    env, _fake, started, stopped, _lines, local, _roaming = windows
    program = local / "Programs" / "ytm-sync"
    program.mkdir(parents=True)
    for name in ("ytm-sync.exe", "ytm-sync-background.exe"):
        (program / name).write_text("x")
    env.executable = program / "ytm-sync.exe"
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 0
    assert stopped == [] and started  # nothing to replace, still started


def test_windows_install_stops_when_the_old_companion_will_not_quit(tmp_path, built_app, windows):
    env, _fake, started, _stopped, lines, local, _roaming = windows
    env.stop_companion = lambda _s: False
    assert installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env) == 1
    assert started == [] and "would not stop" in "\n".join(lines)
    assert not (local / "Programs" / "ytm-sync").exists()


def test_uninstall_removes_everything_but_keeps_the_data(tmp_path, built_app, windows):
    env, fake, _started, stopped, _lines, local, roaming = windows
    settings = settings_in(tmp_path)
    installer.install(settings, app_dir=str(built_app), env=env)
    startup = roaming / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    startup.mkdir(parents=True)
    (startup / "YTM Sync.lnk").touch()  # the fake PowerShell does not create files
    (startup.parent / "YTM Sync Companion.lnk").touch()
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "browser.json").write_text("{}")
    stopped.clear()

    assert installer.uninstall(settings, env=env) == 0
    assert stopped == [settings]
    assert fake.apps == []
    assert not (roaming / "spicetify" / "CustomApps" / "ytm-sync").exists()
    assert not (local / "Programs" / "ytm-sync").exists()
    assert not (startup / "YTM Sync.lnk").exists()
    assert not (startup.parent / "YTM Sync Companion.lnk").exists()
    assert (settings.data_dir / "browser.json").exists()  # the YouTube Music session survives


def test_uninstall_purge_deletes_the_data(tmp_path, built_app, windows):
    env, *_ = windows
    settings = settings_in(tmp_path)
    settings.data_dir.mkdir(parents=True)
    (settings.data_dir / "browser.json").write_text("{}")
    assert installer.uninstall(settings, purge=True, env=env) == 0
    assert not settings.data_dir.exists()


def test_uninstall_without_spicetify_still_cleans_up(tmp_path, linux):
    env, _fake, lines = linux
    (env.home / ".spicetify" / "spicetify").unlink()
    assert installer.uninstall(settings_in(tmp_path), env=env) == 0
    assert "Spicetify was not found" in "\n".join(lines)


def test_uninstall_dry_run_changes_nothing(tmp_path, built_app, linux):
    env, fake, _ = linux
    installer.install(settings_in(tmp_path), app_dir=str(built_app), env=env)
    before = list(fake.calls)
    assert installer.uninstall(settings_in(tmp_path), dry_run=True, env=env) == 0
    assert fake.calls == before and fake.apps == ["ytm-sync"]
