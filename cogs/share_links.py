"""Asking viibrmusic.com which song a share link names, and what it is called."""

import asyncio
import json
from collections.abc import Iterator, Mapping
from datetime import timedelta
from html.parser import HTMLParser
from typing import Final

import aiohttp
from yarl import URL

from wisp.links import ShareLink, Track, TrackKind, whole_link
from wisp.rules import SONG_TITLE_LIMIT, VIIBR_RESOLVE_TIMEOUT

_APEX: Final = "viibrmusic.com"
_WWW: Final = "www.viibrmusic.com"
_USER_AGENT: Final = "WispBot/1.0"
_JSON_LD: Final = "application/ld+json"
_RECORDING: Final = "MusicRecording"

# ---
# Reading a song page
# ---


class _JsonLdBlocks(HTMLParser):
    """Collects the text of every JSON-LD script on a page, in order."""

    def __init__(self) -> None:
        super().__init__()
        self.blocks: list[str] = []
        self._inside = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        kind = (dict(attrs).get("type") or "").strip().lower()
        if tag == "script" and kind == _JSON_LD:
            self._inside = True
            self.blocks.append("")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._inside = False

    def handle_data(self, data: str) -> None:
        if self._inside:
            self.blocks[-1] += data


def _recordings(node: object) -> Iterator[dict[str, object]]:
    """Every MusicRecording in a JSON-LD value, its `@graph` searched too."""
    if isinstance(node, list):
        for item in node:
            yield from _recordings(item)
        return
    if not isinstance(node, dict):
        return
    kind = node.get("@type")
    if kind == _RECORDING or (isinstance(kind, list) and _RECORDING in kind):
        yield node
    yield from _recordings(node.get("@graph"))


def recording_name(page: str) -> str:
    """The song's name in a page's JSON-LD MusicRecording, or "" with none.

    Its whitespace is collapsed and it is cut to `SONG_TITLE_LIMIT`
    characters. A JSON-LD block that is not valid JSON is passed over.
    """
    parser = _JsonLdBlocks()
    parser.feed(page)
    parser.close()
    for block in parser.blocks:
        try:
            found = json.loads(block)
        except json.JSONDecodeError:
            continue
        for song in _recordings(found):
            name = song.get("name")
            if isinstance(name, str) and (words := " ".join(name.split())):
                return words[:SONG_TITLE_LIMIT].strip()
    return ""


def _song_page(song: Track) -> str:
    """The page of a viibrmusic.com song, on the bare domain."""
    return f"https://{_APEX}/songs/{song.key.removeprefix(f'{TrackKind.VIIBR}:')}"


# ---
# The resolver
# ---


class ShareLinkResolver:
    """Asks viibrmusic.com which song a share link names, and a song's name.

    The site answers a share link with a redirect to the song's page, or 404
    for a code it does not know. Redirects are read, not followed, apart from
    one hop from www.viibrmusic.com to viibrmusic.com. The HTTP session is
    opened on first use and closed by `close`.

    `origins` maps a viibrmusic.com host to the address it is reached at, so
    tests can stand in a local server; any other host is reached as written.
    """

    def __init__(
        self,
        *,
        origins: Mapping[str, str] | None = None,
        timeout: timedelta = VIIBR_RESOLVE_TIMEOUT,
    ) -> None:
        self._origins = dict(origins or {})
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._closed = False

    async def resolve(self, link: ShareLink) -> Track | None:
        """Return the song `link` names, shown as posted, or None if it names none.

        Raises:
            aiohttp.ClientError: viibrmusic.com could not be reached.
            TimeoutError: viibrmusic.com did not answer in time.
        """
        target = await self._redirect(link.url)
        if (
            isinstance(target, ShareLink)
            and target.code == link.code
            and URL(link.url).host == _WWW
            and URL(target.url).host == _APEX
        ):
            target = await self._redirect(target.url)
        if isinstance(target, Track) and target.kind is TrackKind.VIIBR:
            return link.as_track(target)
        return None

    async def song_title(self, url: str) -> str | None:
        """The name of the song at `url`, read from its page, or "" with none.

        `url` is a song's link or a share link, which is read at the song page
        it redirects to. The name is the page's JSON-LD MusicRecording name,
        as `recording_name` reads it; a link that names no viibrmusic.com
        song, a page the site does not have and a page with no name all give
        "". Returns None when the page could not be read: the site could not
        be reached, answered with an error, or took longer than the timeout
        for the whole read.
        """
        try:
            async with asyncio.timeout(self._timeout.total_seconds()):
                return await self._read_title(url)
        except (aiohttp.ClientError, TimeoutError):
            return None

    async def close(self) -> None:
        """Close the HTTP session if one is open, and open no other."""
        self._closed = True
        if self._session is not None and not self._session.closed:
            await self._session.close()

    async def _redirect(self, url: str) -> Track | ShareLink | None:
        """Where a share link redirects to, when that is a track or share link.

        A redirect whose address cannot be parsed names no song.
        """
        async with self._open().get(
            self._address(url), allow_redirects=False
        ) as response:
            location = response.headers.get("Location")
            if location is None or not 300 <= response.status < 400:
                return None
        try:
            target = URL(url).join(URL(location))
        except ValueError:
            return None
        return whole_link(str(target))

    async def _read_title(self, url: str) -> str | None:
        """`song_title` without its timeout and with its errors raised."""
        found = whole_link(url)
        song = await self.resolve(found) if isinstance(found, ShareLink) else found
        if song is None or song.kind is not TrackKind.VIIBR:
            return ""
        async with self._open().get(
            self._address(_song_page(song)), allow_redirects=False
        ) as response:
            if response.status == 404:
                return ""
            if response.status != 200:
                return None
            page = await response.text(errors="replace")
        return recording_name(page)

    def _address(self, url: str) -> str:
        """The address to request `url` at."""
        parsed = URL(url)
        origin = self._origins.get(parsed.host or "")
        return url if origin is None else str(URL(origin).join(parsed.relative()))

    def _open(self) -> aiohttp.ClientSession:
        """The shared session, opened on first use; none once the resolver is closed.

        Raises:
            aiohttp.ClientConnectionError: The resolver is closed for shutdown.
        """
        if self._closed:
            raise aiohttp.ClientConnectionError("the share link resolver is closed")
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout.total_seconds()),
                headers={"User-Agent": _USER_AGENT},
            )
        return self._session
