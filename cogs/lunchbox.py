"""The lunchbox: members buy snacks with points and feed them to Wisp."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.announce import ASSETS_DIR, say_in_house
from cogs.groups import require_guild, wisp
from cogs.players import EXPECTED_FAILURES, bot_of, maybe_meet, report_failure
from db.activity import InteractionKind
from db.players import Player
from wisp.bond import casual_bond_grant, meal_grant
from wisp.life import Life, Mood, Phase, add_growth, feed
from wisp.lines import Moment
from wisp.rules import BOND_PER_SNACK, FANCY_SNACK_COST, SNACKS, Snack
from wisp.text import SEPARATOR, count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_COIN: Final = "wisp_coin"
_FEED_ID: Final = "wisp:feed"

_BANNED: Final = "♪ Wisp is not taking snacks from you right now."
_NOT_HATCHED: Final = "♪ Wisp isn't hatched yet. Snacks have to wait until he is."
_NO_SNACKS: Final = "♪ You have no snacks. Buy some with /wisp lunchbox."
_SINE_USED: Final = "♪ You've had today's free Sine Wave. A new one comes tomorrow."

_FREE: Final = next(snack for snack in SNACKS if snack.cost == 0)
_MENU: Final = tuple(snack for snack in SNACKS if snack.cost > 0)
_BY_KEY: Final = {snack.key: snack for snack in SNACKS}
_MOMENTS: Final = {
    "spicywave": Moment.SPICY,
    "juicewave": Moment.JUICE,
    "pickles": Moment.PICKLE_HEDGE,
}

_Choice = Callable[[discord.Interaction, Snack], Awaitable[None]]

# ---
# Shared pieces
# ---


def _with_emoji(emoji: str, text: str) -> str:
    return f"{emoji} {text}" if emoji else text


def _care(snack: Snack) -> str:
    return f"care +{snack.care}"


def _named(bot: "WispBot", snack: Snack) -> str:
    return _with_emoji(bot.emoji(snack.emoji_name), snack.name)


def _option(
    bot: "WispBot", snack: Snack, label: str, description: str
) -> discord.SelectOption:
    return discord.SelectOption(
        label=label,
        value=snack.key,
        description=description,
        emoji=bot.emojis_by_name.get(snack.emoji_name),
    )


async def _is_banned(bot: "WispBot", guild_id: int, user_id: int) -> bool:
    player = await bot.players.get(guild_id, user_id)
    return player.is_banned(discord.utils.utcnow())


async def _say(interaction: discord.Interaction, text: str) -> None:
    """Answer a deferred interaction with a plain private message."""
    await interaction.followup.send(text, ephemeral=True, allowed_mentions=_NO_PING)


class SnackSelect(discord.ui.Select["SnackMenu"]):
    """A select of snacks that hands the chosen one to its handler."""

    def __init__(
        self, options: list[discord.SelectOption], placeholder: str, on_choice: _Choice
    ) -> None:
        super().__init__(placeholder=placeholder, options=options)
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen snack on."""
        await self._on_choice(interaction, _BY_KEY[self.values[0]])


class SnackMenu(discord.ui.View):
    """An ephemeral menu with one select of snacks."""

    def __init__(
        self, options: list[discord.SelectOption], placeholder: str, on_choice: _Choice
    ) -> None:
        super().__init__()
        self.add_item(SnackSelect(options, placeholder, on_choice))

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        """Report a failure to staff and tell the member."""
        await report_failure(interaction, "the lunchbox", error)


# ---
# Buying
# ---


