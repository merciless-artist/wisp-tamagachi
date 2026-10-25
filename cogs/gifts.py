"""Gifts from the ViiBR Vault: the roll, Wisp's reaction and the Vault's gift list.

Buying a gift is giving it: there is no inventory. Whether he keeps it is a
gamble, decided by the Gifts cog's random source.
"""

import random
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord
from discord.ext import commands

from cogs.announce import post_in_house
from cogs.assets import ASSETS_DIR, asset_image
from cogs.players import Refusal, check_member
from db.activity import InteractionKind
from db.gifts import GiftAttempt
from db.players import Player
from wisp.gifts import GiftState, Outcome, collection_of, decide, with_article
from wisp.life import Life, Phase, add_growth, mood
from wisp.lines import Moment
from wisp.rules import (
    BOND_PER_KEPT_GIFT,
    COLLECTION_BOND_BONUS,
    GIFT_BY_KEY,
    GIFT_COLLECTIONS,
    GIFT_COST,
    GROWTH_PER_BOND_MOMENT,
    Gift,
    GiftCollection,
)
from wisp.text import VAULT_RAIL, count, richest, text_length, with_emoji

if TYPE_CHECKING:
    from app import WispBot

_NOT_HATCHED: Final = "♪ Wisp isn't hatched yet. Gifts have to wait until he is."
_BACK_IN_VAULT: Final = "♪ It's back in the ViiBR Vault."
_KEPT_TODAY: Final = (
    f"{VAULT_RAIL}Wisp already picked his treasure today. "
    "Anything you give him goes back to the Vault."
)
_MOMENTS: Final = {
    Outcome.KEPT: Moment.GIFT_KEPT,
    Outcome.PASSED: Moment.GIFT_PASSED,
    Outcome.FULL: Moment.GIFT_FULL,
}

# ---
# The cog
# ---


class Gifts(commands.Cog):
    """Holds `rng`, the random source that decides whether Wisp keeps a gift."""

    def __init__(self, bot: "WispBot") -> None:
        self.bot = bot
        self.rng = random.Random()


def gift_rng(bot: "WispBot") -> random.Random:
    """The Gifts cog's random source.

    Raises:
        LookupError: The Gifts cog is not loaded.
    """
    cog = bot.get_cog(Gifts.__cog_name__)
    if not isinstance(cog, Gifts):
        raise LookupError("the Gifts cog is not loaded")
    return cog.rng


# ---
# Stock
# ---


def _living_id(life: Life | None) -> int | None:
    """The id of a living Wisp's life, or None when he is not alive."""
    if life is None or life.phase is not Phase.ALIVE:
        return None
    return life.id


async def _state(
    bot: "WispBot", guild_id: int, life_id: int, now: datetime
) -> GiftState:
    kept = await bot.gifts.kept(guild_id, life_id)
    today = await bot.gifts.today(guild_id, life_id, now)
    return GiftState(
        frozenset(attempt.gift for attempt in kept),
        frozenset(
            GIFT_BY_KEY[attempt.gift].collection
            for attempt in today
            if attempt.gift in GIFT_BY_KEY
        ),
        any(attempt.kept for attempt in today),
    )


async def todays_gifts(
    bot: "WispBot", guild_id: int, now: datetime
) -> GiftState | None:
    """The current life's gifts on the UTC day of `now`; None unless he is alive."""
    life_id = _living_id(await bot.lives.current(guild_id))
    return None if life_id is None else await _state(bot, guild_id, life_id, now)


def _label(bot: "WispBot", gift: Gift) -> str:
    """The gift's emoji, or its name when the emoji is not uploaded."""
    return bot.emoji(gift.emoji_name) or gift.name


def _stock(
    bot: "WispBot", state: GiftState, collection: GiftCollection, *, rich: bool
) -> str:
    """What is left of a collection: its gifts when `rich`, else how many."""
    in_stock = [gift for gift in collection.gifts if state.in_stock(gift)]
    if not in_stock:
        return "all kept this life"
    if not state.is_open(collection):
        return "back tomorrow"
    if not rich:
        return f"{len(in_stock)} left"
    return " ".join(_label(bot, gift) for gift in in_stock)


