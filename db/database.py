"""Async MySQL access through an aiomysql connection pool."""

from collections.abc import Sequence
from typing import Any

import aiomysql

import config

Params = Sequence[Any]
Row = dict[str, Any]


class Database:
    """A connection pool plus the table prefix every query must use."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix
        self._pool: Any = None

    async def connect(self) -> None:
        """Open the pool. Every connection autocommits in UTC."""
        self._pool = await aiomysql.create_pool(
            **config.MYSQL,
            charset="utf8mb4",
            autocommit=True,
            init_command="SET time_zone = '+00:00'",
            cursorclass=aiomysql.DictCursor,
            minsize=1,
            maxsize=5,
        )

    async def close(self) -> None:
        """Close the pool and wait for its connections to finish."""
        self._pool.close()
        await self._pool.wait_closed()

    def t(self, name: str) -> str:
        """Return the prefixed name of a table."""
        return f"{self._prefix}{name}"

    async def execute(self, query: str, params: Params = ()) -> int:
        """Run a statement and return the number of affected rows."""
        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(query, params)
            return int(cur.rowcount)

    async def insert(self, query: str, params: Params = ()) -> int:
        """Run an INSERT and return the generated auto-increment id."""
        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(query, params)
            return int(cur.lastrowid)

    async def fetchone(self, query: str, params: Params = ()) -> Row | None:
        """Return the first row of a query, or None when there is none."""
        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(query, params)
            row: Row | None = await cur.fetchone()
            return row

    async def fetchall(self, query: str, params: Params = ()) -> list[Row]:
        """Return every row of a query."""
        async with self._pool.acquire() as conn, conn.cursor() as cur:
            await cur.execute(query, params)
            rows: list[Row] = list(await cur.fetchall())
            return rows
