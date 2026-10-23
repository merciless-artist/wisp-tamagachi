"""The ViiBR Vault and lunchboxes: members buy snacks and feed them to Wisp."""

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.announce import say_in_house
from cogs.assets import ASSETS_DIR, COIN_EMOJI
from cogs.channels import where_of
from cogs.groups import require_guild, wisp
from cogs.players import (
    EXPECTED_FAILURES,
    bot_of,
    can_feed,
    maybe_meet,
    report_failure,
    say_privately,
)
from db.activity import InteractionKind
from db.players import Player
from wisp.bond import PickleStance, casual_bond_grant, meal_grant
from wisp.life import Life, Mood, Phase, add_growth, feed
from wisp.lines import Moment
from wisp.rules import BOND_PER_SNACK, FANCY_SNACK_COST, SNACKS, Snack
from wisp.text import SEPARATOR, count

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_FEED_ID: Final = "wisp:feed"
_VAULT_ID: Final = "wisp:vault"
_LUNCHBOX_ID: Final = "wisp:lunchbox"

_BANNED: Final = "♪ Wisp is not taking snacks from you right now."
_CANNOT_FEED: Final = (
    "♪ Only members at Active Lounger or higher who have opened /wisp board "
    "can feed Wisp."
)
_NOT_HATCHED: Final = "♪ Wisp isn't hatched yet. Snacks have to wait until he is."
_NO_SNACKS: Final = (
    "♪ You have no snacks. Buy some in the ViiBR Vault with /wisp vault."
)
_SINE_USED: Final = "♪ You've had today's free Sine Wave. A new one comes tomorrow."
_FULL: Final = "♪ Wisp is full from you today. Save it for tomorrow."

_FREE: Final = next(snack for snack in SNACKS if snack.cost == 0)
_MENU: Final = tuple(snack for snack in SNACKS if snack.cost > 0)
_BY_KEY: Final = {snack.key: snack for snack in SNACKS}
_PICKLES: Final = "pickles"
_MOMENTS: Final = {
    "spicywave": Moment.SPICY,
    "juicewave": Moment.JUICE,
    _PICKLES: Moment.PICKLE_HEDGE,
}
_CONTRARY: Final = {
    PickleStance.LOVE: (Moment.PICKLE_HATE, "eat_pickles_hate.gif"),
    PickleStance.HATE: (Moment.PICKLE_LOVE, "eat_pickles_love.gif"),
}

_Choice = Callable[[discord.Interaction, Snack], Awaitable[None]]
_Action = Callable[[discord.Interaction], Awaitable[None]]

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


async def _admit(interaction: discord.Interaction, *, feeding: bool = False) -> bool:
    """Acknowledge an interaction privately; False, after saying why, if turned away.

    Banned members are always turned away. When `feeding`, so are members who
    cannot feed Wisp.
    """
    await interaction.response.defer(ephemeral=True, thinking=True)
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    refusal = None
    if await _is_banned(bot, guild_id, interaction.user.id):
        refusal = _BANNED
    elif feeding and not await can_feed(bot, guild_id, interaction.user):
        refusal = _CANNOT_FEED
    if refusal is not None:
        await say_privately(interaction, refusal)
        return False
    return True


async def _press(
    interaction: discord.Interaction, context: str, action: _Action
) -> None:
    """Run what a persistent button does, reporting a failure.

    Persistent buttons have no error hook of their own, so the failures they can
    expect are caught here.
    """
    try:
        await action(interaction)
    except EXPECTED_FAILURES as error:
        await report_failure(interaction, context, error)


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
        """Report a failure and tell the member."""
        await report_failure(interaction, "the lunchbox", error)


# ---
# Buying
# ---


async def _vault_text(
    bot: "WispBot", guild_id: int, user_id: int, note: str | None = None
) -> str:
    """The balance and the Snack Box, after an optional note."""
    balance = (await bot.players.get(guild_id, user_id)).balance
    prices = [
        f"・{_named(bot, snack)} ・ {count(snack.cost, 'point')} ・ {_care(snack)}"
        for snack in _MENU
    ]
    lines = [
        "♪ The ViiBR Vault",
        _with_emoji(bot.emoji(COIN_EMOJI), count(balance, "point")),
        SEPARATOR,
        "Snack Box",
        *prices,
    ]
    return "\n".join([note, *lines] if note else lines)


