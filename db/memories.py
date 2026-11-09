"""Wisp's long memory of his House: a ChromaDB folder, searched by meaning."""

import asyncio
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Any, Final

import chromadb
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from chromadb.errors import ChromaError

from wisp.memories import Found, Memory, MemoryStoreError
from wisp.rules import MEMORY_CANDIDATES

_COLLECTION: Final = "house_memories"


def _stamp(moment: datetime) -> int:
    return int(moment.timestamp())


def _moment(stamp: int) -> datetime:
    return datetime.fromtimestamp(stamp, UTC)


def _batch(embedding: Sequence[float]) -> Any:
    """`embedding` as a batch of one; ChromaDB's type hints reject a plain list."""
    return [list(embedding)]


def _metadata(guild_id: int, memory: Memory) -> dict[str, str | int]:
    return {
        "guild_id": guild_id,
        "member_id": memory.member_id,
        "life_id": memory.life_id,
        "life_version": memory.life_version,
        "reply": memory.reply,
        "at": _stamp(memory.at),
        "recalls": memory.recalls,
        "touched": _stamp(memory.touched),
    }


def _memory(said: str, metadata: Any) -> Memory:
    return Memory(
        member_id=metadata["member_id"],
        life_id=metadata["life_id"],
        life_version=metadata["life_version"],
        said=said,
        reply=metadata["reply"],
        at=_moment(metadata["at"]),
        recalls=metadata["recalls"],
        touched=_moment(metadata["touched"]),
    )


class MemoryStore:
    """Saves and searches what was said to Wisp, tagged by member and by life.

    Every life's memories stay, since a fire sprite remembers past lives. All
    of ChromaDB's work runs on one thread of its own, so it never holds up the
    bot and never overlaps itself. Every way it can fail is a MemoryStoreError.
    """

    def __init__(self, path: str) -> None:
        self._path = path
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="memory")
        self._collection: Collection | None = None
        self._closed = False

    async def open(self) -> None:
        """Open the folder, creating it and the collection the first time."""
        await self._run(self._connect)

    async def close(self) -> None:
        """Take no more work and let the work under way finish."""
        self._closed = True
        await asyncio.to_thread(self._pool.shutdown)

    async def count(self) -> int:
        """How many memories he has, from every server and life."""
        return await self._run(lambda: self._memories().count())

    async def add(
        self, guild_id: int, key: str, memory: Memory, embedding: Sequence[float]
    ) -> None:
        """Save a memory under `key`, with the embedding of its meaning."""
        await self._run(
            lambda: self._memories().add(
                ids=[key],
                embeddings=_batch(embedding),
                documents=[memory.said],
                metadatas=[_metadata(guild_id, memory)],
            )
        )

    async def from_member(
        self,
        guild_id: int,
        member_id: int,
        embedding: Sequence[float],
        before: datetime,
    ) -> list[Found]:
        """The closest things this member said to him before `before`."""
        return await self._search(guild_id, embedding, before, {"member_id": member_id})

    async def from_house(
        self,
        guild_id: int,
        embedding: Sequence[float],
        before: datetime,
        excluding: int | None = None,
    ) -> list[Found]:
        """The closest things said to him before `before`, leaving out one member."""
        who = None if excluding is None else {"member_id": {"$ne": excluding}}
        return await self._search(guild_id, embedding, before, who)

    async def recalled(self, found: Sequence[Found], now: datetime) -> None:
        """Strengthen memories that just came back to him."""
        if not found:
            return
        await self._run(
            lambda: self._memories().update(
                ids=[item.key for item in found],
                metadatas=[
                    {"recalls": item.memory.recalls + 1, "touched": _stamp(now)}
                    for item in found
                ],
            )
        )

    async def _search(
        self,
        guild_id: int,
        embedding: Sequence[float],
        before: datetime,
        who: dict[str, Any] | None,
    ) -> list[Found]:
        clauses: list[dict[str, Any]] = [
            {"guild_id": guild_id},
            {"at": {"$lt": _stamp(before)}},
        ]
        if who is not None:
            clauses.append(who)
        result: Any = await self._run(
            lambda: self._memories().query(
                query_embeddings=_batch(embedding),
                n_results=MEMORY_CANDIDATES,
                where={"$and": clauses},
                include=["documents", "metadatas", "distances"],
            )
        )
        return [
            Found(key, _memory(said, metadata), 1 - distance)
            for key, said, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            )
        ]

    def _connect(self) -> None:
        client = chromadb.PersistentClient(
            path=self._path, settings=Settings(anonymized_telemetry=False)
        )
        self._collection = client.get_or_create_collection(
            _COLLECTION,
            embedding_function=None,
            configuration={"hnsw": {"space": "cosine"}},
        )

    def _memories(self) -> Collection:
        if self._collection is None:
            raise MemoryStoreError("not open")
        return self._collection

    async def _run[T](self, work: Callable[[], T]) -> T:
        if self._closed:
            raise MemoryStoreError("closed for shutdown")
        try:
            return await asyncio.get_running_loop().run_in_executor(self._pool, work)
        except (ChromaError, OSError) as error:
            raise MemoryStoreError(f"{type(error).__name__}: {error}") from error
