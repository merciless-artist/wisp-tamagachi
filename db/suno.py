"""Storage for Wisp's own Suno sign-in: one OAuth grant per bot."""

from dataclasses import dataclass
from datetime import datetime

from db.database import Database, from_db_time, to_db_time

_KEY = 1


@dataclass(frozen=True)
class SunoGrant:
    """The OAuth client Wisp registered with Suno and the tokens it was given.

    `expires_at` is when `access_token` stops working; `refresh_token` gets a
    new one, and Suno may hand back a new refresh token with it.
    """

    client_id: str
    access_token: str
    refresh_token: str
    expires_at: datetime
    scope: str


class SunoRepo:
    """Read and replace the one stored Suno grant."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self) -> SunoGrant | None:
        """Return the stored grant, or None before anyone has signed Wisp in."""
        row = await self._db.fetchone(
            "SELECT client_id, access_token, refresh_token, expires_at, scope "
            f"FROM {self._db.t('suno_auth')} WHERE id = %s",
            (_KEY,),
        )
        if row is None:
            return None
        return SunoGrant(
            client_id=row["client_id"],
            access_token=row["access_token"],
            refresh_token=row["refresh_token"],
            expires_at=from_db_time(row["expires_at"]),
            scope=row["scope"],
        )

    async def save(self, grant: SunoGrant, now: datetime) -> None:
        """Store `grant` in place of any earlier one."""
        await self._db.execute(
            f"INSERT INTO {self._db.t('suno_auth')} "
            "(id, client_id, access_token, refresh_token, expires_at, scope, "
            "updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE client_id = VALUES(client_id), "
            "access_token = VALUES(access_token), "
            "refresh_token = VALUES(refresh_token), "
            "expires_at = VALUES(expires_at), scope = VALUES(scope), "
            "updated_at = VALUES(updated_at)",
            (
                _KEY,
                grant.client_id,
                grant.access_token,
                grant.refresh_token,
                to_db_time(grant.expires_at),
                grant.scope,
                to_db_time(now),
            ),
        )
