from __future__ import annotations

import logging

from ytm_sync_companion.logging_setup import REDACTED, redact, setup_logging

SECRETS = [
    "Authorization: Bearer abc123.def-456",
    "authorization: SAPISIDHASH 1791972951_54d6e0dce85e_u SAPISID1PHASH 1791_aa_u",
    "Cookie: SAPISID=nEMMW6xz/AisYr; __Secure-3PSID=g.a000xyz; YSC=zzz",
    "got __Secure-1PSID=g.a000SECRETVALUE and moved on",
    "token=ABCDEF123456",
    "pairing code: 1a2b3c4d",
]


def test_redact_hides_every_secret():
    for line in SECRETS:
        cleaned = redact(line)
        assert REDACTED in cleaned
        for leaked in ("abc123", "54d6e0dce85e", "nEMMW6xz", "SECRETVALUE", "ABCDEF123456",
                       "1a2b3c4d", "g.a000xyz"):
            assert leaked not in cleaned, (line, cleaned)


def test_redact_keeps_normal_text():
    text = "Synced 120 tracks to playlist PLabc in 14 s"
    assert redact(text) == text


def test_setup_logging_writes_file_without_secrets(tmp_path):
    log_path = setup_logging(tmp_path)
    logging.getLogger("ytm_sync_companion.test").error("failed with Cookie: SAPISID=SECRET1")
    for handler in logging.getLogger("ytm_sync_companion").handlers:
        handler.flush()
    content = log_path.read_text(encoding="utf-8")
    assert "failed with" in content
    assert "SECRET1" not in content


def test_setup_logging_is_idempotent(tmp_path):
    setup_logging(tmp_path)
    setup_logging(tmp_path)
    assert len(logging.getLogger("ytm_sync_companion").handlers) == 2
