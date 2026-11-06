"""Storage for drawings: every picture Wisp made for a member, and why."""

from datetime import datetime

from db.activity import utc_day
from db.database import Database, to_db_time


class DrawingRepo:
    """Reads and writes the drawings Wisp made. Every guild has its own.

    The daily caps and the "once a day" reasons are worked out from these rows,
    so they survive a restart.
    """

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        guild_id: int,
        user_id: int,
        life_id: int,
        reason: str,
        message_id: int,
        at: datetime,
    ) -> None:
        """Record a drawing that was posted, for the life that made it."""
        await self._db.insert(
            f"INSERT INTO {self._db.t('drawings')} "
            "(guild_id, user_id, life_id, reason, message_id, at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (guild_id, user_id, life_id, reason, message_id, to_db_time(at)),
        )

    async def count_today(self, guild_id: int, now: datetime) -> int:
        """Drawings made for the whole server on the UTC day of `now`."""
        return await self._count_on_day("", now, guild_id)

    async def count_today_for(self, guild_id: int, user_id: int, now: datetime) -> int:
        """Drawings made for one member on the UTC day of `now`."""
        return await self._count_on_day("AND user_id = %s ", now, guild_id, user_id)

    async def reason_made_today(
        self, guild_id: int, reason: str, now: datetime
    ) -> bool:
        """Whether a drawing for `reason` was made on the UTC day of `now`."""
        return bool(await self._count_on_day("AND reason = %s ", now, guild_id, reason))

    async def count_for(self, guild_id: int, user_id: int) -> int:
        """Every drawing Wisp has made for one member."""
        row = await self._db.fetchone(
            f"SELECT COUNT(*) AS drawings FROM {self._db.t('drawings')} "
            "WHERE guild_id = %s AND user_id = %s",
            (guild_id, user_id),
        )
        assert row is not None
        return int(row["drawings"])

    async def _count_on_day(
        self, extra: str, now: datetime, guild_id: int, *match: int | str
    ) -> int:
        """Count one guild's drawings on the UTC day of `now`.

        `extra` is more `AND` conditions, ending in a space, whose
        placeholders `match` fills.
        """
        start, end = utc_day(now)
        row = await self._db.fetchone(
            f"SELECT COUNT(*) AS drawings FROM {self._db.t('drawings')} "
            f"WHERE guild_id = %s {extra}AND at >= %s AND at < %s",
            (guild_id, *match, start, end),
        )
        assert row is not None
        return int(row["drawings"])
