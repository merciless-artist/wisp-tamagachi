"""Storage for keepsakes: the mementos Wisp gives members."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

import pymysql
from pymysql.constants import ER

from db.database import Database, from_db_time, to_db_time


class KeepsakeKind(StrEnum):
    """The kinds of keepsake Wisp gives."""

    LAST_EMBER = "last_ember"
    EGGSHELL = "eggshell"
    FIRST_SPARK = "first_spark"
    TEEN_SPARK = "teen_spark"
    ADULT_SPARK = "adult_spark"
    GUITAR_PICK = "guitar_pick"
    TIME_PIECE = "time_piece"


_TITLES: Final = {
    KeepsakeKind.LAST_EMBER: "Wisp v{version}'s Last Ember",
    KeepsakeKind.EGGSHELL: "Wisp v{version}'s Eggshell",
    KeepsakeKind.FIRST_SPARK: "Wisp v{version}'s First Spark",
    KeepsakeKind.TEEN_SPARK: "Wisp v{version}'s Teen Spark",
    KeepsakeKind.ADULT_SPARK: "Wisp v{version}'s Adult Spark",
    KeepsakeKind.GUITAR_PICK: "Wisp v{version}'s Guitar Pick",
    KeepsakeKind.TIME_PIECE: "Wisp v{version}'s Time Piece",
}


@dataclass(frozen=True)
class Keepsake:
    """One keepsake a member holds: its kind, the Wisp version it is from and when."""

    kind: KeepsakeKind
    version: int
    given_at: datetime

    @property
    def title(self) -> str:
        """The keepsake's name, such as "Wisp v3's Last Ember"."""
        return _TITLES[self.kind].format(version=self.version)


class KeepsakeRepo:
    """Reads and writes the keepsakes members hold."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def give(
        self,
        guild_id: int,
        user_id: int,
        kind: KeepsakeKind,
        version: int,
        at: datetime,
    ) -> bool:
        """Give a keepsake; False when the member already has that one."""
        try:
            await self._db.insert(
                f"INSERT INTO {self._db.t('keepsakes')} "
                "(guild_id, user_id, kind, version, given_at) "
                "VALUES (%s, %s, %s, %s, %s)",
                (guild_id, user_id, kind.value, version, to_db_time(at)),
            )
        except pymysql.err.IntegrityError as error:
            if error.args[0] != ER.DUP_ENTRY:
                raise
            return False
        return True

    async def of(self, guild_id: int, user_id: int) -> list[Keepsake]:
        """Return the member's keepsakes, oldest Wisp version first.

        Within a version they come in the order they were given.
        """
        rows = await self._db.fetchall(
            f"SELECT kind, version, given_at FROM {self._db.t('keepsakes')} "
            "WHERE guild_id = %s AND user_id = %s ORDER BY version, given_at, kind",
            (guild_id, user_id),
        )
        return [
            Keepsake(
                KeepsakeKind(row["kind"]), row["version"], from_db_time(row["given_at"])
            )
            for row in rows
        ]