def gift_section(bot: "WispBot", state: GiftState | None, room: int) -> list[str]:
    """The Vault's Gifts lines: each collection's stock, or why it is shut.

    Once he has kept a gift today, a line says so before anyone pays. The
    lines take at most `room`, counted by `text_length`: a collection shows
    each gift while there is room, else how many are left.
    """
    price = count(GIFT_COST, "point")
    heading = f"{VAULT_RAIL}**Gifts**・{price} each・he might not like it"
    if state is None:
        return [heading, f"{VAULT_RAIL}He takes gifts once he has hatched"]
    head = [heading, *([_KEPT_TODAY] if state.kept_today else [])]

    def lines(rich: bool) -> list[str]:
        return [
            f"{VAULT_RAIL}{collection.name}: "
            + _stock(bot, state, collection, rich=rich)
            for collection in GIFT_COLLECTIONS
        ]

    left = room - text_length("\n".join(head)) - 1
    return [*head, *richest(lines(False), lines(True), left)]


def collection_options(
    bot: "WispBot", state: GiftState | None
) -> list[discord.SelectOption]:
    """A select option for every collection that can be given from now.

    Each shows its first gift's emoji and how many of its gifts are left.
    """
    if state is None:
        return []
    return [
        discord.SelectOption(
            label=collection.name,
            value=collection.key,
            description=f"{len(gifts)} left",
            emoji=bot.emojis_by_name.get(gifts[0].emoji_name),
        )
        for collection in GIFT_COLLECTIONS
        if (gifts := state.offered_from(collection))
    ]


def gift_options(
    bot: "WispBot", state: GiftState | None, collection: GiftCollection
) -> list[discord.SelectOption]:
    """A select option for every gift of `collection` that can be given now."""
    if state is None:
        return []
    return [
        discord.SelectOption(
            label=gift.title,
            value=gift.key,
            description=count(GIFT_COST, "point"),
            emoji=bot.emojis_by_name.get(gift.emoji_name),
        )
        for gift in state.offered_from(collection)
    ]


def _given_from_today(collection: GiftCollection) -> str:
    return (
        f"♪ Someone already gave Wisp {with_article(collection.item)} today. "
        "Back tomorrow."
    )


def closed_reason(state: GiftState | None, collection: GiftCollection) -> str | None:
    """Why nothing can be given from `collection` now, or None when it is open."""
    if state is None:
        return _NOT_HATCHED
    if not state.is_open(collection):
        return _given_from_today(collection)
    if not state.offered_from(collection):
        return f"♪ Wisp already kept every gift in {collection.name} this life."
    return None


# ---
# Giving
# ---


@dataclass(frozen=True)
class GiftGiven:
    """A gift Wisp was given: what he did with it, his life, the giver and bond."""

    gift: Gift
    outcome: Outcome
    completed: bool
    life: Life
    player: Player
    bond: int


async def give_gift(
    bot: "WispBot",
    rng: random.Random,
    guild_id: int,
    member: discord.User | discord.Member,
    gift: Gift,
    now: datetime,
) -> GiftGiven:
    """Spend the member's points on a gift and let Wisp decide on it.

    Call this under the guild lock. He passes when he already kept a gift
    today; otherwise `rng` decides. A kept gift gives bond outside the daily
    cap, a bond moment's growth, and the collection bonus when it finishes its
    collection. Every attempt counts as an interaction.

    Raises:
        Refusal: The member is banned, cannot feed Wisp or is short of points,
            Wisp is not alive, he already has the gift, or someone gave from
            its collection today. Nothing is spent then.
    """
    player = await check_member(bot, guild_id, member, now)
    life = await bot.lives.current(guild_id)
    life_id = _living_id(life)
    if life is None or life_id is None:
        raise Refusal(_NOT_HATCHED)
    state = await _state(bot, guild_id, life_id, now)
    collection = collection_of(gift)
    if not state.in_stock(gift):
        raise Refusal(f"♪ Wisp already has the {gift.title}.")
    if not state.is_open(collection):
        raise Refusal(_given_from_today(collection))
    if not await bot.players.spend(guild_id, member.id, GIFT_COST):
        name = player.name or member.display_name
        raise Refusal(bot.lines.pick(Moment.NOT_ENOUGH_POINTS, mood(life), name=name))
    outcome = decide(state, rng)
    kept = outcome is Outcome.KEPT
    completed = kept and state.completes(gift)
    bond = BOND_PER_KEPT_GIFT + (COLLECTION_BOND_BONUS if completed else 0)
    await bot.gifts.record(guild_id, life_id, member.id, gift.key, kept, now)
    await bot.activity_log.record_interaction(
        guild_id,
        life_id,
        member.id,
        InteractionKind.GIFT,
        BOND_PER_KEPT_GIFT if kept else 0,
        0,
        now,
    )
    if kept:
        await bot.players.add_bond(guild_id, member.id, bond)
        add_growth(life, GROWTH_PER_BOND_MOMENT)
        await bot.lives.save(guild_id, life)
    return GiftGiven(gift, outcome, completed, life, player, bond if kept else 0)


