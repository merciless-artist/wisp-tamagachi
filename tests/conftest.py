from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

import app
from ai.chain import AIChain
from ai.embedding import Embedder
from ai.images import ImageMaker
from ai.vision import Vision
from db.database import Database
from db.memories import MemoryStore
from db.schema import TABLES, create_tables

TEST_PREFIX = "wisptest_"


@pytest.fixture(autouse=True)
def no_ai_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every WispBot built in a test an AI chain with no providers.

    That chain raises AllProvidersFailed at once, so no test can reach a real
    provider with the real keys. Tests that need answers fake `bot.ai.complete`;
    the vision model gets no key and the image maker no address, so they ask
    nothing either.
    `ai.chain.chain_from_config` itself is untouched.
    """
    monkeypatch.setattr(app, "chain_from_config", lambda: AIChain([]))
    monkeypatch.setattr(app, "vision_from_config", lambda: Vision("none", None))
    monkeypatch.setattr(app, "images_from_config", lambda: ImageMaker(None))


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


def _meaning(text: str) -> list[float]:
    """A stand-in embedding: one direction per topic, so topics are far apart."""
    lowered = text.lower()
    topics = [float(topic in lowered) for topic in ("dog", "album", "pickle")]
    return [*topics, 0.01]


@pytest.fixture
def embedder() -> AsyncMock:
    """A stand-in for Gemini's embeddings that tells topics apart."""
    fake = AsyncMock(spec=Embedder)
    fake.for_search.side_effect = _meaning
    fake.for_saving.side_effect = _meaning
    return fake


@pytest_asyncio.fixture
async def long_memory(tmp_path: Path) -> AsyncIterator[MemoryStore]:
    """A real ChromaDB memory in a folder of its own."""
    store = MemoryStore(str(tmp_path / "memory"))
    await store.open()
    try:
        yield store
    finally:
        await store.close()
