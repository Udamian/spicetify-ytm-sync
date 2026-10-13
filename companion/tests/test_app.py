from __future__ import annotations

import json
import os
import stat
import sys

import pytest

from ytm_sync_companion import __version__
from ytm_sync_companion.config import API_VERSION

from .conftest import HOST_HEADER, ORIGIN, RAW_HEADERS, FakeYTMusic

# ---- Host / Origin / CORS ------------------------------------------------------------


def test_health_ok(client):
    response = client.get("/health", headers=HOST_HEADER)
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "version": __version__, "api_version": API_VERSION}
    assert response.headers["Cache-Control"] == "no-store"


def test_wrong_host_is_rejected(client):
    response = client.get("/health", headers={"Host": "evil.example:48215"})
    assert response.status_code == 403
    assert response.get_json()["error"] == "host_not_allowed"


def test_foreign_origin_is_rejected_and_gets_no_cors_header(client):
    response = client.get("/health", headers={**HOST_HEADER, "Origin": "https://evil.example"})
    assert response.status_code == 403
    assert "Access-Control-Allow-Origin" not in response.headers


def test_allowed_origin_gets_cors_headers(client):
    response = client.get("/health", headers={**HOST_HEADER, "Origin": ORIGIN})
    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert response.headers["Vary"] == "Origin"


def test_preflight(client):
    headers = {
        **HOST_HEADER,
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type",
        "Access-Control-Request-Private-Network": "true",
    }
    response = client.options("/auth/headers", headers=headers)
    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == ORIGIN
    assert "Authorization" in response.headers["Access-Control-Allow-Headers"]
    assert response.headers["Access-Control-Allow-Private-Network"] == "true"


def test_preflight_from_foreign_origin_is_refused(client):
    response = client.options("/auth/headers", headers={**HOST_HEADER, "Origin": "https://x.y"})
    assert response.status_code == 403


def test_unknown_route_is_json_404(client):
    response = client.get("/nope", headers=HOST_HEADER)
    assert response.status_code == 404
    assert response.get_json()["error"] == "not_found"


# ---- pairing ------------------------------------------------------------------------


def test_pair_requires_an_origin(app, client):
    code = app.extensions["ytm_sync"].pairing.code
    response = client.post("/pair", json={"code": code}, headers=HOST_HEADER)
    assert response.status_code == 403


def test_pair_with_wrong_code(client):
    response = client.post(
        "/pair", json={"code": "WRONG000"}, headers={**HOST_HEADER, "Origin": ORIGIN}
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "invalid_code"


def test_pair_rejects_malformed_body(client):
    headers = {**HOST_HEADER, "Origin": ORIGIN}
    assert client.post("/pair", data="not json", headers=headers).status_code == 403
    assert client.post("/pair", json={"code": 123}, headers=headers).status_code == 403


def test_pair_locks_out_after_repeated_failures(client):
    headers = {**HOST_HEADER, "Origin": ORIGIN}
    codes = [client.post("/pair", json={"code": "WRONG000"}, headers=headers) for _ in range(6)]
    assert [r.status_code for r in codes[:5]] == [403] * 5
    assert codes[5].status_code == 429
    assert codes[5].headers["Retry-After"] == "60"


def test_pair_announces_the_rotated_code(settings, fake_client):
    from ytm_sync_companion.app import create_app

    seen: list[str] = []
    app = create_app(settings, client_factory=lambda _p: fake_client, on_new_code=seen.append)
    code = app.extensions["ytm_sync"].pairing.code
    client = app.test_client()
    response = client.post(
        "/pair", json={"code": code}, headers={**HOST_HEADER, "Origin": ORIGIN}
    )
    assert response.status_code == 200
    assert seen == [app.extensions["ytm_sync"].pairing.code]
    assert seen[0] != code


# ---- bearer auth --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/auth/status"),
        ("post", "/auth/headers"),
        ("delete", "/auth"),
        ("get", "/playlists"),
        ("post", "/sync/preview"),
        ("post", "/sync/start"),
        ("get", "/status"),
    ],
)
def test_protected_endpoints_need_a_token(client, method, path):
    response = getattr(client, method)(path, headers=HOST_HEADER)
    assert response.status_code == 401


