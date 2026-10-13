from __future__ import annotations

from pathlib import Path

import pytest

from ytm_sync_companion.app import create_app
from ytm_sync_companion.config import Settings

PORT = 48215
ORIGIN = "https://xpui.app.spotify.com"
HOST_HEADER = {"Host": f"127.0.0.1:{PORT}"}

# Fake raw headers, as DevTools "Copy request headers" would produce them.
RAW_HEADERS = "\n".join(
    [
        ":authority: music.youtube.com",
        ":method: POST",
        "accept: */*",
        "authorization: SAPISIDHASH 1700000000_deadbeef",
        "cookie: __Secure-3PAPISID=fake-secret; SID=other",
        "x-goog-authuser: 0",
    ]
)


class FakeYTMusic:
    """Stands in for `ytmusicapi.YTMusic` so tests never touch the network."""

    def __init__(self, *, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with

    def get_library_playlists(self, limit: int | None = 25) -> list[dict]:
        if self.fail_with:
            raise self.fail_with
        return [
            {"playlistId": "VLPLabc123", "title": "Liked mirror", "count": 42},
            {"playlistId": "PLdef456", "title": "Gym"},
            {"title": "Entry without id"},
        ]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(port=PORT, data_dir=tmp_path / "data", allowed_origins=(ORIGIN,))


@pytest.fixture
def fake_client() -> FakeYTMusic:
    return FakeYTMusic()


@pytest.fixture
def app(settings: Settings, fake_client: FakeYTMusic):
    return create_app(settings, client_factory=lambda _path: fake_client)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def token(app, client) -> str:
    """Pair through the real endpoint and return the bearer token."""
    code = app.extensions["ytm_sync"].pairing.code
    response = client.post(
        "/pair", json={"code": code}, headers={**HOST_HEADER, "Origin": ORIGIN}
    )
    assert response.status_code == 200
    return response.get_json()["token"]


@pytest.fixture
def auth(token: str) -> dict[str, str]:
    return {**HOST_HEADER, "Authorization": f"Bearer {token}"}
