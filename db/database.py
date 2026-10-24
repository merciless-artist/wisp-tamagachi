"""Async MySQL access through an aiomysql connection pool."""

import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Final, TypeVar, overload

import aiomysql
import pymysql
from pymysql.constants import CR

import config

log = logging.getLogger("wisp")

Params = Sequence[Any]
Row = dict[str, Any]
_T = TypeVar("_T")

# The network path to the server drops idle connections after a few minutes,
# so a connection idle this long is replaced before it is used.
POOL_RECYCLE_SECONDS: Final = 240
_LOST_CONNECTION: Final = frozenset({CR.CR_SERVER_GONE_ERROR, CR.CR_SERVER_LOST})
_CONNECTION_ERRORS: Final = (pymysql.err.OperationalError, pymysql.err.InterfaceError)


def _lost_connection(error: pymysql.err.MySQLError) -> bool:
    """Whether `error` says the connection to the server was lost."""
    return bool(error.args) and error.args[0] in _LOST_CONNECTION


@overload
def to_db_time(moment: datetime) -> datetime: ...


@overload
def to_db_time(moment: None) -> None: ...


def to_db_time(moment: datetime | None) -> datetime | None:
    """Convert a timezone-aware datetime to the naive UTC the database stores.

    Columns hold whole seconds, so the fraction is dropped here rather than left
    to the server, which may round it into the next second or day.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        raise ValueError("Datetime must be timezone-aware")
    return moment.astimezone(UTC).replace(tzinfo=None, microsecond=0)


@overload
def from_db_time(moment: datetime) -> datetime: ...


@overload
def from_db_time(moment: None) -> None: ...


def from_db_time(moment: datetime | None) -> datetime | None:
    """Mark a naive datetime read from the database as UTC."""
    return None if moment is None else moment.replace(tzinfo=UTC)


class Database:
    """A connection pool plus the table prefix every query must use."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._pool: Any = None

    async def connect(self) -> None:
        """Open the pool. Every connection autocommits in UTC.

        A connection idle for POOL_RECYCLE_SECONDS is replaced before use.
        """
        self._pool = await aiomysql.create_pool(
            **config.MYSQL,
            charset="utf8mb4",
            autocommit=True,
            init_command="SET time_zone = '+00:00'",
            cursorclass=aiomysql.DictCursor,
            minsize=1,
            maxsize=5,
            pool_recycle=POOL_RECYCLE_SECONDS,
        )

    async def close(self) -> None:
        """Close the pool and wait for its connections to finish. Safe to repeat."""
        if self._pool is None:
            return
        pool, self._pool = self._pool, None
        pool.close()
        await pool.wait_closed()

    def t(self, name: str) -> str:
        """Return the prefixed name of a table."""
        return f"{self._prefix}{name}"

    async def execute(self, query: str, params: Params = ()) -> int:
        """Run a statement and return the number of affected rows.

        Never retried: a write may have been applied before its connection was
        lost.
        """

        async def rowcount(cur: Any) -> int:
            return int(cur.rowcount)

        return await self._run(query, params, rowcount)

    async def insert(self, query: str, params: Params = ()) -> int:
        """Run an INSERT and return the generated auto-increment id.

        Never retried, like `execute`.
        """

        async def lastrowid(cur: Any) -> int:
            return int(cur.lastrowid)

        return await self._run(query, params, lastrowid)

    async def fetchone(self, query: str, params: Params = ()) -> Row | None:
        """Return the first row of a query, or None when there is none."""

        async def first(cur: Any) -> Row | None:
            row: Row | None = await cur.fetchone()
            return row

        return await self._read(query, params, first)

    async def fetchall(self, query: str, params: Params = ()) -> list[Row]:
        """Return every row of a query."""

        async def every(cur: Any) -> list[Row]:
            return list(await cur.fetchall())

        return await self._read(query, params, every)

    async def _read(
        self, query: str, params: Params, result: Callable[[Any], Awaitable[_T]]
    ) -> _T:
        """Run a read, once more on another connection if the first one was lost."""
        try:
            return await self._run(query, params, result)
        except _CONNECTION_ERRORS as error:
            if not _lost_connection(error):
                raise
            log.warning("Retrying a read after a lost database connection: %s", error)
            return await self._run(query, params, result)

    async def _run(
        self, query: str, params: Params, result: Callable[[Any], Awaitable[_T]]
    ) -> _T:
        """Run one query on a pooled connection and read `result` off its cursor.

        A lost connection is closed, so the pool discards it instead of handing
        it out again.
        """
        async with self._pool.acquire() as conn:
            try:
                async with conn.cursor() as cur:
                    await cur.execute(query, params)
                    return await result(cur)
            except _CONNECTION_ERRORS as error:
                if _lost_connection(error):
                    conn.close()
                raise