async def _lunchbox_text(
    bot: "WispBot", guild_id: int, user_id: int, note: str | None = None
) -> str:
    """The balance, the Snack Box and the member's snacks, after an optional note."""
    balance = (await bot.players.get(guild_id, user_id)).balance
    owned = await bot.activity_log.inventory(guild_id, user_id)
    prices = [
        f"・{_named(bot, snack)} ・ {count(snack.cost, 'point')} ・ {_care(snack)}"
        for snack in _MENU
    ]
    snacks = [
        f"・{_named(bot, snack)} x{owned[snack.key]}"
        for snack in _MENU
        if snack.key in owned
    ] or ["・Nothing yet"]
    lines = [
        "♪ The Lunchbox",
        _with_emoji(bot.emoji(_COIN), count(balance, "point")),
        SEPARATOR,
        "Snack Box",
        *prices,
        SEPARATOR,
        "Your snacks",
        *snacks,
    ]
    return "\n".join([note, *lines] if note else lines)


async def _buy(interaction: discord.Interaction, snack: Snack) -> None:
    """Spend the member's points on a snack, or say why they cannot.

    The interaction is acknowledged first so slow storage cannot make the
    purchase look failed after it went through. If the confirmation itself
    fails, staff are told the purchase went through.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    await interaction.response.defer()
    player = await bot.players.get(guild_id, user.id)
    if player.is_banned(discord.utils.utcnow()):
        await _say(interaction, _BANNED)
    elif not await bot.players.spend(guild_id, user.id, snack.cost):
        line = bot.lines.pick(
            Moment.NOT_ENOUGH_POINTS,
            Mood.HAPPY,
            name=player.name or user.display_name,
        )
        await _say(interaction, line)
    else:
        await bot.activity_log.add_snack(guild_id, user.id, snack.key)
        note = f"♪ Bought {snack.name} for {count(snack.cost, 'point')}."
        try:
            await interaction.edit_original_response(
                content=await _lunchbox_text(bot, guild_id, user.id, note),
                allowed_mentions=_NO_PING,
            )
        except EXPECTED_FAILURES as error:
            await bot.report_error(
                interaction.guild,
                "confirming a snack purchase (the purchase went through)",
                error,
            )


@wisp.command(name="lunchbox", description="Buy snacks for Wisp and see yours.")
async def wisp_lunchbox(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the Snack Box with a select to buy from it, only to the member."""
    bot = interaction.client
    guild_id = require_guild(interaction)
    user_id = interaction.user.id
    await interaction.response.defer(ephemeral=True)
    if await _is_banned(bot, guild_id, user_id):
        await _say(interaction, _BANNED)
        return
    options = [
        _option(
            bot, snack, snack.name, f"{count(snack.cost, 'point')} ・ {_care(snack)}"
        )
        for snack in _MENU
    ]
    await interaction.followup.send(
        await _lunchbox_text(bot, guild_id, user_id),
        view=SnackMenu(options, "Buy a snack", _buy),
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


# ---
# Feeding
# ---


class _Refusal(Exception):
    """A reason the member cannot feed Wisp right now, worded for them."""


@dataclass(frozen=True)
class _Meal:
    """A snack Wisp has eaten: his life afterwards, the feeder and the care it gave."""

    life: Life
    player: Player
    care: int


async def _eat(
    bot: "WispBot", guild_id: int, user_id: int, snack: Snack, now: datetime
) -> _Meal:
    """Take the snack and apply it to Wisp. Call this under the guild lock.

    Raises:
        _Refusal: The member is banned, Wisp is not alive, the free snack is
            used up for today or the member has none of this snack.
    """
    log = bot.activity_log
    player = await bot.players.get(guild_id, user_id)
    if player.is_banned(now):
        raise _Refusal(_BANNED)
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or life.phase is not Phase.ALIVE:
        raise _Refusal(_NOT_HATCHED)
    if snack == _FREE:
        if await log.free_snack_used_today(guild_id, user_id, now):
            raise _Refusal(_SINE_USED)
        kind = InteractionKind.FREE_SNACK
    elif await log.take_snack(guild_id, user_id, snack.key):
        kind = InteractionKind.SNACK
    else:
        raise _Refusal(f"♪ You're out of {snack.name}.")
    care = meal_grant(await log.meal_points_today(guild_id, user_id, now), snack.care)
    bond = casual_bond_grant(
        await log.casual_bond_today(guild_id, user_id, now), BOND_PER_SNACK
    )
    feed(life, care, user_id, now)
    add_growth(life, snack.growth)
    if bond:
        await bot.players.add_bond(guild_id, user_id, bond)
    await log.record_interaction(guild_id, life.id, user_id, kind, bond, care, now)
    await bot.lives.save(guild_id, life)
    return _Meal(life, player, care)


def _moment(snack: Snack) -> Moment:
    if snack.key in _MOMENTS:
        return _MOMENTS[snack.key]
    return Moment.SNACK_FANCY if snack.cost >= FANCY_SNACK_COST else Moment.SNACK


def _eating_gif(snack: Snack) -> Path | None:
    """The GIF of Wisp eating this snack; pickles wait for his stance on them."""
    if _moment(snack) is Moment.PICKLE_HEDGE:
        return None
    path = ASSETS_DIR / "eating" / snack.gif_name
    return path if path.is_file() else None


async def _feed(interaction: discord.Interaction, snack: Snack) -> None:
    """Feed Wisp the chosen snack, tell the member, then show it in his House."""
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    await interaction.response.defer()
    try:
        async with bot.guild_lock(guild_id):
            meal = await _eat(bot, guild_id, user.id, snack, discord.utils.utcnow())
    except _Refusal as refusal:
        await interaction.edit_original_response(
            content=str(refusal), view=None, allowed_mentions=_NO_PING
        )
        return
    text = f"♪ Wisp ate your {snack.name} ・ care +{meal.care}"
    if meal.care < snack.care:
        text += " (daily meal limit)"
    await interaction.edit_original_response(
        content=text, view=None, allowed_mentions=_NO_PING
    )
    emoji = bot.emoji(snack.emoji_name)
    await say_in_house(
        bot,
        guild_id,
        _moment(snack),
        meal.life,
        name=meal.player.name or user.display_name,
        prefix=f"{emoji} " if emoji else "",
        image=_eating_gif(snack),
    )
    await maybe_meet(bot, guild_id, user.id, display_name=user.display_name)


async def _feed_menu(bot: "WispBot", guild_id: int, user_id: int) -> SnackMenu | None:
    """A menu of what the member can feed Wisp now, or None when nothing."""
    owned = await bot.activity_log.inventory(guild_id, user_id)
    options = [
        _option(bot, snack, f"{snack.name} x{owned[snack.key]}", _care(snack))
        for snack in _MENU
        if snack.key in owned
    ]
    if not await bot.activity_log.free_snack_used_today(
        guild_id, user_id, discord.utils.utcnow()
    ):
        free = _option(bot, _FREE, f"{_FREE.name} (free today)", _care(_FREE))
        options.insert(0, free)
    return SnackMenu(options, "Pick a snack", _feed) if options else None


class FeedButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_FEED_ID),
):
    """The Feed Wisp button on the status card, which works for everyone.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Feed Wisp",
                style=discord.ButtonStyle.success,
                custom_id=_FEED_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "FeedButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Offer the snacks the member can feed Wisp right now.

        The interaction is acknowledged first. Persistent buttons have no error
        hook, so a failure is reported to staff here.
        """
        bot = bot_of(interaction)
        guild_id = require_guild(interaction)
        user_id = interaction.user.id
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
            if await _is_banned(bot, guild_id, user_id):
                await _say(interaction, _BANNED)
                return
            menu = await _feed_menu(bot, guild_id, user_id)
            if menu is None:
                await _say(interaction, _NO_SNACKS)
                return
            await interaction.followup.send(
                "♪ What should Wisp eat?",
                view=menu,
                ephemeral=True,
                allowed_mentions=_NO_PING,
            )
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, "the Feed Wisp button", error)


def feed_view() -> discord.ui.View:
    """The view that puts the Feed Wisp button on the status card."""
    view = discord.ui.View(timeout=None)
    view.add_item(FeedButton())
    return view


async def setup(bot: "WispBot") -> None:
    """Register the Feed Wisp button so it still works after a restart."""
    bot.add_dynamic_items(FeedButton)
