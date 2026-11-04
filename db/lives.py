"""Storage for Wisp's lives: the current one and the history."""

from typing import Any

from db.database import Database, Row, from_db_time, to_db_time
from wisp.life import EventKind, Life, Phase
from wisp.rules import Stage

# The columns keep their live names: `care` holds Life.health, `fondness` holds
# Life.wellbeing and `high_happiness_since` holds Life.high_mood_since. The
# cold's, Mood's, stretches' and chores' columns share their fields' names.
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
    "from_coal",
    "favorite_snack",
    "fondness",
    "lonely_warned",
    "cold_due_at",
    "cold_left",
    "had_cold",
    "mood_meter",
    "health_stretch",
    "wellbeing_stretch",
    "mood_stretch",
    "sniffles_left",
    "mess_in",
    "mess_left",
    "mess_gap",
    "mess_message_id",
    "tantrum_due_at",
    "tantrum_left",
    "tantrum_message_id",
    "spoiled_until",
    "nap_slot",
    "nap_left",
    "lights_left",
    "nap_message_id",
    "cranky_until",
)
_SELECT = f"SELECT id, {', '.join(_COLUMNS)} FROM"


def _from_row(row: Row) -> Life:
    return Life(
        id=row["id"],
        version=row["version"],
        phase=Phase(row["phase"]),
        stage=Stage(row["stage"]),
        health=row["care"],
        egg_food=row["egg_food"],
        growth=row["growth"],
        laid_at=from_db_time(row["laid_at"]),
        hatch_started_at=from_db_time(row["hatch_started_at"]),
        hatched_at=from_db_time(row["hatched_at"]),
        stage_started_at=from_db_time(row["stage_started_at"]),
        ended_at=from_db_time(row["ended_at"]),
        last_tick_at=from_db_time(row["last_tick_at"]),
        phase_seconds=row["phase_seconds"],
        high_mood_since=from_db_time(row["high_happiness_since"]),
        warned=EventKind(row["warned"]) if row["warned"] else None,
        hatched_by=row["hatched_by"],
        peak_stage=Stage(row["peak_stage"]),
        from_coal=bool(row["from_coal"]),
        favorite_snack=row["favorite_snack"],
        wellbeing=row["fondness"],
        lonely_warned=bool(row["lonely_warned"]),
        cold_due_at=from_db_time(row["cold_due_at"]),
        cold_left=row["cold_left"],
        had_cold=bool(row["had_cold"]),
        mood_meter=row["mood_meter"],
        health_stretch=row["health_stretch"],
        wellbeing_stretch=row["wellbeing_stretch"],
        mood_stretch=row["mood_stretch"],
        sniffles_left=row["sniffles_left"],
        mess_in=row["mess_in"],
        mess_left=row["mess_left"],
        mess_gap=row["mess_gap"],
        mess_message_id=row["mess_message_id"],
        tantrum_due_at=from_db_time(row["tantrum_due_at"]),
        tantrum_left=row["tantrum_left"],
        tantrum_message_id=row["tantrum_message_id"],
        spoiled_until=from_db_time(row["spoiled_until"]),
        nap_slot=from_db_time(row["nap_slot"]),
        nap_left=row["nap_left"],
        lights_left=row["lights_left"],
        nap_message_id=row["nap_message_id"],
        cranky_until=from_db_time(row["cranky_until"]),
    )


def _values(life: Life) -> tuple[Any, ...]:
    """The life's column values, in `_COLUMNS` order."""
    return (
        life.version,
        life.phase.value,
        life.stage.value,
        life.health,
        life.egg_food,
        life.growth,
        to_db_time(life.laid_at),
        to_db_time(life.hatch_started_at),
        to_db_time(life.hatched_at),
        to_db_time(life.stage_started_at),
        to_db_time(life.ended_at),
        to_db_time(life.last_tick_at),
        life.phase_seconds,
        to_db_time(life.high_mood_since),
        life.warned.value if life.warned else None,
        life.hatched_by,
        life.peak_stage.value,
        life.from_coal,
        life.favorite_snack,
        life.wellbeing,
        life.lonely_warned,
        to_db_time(life.cold_due_at),
        life.cold_left,
        life.had_cold,
        life.mood_meter,
        life.health_stretch,
        life.wellbeing_stretch,
        life.mood_stretch,
        life.sniffles_left,
        life.mess_in,
        life.mess_left,
        life.mess_gap,
        life.mess_message_id,
        to_db_time(life.tantrum_due_at),
        life.tantrum_left,
        life.tantrum_message_id,
        to_db_time(life.spoiled_until),
        to_db_time(life.nap_slot),
        life.nap_left,
        life.lights_left,
        life.nap_message_id,
        to_db_time(life.cranky_until),
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
