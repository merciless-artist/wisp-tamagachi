"""Recognition of ViiBR and Suno track links."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar


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


@dataclass(frozen=True)
class ShareLink:
    """A viibrmusic.com share link, such as https://viibrmusic.com/s/bDBmywB5.

    Only the site knows which song its code names, so it counts once it has
    been resolved to that song. The code is case-sensitive and kept exactly.
    """

    kind: ClassVar[TrackKind] = TrackKind.VIIBR
    code: str
    url: str

    def as_track(self, song: Track) -> Track:
        """The song this link names, shown with the link as it was posted."""
        return Track(song.kind, song.key, self.url)


_UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# Any letter, Unicode ones too, so a link run into one is not a link.
_END = r"(?!(?u:\w)|-)"
_TAIL = re.compile(r"/?(?:[?#].*)?")
# Hosts and paths are ASCII only, so Unicode case folding (such as "ſ" for
# "s") never lets a non-ASCII URL pass for a link.
_FLAGS = re.IGNORECASE | re.ASCII


def _track(kind: TrackKind) -> Callable[[re.Match[str]], Track]:
    """Build a track of `kind`: UUIDs lowercased, shortcodes kept as written."""

    def build(match: re.Match[str]) -> Track:
        uuid = match.groupdict().get("uuid")
        ident = uuid.lower() if uuid else match["code"]
        return Track(kind, f"{kind}:{ident}", match[0])

    return build


def _share_link(match: re.Match[str]) -> ShareLink:
    return ShareLink(match["code"], match[0])


_PATTERNS: tuple[
    tuple[Callable[[re.Match[str]], Track | ShareLink], re.Pattern[str]], ...
] = (
    (
        _track(TrackKind.VIIBR),
        re.compile(
            rf"https://(?:www\.)?viibrmusic\.com/songs/(?P<uuid>{_UUID}){_END}",
            _FLAGS,
        ),
    ),
    (
        _share_link,
        re.compile(
            rf"https://(?:www\.)?viibrmusic\.com/s/(?P<code>[0-9a-z]+){_END}",
            _FLAGS,
        ),
    ),
    (
        _track(TrackKind.SUNO),
        re.compile(
            rf"https://(?:suno\.com|app\.suno\.ai)/song/(?P<uuid>{_UUID}){_END}",
            _FLAGS,
        ),
    ),
    (
        _track(TrackKind.SUNO),
        re.compile(
            rf"https://suno\.com/s/(?P<code>[0-9a-z]+){_END}",
            _FLAGS,
        ),
    ),
)


def find_track(text: str) -> Track | ShareLink | None:
    """Return the first valid track or share link in ``text``, or None.

    UUIDs are lowercased in the key; Suno and viibrmusic.com shortcodes are
    case-sensitive and kept exactly as written.
    """
    matches = [
        (match.start(), build, match)
        for build, pattern in _PATTERNS
        if (match := pattern.search(text))
    ]
    if not matches:
        return None
    _, build, match = min(matches, key=lambda found: found[0])
    return build(match)


def whole_link(url: str) -> Track | ShareLink | None:
    """Return the track or share link that ``url`` is, or None.

    The link must be the whole URL; only a trailing slash, query or fragment
    may follow it.
    """
    found = find_track(url)
    if found is None or not url.startswith(found.url):
        return None
    return found if _TAIL.fullmatch(url[len(found.url) :]) else None
