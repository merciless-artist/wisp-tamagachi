"""Storage for players: activation, points, bond, names, bans, rhymes, rooms and
help pings.
"""

from dataclasses import dataclass, fields
from datetime import datetime

from db.database import Database, Params, Row, from_db_time, to_db_time
from wisp.bond import PickleStance, reached_new_tier
from wisp.language import Language


@dataclass
class Player:
    """One member's row in one guild. The guild id is the repository key.

    `help_pings_off` is set once the member turned the helper role off, so
    Wisp does not give it back to them.
    """

    user_id: int
    activated_at: datetime | None = None
    met_at: datetime | None = None
    name: str | None = None
    lifetime_points: int = 0
    balance: int = 0
    bond: int = 0
    pickle_stance: PickleStance | None = None
    offenses: int = 0
    banned_until: datetime | None = None
    banned_forever: bool = False
    best_rhyme_score: int = 0
    room_thread_id: int | None = None
    room_pack_message_id: int | None = None
    rhyme_language: Language | None = None
    help_pings_off: bool = False

    def is_banned(self, now: datetime) -> bool:
        """Whether the player is banned from Wisp at `now`."""
        return self.banned_forever or (
            self.banned_until is not None and self.banned_until > now
        )


_SELECT = f"SELECT {', '.join(field.name for field in fields(Player))} FROM"


def _from_row(row: Row) -> Player:
    stance = row["pickle_stance"]
    language = row["rhyme_language"]
    return Player(
        **{
            **row,
            "pickle_stance": None if stance is None else PickleStance(stance),
            "rhyme_language": None if language is None else Language(language),
            "activated_at": from_db_time(row["activated_at"]),
            "met_at": from_db_time(row["met_at"]),
            "banned_until": from_db_time(row["banned_until"]),
            "banned_forever": bool(row["banned_forever"]),
            "help_pings_off": bool(row["help_pings_off"]),
        }
    )


