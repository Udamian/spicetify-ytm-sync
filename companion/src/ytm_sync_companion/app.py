"""HTTP API served to the Spicetify custom app (contract v1, see companion/README.md).

Request pipeline: Host check -> Origin check -> CORS preflight -> bearer auth -> handler.
The rationale for each step is in docs/security.md.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from flask import Flask, Response, jsonify, request

from . import __version__, jobs, ytm
from .config import API_VERSION, Settings
from .db import connect, init_db
from .headers import check_headers
from .security import (
    Pairing,
    TokenStore,
    extract_bearer,
    host_allowed,
    origin_allowed,
    write_private,
)
from .sync import resolve_review
from .worker import Worker

# Endpoints reachable without a bearer token.
PUBLIC_ENDPOINTS = frozenset({"health", "pair"})
# Endpoints that browsers only; a request without an Origin header is refused.
ORIGIN_REQUIRED_ENDPOINTS = frozenset({"pair"})
MAX_BODY_BYTES = 256 * 1024  # raw DevTools headers are a few KB
# A library of thousands of tracks is sent in one request.
SYNC_BODY_BYTES = 8 * 1024 * 1024
LARGE_BODY_ENDPOINTS = frozenset({"sync_preview", "sync_start"})
MAX_TRACKS = 20_000

_TRACK_URI = re.compile(r"^spotify:track:[A-Za-z0-9]{1,32}$")
_SOURCE_URI = re.compile(r"^spotify:(collection:tracks|playlist:[A-Za-z0-9]{1,32})$")
_PLAYLIST_ID = re.compile(r"^[A-Za-z0-9_-]{10,64}$")
_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def parse_tracks(raw: object) -> tuple[list[dict[str, Any]], int | None]:
    """Validate the tracks sent by the app. Returns (clean tracks, index of the first bad one)."""
    if not isinstance(raw, list) or len(raw) > MAX_TRACKS:
        return [], 0
    clean: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            return [], index
        uri, title, artists = item.get("uri"), item.get("title"), item.get("artists", [])
        duration, album = item.get("durationMs"), item.get("album")
        valid = (
            isinstance(uri, str) and _TRACK_URI.match(uri)
            and isinstance(title, str) and len(title) <= 300
            and isinstance(artists, list) and len(artists) <= 20
            and all(isinstance(a, str) and len(a) <= 200 for a in artists)
            and (duration is None or (isinstance(duration, int) and 0 <= duration <= 86_400_000))
            and (album is None or (isinstance(album, str) and len(album) <= 300))
        )
        if not valid:
            return [], index
        clean.append(
            {"uri": uri, "title": title, "artists": artists, "durationMs": duration, "album": album}
        )
    return clean, None


@dataclass
class Services:
    settings: Settings
    pairing: Pairing
    tokens: TokenStore
    client_factory: ytm.ClientFactory = ytm.load_client
    # Called with the fresh pairing code whenever it rotates, so the CLI can show it.
    on_new_code: Callable[[str], None] | None = None
    worker: Worker | None = None


def _job_json(job: jobs.Job) -> dict[str, Any]:
    return {
        "id": job.id, "pair_id": job.pair_id, "kind": job.kind, "state": job.state,
        "done": job.done, "total": job.total, "progress": round(job.progress, 3),
        "error": job.error, "error_code": job.error_code, "report": job.report,
        "created_at": job.created_at, "finished_at": job.finished_at,
    }


def _error(code: str, status: int, **extra: Any) -> tuple[Response, int]:
    return jsonify({"error": code, **extra}), status


def create_app(
    settings: Settings | None = None,
    *,
    pairing: Pairing | None = None,
    tokens: TokenStore | None = None,
    client_factory: ytm.ClientFactory = ytm.load_client,
    on_new_code: Callable[[str], None] | None = None,
    worker_enabled: bool = False,
    engine_kwargs: dict[str, Any] | None = None,
) -> Flask:
    settings = settings or Settings.from_env()
    services = Services(
        settings=settings,
        pairing=pairing or Pairing(),
        tokens=tokens or TokenStore(settings.token_path),
        client_factory=client_factory,
        on_new_code=on_new_code,
    )
    startup = init_db(settings.db_path)
    try:
        jobs.recover_interrupted(startup)  # jobs a crash left "running" go back to the queue
    finally:
        startup.close()
    services.worker = Worker(settings, client_factory, engine_kwargs=engine_kwargs)
    if worker_enabled:
        services.worker.start()

    @contextmanager
    def db() -> Iterator[Any]:
        conn = connect(settings.db_path)
        try:
            yield conn
        finally:
            conn.close()

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.extensions["ytm_sync"] = services

    # ---- request pipeline -------------------------------------------------------------

    @app.before_request
    def guard() -> Any:
        request.max_content_length = (
            SYNC_BODY_BYTES if request.endpoint in LARGE_BODY_ENDPOINTS else MAX_BODY_BYTES
        )
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

    # ---- sync ---------------------------------------------------------------------------

    @app.post("/sync/preview")
    def sync_preview() -> Any:
        body = request.get_json(silent=True)
        tracks, bad = parse_tracks(body.get("tracks") if isinstance(body, dict) else None)
        if bad is not None:
            return _error("bad_tracks", 400, index=bad)
        with db() as conn:
            known = {row[0] for row in conn.execute("SELECT spotify_uri FROM track_map")}
        to_search = sum(1 for track in tracks if track["uri"] not in known)
        estimate = round(to_search * 0.8 + math.ceil(len(tracks) / 25) * 0.5)
        return jsonify({
            "total": len(tracks), "already_matched": len(tracks) - to_search,
            "to_search": to_search, "estimated_seconds": estimate,
        })

    @app.post("/sync/start")
    def sync_start() -> Any:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("bad_request", 400)
        source, kind = body.get("source_uri"), body.get("kind")
        dest = ytm.normalize_playlist_id(str(body.get("dest_playlist_id", "")))
        mode = body.get("mode", "additive")
        if not (isinstance(source, str) and _SOURCE_URI.match(source)):
            return _error("bad_source", 400)
        if not _PLAYLIST_ID.match(dest):
            return _error("bad_destination", 400)
        if kind not in ("initial_dump", "incremental") or mode not in ("additive", "mirror"):
            return _error("bad_request", 400)
        tracks, bad = parse_tracks(body.get("tracks"))
        if bad is not None:
            return _error("bad_tracks", 400, index=bad)
        if not settings.auth_path.exists():
            return _error("not_configured", 409)
        if not tracks:
            if kind == "initial_dump":
                return _error("bad_tracks", 400, index=0)
            return jsonify({"job_id": None, "nothing_to_do": True})
        with db() as conn:
            pair_id = jobs.upsert_pair(conn, source, dest, mode)
            running = jobs.active_for_pair(conn, pair_id)
            if running:
                return _error("already_running", 409, job_id=running.id)
            job = jobs.enqueue(conn, pair_id, kind, len(tracks), json.dumps(tracks))
        if services.worker:
            services.worker.wake()
        return jsonify({"job_id": job.id, "pair_id": pair_id}), 202

    @app.post("/sync/cancel")
    def sync_cancel() -> Any:
        body = request.get_json(silent=True)
        job_id = body.get("job_id") if isinstance(body, dict) else None
        if not isinstance(job_id, int):
            return _error("bad_request", 400)
        with db() as conn:
            return jsonify({"cancelled": jobs.cancel(conn, job_id)})

    @app.get("/status")
    def status() -> Any:
        job_id = request.args.get("job_id", type=int)
        with db() as conn:
            if job_id is not None:
                job = jobs.get(conn, job_id)
                return _error("not_found", 404) if job is None else jsonify({"job": _job_json(job)})
            grouped = conn.execute("SELECT status, COUNT(*) AS n FROM track_map GROUP BY status")
            counts = {row["status"]: row["n"] for row in grouped}
            return jsonify({
                "jobs": [_job_json(job) for job in jobs.recent(conn)],
                "worker_running": bool(services.worker and services.worker.running),
                "review_count": counts.get("review", 0),
                "not_found_count": counts.get("not_found", 0),
            })

    # ---- tracks the matcher was unsure about --------------------------------------------

    @app.get("/review")
    def review() -> Any:
        with db() as conn:
            rows = conn.execute(
                "SELECT spotify_uri, title, artists, duration_ms, status, video_id, confidence "
                "FROM track_map WHERE status IN ('review', 'not_found') "
                "ORDER BY confidence DESC LIMIT 500"
            ).fetchall()
        return jsonify({"items": [
            {"uri": r["spotify_uri"], "title": r["title"], "artists": r["artists"],
             "duration_ms": r["duration_ms"], "status": r["status"],
             "video_id": r["video_id"], "confidence": r["confidence"]}
            for r in rows
        ]})

    @app.post("/review/resolve")
    def review_resolve() -> Any:
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            return _error("bad_request", 400)
        uri, video_id = body.get("uri"), body.get("video_id")
        if not (isinstance(uri, str) and _TRACK_URI.match(uri)):
            return _error("bad_request", 400)
        if video_id is not None and not (isinstance(video_id, str) and _VIDEO_ID.match(video_id)):
            return _error("bad_video_id", 400)
        with db() as conn:
            found = resolve_review(conn, uri, video_id)
        return jsonify({"ok": True}) if found else _error("not_found", 404)

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
