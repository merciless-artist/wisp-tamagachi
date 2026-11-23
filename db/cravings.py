"""Storage for Wisp's Craving: each member's round for one UTC day."""

from dataclasses import dataclass
from datetime import UTC, date, datetime

from db.database import Database, Row, from_db_time, to_db_time


@dataclass(frozen=True)
class Round:
    """One member's Craving round for one UTC day.

    `guesses` are the wrong snack keys guessed so far, in order. `ended_at` is
    None while the round is open; `bought_at` is when they bought the snack
    themselves after losing.
    """

    guild_id: int
    user_id: int
    day: date
    snack: str
    guesses: tuple[str, ...]
    last_at: datetime
    ended_at: datetime | None
    won: bool
    bought_at: datetime | None


_COLUMNS = "guild_id, user_id, day, snack, guesses, last_at, ended_at, won, bought_at"
_KEY = "guild_id = %s AND user_id = %s AND day = %s"


def _utc_date(now: datetime) -> date:
    return now.astimezone(UTC).date()


def _from_row(row: Row) -> Round:
    guesses: str = row["guesses"]
    return Round(
        guild_id=row["guild_id"],
        user_id=row["user_id"],
        day=row["day"],
        snack=row["snack"],
        guesses=tuple(guesses.split(",")) if guesses else (),
        last_at=from_db_time(row["last_at"]),
        ended_at=from_db_time(row["ended_at"]),
        won=bool(row["won"]),
        bought_at=from_db_time(row["bought_at"]),
    )


class CravingRepo:
    """Reads and writes Craving rounds, one per member per server per UTC day."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def today(self, guild_id: int, user_id: int, now: datetime) -> Round | None:
        """Return the member's round for the UTC day of `now`, or None."""
        return await self.get(guild_id, user_id, _utc_date(now))

    async def start(
        self, guild_id: int, user_id: int, snack: str, now: datetime
    ) -> Round:
        """Start the day's round craving `snack`, or return the one already started.

        A round already stored for the day keeps its snack and guesses, so
        starting again never rerolls it.
        """
        day = _utc_date(now)
        await self._db.execute(
            f"INSERT INTO {self._db.t('cravings')} "
            "(guild_id, user_id, day, snack, last_at) VALUES (%s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE guild_id = guild_id",
            (guild_id, user_id, day, snack, to_db_time(now)),
        )
        return await self._stored(guild_id, user_id, day)

    async def add_guess(
        self, guild_id: int, user_id: int, day: date, snack: str, now: datetime
    ) -> Round:
        """Add a wrong guess to an open round and return the round.

        A snack already guessed, or a round already ended, is left unchanged.

        Raises:
            LookupError: The member has no round on `day`.
        """
        await self._db.execute(
            f"UPDATE {self._db.t('cravings')} "
            "SET guesses = IF(guesses = '', %s, CONCAT(guesses, ',', %s)), "
            "last_at = %s "
            f"WHERE {_KEY} AND ended_at IS NULL AND NOT FIND_IN_SET(%s, guesses)",
            (snack, snack, to_db_time(now), guild_id, user_id, day, snack),
        )
        return await self._stored(guild_id, user_id, day)

    async def end(
        self,
        guild_id: int,
        user_id: int,
        day: date,
        *,
        won: bool,
        now: datetime,
        idle_before: datetime | None = None,
    ) -> bool:
        """End an open round as won or lost; False when nothing was ended.

        With `idle_before`, the round ends only if it was last touched before
        then, so a guess that just came in keeps it open.
        """
        idle = ""
        params: list[object] = [to_db_time(now), won, guild_id, user_id, day]
        if idle_before is not None:
            idle = " AND last_at < %s"
            params.append(to_db_time(idle_before))
        changed = await self._db.execute(
            f"UPDATE {self._db.t('cravings')} SET ended_at = %s, won = %s "
            f"WHERE {_KEY} AND ended_at IS NULL{idle}",
            params,
        )
        return changed == 1

    async def idle_since(self, cutoff: datetime) -> list[Round]:
        """Return every open round, in any server, last touched before `cutoff`."""
        rows = await self._db.fetchall(
            f"SELECT {_COLUMNS} FROM {self._db.t('cravings')} "
            "WHERE ended_at IS NULL AND last_at < %s "
            "ORDER BY last_at, guild_id, user_id",
            (to_db_time(cutoff),),
        )
        return [_from_row(row) for row in rows]

    async def open_since(
        self, guild_id: int, user_id: int, cutoff: datetime
    ) -> Round | None:
        """Return the member's newest open round touched at or after `cutoff`."""
        row = await self._db.fetchone(
            f"SELECT {_COLUMNS} FROM {self._db.t('cravings')} "
            "WHERE guild_id = %s AND user_id = %s AND ended_at IS NULL "
            "AND last_at >= %s ORDER BY day DESC LIMIT 1",
            (guild_id, user_id, to_db_time(cutoff)),
        )
        return None if row is None else _from_row(row)

    async def mark_bought(
        self, guild_id: int, user_id: int, day: date, now: datetime
    ) -> bool:
        """Record that the member bought the snack after losing the round.

        Returns False, changing nothing, unless the round ended in a loss and
        was not marked bought before.
        """
        changed = await self._db.execute(
            f"UPDATE {self._db.t('cravings')} SET bought_at = %s "
            f"WHERE {_KEY} AND ended_at IS NOT NULL AND won = 0 "
            "AND bought_at IS NULL",
            (to_db_time(now), guild_id, user_id, day),
        )
        return changed == 1

    async def get(self, guild_id: int, user_id: int, day: date) -> Round | None:
        """Return the member's round for the UTC date `day`, or None."""
        row = await self._db.fetchone(
            f"SELECT {_COLUMNS} FROM {self._db.t('cravings')} WHERE {_KEY}",
            (guild_id, user_id, day),
        )
        return None if row is None else _from_row(row)

    async def _stored(self, guild_id: int, user_id: int, day: date) -> Round:
        found = await self.get(guild_id, user_id, day)
        if found is None:
            raise LookupError(
                f"No Craving round for member {user_id} in guild {guild_id} on {day}"
            )
        return found
