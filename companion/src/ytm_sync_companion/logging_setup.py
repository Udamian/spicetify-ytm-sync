"""Logging that never writes secrets.

Cookies, bearer tokens, SAPISIDHASH values and pairing codes must not reach the log file, even
inside an exception message. Every record goes through `redact` before it is formatted.
"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

REDACTED = "[redacted]"

_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "Authorization: Bearer xxx", "Authorization: SAPISIDHASH xxx ..."
    re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)[^\r\n'\"]+"),
    # cookie headers and Set-Cookie
    re.compile(r"(?i)((?:set-)?cookie['\"]?\s*[:=]\s*['\"]?)[^\r\n'\"]+"),
    # key=value pairs for well known secret names
    re.compile(
        r"(?i)\b((?:__Secure-)?(?:[13]P)?(?:SAPISID|APISID|SID|HSID|SSID|PSIDTS|PSIDCC|PSID|"
        r"LOGIN_INFO|token|code)\s*[=:]\s*)[^\s;,'\"]+"
    ),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(SAPISID[0-9A-Z]*HASH\s+)\S+"),
)


def redact(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(lambda m: m.group(1) + REDACTED, text)
    return text


class RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def setup_logging(data_dir: Path, level: int = logging.INFO, *, console: bool = True) -> Path:
    """Log to `<data_dir>/logs/companion.log` (1 MB x 3 files) and, unless disabled, the console."""
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "companion.log"
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    root = logging.getLogger("ytm_sync_companion")
    root.setLevel(level)
    for handler in list(root.handlers):  # idempotent: tests and reloads call this repeatedly
        root.removeHandler(handler)
        handler.close()
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    ]
    if console:
        handlers.append(logging.StreamHandler())
    for handler in handlers:
        handler.setFormatter(formatter)
        root.addHandler(handler)
    root.propagate = False
    return log_path
