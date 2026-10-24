"""Per-guild settings: channels, threads, roles, food values and the freeze."""

import json
import logging
from dataclasses import dataclass, fields
from typing import Any

from db.database import Database
from wisp import rules
from wisp.links import TrackKind

log = logging.getLogger("wisp")


@dataclass(frozen=True)
class Settings:
    """One guild's settings row. The guild id is the repository key, not a field.

    It is frozen, so the copy the repository caches can be shared safely.
    `faq_message_ids` are the Wisp FAQ's section posts, in order; the column
    holds them as a JSON list.
    """

    tracks_channel_id: int | None = None
    house_channel_id: int | None = None
    studio_forum_id: int | None = None
    status_thread_id: int | None = None
    status_message_id: int | None = None
    mealtime_thread_id: int | None = None
    vault_thread_id: int | None = None
    vault_message_id: int | None = None
    jam_thread_id: int | None = None
    rules_thread_id: int | None = None
    rules_message_id: int | None = None
    faq_message_ids: tuple[int, ...] | None = None
    viibr_meal_points: int | None = None
    suno_meal_points: int | None = None
    frozen: bool = False


_COLUMNS = tuple(field.name for field in fields(Settings))
_ID_LISTS = frozenset({"faq_message_ids"})


def _to_column(name: str, value: Any) -> Any:
    """A settings value as its column stores it."""
    if name in _ID_LISTS and value is not None:
        return json.dumps(list(value))
    return value


def _id_list(guild_id: int, name: str, value: str | None) -> tuple[int, ...] | None:
    """A stored id list, or None when there is none or it cannot be read.

    An unreadable list is logged and read as None, so the next setup posts
    what it belongs to again.
    """
    if value is None:
        return None
    try:
        return tuple(int(item) for item in json.loads(value))
    except (ValueError, TypeError):
        log.error(
            "Guild %d has an unreadable %s, read as none: %r", guild_id, name, value
        )
        return None


def _from_row(guild_id: int, row: dict[str, Any]) -> Settings:
    """Settings from a database row."""
    values: dict[str, Any] = {
        name: _id_list(guild_id, name, value) if name in _ID_LISTS else value
        for name, value in row.items()
    }
    return Settings(**{**values, "frozen": bool(row["frozen"])})


def meal_points(settings: Settings) -> dict[TrackKind, int]:
    """The meal points each kind of track feeds: staff's value, else the rules'."""
    chosen = {
        TrackKind.VIIBR: settings.viibr_meal_points,
        TrackKind.SUNO: settings.suno_meal_points,
    }
    return {
        kind: default if (value := chosen[kind]) is None else value
        for kind, default in rules.MEAL_POINTS.items()
    }


class SettingsRepo:
    """Reads and writes guild settings and the qualifying role list.

    Both are cached in this process after the first read, since nearly every
    guild message needs them, and every write here refreshes its guild. There
    is one bot process, so nothing else changes them behind the cache. A read
    that overlaps a write is not cached, so it cannot bring back an old value.
    """

    def __init__(self, db: Database) -> None:
        self._db = db
        self._settings: dict[int, Settings] = {}
        self._roles: dict[int, frozenset[int]] = {}
        self._writes: dict[int, int] = {}

    async def get(self, guild_id: int) -> Settings:
        """Return a guild's settings, or the defaults when it has no row yet."""
        cached = self._settings.get(guild_id)
        if cached is not None:
            return cached
        writes = self._writes.get(guild_id, 0)
        settings = await self._read(guild_id)
        if self._writes.get(guild_id, 0) == writes:
            self._settings[guild_id] = settings
        return settings

    async def _read(self, guild_id: int) -> Settings:
        row = await self._db.fetchone(
            f"SELECT {', '.join(_COLUMNS)} FROM {self._db.t('settings')} "
            "WHERE guild_id = %s",
            (guild_id,),
        )
        if row is None:
            return Settings()
        return _from_row(guild_id, row)

    async def update(self, guild_id: int, **values: Any) -> None:
        """Set the named settings; None clears a channel or thread."""
        unknown = set(values) - set(_COLUMNS)
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        if not values:
            return
        await self._ensure(guild_id)
        assignments = ", ".join(f"{column} = %s" for column in values)
        await self._db.execute(
            f"UPDATE {self._db.t('settings')} SET {assignments} WHERE guild_id = %s",
            (*(_to_column(name, value) for name, value in values.items()), guild_id),
        )
        self._forget(guild_id)

    async def roles(self, guild_id: int) -> frozenset[int]:
        """Return the role ids that qualify a member to feed Wisp."""
        cached = self._roles.get(guild_id)
        if cached is not None:
            return cached
        writes = self._writes.get(guild_id, 0)
        rows = await self._db.fetchall(
            f"SELECT role_id FROM {self._db.t('qualifying_roles')} WHERE guild_id = %s",
            (guild_id,),
        )
        roles = frozenset(row["role_id"] for row in rows)
        if self._writes.get(guild_id, 0) == writes:
            self._roles[guild_id] = roles
        return roles

    async def add_role(self, guild_id: int, role_id: int) -> None:
        """Add a qualifying role; adding it twice changes nothing."""
        await self._db.execute(
            f"INSERT INTO {self._db.t('qualifying_roles')} (guild_id, role_id) "
            "VALUES (%s, %s) ON DUPLICATE KEY UPDATE role_id = role_id",
            (guild_id, role_id),
        )
        self._forget(guild_id)

    async def remove_role(self, guild_id: int, role_id: int) -> None:
        """Remove a qualifying role."""
        await self._db.execute(
            f"DELETE FROM {self._db.t('qualifying_roles')} "
            "WHERE guild_id = %s AND role_id = %s",
            (guild_id, role_id),
        )
        self._forget(guild_id)

    async def guilds(self) -> list[int]:
        """Return every guild that has settings, in id order."""
        rows = await self._db.fetchall(
            f"SELECT guild_id FROM {self._db.t('settings')} ORDER BY guild_id"
        )
        return [row["guild_id"] for row in rows]

    def _forget(self, guild_id: int) -> None:
        """Drop a guild's cached settings and roles after a write."""
        self._writes[guild_id] = self._writes.get(guild_id, 0) + 1
        self._settings.pop(guild_id, None)
        self._roles.pop(guild_id, None)

    async def _ensure(self, guild_id: int) -> None:
        await self._db.execute(
            f"INSERT INTO {self._db.t('settings')} (guild_id) VALUES (%s) "
            "ON DUPLICATE KEY UPDATE guild_id = guild_id",
            (guild_id,),
        )
