"""Storage for badges: the badge roles in each guild and who bought which."""

from dataclasses import dataclass
from datetime import datetime

import pymysql
from pymysql.constants import ER

from db.database import Database, from_db_time, to_db_time


@dataclass(frozen=True)
class OwnedBadge:
    """A badge a member bought: which, for which Wisp version, and when."""

    badge: str
    version: int
    bought_at: datetime


class BadgeRepo:
    """Reads and writes badge roles and badge purchases. Purchases are per life."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def role_ids(self, guild_id: int) -> dict[str, int]:
        """Return the stored role id of each badge, keyed by badge."""
        rows = await self._db.fetchall(
            f"SELECT badge, role_id FROM {self._db.t('badge_roles')} "
            "WHERE guild_id = %s",
            (guild_id,),
        )
        return {row["badge"]: int(row["role_id"]) for row in rows}

    async def set_role(self, guild_id: int, badge: str, role_id: int) -> None:
        """Remember the role that is a badge, replacing any role stored before."""
        await self._db.execute(
            f"INSERT INTO {self._db.t('badge_roles')} (guild_id, badge, role_id) "
            "VALUES (%s, %s, %s) ON DUPLICATE KEY UPDATE role_id = VALUES(role_id)",
            (guild_id, badge, role_id),
        )

    async def record(
        self,
        guild_id: int,
        user_id: int,
        badge: str,
        life_id: int,
        version: int,
        at: datetime,
    ) -> bool:
        """Record a badge bought for one life; False when it was bought already."""
        try:
            await self._db.insert(
                f"INSERT INTO {self._db.t('badges')} "
                "(guild_id, user_id, badge, life_id, version, bought_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (guild_id, user_id, badge, life_id, version, to_db_time(at)),
            )
        except pymysql.err.IntegrityError as error:
            if error.args[0] != ER.DUP_ENTRY:
                raise
            return False
        return True

    async def forget(
        self, guild_id: int, user_id: int, badge: str, life_id: int
    ) -> None:
        """Delete one purchase, for a badge whose role could not be given."""
        await self._db.execute(
            f"DELETE FROM {self._db.t('badges')} WHERE guild_id = %s "
            "AND user_id = %s AND badge = %s AND life_id = %s",
            (guild_id, user_id, badge, life_id),
        )

    async def owned(self, guild_id: int, user_id: int, life_id: int) -> set[str]:
        """Return the badges the member bought for one life."""
        rows = await self._db.fetchall(
            f"SELECT badge FROM {self._db.t('badges')} "
            "WHERE guild_id = %s AND user_id = %s AND life_id = %s",
            (guild_id, user_id, life_id),
        )
        return {row["badge"] for row in rows}

    async def of(self, guild_id: int, user_id: int) -> list[OwnedBadge]:
        """Return every badge the member ever bought, newest Wisp version first.

        Within a version they come newest purchase first.
        """
        rows = await self._db.fetchall(
            f"SELECT badge, version, bought_at FROM {self._db.t('badges')} "
            "WHERE guild_id = %s AND user_id = %s "
            "ORDER BY version DESC, bought_at DESC, badge",
            (guild_id, user_id),
        )
        return [
            OwnedBadge(row["badge"], row["version"], from_db_time(row["bought_at"]))
            for row in rows
        ]

    async def buyers(self, guild_id: int, life_id: int) -> dict[int, set[str]]:
        """Return the badges bought for one life, keyed by the member who bought."""
        rows = await self._db.fetchall(
            f"SELECT user_id, badge FROM {self._db.t('badges')} "
            "WHERE guild_id = %s AND life_id = %s",
            (guild_id, life_id),
        )
        bought: dict[int, set[str]] = {}
        for row in rows:
            bought.setdefault(int(row["user_id"]), set()).add(row["badge"])
        return bought
