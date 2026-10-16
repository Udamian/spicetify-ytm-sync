"""Background worker: takes queued jobs and runs them with the sync engine.

One worker, one job at a time. Every job runs on its own SQLite connection (connections are
not shared between threads). `run_once` does a single job synchronously, which is what the
tests use; `start` runs it in a daemon thread for the real companion.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict
from typing import Any

from . import jobs, ytm
from .config import Settings
from .db import connect
from .sync import (
    SessionExpired,
    Stopped,
    SyncEngine,
    SyncError,
    SyncReport,
    WriteFailed,
    to_spotify_tracks,
)

log = logging.getLogger(__name__)


class Worker:
    def __init__(
        self,
        settings: Settings,
        client_factory: ytm.ClientFactory = ytm.load_client,
        *,
        engine_kwargs: dict[str, Any] | None = None,
        poll_seconds: float = 2.0,
    ) -> None:
        self.settings = settings
        self.client_factory = client_factory
        self.engine_kwargs = engine_kwargs or {}
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- thread control -------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="ytm-sync-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout)

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                worked = self.run_once()
            except Exception:  # never let the thread die; details go to the redacting log
                log.exception("worker iteration failed")
                worked = False
            if not worked:
                self._wake.wait(self.poll_seconds)
                self._wake.clear()

    # ---- one job --------------------------------------------------------------------------

    def run_once(self) -> bool:
        """Run the oldest queued job to its end. Returns False when there was none."""
        conn = connect(self.settings.db_path)
        try:
            job = jobs.claim_next(conn)
            if job is None:
                return False
            self._run(conn, job)
            return True
        finally:
            conn.close()

    def _run(self, conn: Any, job: jobs.Job) -> None:
        log.info("job %d (%s) started", job.id, job.kind)
        try:
            raw = jobs.payload(conn, job.id)
            tracks = to_spotify_tracks(json.loads(raw)) if raw else []
            engine = SyncEngine(conn, self.client_factory(self.settings.auth_path),
                                **self.engine_kwargs)

            def progress(done: int, total: int) -> None:
                jobs.set_progress(conn, job.id, done, total)

            def should_stop() -> bool:
                return self._stop.is_set() or jobs.is_cancelled(conn, job.id)

            run = engine.dump if job.kind == "initial_dump" else engine.incremental
            report: SyncReport = run(job.pair_id, tracks, progress, should_stop)
            jobs.finish(conn, job.id, "done", report=asdict(report))
            log.info("job %d done: %s", job.id, asdict(report))
        except Stopped:
            if jobs.is_cancelled(conn, job.id):
                log.info("job %d cancelled", job.id)
            else:  # shutting down: pick it up again at the next start
                jobs.requeue(conn, job.id)
                log.info("job %d paused for shutdown", job.id)
        except SessionExpired as exc:
            jobs.finish(conn, job.id, "failed", str(exc), error_code="session_expired")
        except WriteFailed as exc:
            jobs.finish(conn, job.id, "failed", str(exc), error_code="write_failed")
        except SyncError as exc:
            jobs.finish(conn, job.id, "failed", str(exc), error_code="sync_error")
        except Exception as exc:
            log.exception("job %d crashed", job.id)
            jobs.finish(conn, job.id, "failed", type(exc).__name__, error_code="internal_error")
