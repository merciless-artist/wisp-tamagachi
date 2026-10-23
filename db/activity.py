"""Storage for feeds, interactions, snack inventory and the daily counts."""

from datetime import UTC, datetime, timedelta
from enum import StrEnum

import pymysql
from pymysql.constants import ER

from db.database import Database, to_db_time
from wisp.links import Track


class InteractionKind(StrEnum):
    """What a member did with Wisp. FEED and GIFT are not casual play."""

    FEED = "feed"
    SNACK = "snack"
    FREE_SNACK = "free"
    PLAY = "play"
    GIFT = "gift"


_CASUAL = (InteractionKind.SNACK, InteractionKind.FREE_SNACK, InteractionKind.PLAY)


def utc_day(now: datetime) -> tuple[datetime, datetime]:
    """The naive UTC bounds [midnight, next midnight) of the day containing `now`."""
    start = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return to_db_time(start), to_db_time(start + timedelta(days=1))


class ActivityRepo:
    """Reads and writes everything members do with Wisp."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def record_feed(
        self,
        guild_id: int,
        life_id: int,
        user_id: int,
        track: Track,
        meal_points: int,
        message_id: int,
        at: datetime,
    ) -> bool:
        """Record a track feed; False when the guild already fed that track."""
        try:
            await self._db.insert(
                f"INSERT INTO {self._db.t('feeds')} (guild_id, life_id, user_id, "
                "track_key, url, meal_points, message_id, fed_at) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    guild_id,
                    life_id,
                    user_id,
                    track.key,
                    track.url,
                    meal_points,
                    message_id,
                    to_db_time(at),
                ),
            )
        except pymysql.err.IntegrityError as error:
            if error.args[0] != ER.DUP_ENTRY:
                raise
            return False
        return True

    async def record_interaction(
        self,
        guild_id: int,
        life_id: int,
        user_id: int,
        kind: InteractionKind,
        bond: int,
        meal_points: int,
        at: datetime,
    ) -> None:
        """Record something a member did with Wisp and what it earned."""
        await self._db.insert(
            f"INSERT INTO {self._db.t('interactions')} (guild_id, life_id, user_id, "
            "kind, bond, meal_points, at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (guild_id, life_id, user_id, kind.value, bond, meal_points, to_db_time(at)),
        )

    async def meal_points_today(
        self, guild_id: int, user_id: int, now: datetime
    ) -> int:
        """Meal points the member has given Wisp on the UTC day of `now`."""
        return await self._sum_today(
            "meal_points", tuple(InteractionKind), guild_id, user_id, now
        )

    async def casual_bond_today(
        self, guild_id: int, user_id: int, now: datetime
    ) -> int:
        """Bond earned from snacks and play on the UTC day of `now`."""
        return await self._sum_today("bond", _CASUAL, guild_id, user_id, now)

    async def distinct_days(self, guild_id: int, user_id: int) -> int:
        """Number of different UTC days the member has interacted with Wisp."""
        row = await self._db.fetchone(
            f"SELECT COUNT(DISTINCT DATE(at)) AS days "
            f"FROM {self._db.t('interactions')} WHERE guild_id = %s AND user_id = %s",
            (guild_id, user_id),
        )
        assert row is not None
        return int(row["days"])

    async def people_since(self, guild_id: int, since: datetime) -> int:
        """Number of different members who interacted with Wisp since `since`."""
        row = await self._db.fetchone(
            f"SELECT COUNT(DISTINCT user_id) AS people FROM "
            f"{self._db.t('interactions')} WHERE guild_id = %s AND at >= %s",
            (guild_id, to_db_time(since)),
        )
        assert row is not None
        return int(row["people"])

    async def caretakers(self, guild_id: int, life_id: int, since: datetime) -> int:
        """Number of different members who cared for one life since `since`."""
        row = await self._db.fetchone(
            f"SELECT COUNT(DISTINCT user_id) AS people FROM "
            f"{self._db.t('interactions')} "
            "WHERE guild_id = %s AND life_id = %s AND at >= %s",
            (guild_id, life_id, to_db_time(since)),
        )
        assert row is not None
        return int(row["people"])

    async def top_this_life(
        self, guild_id: int, life_id: int, limit: int
    ) -> list[tuple[int, int]]:
        """Return (user_id, meal points fed) for one life, biggest feeders first."""
        rows = await self._db.fetchall(
            f"SELECT user_id, SUM(meal_points) AS points FROM {self._db.t('feeds')} "
            "WHERE guild_id = %s AND life_id = %s GROUP BY user_id "
            "ORDER BY points DESC, user_id LIMIT %s",
            (guild_id, life_id, limit),
        )
        return [(row["user_id"], int(row["points"])) for row in rows]

    async def inventory(self, guild_id: int, user_id: int) -> dict[str, int]:
        """Return the snacks the member owns, keyed by snack, never zero."""
        rows = await self._db.fetchall(
            f"SELECT snack, qty FROM {self._db.t('inventory')} "
            "WHERE guild_id = %s AND user_id = %s AND qty > 0",
            (guild_id, user_id),
        )
        return {row["snack"]: row["qty"] for row in rows}

    async def add_snack(
        self, guild_id: int, user_id: int, snack: str, quantity: int = 1
    ) -> None:
        """Add snacks to the member's inventory."""
        await self._db.execute(
            f"INSERT INTO {self._db.t('inventory')} (guild_id, user_id, snack, qty) "
            "VALUES (%s, %s, %s, %s) ON DUPLICATE KEY UPDATE qty = qty + %s",
            (guild_id, user_id, snack, quantity, quantity),
        )

    async def take_snack(self, guild_id: int, user_id: int, snack: str) -> bool:
        """Take one snack from the inventory; False when the member has none."""
        changed = await self._db.execute(
            f"UPDATE {self._db.t('inventory')} SET qty = qty - 1 "
            "WHERE guild_id = %s AND user_id = %s AND snack = %s AND qty > 0",
            (guild_id, user_id, snack),
        )
        return changed == 1

    async def free_snack_used_today(
        self, guild_id: int, user_id: int, now: datetime
    ) -> bool:
        """Whether the member has had today's free snack on the UTC day of `now`."""
        return bool(
            await self._count_today(InteractionKind.FREE_SNACK, guild_id, user_id, now)
        )

    async def plays_today(self, guild_id: int, user_id: int, now: datetime) -> int:
        """Games the member has played with Wisp on the UTC day of `now`."""
        return await self._count_today(InteractionKind.PLAY, guild_id, user_id, now)

    async def _count_today(
        self, kind: InteractionKind, guild_id: int, user_id: int, now: datetime
    ) -> int:
        start, end = utc_day(now)
        row = await self._db.fetchone(
            f"SELECT COUNT(*) AS times FROM {self._db.t('interactions')} "
            "WHERE guild_id = %s AND user_id = %s AND kind = %s "
            "AND at >= %s AND at < %s",
            (guild_id, user_id, kind.value, start, end),
        )
        assert row is not None
        return int(row["times"])

    async def _sum_today(
        self,
        column: str,
        kinds: tuple[InteractionKind, ...],
        guild_id: int,
        user_id: int,
        now: datetime,
    ) -> int:
        start, end = utc_day(now)
        marks = ", ".join(["%s"] * len(kinds))
        row = await self._db.fetchone(
            f"SELECT COALESCE(SUM({column}), 0) AS total FROM "
            f"{self._db.t('interactions')} WHERE guild_id = %s AND user_id = %s "
            f"AND at >= %s AND at < %s AND kind IN ({marks})",
            (guild_id, user_id, start, end, *(kind.value for kind in kinds)),
        )
        assert row is not None
        return int(row["total"])
