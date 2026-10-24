"""Resolving viibrmusic.com share links to the songs they name."""

from collections.abc import Mapping
from datetime import timedelta
from typing import Final

import aiohttp
from yarl import URL

from wisp.links import ShareLink, Track, TrackKind, whole_link
from wisp.rules import VIIBR_RESOLVE_TIMEOUT

_APEX: Final = "viibrmusic.com"
_WWW: Final = "www.viibrmusic.com"
_USER_AGENT: Final = "WispBot/1.0"


class ShareLinkResolver:
    """Asks viibrmusic.com which song a share link names.

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

    async def close(self) -> None:
        """Close the HTTP session if one is open."""
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
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self._timeout.total_seconds()),
                headers={"User-Agent": _USER_AGENT},
            )
        return self._session