def test_wrong_token_is_rejected(client):
    response = client.get("/auth/status", headers={**HOST_HEADER, "Authorization": "Bearer nope"})
    assert response.status_code == 401


# ---- credentials & playlists ---------------------------------------------------------


def test_auth_status_not_configured(client, auth):
    assert client.get("/auth/status", headers=auth).get_json() == {"status": "not_configured"}


def test_submit_headers_and_session_ok(client, auth, settings):
    response = client.post("/auth/headers", json={"headers": RAW_HEADERS}, headers=auth)
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "warnings": []}
    stored = json.loads(settings.auth_path.read_text())
    assert stored["x-goog-authuser"] == "0"
    if sys.platform != "win32":
        assert stat.S_IMODE(os.stat(settings.auth_path).st_mode) == 0o600
    assert client.get("/auth/status", headers=auth).get_json() == {"status": "ok"}


def test_submit_headers_reports_expired_session(app, client, auth, fake_client):
    fake_client.fail_with = RuntimeError("Server returned HTTP 401: Unauthorized.")
    response = client.post("/auth/headers", json={"headers": RAW_HEADERS}, headers=auth)
    assert response.get_json()["status"] == "expired"


def test_submit_incomplete_headers_never_echoes_values(client, auth, settings):
    raw = "cookie: __Secure-3PAPISID=super-secret-value"
    response = client.post("/auth/headers", json={"headers": raw}, headers=auth)
    assert response.status_code == 400
    body = response.get_data(as_text=True)
    assert "super-secret-value" not in body
    assert response.get_json()["missing"] == ["x-goog-authuser"]
    assert not settings.auth_path.exists()


@pytest.mark.parametrize("payload", [{}, {"headers": ""}, {"headers": 5}, [1, 2]])
def test_submit_headers_bad_body(client, auth, payload):
    assert client.post("/auth/headers", json=payload, headers=auth).status_code == 400


def test_oversized_body_is_refused(client, auth):
    big = {"headers": "x" * (300 * 1024)}
    assert client.post("/auth/headers", json=big, headers=auth).status_code == 413


def test_delete_credentials(client, auth, settings):
    client.post("/auth/headers", json={"headers": RAW_HEADERS}, headers=auth)
    assert settings.auth_path.exists()
    assert client.delete("/auth", headers=auth).status_code == 204
    assert not settings.auth_path.exists()
    assert client.delete("/auth", headers=auth).status_code == 204  # idempotent


def test_playlists_requires_credentials(client, auth):
    response = client.get("/playlists", headers=auth)
    assert response.status_code == 409
    assert response.get_json()["error"] == "not_configured"


def test_playlists(client, auth):
    client.post("/auth/headers", json={"headers": RAW_HEADERS}, headers=auth)
    response = client.get("/playlists", headers=auth)
    assert response.status_code == 200
    assert response.get_json()["playlists"][0] == {
        "id": "PLabc123",
        "title": "Liked mirror",
        "count": 42,
    }


def test_playlists_upstream_failure_is_generic(client, auth, fake_client):
    client.post("/auth/headers", json={"headers": RAW_HEADERS}, headers=auth)
    fake_client.fail_with = RuntimeError("cookie=super-secret leaked in message")
    response = client.get("/playlists", headers=auth)
    assert response.status_code == 502
    assert "super-secret" not in response.get_data(as_text=True)


def test_sync_endpoints_are_not_implemented_yet(client, auth):
    assert client.post("/sync/preview", headers=auth).status_code == 501
    assert client.post("/sync/start", headers=auth).status_code == 501
    assert client.get("/status", headers=auth).status_code == 501


def test_fake_client_defaults_are_healthy():
    assert FakeYTMusic().get_library_playlists(limit=1)
