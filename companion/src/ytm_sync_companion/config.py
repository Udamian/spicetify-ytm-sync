"""Runtime configuration and filesystem locations."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Bump when the HTTP contract with the Spicetify app changes in an incompatible way.
API_VERSION = 1

# The server is never exposed on other interfaces.
HOST = "127.0.0.1"
DEFAULT_PORT = 48215

# Origin of the Spotify web view (confirmed with `location.origin` in spike S3).
DEFAULT_ALLOWED_ORIGINS = ("https://xpui.app.spotify.com",)


def default_data_dir() -> Path:
    override = os.environ.get("YTM_SYNC_DATA_DIR")
    if override:
        return Path(override)
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share")))
    return base / "ytm-sync"


@dataclass(frozen=True)
class Settings:
    port: int = DEFAULT_PORT
    data_dir: Path = field(default_factory=default_data_dir)
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Values of the `Host` header we accept (protects against DNS rebinding)."""
        return frozenset({f"127.0.0.1:{self.port}", f"localhost:{self.port}"})

    @property
    def db_path(self) -> Path:
        return self.data_dir / "ytm-sync.sqlite3"

    @property
    def auth_path(self) -> Path:
        return self.data_dir / "browser.json"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "token"

    @classmethod
    def from_env(cls) -> Settings:
        port = int(os.environ.get("YTM_SYNC_PORT", DEFAULT_PORT))
        raw_origins = os.environ.get("YTM_SYNC_ALLOWED_ORIGINS")
        origins = (
            tuple(o.strip() for o in raw_origins.split(",") if o.strip())
            if raw_origins
            else DEFAULT_ALLOWED_ORIGINS
        )
        return cls(port=port, allowed_origins=origins)
