"""The ViiBR Vault, Snack Packs and the Feed button: snacks and gifts for Wisp."""

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
from cogs.gifts import (
    announce_gift,
    closed_reason,
    collection_options,
    gift_note,
    gift_options,
    gift_rng,
    gift_section,
    give_gift,
    todays_gifts,
)
from cogs.groups import require_guild, wisp
from cogs.players import (
    CANNOT_FEED,
    EXPECTED_FAILURES,
    NOT_TAKING,
    Refusal,
    bot_of,
    can_feed,
    check_member,
    maybe_meet,
    report_failure,
    say_privately,
)
from db.activity import InteractionKind
from db.players import Player
from wisp.bond import PickleStance, casual_bond_grant, meal_grant
from wisp.gifts import GiftState
from wisp.life import Life, Mood, Phase, add_growth, feed
from wisp.lines import Moment
from wisp.rules import (
    BOND_PER_SNACK,
    COLLECTION_BY_KEY,
    FANCY_SNACK_COST,
    GIFT_BY_KEY,
    PAID_SNACKS,
    SNACK_BY_KEY,
    SNACKS,
    Gift,
    GiftCollection,
    Snack,
)
from wisp.text import MESSAGE_LIMIT, SEPARATOR, count, fit, with_emoji

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_FEED_ID: Final = "wisp:feed"
_VAULT_ID: Final = "wisp:vault"
_SNACK_PACK_ID: Final = "wisp:snackpack"

_NOT_HATCHED: Final = "♪ Wisp isn't hatched yet. Snacks have to wait until he is."
_NO_SNACKS: Final = (
    "♪ You have no snacks. Buy some in the ViiBR Vault with /wisp vault."
)
_SINE_USED: Final = "♪ You've had today's free Sine Wave. A new one comes tomorrow."
_FULL: Final = "♪ Wisp is full from you today. Save it for tomorrow."

_FREE: Final = next(snack for snack in SNACKS if snack.cost == 0)
_MENU: Final = PAID_SNACKS
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

_SnackChoice = Callable[[discord.Interaction, Snack], Awaitable[None]]
_GiftChoice = Callable[[discord.Interaction, Gift], Awaitable[None]]
_CollectionChoice = Callable[[discord.Interaction, GiftCollection], Awaitable[None]]
_Action = Callable[[discord.Interaction], Awaitable[None]]

# ---
# Shared pieces
# ---


def _care(snack: Snack) -> str:
    return f"care +{snack.care}"


def _named(bot: "WispBot", snack: Snack) -> str:
    return with_emoji(bot.emoji(snack.emoji_name), snack.name)


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
        refusal = NOT_TAKING
    elif feeding and not await can_feed(bot, guild_id, interaction.user):
        refusal = CANNOT_FEED
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


class SnackSelect(discord.ui.Select["Menu"]):
    """A select of snacks that hands the chosen one to its handler."""

    def __init__(
        self,
        options: list[discord.SelectOption],
        placeholder: str,
        on_choice: _SnackChoice,
    ) -> None:
        super().__init__(placeholder=placeholder, options=options)
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen snack on."""
        await self._on_choice(interaction, SNACK_BY_KEY[self.values[0]])


class CollectionSelect(discord.ui.Select["Menu"]):
    """The Vault's select of gift collections; hands the chosen one on."""

    def __init__(
        self, options: list[discord.SelectOption], on_choice: _CollectionChoice
    ) -> None:
        super().__init__(placeholder="Pick a collection", options=options)
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen collection on."""
        await self._on_choice(interaction, COLLECTION_BY_KEY[self.values[0]])


class GiftSelect(discord.ui.Select["Menu"]):
    """The Vault's select of one collection's gifts; hands the chosen one on."""

    def __init__(
        self, options: list[discord.SelectOption], on_choice: _GiftChoice
    ) -> None:
        super().__init__(placeholder="Give Wisp a gift", options=options)
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen gift on."""
        await self._on_choice(interaction, GIFT_BY_KEY[self.values[0]])


class Menu(discord.ui.View):
    """An ephemeral menu of selects; a failure is reported as `context`."""

    def __init__(self, context: str, *selects: discord.ui.Select["Menu"]) -> None:
        super().__init__()
        self._context = context
        for select in selects:
            self.add_item(select)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        """Report a failure and tell the member."""
        await report_failure(interaction, self._context, error)


# ---
# Buying
# ---


async def _vault_text(
    bot: "WispBot",
    guild_id: int,
    user_id: int,
    gifts: GiftState | None,
    note: str | None,
) -> str:
    """The balance, the Snack Box and the Gifts, after an optional note.

    The Gifts take whatever room the rest of one message leaves.
    """
    balance = (await bot.players.get(guild_id, user_id)).balance
    prices = [
        f"・{_named(bot, snack)} ・ {count(snack.cost, 'point')} ・ {_care(snack)}"
        for snack in _MENU
    ]
    head = [
        *([note] if note else []),
        "♪ The ViiBR Vault",
        with_emoji(bot.emoji(COIN_EMOJI), count(balance, "point")),
        SEPARATOR,
        "Snack Box",
        *prices,
        "",
    ]
    room = MESSAGE_LIMIT - len("\n".join(head)) - 1
    return "\n".join([*head, *gift_section(bot, gifts, room)])


