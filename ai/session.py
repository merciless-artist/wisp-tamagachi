"""The shared HTTP session of an AI client, opened on first use, closed once."""

from datetime import timedelta

import aiohttp


class SessionOwner:
    """Owns one lazily opened HTTP session whose requests all share a time limit.

    Once closed, it opens no other session, so a request still running at
    shutdown cannot leave one unclosed.
    """

    def __init__(self, timeout: timedelta) -> None:
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None
        self._closed = False

    async def close(self) -> None:
        """Close the HTTP session, if one was opened, and open no other."""
        self._closed = True
        session, self._session = self._session, None
        if session is not None:
            await session.close()

    def _open_session(self) -> aiohttp.ClientSession:
        """Return the shared session, opening it on first use.

        Its timeout applies to each request.
        """
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=self._timeout.total_seconds())
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self._session
