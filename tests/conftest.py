from collections.abc import AsyncIterator

import pytest_asyncio

from db.database import Database
from db.schema import TABLES, create_tables

TEST_PREFIX = "wisptest_"


@pytest_asyncio.fixture(scope="session")
async def _database() -> AsyncIterator[Database]:
    database = Database(TEST_PREFIX)
    await database.connect()
    await create_tables(database)
    try:
        yield database
    finally:
        for name in TABLES:
            await database.execute(f"DROP TABLE IF EXISTS {database.t(name)}")
        await database.close()


@pytest_asyncio.fixture
async def db(_database: Database) -> Database:
    """The shared test database with every table emptied."""
    for name in TABLES:
        await _database.execute(f"TRUNCATE TABLE {_database.t(name)}")
    return _database
