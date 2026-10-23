"""Storage for gifts: every gift members gave Wisp and whether he kept it.

Stock, the day's buys, the day's kept gift and finished collections are all
worked out from these attempts.
"""

from dataclasses import dataclass
from datetime import datetime

from db.activity import utc_day
from db.database import Database, Row, from_db_time, to_db_time

_SELECT = "SELECT gift, user_id, kept, at FROM"


@dataclass(frozen=True)
class GiftAttempt:
    """One gift a member gave Wisp: which, from whom, whether he kept it and when."""

    gift: str
    user_id: int
    kept: bool
    at: datetime


def _from_row(row: Row) -> GiftAttempt:
    return GiftAttempt(
        row["gift"], row["user_id"], bool(row["kept"]), from_db_time(row["at"])
    )


class GiftRepo:
    """Reads and writes gift attempts. Each life of each guild has its own."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        guild_id: int,
        life_id: int,
        user_id: int,
        gift: str,
        kept: bool,
        at: datetime,
    ) -> None:
        """Record a gift given to one life and whether he kept it."""
        await self._db.insert(
            f"INSERT INTO {self._db.t('gift_attempts')} "
            "(guild_id, life_id, user_id, gift, kept, at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (guild_id, life_id, user_id, gift, kept, to_db_time(at)),
        )

    async def kept(self, guild_id: int, life_id: int) -> list[GiftAttempt]:
        """Return the gifts this life kept, oldest first."""
        rows = await self._db.fetchall(
            f"{_SELECT} {self._db.t('gift_attempts')} "
            "WHERE guild_id = %s AND life_id = %s AND kept ORDER BY at, id",
            (guild_id, life_id),
        )
        return [_from_row(row) for row in rows]

    async def today(
        self, guild_id: int, life_id: int, now: datetime
    ) -> list[GiftAttempt]:
        """Return the gifts given to this life on the UTC day of `now`, oldest first."""
        start, end = utc_day(now)
        rows = await self._db.fetchall(
            f"{_SELECT} {self._db.t('gift_attempts')} "
            "WHERE guild_id = %s AND life_id = %s AND at >= %s AND at < %s "
            "ORDER BY at, id",
            (guild_id, life_id, start, end),
        )
        return [_from_row(row) for row in rows]
