"""Tests for recognising ViiBR and Suno track links."""

import pytest

from wisp.links import Track, TrackKind, find_track

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
    assert track is not None
    assert track.key == key


def test_suno_shortcodes_are_case_sensitive() -> None:
    lower = find_track("https://suno.com/s/abc123")
    upper = find_track("https://suno.com/s/ABC123")
    assert lower is not None and upper is not None
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
    assert track is not None
    assert track.kind is TrackKind.SUNO


def test_skips_invalid_links_before_a_valid_one() -> None:
    text = f"https://viibrmusic.com/creators/{VIIBR_ID} https://suno.com/s/two"
    track = find_track(text)
    assert track is not None
    assert track.key == "suno:two"
