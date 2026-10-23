from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

import app
from ai.chain import AIChain
from db.database import Database
from db.schema import TABLES, create_tables

TEST_PREFIX = "wisptest_"


@pytest.fixture(autouse=True)
def no_ai_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every WispBot built in a test an AI chain with no providers.

    That chain raises AllProvidersFailed at once, so no test can reach a real
    provider with the real keys. Tests that need answers fake `bot.ai.complete`.
    `ai.chain.chain_from_config` itself is untouched.
    """
    monkeypatch.setattr(app, "chain_from_config", lambda: AIChain([]))


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
