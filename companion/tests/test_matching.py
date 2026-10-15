from __future__ import annotations

from ytm_sync_companion.matching import (
    Candidate,
    SpotifyTrack,
    build_query,
    candidate_from_ytm,
    decide,
    duration_similarity,
    normalize,
    score,
    version_markers,
)

TRACK = SpotifyTrack("spotify:track:1", "Hello", ("Adele",), 295_000, "25")


def cand(title="Hello", artists=("Adele",), ms=295_000, vid="v1") -> Candidate:
    return Candidate(vid, title, artists, ms)


def test_normalize_removes_feat_remaster_accents_punctuation():
    assert normalize("Canción (feat. Bad Bunny) - Remastered 2011") == "cancion"
    assert normalize("Rock & Roll [Deluxe Edition]") == "rock and roll"
    assert normalize("Song - 2009 Remaster") == "song"


def test_version_markers():
    assert version_markers("Hello (Live at the Royal Albert Hall)") == {"live"}
    assert version_markers("Hello (Karaoke Version)") == {"karaoke"}
    assert version_markers("Hello") == set()
    assert version_markers("Alive") == set()  # whole words only


def test_duration_similarity():
    assert duration_similarity(200_000, 201_000) == 1.0
    assert duration_similarity(200_000, 230_000) == 0.0
    assert 0.0 < duration_similarity(200_000, 207_000) < 1.0
    assert duration_similarity(None, 200_000) is None


def test_exact_match_is_ok():
    result = decide(TRACK, [cand()])
    assert result.status == "ok"
    assert result.video_id == "v1"
    assert result.confidence > 0.95


def test_picks_the_best_of_several():
    wrong = cand("Hello", ("Lionel Richie",), 250_000, "wrong")
    right = cand("Hello", ("Adele",), 295_500, "right")
    assert decide(TRACK, [wrong, right]).video_id == "right"


def test_remaster_and_accents_still_ok():
    track = SpotifyTrack("u", "Canción de Cuna - Remastered 2011", ("Café Tacvba",), 200_000)
    result = decide(track, [cand("Cancion de cuna", ("Cafe Tacvba",), 200_500)])
    assert result.status == "ok"


def test_live_version_is_not_auto_accepted():
    live = cand("Hello (Live)", ("Adele",), 295_000)
    assert score(TRACK, live) < score(TRACK, cand())
    assert decide(TRACK, [live]).status != "ok"


def test_other_artist_same_title_is_not_ok():
    result = decide(TRACK, [cand("Hello", ("Lionel Richie",), 295_000)])
    assert result.status != "ok"


def test_much_longer_duration_goes_to_review_or_not_found():
    result = decide(TRACK, [cand("Hello", ("Adele",), 600_000)])
    assert result.status in {"review", "not_found"}


def test_unknown_duration_does_not_block_a_good_match():
    track = SpotifyTrack("u", "Hello", ("Adele",), None)
    assert decide(track, [cand(ms=None)]).status == "ok"


def test_no_candidates():
    result = decide(TRACK, [])
    assert result.status == "not_found"
    assert result.video_id is None


def test_unrelated_candidate_is_not_found():
    assert decide(TRACK, [cand("Totally Different", ("Someone",), 100_000)]).status == "not_found"


def test_build_query_uses_first_two_artists():
    track = SpotifyTrack("u", "Song (feat. X)", ("A", "B", "C"))
    assert build_query(track) == "song A B"


def test_candidate_from_ytm_result():
    item = {
        "videoId": "abc",
        "title": "Hello",
        "artists": [{"name": "Adele", "id": "1"}],
        "album": {"name": "25"},
        "duration_seconds": 295,
    }
    c = candidate_from_ytm(item)
    assert c == Candidate("abc", "Hello", ("Adele",), 295_000, "25")
    assert candidate_from_ytm({"title": "no id"}) is None
    assert candidate_from_ytm({"videoId": "x", "title": "t"}).artists == ()


def test_collaboration_with_featured_names_in_title_is_ok():
    # Spotify lists every artist; YouTube Music shows only the main one, the rest are in the title.
    track = SpotifyTrack(
        "u", "Know No Better", ("Major Lazer", "Travis Scott", "Camila Cabello", "Quavo"), 234_000
    )
    found = cand("Know No Better (feat. Travis Scott, Camila Cabello & Quavo)", ("Major Lazer",),
                 226_000)
    assert decide(track, [found]).status == "ok"


def test_other_listed_artist_first_is_ok_despite_longer_edit():
    track = SpotifyTrack("u", "Tu Turrito", ("Rei", "Callejero Fino"), 165_000)
    found = cand("Tu turrito", ("Callejero Fino",), 177_000)
    assert decide(track, [found]).status == "ok"


def test_clean_rule_does_not_accept_a_live_version_or_big_duration_gap():
    track = SpotifyTrack("u", "Song", ("A", "B"), 200_000)
    assert decide(track, [cand("Song (Live)", ("A",), 200_000)]).status != "ok"
    assert decide(track, [cand("Song", ("A",), 260_000)]).status != "ok"


def test_no_shared_artist_is_never_ok_even_with_perfect_title_and_duration():
    track = SpotifyTrack("u", "Hello", ("Adele",), 295_000)
    assert decide(track, [cand("Hello", ("Someone Else",), 295_000)]).status != "ok"