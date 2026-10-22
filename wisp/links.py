"""Recognition of ViiBR and Suno track links."""

import re
from dataclasses import dataclass
from enum import StrEnum


class TrackKind(StrEnum):
    """The site a track was published on."""

    VIIBR = "viibr"
    SUNO = "suno"


@dataclass(frozen=True)
class Track:
    """A recognised track: where it lives, its unique key and its link."""

    kind: TrackKind
    key: str
    url: str


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
_END = r"(?![\w-])"

_PATTERNS: tuple[tuple[TrackKind, re.Pattern[str]], ...] = (
    (
        TrackKind.VIIBR,
        re.compile(
            rf"https://(?:www\.)?viibrmusic\.com/songs/(?P<id>{_UUID}){_END}",
            re.IGNORECASE,
        ),
    ),
    (
        TrackKind.SUNO,
        re.compile(
            rf"https://(?:suno\.com|app\.suno\.ai)/song/(?P<id>{_UUID}){_END}",
            re.IGNORECASE,
        ),
    ),
    (
        TrackKind.SUNO,
        re.compile(
            rf"https://suno\.com/s/(?P<id>[0-9a-z]+){_END}",
            re.IGNORECASE,
        ),
    ),
)


def find_track(text: str) -> Track | None:
    """Return the first valid track link in ``text``, or None if there is none."""
    matches = [
        (match.start(), kind, match)
        for kind, pattern in _PATTERNS
        if (match := pattern.search(text))
    ]
    if not matches:
        return None
    _, kind, match = min(matches, key=lambda found: found[0])
    return Track(kind, f"{kind}:{match['id'].lower()}", match[0])
