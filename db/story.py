"""Storage for Wisp's life story: the moments of each life worth remembering."""

from collections.abc import Sequence

from db.database import Database, from_db_time, to_db_time
from wisp.rules import LIFE_STORY_ENTRIES, Stage
from wisp.story import Entry, EntryKind


class LifeStoryRepo:
    """Reads and writes the moments saved for each of Wisp's lives."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, guild_id: int, life_id: int, entries: Sequence[Entry]) -> None:
        """Save moments of a life, in the order given."""
        for entry in entries:
            await self._db.insert(
                f"INSERT INTO {self._db.t('life_story')} "
                "(guild_id, life_id, kind, stage, member_id, at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    guild_id,
                    life_id,
                    entry.kind.value,
                    entry.stage.value,
                    entry.member_id,
                    to_db_time(entry.at),
                ),
            )

    async def recent(self, guild_id: int, life_id: int) -> list[Entry]:
        """Return the newest LIFE_STORY_ENTRIES moments of a life, oldest first."""
        rows = await self._db.fetchall(
            "SELECT kind, stage, member_id, at "
            f"FROM {self._db.t('life_story')} "
            "WHERE guild_id = %s AND life_id = %s "
            "ORDER BY at DESC, id DESC LIMIT %s",
            (guild_id, life_id, LIFE_STORY_ENTRIES),
        )
        return [
            Entry(
                EntryKind(row["kind"]),
                Stage(row["stage"]),
                row["member_id"],
                from_db_time(row["at"]),
            )
            for row in reversed(rows)
        ]
