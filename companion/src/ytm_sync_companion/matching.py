"""Match a Spotify track to a YouTube Music search result.

Pure functions, no network: the caller runs the search (see `ytm.py`) and passes the candidates
in. That keeps the scoring testable and lets spike S5 tune the thresholds on real libraries.

Score in [0, 1] = weighted title / artist / duration similarity, minus a penalty when the
candidate is a different *version* (live, remix, karaoke...) of the song.

Decision: `ok` (score >= OK_THRESHOLD and an artist matches), `review` (plausible but unsure,
the user decides) or `not_found`.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any, Literal

OK_THRESHOLD = 0.85
CLEAN_THRESHOLD = 0.70  # lower bar when all the hard checks in `decide` pass
REVIEW_THRESHOLD = 0.60

W_TITLE, W_ARTIST, W_DURATION = 0.50, 0.30, 0.20
VERSION_PENALTY = 0.25

# Words that make a recording a different version of the song.
VERSION_MARKERS = (
    "live", "remix", "cover", "karaoke", "instrumental", "acoustic", "sped up",
    "slowed", "nightcore", "8d", "reverb", "tribute", "en vivo", "en directo",
)

Status = Literal["ok", "review", "not_found"]


@dataclass(frozen=True)
class SpotifyTrack:
    uri: str
    title: str
    artists: tuple[str, ...]
    duration_ms: int | None = None
    album: str | None = None


@dataclass(frozen=True)
class Candidate:
    video_id: str
    title: str
    artists: tuple[str, ...]
    duration_ms: int | None = None
    album: str | None = None


@dataclass(frozen=True)
class MatchResult:
    status: Status
    video_id: str | None
    confidence: float
    reason: str = ""


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


_FEAT_GROUP = re.compile(r"[\(\[][^\)\]]*\b(?:feat|ft|featuring|with|con)\b[^\)\]]*[\)\]]", re.I)
_TAIL_DASH = re.compile(
    r"\s+-\s+(?:\d{4}\s+)?(?:remaster(?:ed)?|single version|radio edit|album version|"
    r"mono|stereo|deluxe|bonus track|version).*$",
    re.I,
)
_REMASTER_GROUP = re.compile(
    r"[\(\[][^\)\]]*\b(?:remaster(?:ed)?|deluxe|bonus)\b[^\)\]]*[\)\]]", re.I
)
_NON_WORD = re.compile(r"[^\w\s]")


def normalize(text: str) -> str:
    """Lowercase, no accents or punctuation, without 'feat.' groups and remaster tails."""
    text = _FEAT_GROUP.sub(" ", text)
    text = _REMASTER_GROUP.sub(" ", text)
    text = _TAIL_DASH.sub("", text)
    text = strip_accents(text).lower().replace("&", " and ")
    text = _NON_WORD.sub(" ", text)
    return " ".join(text.split())


def version_markers(text: str) -> set[str]:
    haystack = f" {_NON_WORD.sub(' ', strip_accents(text).lower())} "
    return {m for m in VERSION_MARKERS if f" {m} " in haystack}


def _ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ratio = SequenceMatcher(None, a, b).ratio()
    # One title contained in the other ("song" vs "song radio mix") deserves some credit.
    if a in b or b in a:
        ratio = max(ratio, 0.85)
    return ratio


def title_similarity(a: str, b: str) -> float:
    return _ratio(normalize(a), normalize(b))


def _plain(text: str) -> str:
    """Lowercase words only (keeps 'feat.' groups, unlike `normalize`)."""
    return " ".join(_NON_WORD.sub(" ", strip_accents(text).lower().replace("&", " and ")).split())


def artist_similarity(
    wanted: tuple[str, ...], found: tuple[str, ...], candidate_title: str = ""
) -> float:
    """0.6 if ANY wanted artist is among the candidate's, plus 0.4 x the fraction that are.

    Spotify lists every collaborator while YouTube Music often shows only one (the other
    names live in the title as "feat. X"), and either side may put a different artist first.
    So one shared artist is strong evidence, and names found in the candidate title count too.
    """
    wanted_n = [normalize(a) for a in wanted if a]
    found_n = [normalize(a) for a in found if a]
    if not wanted_n or not found_n:
        return 0.0
    title_words = f" {_plain(candidate_title)} "
    matched = 0
    for name in wanted_n:
        in_artists = max(_ratio(name, other) for other in found_n) >= 0.8
        in_title = bool(candidate_title) and f" {name} " in title_words
        matched += in_artists or in_title
    any_artist_listed = any(
        max(_ratio(name, other) for other in found_n) >= 0.8 for name in wanted_n
    )
    return 0.6 * any_artist_listed + 0.4 * matched / len(wanted_n)


def duration_similarity(wanted_ms: int | None, found_ms: int | None) -> float | None:
    """1.0 within 2 s, decaying to 0 beyond 15 s. `None` when either side is unknown."""
    if not wanted_ms or not found_ms:
        return None
    diff = abs(wanted_ms - found_ms) / 1000
    if diff <= 2:
        return 1.0
    if diff >= 15:
        return 0.0
    return 1.0 - (diff - 2) / 13


def score(track: SpotifyTrack, cand: Candidate) -> float:
    title = title_similarity(track.title, cand.title)
    artist = artist_similarity(track.artists, cand.artists, cand.title)
    duration = duration_similarity(track.duration_ms, cand.duration_ms)

    if duration is None:  # unknown duration: redistribute its weight
        total = (W_TITLE * title + W_ARTIST * artist) / (W_TITLE + W_ARTIST)
    else:
        total = W_TITLE * title + W_ARTIST * artist + W_DURATION * duration

    extra = version_markers(cand.title) - version_markers(track.title)
    if extra:
        total -= VERSION_PENALTY
    return max(0.0, min(1.0, total))


def build_query(track: SpotifyTrack) -> str:
    """Search text: clean title plus the first two artists."""
    return " ".join([normalize(track.title), *[a for a in track.artists[:2] if a]]).strip()


def _duration_gap_s(track: SpotifyTrack, cand: Candidate) -> float | None:
    if not track.duration_ms or not cand.duration_ms:
        return None
    return abs(track.duration_ms - cand.duration_ms) / 1000


def decide(track: SpotifyTrack, candidates: list[Candidate]) -> MatchResult:
    """Accept automatically when the score is high, or when every hard check passes.

    Hard checks (so that a different edit length alone does not send a clearly right match to
    review): same title (>= 0.9), a shared artist, no extra version word (live, remix...) and a
    duration gap of at most 20 s. Anything else plausible goes to review.
    """
    if not candidates:
        return MatchResult("not_found", None, 0.0, "no search results")
    best = max(candidates, key=lambda c: score(track, c))
    best_score = score(track, best)
    artist = artist_similarity(track.artists, best.artists, best.title)
    gap = _duration_gap_s(track, best)
    extra_version = version_markers(best.title) - version_markers(track.title)
    clean = (
        title_similarity(track.title, best.title) >= 0.9
        and artist >= 0.6
        and not extra_version
        and (gap is None or gap <= 20)
    )
    if artist >= 0.6 and (best_score >= OK_THRESHOLD or (clean and best_score >= CLEAN_THRESHOLD)):
        return MatchResult("ok", best.video_id, best_score)
    if best_score >= REVIEW_THRESHOLD:
        return MatchResult("review", best.video_id, best_score, "low confidence")
    return MatchResult("not_found", None, best_score, "best candidate too different")


def candidate_from_ytm(item: dict[str, Any]) -> Candidate | None:
    """Convert one `ytmusicapi` search result (filter="songs" or "videos") to a Candidate."""
    video_id = item.get("videoId")
    if not video_id:
        return None
    seconds = item.get("duration_seconds")
    album = item.get("album")
    return Candidate(
        video_id=str(video_id),
        title=str(item.get("title", "")),
        artists=tuple(a.get("name", "") for a in item.get("artists") or [] if isinstance(a, dict)),
        duration_ms=int(seconds) * 1000 if seconds else None,
        album=album.get("name") if isinstance(album, dict) else None,
    )