async def _my_lunchbox_text(
    bot: "WispBot", guild_id: int, user_id: int, display_name: str
) -> str:
    """The member's balance, snacks and keepsakes."""
    player = await bot.players.get(guild_id, user_id)
    owned = await bot.activity_log.inventory(guild_id, user_id)
    free_left = not await bot.activity_log.free_snack_used_today(
        guild_id, user_id, discord.utils.utcnow()
    )
    snacks = [
        f"・{_named(bot, snack)} x{owned[snack.key]}"
        for snack in _MENU
        if snack.key in owned
    ]
    if free_left:
        snacks.append(f"・{_named(bot, _FREE)} ・ free today")
    keepsakes = [
        f"・{keepsake.title}" for keepsake in await bot.keepsakes.of(guild_id, user_id)
    ]
    lines = [
        f"♪ {player.name or display_name}'s lunchbox",
        _with_emoji(bot.emoji(COIN_EMOJI), count(player.balance, "point")),
        SEPARATOR,
        "Snacks",
        *(snacks or ["・Nothing saved yet"]),
        SEPARATOR,
        "Keepsakes",
        *(keepsakes or ["・None yet"]),
    ]
    return "\n".join(lines)


async def _buy(interaction: discord.Interaction, snack: Snack) -> None:
    """Spend the member's points on a snack, or say why they cannot.

    The interaction is acknowledged first so slow storage cannot make the
    purchase look failed after it went through. If the confirmation itself
    fails, the error posted says the purchase went through.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    await interaction.response.defer()
    player = await bot.players.get(guild_id, user.id)
    if player.is_banned(discord.utils.utcnow()):
        await say_privately(interaction, _BANNED)
    elif not await bot.players.spend(guild_id, user.id, snack.cost):
        line = bot.lines.pick(
            Moment.NOT_ENOUGH_POINTS,
            Mood.HAPPY,
            name=player.name or user.display_name,
        )
        await say_privately(interaction, line)
    else:
        await bot.activity_log.add_snack(guild_id, user.id, snack.key)
        note = f"♪ Bought {snack.name} for {count(snack.cost, 'point')}."
        try:
            await interaction.edit_original_response(
                content=await _vault_text(bot, guild_id, user.id, note),
                allowed_mentions=_NO_PING,
            )
        except EXPECTED_FAILURES as error:
            await bot.report_error(
                interaction.guild,
                "confirming a snack purchase (the purchase went through)",
                error,
                where=where_of(interaction),
            )


# ---
# The Vault and lunchboxes
# ---


async def _open_vault(interaction: discord.Interaction) -> None:
    """Show the Snack Box with a select to buy from it, only to the member."""
    if not await _admit(interaction):
        return
    bot = bot_of(interaction)
    options = [
        _option(
            bot, snack, snack.name, f"{count(snack.cost, 'point')} ・ {_care(snack)}"
        )
        for snack in _MENU
    ]
    await interaction.followup.send(
        await _vault_text(bot, require_guild(interaction), interaction.user.id),
        view=SnackMenu(options, "Buy a snack", _buy),
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


async def _open_lunchbox(interaction: discord.Interaction) -> None:
    """Show the member's own snacks and keepsakes, with a button to the shop."""
    if not await _admit(interaction):
        return
    view = discord.ui.View()
    view.add_item(ShopButton())
    await interaction.followup.send(
        await _my_lunchbox_text(
            bot_of(interaction),
            require_guild(interaction),
            interaction.user.id,
            interaction.user.display_name,
        ),
        view=view,
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


@wisp.command(name="vault", description="Buy snacks for Wisp in the ViiBR Vault.")
async def wisp_vault(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the Vault shop, only to the member."""
    await _open_vault(interaction)


@wisp.command(name="lunchbox", description="See your snacks and keepsakes.")
async def wisp_lunchbox(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the member's own lunchbox, only to them."""
    await _open_lunchbox(interaction)


class ShopButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_VAULT_ID),
):
    """The Shop the Vault button, which opens the shop for whoever presses it.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Shop the Vault",
                style=discord.ButtonStyle.primary,
                custom_id=_VAULT_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "ShopButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the Vault shop privately."""
        await _press(interaction, "the Vault shop button", _open_vault)


class LunchboxButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_LUNCHBOX_ID),
):
    """The Open my lunchbox button, which shows the presser their own lunchbox.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Open my lunchbox",
                style=discord.ButtonStyle.secondary,
                custom_id=_LUNCHBOX_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "LunchboxButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the presser's own lunchbox privately."""
        await _press(interaction, "the lunchbox button", _open_lunchbox)


def vault_view() -> discord.ui.View:
    """The view that puts the shop and lunchbox buttons on the Vault card."""
    view = discord.ui.View(timeout=None)
    view.add_item(ShopButton())
    view.add_item(LunchboxButton())
    return view


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
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    snack: Snack,
    now: datetime,
) -> _Meal:
    """Take the snack and apply it to Wisp. Call this under the guild lock.

    Raises:
        _Refusal: The member is banned or cannot feed Wisp, Wisp is not alive,
            the free snack is used up for today, the member has had their
            meals for today or has none of this snack. Nothing is taken then.
    """
    log = bot.activity_log
    user_id = member.id
    player = await bot.players.get(guild_id, user_id)
    if player.is_banned(now):
        raise _Refusal(_BANNED)
    if not await can_feed(bot, guild_id, member):
        raise _Refusal(_CANNOT_FEED)
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or life.phase is not Phase.ALIVE:
        raise _Refusal(_NOT_HATCHED)
    if snack == _FREE and await log.free_snack_used_today(guild_id, user_id, now):
        raise _Refusal(_SINE_USED)
    care = meal_grant(await log.meal_points_today(guild_id, user_id, now), snack.care)
    if care == 0:
        raise _Refusal(_FULL)
    if snack == _FREE:
        kind = InteractionKind.FREE_SNACK
    elif await log.take_snack(guild_id, user_id, snack.key):
        kind = InteractionKind.SNACK
    else:
        raise _Refusal(f"♪ You're out of {snack.name}.")
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


def _reaction(snack: Snack, stance: PickleStance | None) -> tuple[Moment, str]:
    """The moment Wisp reacts with and the name of his eating GIF.

    Pickles go the other way from the member's stance; every other snack ignores it.
    """
    if snack.key == _PICKLES and stance is not None:
        return _CONTRARY[stance]
    return _moment(snack), snack.gif_name


def _eating_gif(gif_name: str) -> Path | None:
    """The GIF of Wisp eating, when the art is on disk."""
    path = ASSETS_DIR / "eating" / gif_name
    return path if path.is_file() else None


async def _feed(interaction: discord.Interaction, snack: Snack) -> None:
    """Feed Wisp the chosen snack, tell the member, then show it in his House."""
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    await interaction.response.defer()
    try:
        async with bot.guild_lock(guild_id):
            meal = await _eat(bot, guild_id, user, snack, discord.utils.utcnow())
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
    moment, gif_name = _reaction(snack, meal.player.pickle_stance)
    await say_in_house(
        bot,
        guild_id,
        moment,
        meal.life,
        name=meal.player.name or user.display_name,
        prefix=f"{emoji} " if emoji else "",
        image=_eating_gif(gif_name),
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


async def _offer_snacks(interaction: discord.Interaction) -> None:
    """Show the member what they can feed Wisp, or say they have nothing."""
    if not await _admit(interaction, feeding=True):
        return
    menu = await _feed_menu(
        bot_of(interaction), require_guild(interaction), interaction.user.id
    )
    if menu is None:
        await say_privately(interaction, _NO_SNACKS)
        return
    await interaction.followup.send(
        "♪ What should Wisp eat?",
        view=menu,
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


class FeedButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_FEED_ID),
):
    """The Feed Wisp button on the status card, for every member who can feed Wisp.

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
        """Offer the snacks the member can feed Wisp right now."""
        await _press(interaction, "the Feed Wisp button", _offer_snacks)


def feed_view() -> discord.ui.View:
    """The view that puts the Feed Wisp button on the status card."""
    view = discord.ui.View(timeout=None)
    view.add_item(FeedButton())
    return view


async def setup(bot: "WispBot") -> None:
    """Register the persistent buttons so they still work after a restart."""
    bot.add_dynamic_items(FeedButton, ShopButton, LunchboxButton)