def gift_note(given: GiftGiven) -> str:
    """What happened to the gift, for the member who gave it."""
    title = given.gift.title
    if given.outcome is Outcome.FULL:
        return f"♪ Wisp already kept a gift today. Your {title} is back in the Vault."
    if given.outcome is Outcome.PASSED:
        return f"♪ Wisp passed on your {title}. It's back in the Vault."
    note = f"♪ Wisp kept your {title} ・ bond +{given.bond}"
    if given.completed:
        return f"{note} ・ {collection_of(given.gift).name} complete"
    return note


def _gift_art(gift: Gift) -> Path | None:
    """The gift's picture, when the art is on disk."""
    return asset_image(ASSETS_DIR / "gifts", gift.key)


async def announce_gift(
    bot: "WispBot", guild_id: int, given: GiftGiven, name: str
) -> None:
    """Tell Wisp's House about a gift, with its picture when he kept it."""
    feeling = mood(given.life)
    title = given.gift.title
    lines = [
        f"♪ {name} gave Wisp {with_article(title)}",
        bot.lines.pick(_MOMENTS[given.outcome], feeling, name=name, gift=title),
    ]
    if given.completed:
        collection = collection_of(given.gift).name
        lines.append(
            bot.lines.pick(
                Moment.COLLECTION_DONE, feeling, name=name, collection=collection
            )
        )
    kept = given.outcome is Outcome.KEPT
    if not kept:
        lines.append(_BACK_IN_VAULT)
    await post_in_house(
        bot, guild_id, "\n".join(lines), image=_gift_art(given.gift) if kept else None
    )


# ---
# Wisp's lunchbox
# ---


def collection_lines(
    bot: "WispBot", kept: Sequence[GiftAttempt], room: int
) -> list[str]:
    """One line per collection this life has kept gifts from, in catalog order.

    The lines take at most `room` characters: an unfinished collection lists
    its gifts and givers while there is room, else only its progress.
    """
    plain: list[str] = []
    rich: list[str] = []
    for collection in GIFT_COLLECTIONS:
        got = [
            (GIFT_BY_KEY[attempt.gift], attempt.user_id)
            for attempt in kept
            if attempt.gift in GIFT_BY_KEY
            and GIFT_BY_KEY[attempt.gift].collection == collection.key
        ]
        if not got:
            continue
        progress = f"・{collection.name} {len(got)}/{len(collection.gifts)}"
        if len(got) == len(collection.gifts):
            done = f"{progress} complete ・ finished by <@{got[-1][1]}>"
            plain.append(done)
            rich.append(done)
            continue
        items = (
            f"{with_emoji(bot.emoji(gift.emoji_name), gift.name)} (from <@{user_id}>)"
            for gift, user_id in got
        )
        plain.append(progress)
        rich.append(f"{progress} ・ {' ・ '.join(items)}")
    return richest(plain, rich, room)


async def setup(bot: "WispBot") -> None:
    """Load the Gifts cog."""
    await bot.add_cog(Gifts(bot))
