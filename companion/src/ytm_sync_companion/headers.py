"""Parsing and validation of the raw request headers copied from the browser.

Values are secrets (they are the user's Google session): never log or echo them.
"""

from __future__ import annotations

import re
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


_PS_COOKIE = re.compile(r'System\.Net\.Cookie\("((?:[^"`]|`.)*)",\s*"((?:[^"`]|`.)*)"')
_PS_HEADER = re.compile(r'^\s*"((?:[^"`]|`.)+)"\s*=\s*"((?:[^"`]|`.)*)"\s*$')
_CURL_HEADER = re.compile(r"""(?:-H|--header)\s+(?:'([^']*)'|"((?:[^"\\]|\\.)*)")""")
_CURL_COOKIE = re.compile(r"""(?:-b|--cookie)\s+(?:'([^']*)'|"((?:[^"\\]|\\.)*)")""")


def _ps_unescape(value: str) -> str:
    return re.sub(r"`(.)", r"\1", value)


def _parse_powershell(raw: str) -> dict[str, str]:
    """DevTools "Copy as PowerShell": cookies in $session.Cookies.Add, headers in @{ ... }."""
    headers: dict[str, str] = {}
    cookies = [f"{_ps_unescape(n)}={_ps_unescape(v)}" for n, v in _PS_COOKIE.findall(raw)]
    in_block = False
    for line in raw.splitlines():
        if "-Headers @{" in line:
            in_block = True
            continue
        if in_block and line.strip().startswith("}"):
            in_block = False
        if in_block:
            match = _PS_HEADER.match(line)
            if match:
                headers[_ps_unescape(match.group(1)).lower()] = _ps_unescape(match.group(2))
    if cookies:
        headers["cookie"] = "; ".join(cookies)
    return headers


def _parse_curl(raw: str) -> dict[str, str]:
    """DevTools "Copy as cURL" (bash or cmd): -H 'name: value' and -b 'cookies'."""
    headers: dict[str, str] = {}
    if '^"' in raw:  # cmd flavour: "^" escapes the next character and ends lines
        raw = re.sub(r"\^(.)", r"\1", raw, flags=re.DOTALL)
    for match in _CURL_HEADER.finditer(raw):
        name, sep, value = (match.group(1) or match.group(2)).partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    cookie = _CURL_COOKIE.search(raw)
    if cookie:
        headers["cookie"] = (cookie.group(1) or cookie.group(2)).strip()
    return headers


def parse_raw_headers(raw: str) -> dict[str, str]:
    """Parse what DevTools copies: plain request headers, "Copy as PowerShell" or "Copy as cURL"."""
    if "$session.Cookies.Add" in raw or "Invoke-WebRequest" in raw:
        return _parse_powershell(raw)
    if re.match(r"\s*curl\s", raw):
        return _parse_curl(raw)
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
