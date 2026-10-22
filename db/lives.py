"""Storage for Wisp's lives: the current one and the history."""

from typing import Any

from db.database import Database, Row, from_db_time, to_db_time
from wisp.life import EventKind, Life, Phase
from wisp.rules import Stage

_COLUMNS = (
    "version",
    "phase",
    "stage",
    "care",
    "egg_food",
    "growth",
    "laid_at",
    "hatch_started_at",
    "hatched_at",
    "stage_started_at",
    "ended_at",
    "last_tick_at",
    "phase_seconds",
    "high_happiness_since",
    "warned",
    "hatched_by",
    "peak_stage",
)
_SELECT = f"SELECT id, {', '.join(_COLUMNS)} FROM"


def _from_row(row: Row) -> Life:
    return Life(
        id=row["id"],
        version=row["version"],
        phase=Phase(row["phase"]),
        stage=Stage(row["stage"]),
        care=row["care"],
        egg_food=row["egg_food"],
        growth=row["growth"],
        laid_at=from_db_time(row["laid_at"]),
        hatch_started_at=from_db_time(row["hatch_started_at"]),
        hatched_at=from_db_time(row["hatched_at"]),
        stage_started_at=from_db_time(row["stage_started_at"]),
        ended_at=from_db_time(row["ended_at"]),
        last_tick_at=from_db_time(row["last_tick_at"]),
        phase_seconds=row["phase_seconds"],
        high_happiness_since=from_db_time(row["high_happiness_since"]),
        warned=EventKind(row["warned"]) if row["warned"] else None,
        hatched_by=row["hatched_by"],
        peak_stage=Stage(row["peak_stage"]),
    )


def _values(life: Life) -> tuple[Any, ...]:
    """The life's column values, in `_COLUMNS` order."""
    return (
        life.version,
        life.phase.value,
        life.stage.value,
        life.care,
        life.egg_food,
        life.growth,
        to_db_time(life.laid_at),
        to_db_time(life.hatch_started_at),
        to_db_time(life.hatched_at),
        to_db_time(life.stage_started_at),
        to_db_time(life.ended_at),
        to_db_time(life.last_tick_at),
        life.phase_seconds,
        to_db_time(life.high_happiness_since),
        life.warned.value if life.warned else None,
        life.hatched_by,
        life.peak_stage.value,
    )


class LifeRepo:
    """Reads and writes lives. A guild's current life has its highest version."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def current(self, guild_id: int) -> Life | None:
        """Return the guild's newest life, or None when it has never had one."""
        row = await self._db.fetchone(
            f"{_SELECT} {self._db.t('lives')} WHERE guild_id = %s "
            "ORDER BY version DESC LIMIT 1",
            (guild_id,),
        )
        return _from_row(row) if row else None

    async def insert(self, guild_id: int, life: Life) -> Life:
        """Store a new life, set its `id` and return it."""
        placeholders = ", ".join(["%s"] * (len(_COLUMNS) + 1))
        life.id = await self._db.insert(
            f"INSERT INTO {self._db.t('lives')} (guild_id, {', '.join(_COLUMNS)}) "
            f"VALUES ({placeholders})",
            (guild_id, *_values(life)),
        )
        return life

    async def save(self, guild_id: int, life: Life) -> None:
        """Write every field of an inserted life back to its row."""
        if life.id is None:
            raise ValueError("Life must be inserted before it can be saved")
        assignments = ", ".join(f"{column} = %s" for column in _COLUMNS)
        await self._db.execute(
            f"UPDATE {self._db.t('lives')} SET {assignments} "
            "WHERE id = %s AND guild_id = %s",
            (*_values(life), life.id, guild_id),
        )

    async def history(self, guild_id: int) -> list[Life]:
        """Return every life of a guild, newest first."""
        rows = await self._db.fetchall(
            f"{_SELECT} {self._db.t('lives')} WHERE guild_id = %s "
            "ORDER BY version DESC",
            (guild_id,),
        )
        return [_from_row(row) for row in rows]

    async def next_version(self, guild_id: int) -> int:
        """Return the version number for a guild's next egg, cold ones included."""
        row = await self._db.fetchone(
            f"SELECT COALESCE(MAX(version), 0) + 1 AS next FROM {self._db.t('lives')} "
            "WHERE guild_id = %s",
            (guild_id,),
        )
        assert row is not None
        return int(row["next"])
