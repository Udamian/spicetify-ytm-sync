"""Parsing and validation of the raw request headers copied from the browser.

Values are secrets (they are the user's Google session): never log or echo them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

REQUIRED_HEADERS = ("cookie", "x-goog-authuser")
SESSION_COOKIES = ("__Secure-3PAPISID", "SAPISID")


@dataclass(frozen=True)
class HeaderCheck:
    headers: dict[str, str] = field(repr=False)  # repr=False: contains secrets
    missing: list[str]
    warnings: list[str]

    @property
    def ok(self) -> bool:
        return not self.missing


def parse_raw_headers(raw: str) -> dict[str, str]:
    """Parse the "name: value" lines produced by DevTools ("Copy request headers")."""
    headers: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        # Skip blanks and HTTP/2 pseudo-headers such as ":authority: music.youtube.com".
        if not line or line.startswith(":"):
            continue
        name, sep, value = line.partition(":")
        if not sep:
            continue
        headers[name.strip().lower()] = value.strip()
    return headers


def check_headers(raw: str) -> HeaderCheck:
    headers = parse_raw_headers(raw)
    missing = [name for name in REQUIRED_HEADERS if not headers.get(name)]
    warnings: list[str] = []

    cookie = headers.get("cookie", "")
    if cookie and not any(f"{name}=" in cookie for name in SESSION_COOKIES):
        missing.append("cookie:__Secure-3PAPISID")
    if not headers.get("authorization"):
        warnings.append(
            "No 'authorization' header: copy the headers from a POST request to "
            "music.youtube.com (for example a /browse request)."
        )
    return HeaderCheck(headers=headers, missing=missing, warnings=warnings)
