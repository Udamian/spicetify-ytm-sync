"""The pieces behind the companion panel: start-with-Windows switch and diagnostics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ytm_sync_companion import installer
from ytm_sync_companion.app import create_app
from ytm_sync_companion.autostart import Autostart
from ytm_sync_companion.installer import Env

from .conftest import HOST_HEADER, ORIGIN, RAW_HEADERS


class Powershell:
    def __init__(self) -> None:
        self.scripts: list[str] = []
        self.fail = False

    def __call__(self, command):
        if list(command)[0] == "powershell":
            if self.fail:
                return 1, "boom"
            self.scripts.append(list(command)[-1])
        return 0, ""


def windows_env(tmp_path: Path, *, installed: bool = True) -> tuple[Env, Powershell, Path]:
    local, roaming = tmp_path / "Local", tmp_path / "Roaming"
    program = local / "Programs" / "ytm-sync"
    program.mkdir(parents=True)
    run = Powershell()
    exe_dir = program if installed else tmp_path / "unzipped"
    exe_dir.mkdir(exist_ok=True)
    env = Env(
        platform="win32", environ={"LOCALAPPDATA": str(local), "APPDATA": str(roaming)},
        home=tmp_path, run=run, frozen=True, executable=exe_dir / "ytm-sync.exe",
        out=lambda _m: None, sleep=lambda _s: None,
    )
    shortcut = roaming / "Microsoft/Windows/Start Menu/Programs/Startup" / "YTM Sync.lnk"
    return env, run, shortcut


# ---- Autostart ---------------------------------------------------------------------------


def test_autostart_is_only_offered_for_the_installed_windows_program(tmp_path):
    env, _, _ = windows_env(tmp_path, installed=False)
    assert Autostart(env).state() == {"supported": False, "enabled": False}

    linux = Env(platform="linux", environ={}, home=tmp_path, frozen=True)
    assert Autostart(linux).supported is False
    source = Env(platform="win32", environ={}, home=tmp_path, frozen=False)
    assert Autostart(source).supported is False


def test_autostart_creates_and_removes_the_startup_shortcut(tmp_path):
    env, run, shortcut = windows_env(tmp_path)
    autostart = Autostart(env)
    assert autostart.state() == {"supported": True, "enabled": False}

    autostart.set(True)
    assert len(run.scripts) == 1 and "YTM Sync.lnk" in run.scripts[0]
    assert "WindowStyle = 7" in run.scripts[0]
    shortcut.parent.mkdir(parents=True)
    shortcut.touch()  # what PowerShell would have created
    assert autostart.state()["enabled"] is True

    autostart.set(False)
    assert not shortcut.exists()
    assert autostart.state()["enabled"] is False
    autostart.set(False)  # switching off twice is fine


def test_autostart_set_refuses_when_not_supported(tmp_path):
    env, _, _ = windows_env(tmp_path, installed=False)
    with pytest.raises(installer.InstallError):
        Autostart(env).set(True)


# ---- the endpoints ----------------------------------------------------------------------


class FakeAutostart:
    def __init__(self, supported: bool = True) -> None:
        self.supported = supported
        self.on = False
        self.fail = False

    def state(self):
        return {"supported": self.supported, "enabled": self.supported and self.on}

    def set(self, enabled: bool) -> None:
        if self.fail:
            raise OSError("no")
        self.on = enabled


@pytest.fixture
def fake_autostart() -> FakeAutostart:
    return FakeAutostart()


@pytest.fixture
def panel_client(settings, fake_client, fake_autostart):
    app = create_app(settings, client_factory=lambda _p: fake_client, autostart=fake_autostart)
    client = app.test_client()
    code = app.extensions["ytm_sync"].pairing.code
    token = client.post(
        "/pair", json={"code": code}, headers={**HOST_HEADER, "Origin": ORIGIN}
    ).get_json()["token"]
    return client, {**HOST_HEADER, "Authorization": f"Bearer {token}"}


def test_autostart_endpoints_need_the_token(client):
    assert client.get("/autostart", headers=HOST_HEADER).status_code == 401
    assert client.post("/autostart", json={"enabled": True}, headers=HOST_HEADER).status_code == 401
    assert client.get("/diagnostics", headers=HOST_HEADER).status_code == 401


def test_autostart_get_and_set(panel_client, fake_autostart):
    client, auth = panel_client
    assert client.get("/autostart", headers=auth).get_json() == {
        "supported": True, "enabled": False}
    response = client.post("/autostart", json={"enabled": True}, headers=auth)
    assert response.get_json() == {"supported": True, "enabled": True}
    assert fake_autostart.on is True


def test_autostart_set_validates_and_reports_problems(panel_client, fake_autostart):
    client, auth = panel_client
    assert client.post("/autostart", json={"enabled": "yes"}, headers=auth).status_code == 400
    assert client.post("/autostart", json={}, headers=auth).status_code == 400
    fake_autostart.fail = True
    failed = client.post("/autostart", json={"enabled": True}, headers=auth)
    assert failed.status_code == 500 and failed.get_json() == {"error": "autostart_failed"}
    fake_autostart.fail = False
    fake_autostart.supported = False
    unsupported = client.post("/autostart", json={"enabled": True}, headers=auth)
    assert unsupported.status_code == 409 and unsupported.get_json()["error"] == "not_supported"


def test_cors_allows_the_methods_the_panel_uses(panel_client):
    client, _ = panel_client
    response = client.options("/autostart", headers={
        **HOST_HEADER, "Origin": ORIGIN, "Access-Control-Request-Method": "POST"})
    assert response.status_code == 204


# ---- diagnostics ----------------------------------------------------------------------------


def seed(settings, panel_client):
    client, auth = panel_client
    client.post("/auth/headers", json={"headers": RAW_HEADERS}, headers=auth)
    track = {"uri": "spotify:track:abc123", "title": "Secret Title", "artists": ["Someone"],
             "durationMs": 1000, "album": None}
    client.post("/sync/start", headers=auth, json={
        "source_uri": "spotify:playlist:37i9dQZF1DX", "dest_playlist_id": "PLabcdefghij1",
        "kind": "initial_dump", "tracks": [track]})
    log = settings.data_dir / "logs"
    log.mkdir(parents=True, exist_ok=True)
    home = str(Path.home())
    (log / "companion.log").write_text(
        f"opened {home}/x\nrefused: cookie: SID=topsecret\nbearer abc.def.ghi\n",
        encoding="utf-8")
    return client, auth


def test_diagnostics_has_state_but_no_secrets_ids_or_titles(settings, panel_client):
    client, auth = seed(settings, panel_client)
    response = client.get("/diagnostics", headers=auth)
    assert response.status_code == 200
    report = response.get_json()
    text = json.dumps(report)

    assert report["companion"]["version"]
    assert report["youtube_session"] in ("ok", "expired", "error", "not_configured")
    assert report["autostart"] == {"supported": True, "enabled": False}
    assert report["pairs"][0]["source"] == "playlist"
    assert report["jobs"][0]["kind"] == "initial_dump"

    for secret in ("topsecret", "abc.def.ghi", "fake-secret", "Secret Title", "PLabcdefghij1",
                   "37i9dQZF1DX", "spotify:track", str(Path.home())):
        assert secret not in text
    assert any("[redacted]" in line for line in report["log_tail"])
    assert any("~/x" in line for line in report["log_tail"])


def test_diagnostics_marks_liked_songs_and_survives_a_missing_log(settings, panel_client):
    client, auth = panel_client
    report = client.get("/diagnostics", headers=auth).get_json()
    assert report["log_tail"] == [] and report["pairs"] == [] and report["jobs"] == []


def test_log_tail_keeps_only_the_last_lines(settings):
    from ytm_sync_companion import diagnostics

    log = settings.data_dir / "logs"
    log.mkdir(parents=True)
    (log / "companion.log").write_text("\n".join(f"l{i}" for i in range(100)), encoding="utf-8")
    tail = diagnostics.log_tail(settings, lines=5)
    assert tail == ["l95", "l96", "l97", "l98", "l99"]