class PlayerRepo:
    """Reads and writes players. Writing to an unknown player creates it."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._tier_ups: dict[int, list[int]] = {}

    async def get(self, guild_id: int, user_id: int) -> Player:
        """Return a player, creating the defaults on first read."""
        await self._ensure(guild_id, user_id)
        row = await self._db.fetchone(
            f"{_SELECT} {self._db.t('players')} WHERE guild_id = %s AND user_id = %s",
            (guild_id, user_id),
        )
        assert row is not None
        return _from_row(row)

    async def activate(
        self, guild_id: int, user_id: int, at: datetime, *, coins: int = 0
    ) -> bool:
        """Record when the player joined in; the first time is kept.

        Only that first time also adds `coins` to their balance, not to their
        lifetime points. Returns whether this was the first time.
        """
        await self._ensure(guild_id, user_id)
        changed = await self._db.execute(
            f"UPDATE {self._db.t('players')} "
            "SET activated_at = %s, balance = balance + %s "
            "WHERE guild_id = %s AND user_id = %s AND activated_at IS NULL",
            (to_db_time(at), coins, guild_id, user_id),
        )
        return changed == 1

    async def activated(self, guild_id: int) -> list[Player]:
        """Return the players who opened /wisp board, first to join first."""
        rows = await self._db.fetchall(
            f"{_SELECT} {self._db.t('players')} "
            "WHERE guild_id = %s AND activated_at IS NOT NULL "
            "ORDER BY activated_at, user_id",
            (guild_id,),
        )
        return [_from_row(row) for row in rows]

    async def add_points(self, guild_id: int, user_id: int, points: int) -> None:
        """Add leaderboard points to both the lifetime total and the balance."""
        await self._update(
            guild_id,
            user_id,
            "lifetime_points = lifetime_points + %s, balance = balance + %s",
            (points, points),
        )

    async def spend(self, guild_id: int, user_id: int, cost: int) -> bool:
        """Take `cost` from the balance; False, and no change, when it is short."""
        if cost == 0:
            return True
        changed = await self._db.execute(
            f"UPDATE {self._db.t('players')} SET balance = balance - %s "
            "WHERE guild_id = %s AND user_id = %s AND balance >= %s",
            (cost, guild_id, user_id, cost),
        )
        return changed == 1

    async def refund(self, guild_id: int, user_id: int, amount: int) -> None:
        """Give back points that were spent; the lifetime total is unchanged."""
        await self._update(guild_id, user_id, "balance = balance + %s", (amount,))

    async def add_bond(self, guild_id: int, user_id: int, amount: int) -> None:
        """Add to the player's bond with Wisp, noting a rise to a new tier."""
        before = (await self.get(guild_id, user_id)).bond
        await self._update(guild_id, user_id, "bond = bond + %s", (amount,))
        if reached_new_tier(before, before + amount):
            self._tier_ups.setdefault(guild_id, []).append(user_id)

    def take_tier_ups(self, guild_id: int) -> list[int]:
        """The members whose bond reached a new tier since the last call.

        They are in the order it happened, and are forgotten once taken.
        """
        return self._tier_ups.pop(guild_id, [])

    async def set_name(self, guild_id: int, user_id: int, name: str | None) -> None:
        """Set the name Wisp calls the player; None clears it."""
        await self._update(guild_id, user_id, "name = %s", (name,))

    async def set_pickle_stance(
        self, guild_id: int, user_id: int, stance: PickleStance | None
    ) -> None:
        """Set where the player stands on pickles; None clears it."""
        await self._update(
            guild_id,
            user_id,
            "pickle_stance = %s",
            (None if stance is None else stance.value,),
        )

    async def mark_met(self, guild_id: int, user_id: int, at: datetime) -> None:
        """Record when Wisp met the player."""
        await self._update(guild_id, user_id, "met_at = %s", (to_db_time(at),))

    async def set_offense(
        self,
        guild_id: int,
        user_id: int,
        offenses: int,
        banned_until: datetime | None,
        banned_forever: bool,
    ) -> None:
        """Set the offense count and the ban that goes with it."""
        await self._update(
            guild_id,
            user_id,
            "offenses = %s, banned_until = %s, banned_forever = %s",
            (offenses, to_db_time(banned_until), banned_forever),
        )

    async def strip_points(self, guild_id: int, user_id: int, amount: int) -> None:
        """Take points from the lifetime total and the balance, never below zero."""
        await self._update(
            guild_id,
            user_id,
            "lifetime_points = GREATEST(lifetime_points - %s, 0), "
            "balance = GREATEST(balance - %s, 0)",
            (amount, amount),
        )

    async def top_lifetime(self, guild_id: int, limit: int) -> list[Player]:
        """Return the players with points, most lifetime points first."""
        rows = await self._db.fetchall(
            f"{_SELECT} {self._db.t('players')} "
            "WHERE guild_id = %s AND lifetime_points > 0 "
            "ORDER BY lifetime_points DESC, user_id LIMIT %s",
            (guild_id, limit),
        )
        return [_from_row(row) for row in rows]

    async def record_rhyme_score(self, guild_id: int, user_id: int, score: int) -> bool:
        """Keep a Rhyme Duel score if it beats the player's best; True when it does."""
        await self._ensure(guild_id, user_id)
        changed = await self._db.execute(
            f"UPDATE {self._db.t('players')} SET best_rhyme_score = %s "
            "WHERE guild_id = %s AND user_id = %s AND best_rhyme_score < %s",
            (score, guild_id, user_id, score),
        )
        return changed == 1

    async def set_rhyme_language(
        self, guild_id: int, user_id: int, language: Language
    ) -> None:
        """Set the language the player's Rhyme Duels are played in."""
        await self._update(guild_id, user_id, "rhyme_language = %s", (language.value,))

    async def top_rhyme(self, guild_id: int, limit: int) -> list[Player]:
        """Return the players with a Rhyme Duel score, best score first."""
        rows = await self._db.fetchall(
            f"{_SELECT} {self._db.t('players')} "
            "WHERE guild_id = %s AND best_rhyme_score > 0 "
            "ORDER BY best_rhyme_score DESC, user_id LIMIT %s",
            (guild_id, limit),
        )
        return [_from_row(row) for row in rows]

    async def set_room(
        self, guild_id: int, user_id: int, thread_id: int | None
    ) -> None:
        """Set the player's room thread; None clears it.

        The pinned Snack Pack belonged to the old room, so it is forgotten too.
        """
        await self._update(
            guild_id,
            user_id,
            "room_thread_id = %s, room_pack_message_id = NULL",
            (thread_id,),
        )

    async def set_room_pack(
        self, guild_id: int, user_id: int, message_id: int | None
    ) -> None:
        """Set the Snack Pack message pinned in the player's room; None clears it."""
        await self._update(
            guild_id, user_id, "room_pack_message_id = %s", (message_id,)
        )

    async def set_help_pings_off(self, guild_id: int, user_id: int, off: bool) -> None:
        """Record whether the player turned the helper role off."""
        await self._update(guild_id, user_id, "help_pings_off = %s", (off,))

    async def _ensure(self, guild_id: int, user_id: int) -> None:
        await self._db.execute(
            f"INSERT INTO {self._db.t('players')} (guild_id, user_id) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE guild_id = guild_id",
            (guild_id, user_id),
        )

    async def _update(
        self, guild_id: int, user_id: int, assignments: str, params: Params
    ) -> None:
        await self._ensure(guild_id, user_id)
        await self._db.execute(
            f"UPDATE {self._db.t('players')} SET {assignments} "
            "WHERE guild_id = %s AND user_id = %s",
            (*params, guild_id, user_id),
        )
