"""Per-guild settings: channels, threads, qualifying roles and the freeze."""

from dataclasses import dataclass, fields
from typing import Any

from db.database import Database


@dataclass
class Settings:
    """One guild's settings row. The guild id is the repository key, not a field."""

    tracks_channel_id: int | None = None
    house_channel_id: int | None = None
    studio_forum_id: int | None = None
    error_channel_id: int | None = None
    status_thread_id: int | None = None
    status_message_id: int | None = None
    mealtime_thread_id: int | None = None
    vault_thread_id: int | None = None
    vault_message_id: int | None = None
    jam_thread_id: int | None = None
    rules_thread_id: int | None = None
    frozen: bool = False


_COLUMNS = tuple(field.name for field in fields(Settings))


class SettingsRepo:
    """Reads and writes guild settings and the qualifying role list."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, guild_id: int) -> Settings:
        """Return a guild's settings, or the defaults when it has no row yet."""
        row = await self._db.fetchone(
            f"SELECT {', '.join(_COLUMNS)} FROM {self._db.t('settings')} "
            "WHERE guild_id = %s",
            (guild_id,),
        )
        if row is None:
            return Settings()
        return Settings(**{**row, "frozen": bool(row["frozen"])})

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
            (*values.values(), guild_id),
        )

    async def roles(self, guild_id: int) -> set[int]:
        """Return the role ids that qualify a member to feed Wisp."""
        rows = await self._db.fetchall(
            f"SELECT role_id FROM {self._db.t('qualifying_roles')} WHERE guild_id = %s",
            (guild_id,),
        )
        return {row["role_id"] for row in rows}

    async def add_role(self, guild_id: int, role_id: int) -> None:
        """Add a qualifying role; adding it twice changes nothing."""
        await self._db.execute(
            f"INSERT INTO {self._db.t('qualifying_roles')} (guild_id, role_id) "
            "VALUES (%s, %s) ON DUPLICATE KEY UPDATE role_id = role_id",
            (guild_id, role_id),
        )

    async def remove_role(self, guild_id: int, role_id: int) -> None:
        """Remove a qualifying role."""
        await self._db.execute(
            f"DELETE FROM {self._db.t('qualifying_roles')} "
            "WHERE guild_id = %s AND role_id = %s",
            (guild_id, role_id),
        )

    async def guilds(self) -> list[int]:
        """Return every guild that has settings, in id order."""
        rows = await self._db.fetchall(
            f"SELECT guild_id FROM {self._db.t('settings')} ORDER BY guild_id"
        )
        return [row["guild_id"] for row in rows]

    async def _ensure(self, guild_id: int) -> None:
        await self._db.execute(
            f"INSERT INTO {self._db.t('settings')} (guild_id) VALUES (%s) "
            "ON DUPLICATE KEY UPDATE guild_id = guild_id",
            (guild_id,),
        )