async def _vault(
    bot: "WispBot",
    guild_id: int,
    user_id: int,
    note: str | None = None,
    collection: GiftCollection | None = None,
) -> tuple[str, Menu]:
    """The Vault's text, after an optional note, and its menu.

    The menu has the snack select, plus the collection select when a gift can
    be given today. With a picked `collection` that can still be given from,
    it also has that collection's gift select.
    """
    gifts = await todays_gifts(bot, guild_id, discord.utils.utcnow())
    snack_options = [
        _option(
            bot, snack, snack.name, f"{count(snack.cost, 'point')} ・ {_care(snack)}"
        )
        for snack in _MENU
    ]
    selects: list[discord.ui.Select[Menu]] = [
        SnackSelect(snack_options, "Buy a snack", _buy)
    ]
    if collection_choices := collection_options(bot, gifts):
        selects.append(CollectionSelect(collection_choices, _pick_collection))
    if collection is not None and (
        gift_choices := gift_options(bot, gifts, collection)
    ):
        selects.append(GiftSelect(gift_choices, _give))
    text = await _vault_text(bot, guild_id, user_id, gifts, note)
    return text, Menu("the ViiBR Vault menu", *selects)


async def _confirm(
    interaction: discord.Interaction,
    note: str | None,
    context: str,
    collection: GiftCollection | None = None,
    *,
    tell_member: bool = False,
) -> None:
    """Show the Vault again under `note`; a failure is reported as `context`.

    With a picked `collection`, its gift select is shown too. A failure never
    reaches the caller, so whatever follows the confirmation, such as
    announcing a gift, still happens. With `tell_member`, the member is also
    told it failed, for when nothing else would answer them.
    """
    bot = bot_of(interaction)
    try:
        text, menu = await _vault(
            bot, require_guild(interaction), interaction.user.id, note, collection
        )
        await interaction.edit_original_response(
            content=text, view=menu, allowed_mentions=_NO_PING
        )
    except EXPECTED_FAILURES as error:
        if tell_member:
            await report_failure(interaction, context, error)
            return
        await bot.report_error(
            interaction.guild, context, error, where=where_of(interaction)
        )


