"""Storage for moody phrases: staff's song lines, the rounds and the guesses."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from db.database import Database, Row, from_db_time, to_db_time
from wisp.moody import Phrase
from wisp.rules import Stage


@dataclass(frozen=True)
class MoodyRound:
    """One name-that-song round under one of Wisp's replies.

    `options` are the menu's phrase ids in the order shown. `message_id` is
    None until the reply is posted; `winner_id` until someone names the song.
    """

    id: int
    guild_id: int
    message_id: int | None
    phrase_id: int
    options: tuple[int, ...]
    winner_id: int | None
    opened_at: datetime


_PHRASE_COLUMNS = "id, stage, phrase, artist, song, year"
_ROUND_COLUMNS = (
    "id, guild_id, message_id, phrase_id, option_1, option_2, option_3, "
    "winner_id, opened_at"
)


def _phrase(row: Row) -> Phrase:
    return Phrase(
        id=row["id"],
        stage=row["stage"],
        text=row["phrase"],
        artist=row["artist"],
        song=row["song"],
        year=row["year"],
    )


def _round(row: Row) -> MoodyRound:
    return MoodyRound(
        id=row["id"],
        guild_id=row["guild_id"],
        message_id=row["message_id"],
        phrase_id=row["phrase_id"],
        options=(row["option_1"], row["option_2"], row["option_3"]),
        winner_id=row["winner_id"],
        opened_at=from_db_time(row["opened_at"]),
    )


class MoodyRepo:
    """Reads and writes each server's moody phrases and their rounds."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(
        self,
        guild_id: int,
        stage: Stage,
        text: str,
        artist: str,
        song: str,
        year: int,
        added_by: int,
        now: datetime,
    ) -> int:
        """Save a phrase for `stage` and return its id."""
        return await self._db.insert(
            f"INSERT INTO {self._db.t('moody_phrases')} "
            "(guild_id, stage, phrase, artist, song, year, added_by, added_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                guild_id,
                stage.value,
                text,
                artist,
                song,
                year,
                added_by,
                to_db_time(now),
            ),
        )

    async def for_stage(self, guild_id: int, stage: Stage) -> list[Phrase]:
        """The server's phrases for `stage`, oldest first."""
        rows = await self._db.fetchall(
            f"SELECT {_PHRASE_COLUMNS} FROM {self._db.t('moody_phrases')} "
            "WHERE guild_id = %s AND stage = %s ORDER BY id",
            (guild_id, stage.value),
        )
        return [_phrase(row) for row in rows]

    async def by_ids(self, guild_id: int, ids: Sequence[int]) -> dict[int, Phrase]:
        """The server's phrases among `ids`, by id; removed ones are left out."""
        if not ids:
            return {}
        marks = ", ".join(["%s"] * len(ids))
        rows = await self._db.fetchall(
            f"SELECT {_PHRASE_COLUMNS} FROM {self._db.t('moody_phrases')} "
            f"WHERE guild_id = %s AND id IN ({marks})",
            (guild_id, *ids),
        )
        return {row["id"]: _phrase(row) for row in rows}

    async def remove(self, guild_id: int, phrase_id: int) -> bool:
        """Delete one of the server's phrases; False when it has no such phrase."""
        changed = await self._db.execute(
            f"DELETE FROM {self._db.t('moody_phrases')} "
            "WHERE guild_id = %s AND id = %s",
            (guild_id, phrase_id),
        )
        return changed == 1

    async def open_round(
        self, guild_id: int, phrase_id: int, options: Sequence[int], now: datetime
    ) -> int:
        """Store a new round for `phrase_id` with its menu's `options`; its id."""
        first, second, third = options
        return await self._db.insert(
            f"INSERT INTO {self._db.t('moody_rounds')} "
            "(guild_id, phrase_id, option_1, option_2, option_3, opened_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (guild_id, phrase_id, first, second, third, to_db_time(now)),
        )

    async def set_message(self, round_id: int, message_id: int) -> None:
        """Record the reply a round's menu was posted under."""
        await self._db.execute(
            f"UPDATE {self._db.t('moody_rounds')} SET message_id = %s WHERE id = %s",
            (message_id, round_id),
        )

    async def drop_round(self, round_id: int) -> None:
        """Delete a round whose reply never went out."""
        await self._db.execute(
            f"DELETE FROM {self._db.t('moody_rounds')} WHERE id = %s", (round_id,)
        )

    async def last_round(self, guild_id: int) -> MoodyRound | None:
        """The server's newest round, or None."""
        row = await self._db.fetchone(
            f"SELECT {_ROUND_COLUMNS} FROM {self._db.t('moody_rounds')} "
            "WHERE guild_id = %s ORDER BY opened_at DESC, id DESC LIMIT 1",
            (guild_id,),
        )
        return None if row is None else _round(row)

    async def get_round(self, guild_id: int, round_id: int) -> MoodyRound | None:
        """One of the server's rounds, or None."""
        row = await self._db.fetchone(
            f"SELECT {_ROUND_COLUMNS} FROM {self._db.t('moody_rounds')} "
            "WHERE guild_id = %s AND id = %s",
            (guild_id, round_id),
        )
        return None if row is None else _round(row)

    async def take_guess(self, round_id: int, user_id: int) -> bool:
        """Record the member's one guess at a round; False if they had one."""
        changed = await self._db.execute(
            f"INSERT INTO {self._db.t('moody_guesses')} "
            "(round_id, user_id) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE user_id = user_id",
            (round_id, user_id),
        )
        return changed == 1

    async def win(self, round_id: int, user_id: int) -> bool:
        """Make the member a round's winner; False when it already has one."""
        changed = await self._db.execute(
            f"UPDATE {self._db.t('moody_rounds')} SET winner_id = %s "
            "WHERE id = %s AND winner_id IS NULL",
            (user_id, round_id),
        )
        return changed == 1
