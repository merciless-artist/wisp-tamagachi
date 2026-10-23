"""Storage for Wisp's lunchbox: his favorite songs and the expressions he uses."""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

import pymysql
from pymysql.constants import ER

from db.activity import utc_day
from db.database import Database, to_db_time
from wisp.links import TrackKind, find_track


@dataclass(frozen=True)
class Favorite:
    """The track Wisp kept as his favorite of one UTC day, and who fed it."""

    day: date
    user_id: int
    track_key: str
    url: str


class WispLunchboxRepo:
    """Reads and writes what Wisp keeps in his lunchbox. Every guild has its own."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def pick_favorite(
        self, guild_id: int, day: date, rng: random.Random, now: datetime
    ) -> Favorite | None:
        """Keep one of the day's viibrmusic.com feeds, chosen by `rng`, as his favorite.

        Returns None when the day already has a favorite or had no
        viibrmusic.com feeds. The (guild, day) key means a second pick for the
        same day, even one racing this one, keeps nothing.
        """
        favorites = self._db.t("favorites")
        picked = await self._db.fetchone(
            f"SELECT day FROM {favorites} WHERE guild_id = %s AND day = %s",
            (guild_id, day),
        )
        if picked is not None:
            return None
        start, end = utc_day(datetime.combine(day, time(), UTC))
        rows = await self._db.fetchall(
            f"SELECT user_id, track_key, url FROM {self._db.t('feeds')} "
            "WHERE guild_id = %s AND fed_at >= %s AND fed_at < %s ORDER BY id",
            (guild_id, start, end),
        )
        viibr = [
            row
            for row in rows
            if (track := find_track(row["url"])) is not None
            and track.kind is TrackKind.VIIBR
        ]
        if not viibr:
            return None
        chosen = rng.choice(viibr)
        try:
            await self._db.insert(
                f"INSERT INTO {favorites} "
                "(guild_id, day, user_id, track_key, url, picked_at) "
                "VALUES (%s, %s, %s, %s, %s, %s)",
                (
                    guild_id,
                    day,
                    chosen["user_id"],
                    chosen["track_key"],
                    chosen["url"],
                    to_db_time(now),
                ),
            )
        except pymysql.err.IntegrityError as error:
            if error.args[0] != ER.DUP_ENTRY:
                raise
            return None
        return Favorite(day, chosen["user_id"], chosen["track_key"], chosen["url"])

    async def favorites(self, guild_id: int, limit: int) -> list[Favorite]:
        """Return up to `limit` of the guild's favorite songs, newest day first."""
        rows = await self._db.fetchall(
            f"SELECT day, user_id, track_key, url FROM {self._db.t('favorites')} "
            "WHERE guild_id = %s ORDER BY day DESC LIMIT %s",
            (guild_id, limit),
        )
        return [
            Favorite(row["day"], row["user_id"], row["track_key"], row["url"])
            for row in rows
        ]

    async def record_expressions(self, guild_id: int, names: Sequence[str]) -> None:
        """Count one use of each expression name, once per time it appears."""
        for name in names:
            await self._db.execute(
                f"INSERT INTO {self._db.t('expression_uses')} (guild_id, name, uses) "
                "VALUES (%s, %s, 1) ON DUPLICATE KEY UPDATE uses = uses + 1",
                (guild_id, name),
            )

    async def favorite_expressions(self, guild_id: int) -> list[str]:
        """Return the expression names he has used, most used first, ties by name."""
        rows = await self._db.fetchall(
            f"SELECT name FROM {self._db.t('expression_uses')} "
            "WHERE guild_id = %s ORDER BY uses DESC, name",
            (guild_id,),
        )
        return [row["name"] for row in rows]
