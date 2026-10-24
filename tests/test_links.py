"""Tests for recognising ViiBR and Suno track links."""

import pytest

from wisp.links import ShareLink, Track, TrackKind, find_track, whole_link

VIIBR_ID = "13a1cf54-f186-497d-9124-6a23166f1303"
SUNO_ID = "3e504622-bf17-42ca-9059-c83393bce7dc"


@pytest.mark.parametrize(
    "text,key",
    [
        (f"new one https://viibrmusic.com/songs/{VIIBR_ID} !!", f"viibr:{VIIBR_ID}"),
        (
            f"https://www.viibrmusic.com/songs/{VIIBR_ID.upper()}/?ref=x",
            f"viibr:{VIIBR_ID}",
        ),
        (f"https://suno.com/song/{SUNO_ID}", f"suno:{SUNO_ID}"),
        ("https://suno.com/s/AbC123xyz", "suno:AbC123xyz"),
        (f"https://app.suno.ai/song/{SUNO_ID}", f"suno:{SUNO_ID}"),
        (f"https://suno.com/song/{SUNO_ID}?sh=abc#top", f"suno:{SUNO_ID}"),
    ],
)
def test_finds_track(text: str, key: str) -> None:
    track = find_track(text)
    assert isinstance(track, Track)
    assert track.key == key


def test_suno_shortcodes_are_case_sensitive() -> None:
    lower = find_track("https://suno.com/s/abc123")
    upper = find_track("https://suno.com/s/ABC123")
    assert isinstance(lower, Track) and isinstance(upper, Track)
    assert lower.key != upper.key


def test_track_carries_kind_and_url() -> None:
    url = f"https://viibrmusic.com/songs/{VIIBR_ID}"
    assert find_track(f"listen: {url}") == Track(
        TrackKind.VIIBR, f"viibr:{VIIBR_ID}", url
    )


@pytest.mark.parametrize(
    "text",
    [
        "https://viibrmusic.com",
        f"https://viibrmusic.com/creators/{VIIBR_ID}",
        f"https://viibrmusic.com/p/{VIIBR_ID}",
        "https://viibrmusic.com/songs/not-a-uuid",
        "https://suno.com",
        "https://youtube.com/watch?v=abc",
        "no links here",
        "",
        f"https://viibrmusic.com.evil.example/songs/{VIIBR_ID}",
        f"https://evilviibrmusic.com/songs/{VIIBR_ID}",
        f"https://example.com/?next=https://suno.com.evil.example/song/{SUNO_ID}",
    ],
)
def test_rejects_non_tracks(text: str) -> None:
    assert find_track(text) is None


def test_first_valid_link_wins() -> None:
    text = f"https://suno.com/s/one https://viibrmusic.com/songs/{VIIBR_ID}"
    track = find_track(text)
    assert isinstance(track, Track)
    assert track.kind is TrackKind.SUNO


def test_skips_invalid_links_before_a_valid_one() -> None:
    text = f"https://viibrmusic.com/creators/{VIIBR_ID} https://suno.com/s/two"
    track = find_track(text)
    assert isinstance(track, Track)
    assert track.key == "suno:two"


# ---
# viibrmusic.com share links
# ---

SHARE_CODE = "bDBmywB5"
SHARE_URL = f"https://viibrmusic.com/s/{SHARE_CODE}"


@pytest.mark.parametrize(
    "text,url",
    [
        (f"listen {SHARE_URL} now", SHARE_URL),
        (
            f"https://www.viibrmusic.com/s/{SHARE_CODE}",
            f"https://www.viibrmusic.com/s/{SHARE_CODE}",
        ),
        (f"{SHARE_URL}?ref=discord", SHARE_URL),
        (f"{SHARE_URL}/", SHARE_URL),
    ],
)
def test_finds_a_share_link(text: str, url: str) -> None:
    assert find_track(text) == ShareLink(SHARE_CODE, url)


def test_a_share_code_stops_at_the_first_non_ascii_character() -> None:
    found = find_track("https://viibrmusic.com/s/ab\u017fc")
    assert found == ShareLink("ab", "https://viibrmusic.com/s/ab")


def test_share_codes_are_case_sensitive_and_kept_exactly() -> None:
    upper = find_track("https://viibrmusic.com/s/ABCdef12")
    lower = find_track("https://viibrmusic.com/s/abcdef12")
    assert isinstance(upper, ShareLink) and isinstance(lower, ShareLink)
    assert (upper.code, lower.code) == ("ABCdef12", "abcdef12")


def test_a_share_link_counts_as_viibr() -> None:
    assert ShareLink(SHARE_CODE, SHARE_URL).kind is TrackKind.VIIBR


def test_a_share_link_becomes_the_song_it_names_shown_as_posted() -> None:
    song = Track(
        TrackKind.VIIBR,
        f"viibr:{VIIBR_ID}",
        f"https://viibrmusic.com/songs/{VIIBR_ID}",
    )

    track = ShareLink(SHARE_CODE, SHARE_URL).as_track(song)

    assert track == Track(TrackKind.VIIBR, f"viibr:{VIIBR_ID}", SHARE_URL)


@pytest.mark.parametrize(
    "text",
    [
        "https://viibrmusic.com/s/",
        "https://viibrmusic.com/s/ab-cd",
        "https://viibrmusic.com/s/ab_cd",
        "https://viibrmusic.com.evil.example/s/abc123",
        "https://evilviibrmusic.com/s/abc123",
        "http://viibrmusic.com/s/abc123",
        "http\u017f://viibrmusic.com/s/abc",
        "https://viibrmu\u017fic.com/s/abc",
    ],
)
def test_rejects_what_is_not_a_share_link(text: str) -> None:
    assert find_track(text) is None


def test_the_first_link_wins_between_share_and_song_links() -> None:
    song = f"https://viibrmusic.com/songs/{VIIBR_ID}"
    assert isinstance(find_track(f"{SHARE_URL} {song}"), ShareLink)
    assert isinstance(find_track(f"{song} {SHARE_URL}"), Track)
    assert isinstance(find_track(f"https://suno.com/s/one {SHARE_URL}"), Track)


# ---
# Whole links
# ---


@pytest.mark.parametrize(
    "url,expected",
    [
        (
            f"https://viibrmusic.com/songs/{VIIBR_ID}",
            Track(
                TrackKind.VIIBR,
                f"viibr:{VIIBR_ID}",
                f"https://viibrmusic.com/songs/{VIIBR_ID}",
            ),
        ),
        (
            f"https://viibrmusic.com/songs/{VIIBR_ID.upper()}/?from=share",
            Track(
                TrackKind.VIIBR,
                f"viibr:{VIIBR_ID}",
                f"https://viibrmusic.com/songs/{VIIBR_ID.upper()}",
            ),
        ),
        (SHARE_URL, ShareLink(SHARE_CODE, SHARE_URL)),
        (f"https://example.com/?next=https://viibrmusic.com/songs/{VIIBR_ID}", None),
        (f"https://viibrmusic.com/songs/{VIIBR_ID}/comments", None),
        (f"see https://viibrmusic.com/songs/{VIIBR_ID}", None),
        ("https://viibrmusic.com/creators/abc", None),
        ("", None),
    ],
)
def test_whole_link_is_a_link_only_when_it_is_the_whole_url(
    url: str, expected: Track | ShareLink | None
) -> None:
    assert whole_link(url) == expected
