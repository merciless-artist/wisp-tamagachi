"""Storage for magazines: the Rockstar covers members bought, per Wisp life."""

from dataclasses import dataclass
from datetime import datetime

import pymysql
from pymysql.constants import ER

from db.database import Database, from_db_time, to_db_time


@dataclass(frozen=True)
class OwnedMagazine:
    """A magazine a member bought: which, for which Wisp version, and when."""

    magazine: str
    version: int
    bought_at: datetime


class MagazineRepo:
    """Reads and writes magazine purchases. Each is one per member per life."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record(
        self,
        guild_id: int,
        user_id: int,
        magazine: str,
        life_id: int,
        version: int,
        at: datetime,
    ) -> bool:
        """Record a magazine bought for one life; False when it was bought already."""
        try:
            await self._db.insert(
                f"INSERT INTO {self._db.t('magazines')} "
                "(guild_id, user_id, magazine, life_id, version, bought_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (guild_id, user_id, magazine, life_id, version, to_db_time(at)),
            )
        except pymysql.err.IntegrityError as error:
            if error.args[0] != ER.DUP_ENTRY:
                raise
            return False
        return True

    async def owned(self, guild_id: int, user_id: int, life_id: int) -> set[str]:
        """Return the magazines the member bought for one life."""
        rows = await self._db.fetchall(
            f"SELECT magazine FROM {self._db.t('magazines')} "
            "WHERE guild_id = %s AND user_id = %s AND life_id = %s",
            (guild_id, user_id, life_id),
        )
        return {row["magazine"] for row in rows}

    async def of(self, guild_id: int, user_id: int) -> list[OwnedMagazine]:
        """Return every magazine the member ever bought, newest Wisp version first.

        Within a version they come newest purchase first.
        """
        rows = await self._db.fetchall(
            f"SELECT magazine, version, bought_at FROM {self._db.t('magazines')} "
            "WHERE guild_id = %s AND user_id = %s "
            "ORDER BY version DESC, bought_at DESC, magazine",
            (guild_id, user_id),
        )
        return [
            OwnedMagazine(
                row["magazine"], row["version"], from_db_time(row["bought_at"])
            )
            for row in rows
        ]