async def _snack_pack_text(
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
    head = [
        f"♪ {player.name or display_name}'s Snack Pack",
        with_emoji(bot.emoji(COIN_EMOJI), count(player.balance, "point")),
        SEPARATOR,
        "Snacks",
        *(snacks or ["・Nothing saved yet"]),
        SEPARATOR,
        "Keepsakes",
    ]
    held = await bot.keepsakes.of(guild_id, user_id)
    if not held:
        return "\n".join([*head, "・None yet"])
    newest_life_first = sorted(held, key=lambda keepsake: -keepsake.version)
    keepsakes = [
        f"・{with_emoji(bot.emoji(f'keepsake_{keepsake.kind.value}'), keepsake.title)}"
        for keepsake in newest_life_first
    ]
    return _fit_keepsakes(head, keepsakes)


def _fit_keepsakes(head: list[str], keepsakes: list[str]) -> str:
    """The Snack Pack with as many keepsakes as fit, then how many more there are."""
    whole = "\n".join([*head, *keepsakes])
    if len(whole) <= MESSAGE_LIMIT:
        return whole
    widest_tail = [f"・and {len(keepsakes)} more"]
    shown = fit(head, keepsakes, widest_tail).count("\n") - len(head)
    return "\n".join(
        [*head, *keepsakes[:shown], f"・and {len(keepsakes) - shown} more"]
    )


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
        await say_privately(interaction, NOT_TAKING)
    elif not await bot.players.spend(guild_id, user.id, snack.cost):
        line = bot.lines.pick(
            Moment.NOT_ENOUGH_POINTS,
            Mood.HAPPY,
            name=player.name or user.display_name,
        )
        await say_privately(interaction, line)
    else:
        await bot.activity_log.add_snack(guild_id, user.id, snack.key)
        await _confirm(
            interaction,
            f"♪ Bought {snack.name} for {count(snack.cost, 'point')}.",
            "confirming a snack purchase (the purchase went through)",
        )


async def _pick_collection(
    interaction: discord.Interaction, collection: GiftCollection
) -> None:
    """Show the Vault again with the picked collection's gifts to choose from.

    A collection nobody can give from any more, such as one someone gave
    from a moment ago, is refused with the reason and the Vault as it is now.
    """
    bot = bot_of(interaction)
    await interaction.response.defer()
    state = await todays_gifts(bot, require_guild(interaction), discord.utils.utcnow())
    reason = closed_reason(state, collection)
    if reason is not None:
        await _confirm(
            interaction,
            reason,
            "showing a closed gift collection",
            tell_member=True,
        )
        return
    await _confirm(
        interaction,
        None,
        "showing a gift collection",
        collection,
        tell_member=True,
    )


async def _give(interaction: discord.Interaction, gift: Gift) -> None:
    """Spend the member's points on a gift for Wisp, then show what he did with it.

    The reply shows the Vault again under the result, or under the reason the
    gift was refused. A given gift is announced in his House. If the
    confirmation fails, the error posted says the gift went through.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    await interaction.response.defer()
    try:
        async with bot.guild_lock(guild_id):
            given = await give_gift(
                bot, gift_rng(bot), guild_id, user, gift, discord.utils.utcnow()
            )
    except Refusal as refusal:
        await _confirm(interaction, str(refusal), "showing a refused gift")
        return
    await _confirm(
        interaction, gift_note(given), "confirming a gift (the gift went through)"
    )
    await announce_gift(bot, guild_id, given, given.player.name or user.display_name)
    await maybe_meet(bot, guild_id, user.id, display_name=user.display_name)


# ---
# The Vault and Snack Packs
# ---


async def _open_vault(interaction: discord.Interaction) -> None:
    """Show the Snack Box and the Gifts with selects to buy, only to the member."""
    if not await _admit(interaction):
        return
    text, menu = await _vault(
        bot_of(interaction), require_guild(interaction), interaction.user.id
    )
    await interaction.followup.send(
        text, view=menu, ephemeral=True, allowed_mentions=_NO_PING
    )


async def _open_snack_pack(interaction: discord.Interaction) -> None:
    """Show the member's own snacks and keepsakes, with a button to the shop."""
    if not await _admit(interaction):
        return
    view = discord.ui.View()
    view.add_item(ShopButton())
    await interaction.followup.send(
        await _snack_pack_text(
            bot_of(interaction),
            require_guild(interaction),
            interaction.user.id,
            interaction.user.display_name,
        ),
        view=view,
        ephemeral=True,
        allowed_mentions=_NO_PING,
    )


@wisp.command(
    name="vault", description="Buy snacks and gifts for Wisp in the ViiBR Vault."
)
async def wisp_vault(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the Vault shop, only to the member."""
    await _open_vault(interaction)


@wisp.command(name="snackpack", description="See your snacks and keepsakes.")
async def wisp_snackpack(interaction: discord.Interaction["WispBot"]) -> None:
    """Show the member's own Snack Pack, only to them."""
    await _open_snack_pack(interaction)


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


class SnackPackButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_SNACK_PACK_ID),
):
    """The Open my Snack Pack button, which shows the presser their own Snack Pack.

    Its custom id is fixed, so the button keeps working after the bot restarts.
    """

    def __init__(self) -> None:
        super().__init__(
            discord.ui.Button(
                label="Open my Snack Pack",
                style=discord.ButtonStyle.secondary,
                custom_id=_SNACK_PACK_ID,
            )
        )

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "SnackPackButton":
        """Rebuild the button after a restart."""
        return cls()

    async def callback(self, interaction: discord.Interaction) -> None:
        """Open the presser's own Snack Pack privately."""
        await _press(interaction, "the Snack Pack button", _open_snack_pack)


def vault_view() -> discord.ui.View:
    """The view that puts the shop and Snack Pack buttons on the Vault card."""
    view = discord.ui.View(timeout=None)
    view.add_item(ShopButton())
    view.add_item(SnackPackButton())
    return view


# ---
# Feeding
# ---


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
        Refusal: The member is banned or cannot feed Wisp, Wisp is not alive,
            the free snack is used up for today, the member has had their
            meals for today or has none of this snack. Nothing is taken then.
    """
    log = bot.activity_log
    user_id = member.id
    player = await check_member(bot, guild_id, member, now)
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or life.phase is not Phase.ALIVE:
        raise Refusal(_NOT_HATCHED)
    if snack == _FREE and await log.free_snack_used_today(guild_id, user_id, now):
        raise Refusal(_SINE_USED)
    care = meal_grant(await log.meal_points_today(guild_id, user_id, now), snack.care)
    if care == 0:
        raise Refusal(_FULL)
    if snack == _FREE:
        kind = InteractionKind.FREE_SNACK
    elif await log.take_snack(guild_id, user_id, snack.key):
        kind = InteractionKind.SNACK
    else:
        raise Refusal(f"♪ You're out of {snack.name}.")
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


def _reaction(
    snack: Snack, stance: PickleStance | None, favorite: str | None
) -> tuple[Moment, str]:
    """The moment Wisp reacts with and the name of his eating GIF.

    His favorite snack always gets its own line. Otherwise pickles go the other
    way from the member's stance; every other snack ignores it.
    """
    if snack.key == favorite:
        return Moment.SNACK_FAVORITE, snack.gif_name
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
    except Refusal as refusal:
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
    moment, gif_name = _reaction(
        snack, meal.player.pickle_stance, meal.life.favorite_snack
    )
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


async def _feed_menu(bot: "WispBot", guild_id: int, user_id: int) -> Menu | None:
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
    if not options:
        return None
    return Menu("the snack menu", SnackSelect(options, "Pick a snack", _feed))


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
    bot.add_dynamic_items(FeedButton, ShopButton, SnackPackButton)
