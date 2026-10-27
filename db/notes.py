"""Storage for memory notes: short facts Wisp remembers about members."""

from datetime import datetime

from db.database import Database, to_db_time
from wisp.rules import NOTE_MAX_CHARS, NOTES_KEPT


class NoteRepo:
    """Reads and writes the notes Wisp keeps about each member."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, guild_id: int, user_id: int, note: str, at: datetime) -> None:
        """Save a note, cut to NOTE_MAX_CHARS, keeping only the newest NOTES_KEPT.

        MariaDB refuses LIMIT inside an IN subquery, so the ids to keep are
        wrapped in a derived table.
        """
        notes = self._db.t("notes")
        await self._db.insert(
            f"INSERT INTO {notes} (guild_id, user_id, note, at) "
            "VALUES (%s, %s, %s, %s)",
            (guild_id, user_id, note[:NOTE_MAX_CHARS], to_db_time(at)),
        )
        await self._db.execute(
            f"DELETE FROM {notes} WHERE guild_id = %s AND user_id = %s "
            "AND id NOT IN (SELECT id FROM ("
            f"SELECT id FROM {notes} WHERE guild_id = %s AND user_id = %s "
            "ORDER BY at DESC, id DESC LIMIT %s) AS keep)",
            (guild_id, user_id, guild_id, user_id, NOTES_KEPT),
        )

    async def recent(self, guild_id: int, user_id: int) -> list[str]:
        """Return the member's kept notes, oldest first."""
        rows = await self._db.fetchall(
            f"SELECT note FROM {self._db.t('notes')} "
            "WHERE guild_id = %s AND user_id = %s ORDER BY at, id",
            (guild_id, user_id),
        )
        return [row["note"] for row in rows]
