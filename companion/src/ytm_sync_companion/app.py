"""HTTP API served to the Spicetify custom app (contract v1, see companion/README.md).

Request pipeline: Host check -> Origin check -> CORS preflight -> bearer auth -> handler.
The rationale for each step is in docs/security.md.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

from . import __version__, ytm
from .config import API_VERSION, Settings
from .db import init_db
from .headers import check_headers
from .security import (
    Pairing,
    TokenStore,
    extract_bearer,
    host_allowed,
    origin_allowed,
    write_private,
)

# Endpoints reachable without a bearer token.
PUBLIC_ENDPOINTS = frozenset({"health", "pair"})
# Endpoints that browsers only; a request without an Origin header is refused.
ORIGIN_REQUIRED_ENDPOINTS = frozenset({"pair"})
MAX_BODY_BYTES = 256 * 1024  # raw DevTools headers are a few KB


@dataclass
class Services:
    settings: Settings
    pairing: Pairing
    tokens: TokenStore
    client_factory: ytm.ClientFactory = ytm.load_client
    # Called with the fresh pairing code whenever it rotates, so the CLI can show it.
    on_new_code: Callable[[str], None] | None = None


def _error(code: str, status: int, **extra: Any) -> tuple[Response, int]:
    return jsonify({"error": code, **extra}), status


def create_app(
    settings: Settings | None = None,
    *,
    pairing: Pairing | None = None,
    tokens: TokenStore | None = None,
    client_factory: ytm.ClientFactory = ytm.load_client,
    on_new_code: Callable[[str], None] | None = None,
) -> Flask:
    settings = settings or Settings.from_env()
    services = Services(
        settings=settings,
        pairing=pairing or Pairing(),
        tokens=tokens or TokenStore(settings.token_path),
        client_factory=client_factory,
        on_new_code=on_new_code,
    )
    init_db(settings.db_path).close()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.extensions["ytm_sync"] = services

    # ---- request pipeline -------------------------------------------------------------

    @app.before_request
    def guard() -> Any:
        if not host_allowed(request.headers.get("Host"), settings.allowed_hosts):
            return _error("host_not_allowed", 403)

        origin = request.headers.get("Origin")
        required = request.endpoint in ORIGIN_REQUIRED_ENDPOINTS
        if not origin_allowed(origin, settings.allowed_origins, required=required):
            return _error("origin_not_allowed", 403)

        if request.method == "OPTIONS":
            return Response(status=204)  # CORS headers are added in after_request

        if request.endpoint in PUBLIC_ENDPOINTS or request.endpoint is None:
            return None
        if not services.tokens.verify(extract_bearer(request.headers.get("Authorization"))):
            return _error("unauthorized", 401)
        return None

    @app.after_request
    def add_headers(response: Response) -> Response:
        response.headers["Cache-Control"] = "no-store"
        origin = request.headers.get("Origin")
        if origin and origin in settings.allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
            response.headers["Access-Control-Max-Age"] = "600"
            # Chrome's Private Network Access preflight (public page -> localhost).
            if request.headers.get("Access-Control-Request-Private-Network") == "true":
                response.headers["Access-Control-Allow-Private-Network"] = "true"
        return response

    # ---- public endpoints -------------------------------------------------------------

    @app.get("/health")
    def health() -> Response:
        return jsonify({"ok": True, "version": __version__, "api_version": API_VERSION})

    @app.post("/pair")
    def pair() -> Any:
        body = request.get_json(silent=True)
        code = body.get("code") if isinstance(body, dict) else None
        result = services.pairing.redeem(code if isinstance(code, str) else None)
        if result in ("ok", "expired") and services.on_new_code:
            services.on_new_code(services.pairing.code)  # the code rotated in both cases
        if result == "ok":
            return jsonify({"token": services.tokens.token})
        if result == "locked":
            response, _ = _error("locked", 429)
            response.headers["Retry-After"] = "60"
            return response, 429
        if result == "expired":
            return _error("expired", 410)
        return _error("invalid_code", 403)

    # ---- authenticated endpoints ------------------------------------------------------

    @app.get("/auth/status")
    def auth_status() -> Response:
        status = ytm.session_status(settings.auth_path, services.client_factory)
        return jsonify({"status": status})

    @app.post("/auth/headers")
    def auth_headers() -> Any:
        body = request.get_json(silent=True)
        raw = body.get("headers") if isinstance(body, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            return _error("bad_request", 400)
        check = check_headers(raw)
        if not check.ok:
            # Only header *names* are echoed back, never values.
            return _error("missing_headers", 400, missing=check.missing, warnings=check.warnings)
        write_private(settings.auth_path, json.dumps(check.headers))
        status = ytm.session_status(settings.auth_path, services.client_factory)
        return jsonify({"status": status, "warnings": check.warnings})

    @app.delete("/auth")
    def auth_delete() -> Any:
        Path(settings.auth_path).unlink(missing_ok=True)
        return Response(status=204)

    @app.get("/playlists")
    def playlists() -> Any:
        if not settings.auth_path.exists():
            return _error("not_configured", 409)
        try:
            found = ytm.list_playlists(settings.auth_path, services.client_factory)
            return jsonify({"playlists": found})
        except Exception:  # upstream failures must not leak details
            return _error("youtube_error", 502)

    # ---- sync engine: not implemented yet (roadmap phase 2) ---------------------------

    @app.post("/sync/preview")
    @app.post("/sync/start")
    @app.get("/status")
    def not_implemented() -> Any:
        return _error("not_implemented", 501)

    # ---- generic JSON errors ----------------------------------------------------------

    @app.errorhandler(404)
    def not_found(_: Exception) -> Any:
        return _error("not_found", 404)

    @app.errorhandler(405)
    def method_not_allowed(_: Exception) -> Any:
        return _error("method_not_allowed", 405)

    @app.errorhandler(413)
    def too_large(_: Exception) -> Any:
        return _error("payload_too_large", 413)

    return app
