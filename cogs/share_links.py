"""Asking viibrmusic.com about songs: which song a share link names, and who
made a song."""

import json
import re
from collections.abc import Mapping
from datetime import timedelta
from http import HTTPStatus
from typing import Final

import aiohttp
from yarl import URL

from wisp.links import ShareLink, Track, TrackKind, song_page, whole_link
from wisp.rules import VIIBR_RESOLVE_TIMEOUT

_APEX: Final = "viibrmusic.com"
_WWW: Final = "www.viibrmusic.com"
_USER_AGENT: Final = "WispBot/1.0"
# The song page's schema.org description, which names the song's artist.
_LINKED_DATA: Final = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.DOTALL
)
# Answers that mean the song page is gone for good, so it names no artist.
_NO_PAGE: Final = frozenset({HTTPStatus.NOT_FOUND, HTTPStatus.GONE})


def one_line(text: str) -> str:
    """`text` with every run of whitespace, line breaks included, as one space."""
    return " ".join(text.split())


def artist_on_page(page: str) -> str | None:
    """The artist a song page's schema.org data names, or None when it names none.

    The name is put on one line, so it can never break a box line.
    """
    for found in _LINKED_DATA.finditer(page):
        try:
            data = json.loads(found[1])
        except ValueError:
            continue
        by = data.get("byArtist") if isinstance(data, dict) else None
        name = by.get("name") if isinstance(by, dict) else None
        if isinstance(name, str) and (artist := one_line(name)):
            return artist
    return None


class ShareLinkResolver:
    """Asks viibrmusic.com which song a share link names, and who made a song.

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

    async def artist(self, track_key: str) -> str | None:
        """The artist of the song with `track_key`, as its viibrmusic.com page
        names it.

        None when the key is not a viibrmusic.com song's, or its page is gone
        (404 or 410) or names no artist. The page is not followed anywhere
        else.

        Raises:
            aiohttp.ClientResponseError: viibrmusic.com gave any other answer
                than the page, such as a 5xx, 429 or 403, or a redirect.
            aiohttp.ClientError: viibrmusic.com could not be reached.
            TimeoutError: viibrmusic.com did not answer in time.
        """
        page = song_page(track_key)
        if page is None:
            return None
        async with self._open().get(
            self._address(page), allow_redirects=False
        ) as response:
            if response.status in _NO_PAGE:
                return None
            if response.status != HTTPStatus.OK:
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=response.status,
                    message=response.reason or "",
                    headers=response.headers,
                )
            return artist_on_page(await response.text(errors="replace"))

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
