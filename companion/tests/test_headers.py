from __future__ import annotations

from ytm_sync_companion.headers import check_headers, parse_raw_headers

from .conftest import RAW_HEADERS


def test_parse_skips_pseudo_headers_and_lowercases():
    headers = parse_raw_headers(RAW_HEADERS)
    assert ":authority" not in headers
    assert headers["x-goog-authuser"] == "0"
    assert headers["authorization"].startswith("SAPISIDHASH ")
    assert "__Secure-3PAPISID=fake-secret" in headers["cookie"]


def test_parse_keeps_colons_inside_values():
    headers = parse_raw_headers("referer: https://music.youtube.com/\n")
    assert headers["referer"] == "https://music.youtube.com/"


def test_valid_headers():
    check = check_headers(RAW_HEADERS)
    assert check.ok
    assert check.missing == []
    assert check.warnings == []


def test_missing_required_headers_are_named():
    check = check_headers("accept: */*")
    assert not check.ok
    assert set(check.missing) == {"cookie", "x-goog-authuser"}


def test_cookie_without_session_token_is_rejected():
    check = check_headers("cookie: foo=bar\nx-goog-authuser: 0")
    assert not check.ok
    assert "cookie:__Secure-3PAPISID" in check.missing


def test_missing_authorization_is_only_a_warning():
    raw = "cookie: __Secure-3PAPISID=x\nx-goog-authuser: 0"
    check = check_headers(raw)
    assert check.ok
    assert len(check.warnings) == 1


def test_repr_never_contains_secret_values():
    assert "fake-secret" not in repr(check_headers(RAW_HEADERS))
