"""Tests for the connection pool's handling of dropped connections.

The database is real. Only the first cursor `execute` of a test is rigged to
fail, the way a connection the network dropped fails mid-query.
"""

from typing import Any

import aiomysql
import pymysql
import pytest

from db.database import POOL_RECYCLE_SECONDS, Database

GUILD = 100
LOST = pymysql.err.OperationalError(
    2013, "Lost connection to MySQL server during query"
)
GONE = pymysql.err.OperationalError(2006, "MySQL server has gone away")
LOST_INTERFACE = pymysql.err.InterfaceError(2013, "Lost connection")


def fail_first_execute(
    monkeypatch: pytest.MonkeyPatch, error: pymysql.err.MySQLError
) -> list[Any]:
    """Make the next cursor `execute` raise `error`; later ones run for real.

    Returns the connection behind each attempt, in order.
    """
    real = aiomysql.DictCursor.execute
    connections: list[Any] = []

    async def execute(cursor: Any, query: str, args: Any = None) -> Any:
        connections.append(cursor.connection)
        if len(connections) == 1:
            raise error
        return await real(cursor, query, args)

    monkeypatch.setattr(aiomysql.DictCursor, "execute", execute)
    return connections


async def stored(db: Database) -> int:
    row = await db.fetchone(
        f"SELECT COUNT(*) AS stored FROM {db.t('expression_uses')} WHERE guild_id = %s",
        (GUILD,),
    )
    assert row is not None
    return int(row["stored"])


def test_idle_connections_are_recycled_before_the_tick_comes_round() -> None:
    assert POOL_RECYCLE_SECONDS == 240


@pytest.mark.parametrize("error", [LOST, GONE, LOST_INTERFACE])
async def test_fetchone_retries_once_on_a_fresh_connection(
    db: Database, monkeypatch: pytest.MonkeyPatch, error: pymysql.err.MySQLError
) -> None:
    connections = fail_first_execute(monkeypatch, error)

    assert await db.fetchone("SELECT 1 AS one") == {"one": 1}

    first, retry = connections
    assert first.closed
    assert retry is not first


async def test_fetchall_retries_once_on_a_fresh_connection(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    connections = fail_first_execute(monkeypatch, LOST)

    assert await db.fetchall("SELECT 1 AS one UNION SELECT 2") == [
        {"one": 1},
        {"one": 2},
    ]

    first, retry = connections
    assert first.closed
    assert retry is not first


async def test_a_read_that_fails_twice_raises(
    db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    async def execute(cursor: Any, query: str, args: Any = None) -> Any:
        nonlocal calls
        calls += 1
        raise LOST

    monkeypatch.setattr(aiomysql.DictCursor, "execute", execute)

    with pytest.raises(pymysql.err.OperationalError):
        await db.fetchone("SELECT 1 AS one")
    assert calls == 2


@pytest.mark.parametrize("method", ["execute", "insert"])
async def test_a_write_is_never_retried(
    db: Database, monkeypatch: pytest.MonkeyPatch, method: str
) -> None:
    connections = fail_first_execute(monkeypatch, LOST)

    with pytest.raises(pymysql.err.OperationalError) as raised:
        await getattr(db, method)(
            f"INSERT INTO {db.t('expression_uses')} (guild_id, name, uses) "
            "VALUES (%s, %s, %s)",
            (GUILD, "wisp_happy", 1),
        )

    assert raised.value is LOST
    (only,) = connections
    assert only.closed
    assert await stored(db) == 0


@pytest.mark.parametrize(
    "error",
    [
        pymysql.err.OperationalError(1205, "Lock wait timeout exceeded"),
        pymysql.err.InterfaceError(0, ""),
        pymysql.err.ProgrammingError(1064, "You have an error in your SQL syntax"),
    ],
)
async def test_other_errors_are_not_retried(
    db: Database, monkeypatch: pytest.MonkeyPatch, error: pymysql.err.MySQLError
) -> None:
    connections = fail_first_execute(monkeypatch, error)

    with pytest.raises(type(error)) as raised:
        await db.fetchone("SELECT 1 AS one")

    assert raised.value is error
    (only,) = connections
    assert not only.closed
