"""The ViiBR Vault, Snack Packs and the Feed button: snacks and gifts for Wisp."""

import functools
import re
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import aiohttp
import discord

from cogs.announce import post_in_house, say_in_house
from cogs.assets import ASSETS_DIR, moment_image
from cogs.badges import (
    Offer,
    badge_offers,
    badge_options,
    badge_pack_lines,
    badge_role,
    badge_section,
)
from cogs.channels import where_of
from cogs.conversation import PokeButton
from cogs.drawings import draw_for
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
from cogs.headers import FOOTER, gallery, gallery_files, send_headed
from cogs.magazines import (
    cover_art,
    magazine_options,
    magazine_pack_lines,
    magazine_section,
    magazines_owned,
    on_the_shelf,
)
from cogs.menus import ClosedMenu, menu_id
from cogs.players import (
    EXPECTED_FAILURES,
    NOT_TAKING,
    Blocker,
    Refusal,
    bot_of,
    check_member,
    maybe_meet,
    member_blocker,
    no_wisp_text,
    press,
    refusal_text,
    report_failure,
    require_unfrozen,
    say_privately,
    too_poor_text,
)
from db.activity import InteractionKind
from db.keepsakes import Keepsake
from db.players import Player
from wisp.bond import (
    PickleStance,
    casual_bond_grant,
    daily_meal_cap,
    meal_grant,
    tier_for,
)
from wisp.chores import is_napping
from wisp.gifts import GiftState, Outcome
from wisp.life import (
    Life,
    Meter,
    Mood,
    Phase,
    add_growth,
    change_meter,
    cure_sniffles,
    has_sniffles,
    is_over,
    mood,
)
from wisp.lines import Moment
from wisp.rules import (
    BADGE_BY_KEY,
    BOND_PER_SNACK,
    COLLECTION_BY_KEY,
    FANCY_SNACK_COST,
    GIFT_BY_KEY,
    MAGAZINE_BY_KEY,
    MAGAZINE_COST,
    MEDICINE_COST,
    MEDICINE_EMOJI,
    MEDICINE_PICTURE,
    MEDICINE_POINTS,
    PAID_SNACKS,
    SNACK_BY_KEY,
    SNACKS,
    WELLBEING_PER_SNACK,
    Badge,
    Gift,
    GiftCollection,
    Magazine,
    Snack,
)
from wisp.text import (
    BLANK,
    LAYOUT_TEXT_LIMIT,
    MESSAGE_LIMIT,
    SECTION_BREAK,
    SUB_MARK,
    box_bottom,
    box_top,
    heading,
    item,
    meter_receipt,
    sub,
    text_length,
    with_emoji,
    wrapped,
)
from wisp.voice import COIN_EMOJI, MINI_COIN_EMOJI, DrawReason

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_FEED_ID: Final = "wisp:feed"
_VAULT_ID: Final = "wisp:vault"
_SNACK_PACK_ID: Final = "wisp:snackpack"

_NO_SNACKS: Final = (
    "♪ You have no snacks. Buy some in the ViiBR Vault with /wisp vault."
)
_SINE_USED: Final = "♪ You've had today's free Sine Wave. A new one comes tomorrow."
_FULL: Final = "♪ Wisp is full from you today. Save it for tomorrow."
_NO_WISP: Final = "♪ There's no Wisp to wear a badge for right now."
_NO_COLD: Final = "♪ Wisp doesn't have a cold right now."
_BADGE_NOT_READY: Final = (
    "♪ That badge isn't ready yet. Staff can set it up with !wisp setup."
)
_SHELF_EMPTY: Final = "♪ The magazines are gone from the shelf."
_NONE_YET: Final = item("none yet")
_NOTHING_SAVED: Final = item("nothing saved yet")
_VAULT_HEADER: Final = "vault_title.png"
_PACK_HEADER: Final = "snack_pack_title.png"
# Wide enough for the widest badge row, from its name and padding to its price.
VAULT_WIDTH: Final = 24
_VAULT_CONTEXT: Final = "the ViiBR Vault menu"
# Spaces after each snack's name in the Vault, tuned by Myra so the │ line up.
_VAULT_PADDING: Final[dict[str, int]] = {
    "sinewave": 4,
    "cloudwave": 1,
    "jellywave": 4,
    "juicewave": 3,
    "spicywave": 2,
    "cheese": 8,
    "pickles": 8,
    "glitterwave": 0,
    "viibrwave": 3,
}
_ROLE_REASON: Final = "Bought in the ViiBR Vault"
_ROLE_FAILURES: Final = (
    discord.HTTPException,
    aiohttp.ClientError,
    OSError,
    TimeoutError,
)

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
_BadgeChoice = Callable[[discord.Interaction, Badge], Awaitable[None]]
_MagazineChoice = Callable[[discord.Interaction, Magazine], Awaitable[None]]

# ---
# Shared pieces
# ---


def _wellbeing_gain() -> str:
    return f"wellbeing +{WELLBEING_PER_SNACK}"


def _coins(bot: "WispBot", text: str) -> str:
    """`text` after the small wisp coin, when it is uploaded."""
    return with_emoji(bot.emoji(MINI_COIN_EMOJI), text)


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
    now = discord.utils.utcnow()
    if feeding:
        blocker = await member_blocker(bot, guild_id, interaction.user, now)
    else:
        banned = await _is_banned(bot, guild_id, interaction.user.id)
        blocker = Blocker.BANNED if banned else None
    if blocker is not None:
        await say_privately(interaction, refusal_text(blocker))
        return False
    return True


class SnackSelect(discord.ui.Select[Any]):
    """A select of snacks that hands the chosen one to its handler."""

    def __init__(
        self,
        options: list[discord.SelectOption],
        placeholder: str,
        on_choice: _SnackChoice,
        slot: str,
    ) -> None:
        super().__init__(
            placeholder=placeholder, options=options, custom_id=menu_id(slot)
        )
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen snack on."""
        await self._on_choice(interaction, SNACK_BY_KEY[self.values[0]])


class CollectionSelect(discord.ui.Select[Any]):
    """The Vault's select of gift collections; hands the chosen one on."""

    def __init__(
        self, options: list[discord.SelectOption], on_choice: _CollectionChoice
    ) -> None:
        super().__init__(
            placeholder="Pick a collection",
            options=options,
            custom_id=menu_id("collections"),
        )
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen collection on."""
        await self._on_choice(interaction, COLLECTION_BY_KEY[self.values[0]])


class GiftSelect(discord.ui.Select[Any]):
    """The Vault's select of one collection's gifts; hands the chosen one on."""

    def __init__(
        self, options: list[discord.SelectOption], on_choice: _GiftChoice
    ) -> None:
        super().__init__(
            placeholder="Give Wisp a gift", options=options, custom_id=menu_id("gifts")
        )
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen gift on."""
        await self._on_choice(interaction, GIFT_BY_KEY[self.values[0]])


class BadgeSelect(discord.ui.Select[Any]):
    """The Vault's select of badges the member can get now; hands one on."""

    def __init__(
        self, options: list[discord.SelectOption], on_choice: _BadgeChoice
    ) -> None:
        super().__init__(
            placeholder="Get a badge", options=options, custom_id=menu_id("badges")
        )
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen badge on."""
        await self._on_choice(interaction, BADGE_BY_KEY[self.values[0]])


class MagazineSelect(discord.ui.Select[Any]):
    """The Vault's select of magazines the member can buy now; hands one on."""

    def __init__(
        self, options: list[discord.SelectOption], on_choice: _MagazineChoice
    ) -> None:
        super().__init__(
            placeholder="Get a magazine",
            options=options,
            custom_id=menu_id("magazines"),
        )
        self._on_choice = on_choice

    async def callback(self, interaction: discord.Interaction) -> None:
        """Pass the chosen magazine on."""
        await self._on_choice(interaction, MAGAZINE_BY_KEY[self.values[0]])


class MedicineSelect(discord.ui.Select[Any]):
    """The Vault's select with the one medicine, shown while Wisp has a cold."""

    def __init__(self, bot: "WispBot") -> None:
        super().__init__(
            placeholder="Give Wisp medicine",
            custom_id=menu_id("medicine"),
            options=[
                discord.SelectOption(
                    label="Medicine",
                    value="medicine",
                    description=f"{MEDICINE_COST} WC ・ cures his cold",
                    emoji=bot.emojis_by_name.get(MEDICINE_EMOJI),
                )
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Give Wisp his medicine."""
        await _give_medicine(interaction)


class Menu(discord.ui.View):
    """An ephemeral menu of selects; a failure is reported as `context`.

    It never times out; see `cogs.menus` for a press after a restart.
    """

    def __init__(self, context: str, *selects: discord.ui.Select[Any]) -> None:
        super().__init__(timeout=None)
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


@dataclass(frozen=True)
class _VaultPiece:
    """A run of the Vault's lines and the menus shown under it, or a picture."""

    lines: Sequence[str] = ()
    selects: Sequence[discord.ui.Select[Any]] = ()
    picture: str | None = None


class VaultLayout(discord.ui.LayoutView):
    """The Vault as one Components V2 message, with no container around it.

    Each piece's lines are one text display, followed by an action row for each
    of its menus; a picture piece is a media gallery of its attached picture,
    left out when the picture is missing. A failure is reported as the ViiBR
    Vault menu. It never times out; see `cogs.menus` for a press after a
    restart.
    """

    def __init__(self, pieces: Sequence[_VaultPiece]) -> None:
        super().__init__(timeout=None)
        for piece in pieces:
            if piece.picture is not None:
                if (shown := gallery(piece.picture)) is not None:
                    self.add_item(shown)
                continue
            self.add_item(discord.ui.TextDisplay("\n".join(piece.lines)))
            for select in piece.selects:
                self.add_item(discord.ui.ActionRow(select))

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item[Any],
    ) -> None:
        """Report a failure and tell the member."""
        await report_failure(interaction, _VAULT_CONTEXT, error)


@dataclass(frozen=True)
class _VaultMenus:
    """The Vault's selects: snacks, then any medicine, badges, magazines, gifts."""

    snacks: discord.ui.Select[Any]
    medicine: discord.ui.Select[Any] | None
    badges: discord.ui.Select[Any] | None
    magazines: discord.ui.Select[Any] | None
    collections: discord.ui.Select[Any] | None
    gifts: discord.ui.Select[Any] | None


def _vault_snack(bot: "WispBot", snack: Snack, price: str) -> str:
    """A Vault line: the snack's name, its emoji when uploaded, then `price`."""
    name = snack.key + " " * _VAULT_PADDING.get(snack.key, 1)
    return item(f"{name}│{bot.emoji(snack.emoji_name)}・{price}")


def _vault_pieces(
    bot: "WispBot",
    balance: int,
    offers: list[Offer],
    magazines: set[str] | None,
    gifts: GiftState | None,
    note: str | None,
    menus: _VaultMenus,
) -> list[_VaultPiece]:
    """The Vault's text in pieces, each followed by its menus.

    An optional note comes before Myra's header picture, and her footer
    picture closes the Vault. The Magazines are there only when `magazines`,
    the covers the member owns this life, is not None. The Gifts take
    whatever room the rest leaves of the layout's text limit. Blank lines
    follow the box top and the snacks, as in Myra's draft, and every line is
    wrapped to fit the box.
    """
    told = [note] if note else []
    close = [box_bottom(VAULT_WIDTH)]
    snacks = [
        box_top(VAULT_WIDTH),
        *wrapped(
            [
                BLANK,
                sub(f"wisp coins: {with_emoji(bot.emoji(COIN_EMOJI), str(balance))}"),
                SECTION_BREAK,
                heading("Snacks"),
                _vault_snack(bot, _FREE, "free once a day"),
                *(
                    _vault_snack(bot, snack, _coins(bot, f"{snack.cost} WC"))
                    for snack in _MENU
                ),
                BLANK,
            ],
            VAULT_WIDTH,
        ),
    ]
    medicine = (
        []
        if menus.medicine is None
        else wrapped(
            [
                SECTION_BREAK,
                heading("Medicine"),
                item(
                    f"cures his cold│{bot.emoji(MEDICINE_EMOJI)}・"
                    f"{_coins(bot, f'{MEDICINE_COST} WC')}"
                ),
            ],
            VAULT_WIDTH,
        )
    )
    badges = wrapped([SECTION_BREAK, *badge_section(bot, offers)], VAULT_WIDTH)
    covers = (
        []
        if magazines is None
        else wrapped([SECTION_BREAK, *magazine_section(bot, magazines)], VAULT_WIDTH)
    )
    # Joined as one text, so the newlines between the text displays are
    # counted too: a small safety margin on purpose.
    rest = "\n".join(
        [*told, *snacks, *medicine, *badges, *covers, SECTION_BREAK, *close]
    )
    room = LAYOUT_TEXT_LIMIT - text_length(rest) - 1
    gift_menus = [menu for menu in (menus.collections, menus.gifts) if menu is not None]
    cover_menus = [] if menus.magazines is None else [menus.magazines]
    return [
        *([_VaultPiece(told)] if told else []),
        _VaultPiece(picture=_VAULT_HEADER),
        _VaultPiece(snacks, [menus.snacks]),
        *([_VaultPiece(medicine, [menus.medicine])] if menus.medicine else []),
        _VaultPiece(badges, [] if menus.badges is None else [menus.badges]),
        *([_VaultPiece(covers, cover_menus)] if covers else []),
        _VaultPiece(
            [SECTION_BREAK, *gift_section(bot, gifts, room, VAULT_WIDTH)], gift_menus
        ),
        _VaultPiece(close),
        _VaultPiece(picture=FOOTER),
    ]


async def _vault(
    bot: "WispBot",
    guild_id: int,
    user_id: int,
    note: str | None = None,
    collection: GiftCollection | None = None,
) -> VaultLayout:
    """The Vault, after an optional note, with its menus between its sections.

    The snack select follows the snacks, the medicine select the medicine
    while Wisp has a cold, the badge select the badges when the
    member can get a badge now, the magazine select the magazines while Wisp
    is a Rockstar and the member lacks a cover, and the collection select the
    gifts when a gift can be given today. With a picked `collection` that can
    still be given from, that collection's gift select follows it.
    """
    gifts = await todays_gifts(bot, guild_id, discord.utils.utcnow())
    snack_options = [
        _option(bot, snack, snack.name, f"{snack.cost} WC ・ {_wellbeing_gain()}")
        for snack in _MENU
    ]
    player = await bot.players.get(guild_id, user_id)
    life = await bot.lives.current(guild_id)
    offers = await badge_offers(bot, guild_id, user_id, player.bond)
    badge_choices = badge_options(bot, offers)
    magazines = await magazines_owned(bot, guild_id, user_id)
    magazine_choices = [] if magazines is None else magazine_options(magazines)
    collection_choices = collection_options(bot, gifts)
    gift_choices = [] if collection is None else gift_options(bot, gifts, collection)
    menus = _VaultMenus(
        snacks=SnackSelect(snack_options, "Buy a snack", _buy, "snacks"),
        medicine=(
            MedicineSelect(bot) if life is not None and has_sniffles(life) else None
        ),
        badges=BadgeSelect(badge_choices, _get_badge) if badge_choices else None,
        magazines=(
            MagazineSelect(magazine_choices, _get_magazine)
            if magazine_choices
            else None
        ),
        collections=(
            CollectionSelect(collection_choices, _pick_collection)
            if collection_choices
            else None
        ),
        gifts=GiftSelect(gift_choices, _give) if gift_choices else None,
    )
    return VaultLayout(
        _vault_pieces(bot, player.balance, offers, magazines, gifts, note, menus)
    )


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
        vault = await _vault(
            bot, require_guild(interaction), interaction.user.id, note, collection
        )
        await interaction.edit_original_response(view=vault, allowed_mentions=_NO_PING)
    except EXPECTED_FAILURES as error:
        if tell_member:
            await report_failure(interaction, context, error)
            return
        await bot.report_error(
            interaction.guild, context, error, where=where_of(interaction)
        )


def _pack_snack(bot: "WispBot", snack: Snack, extra: str) -> str:
    """A Snack Pack line: the snack's key, its emoji when uploaded, then `extra`."""
    parts = (snack.key, bot.emoji(snack.emoji_name), extra)
    return item(" ".join(part for part in parts if part))


def _pack_keepsake(bot: "WispBot", keepsake: Keepsake) -> str:
    """A Snack Pack line: "Wisp v3's" and the keepsake's emoji, else its title."""
    emoji = bot.emoji(f"keepsake_{keepsake.kind.value}")
    title = f"Wisp v{keepsake.version}'s {emoji}" if emoji else keepsake.title
    return item(title)


async def _snack_pack_text(bot: "WispBot", guild_id: int, user_id: int) -> str:
    """The member's Snack Pack frame: balance, snacks, keepsakes, badges and any
    magazines.

    Keepsakes, badges and magazines are listed newest life first; the
    Magazines section is there only when the member has bought one. When they
    do not all fit in one message, each is cut short with how many more there
    are: the magazines get at most a quarter of the room, the badges at most
    half of the rest, and each any room the ones before leave over. Every
    line is wrapped to fit the box.
    """
    player = await bot.players.get(guild_id, user_id)
    owned = await bot.activity_log.inventory(guild_id, user_id)
    free_left = not await bot.activity_log.free_snack_used_today(
        guild_id, user_id, discord.utils.utcnow()
    )
    snacks = [
        _pack_snack(bot, snack, f"x{owned[snack.key]}")
        for snack in _MENU
        if snack.key in owned
    ]
    if free_left:
        snacks.append(_pack_snack(bot, _FREE, "free today"))
    balance = _coins(bot, f"{player.balance} WC (wisp coins)")
    drawings = await bot.drawings.count_for(guild_id, user_id)
    head = [
        box_top(),
        *wrapped(
            [
                sub(f"<@{user_id}> snack pack"),
                f"{SUB_MARK}・{balance}",
                sub(f"Drawings from Wisp: {drawings}"),
                SECTION_BREAK,
                heading("Snacks"),
                *(snacks or [_NOTHING_SAVED]),
                SECTION_BREAK,
                heading("Keepsakes"),
            ]
        ),
    ]
    held = await bot.keepsakes.of(guild_id, user_id)
    newest_life_first = sorted(held, key=lambda keepsake: -keepsake.version)
    keepsakes = wrapped(
        [_pack_keepsake(bot, keepsake) for keepsake in newest_life_first]
    ) or [_NONE_YET]
    badges = wrapped(badge_pack_lines(bot, await bot.badges.of(guild_id, user_id))) or [
        _NONE_YET
    ]
    covers = wrapped(magazine_pack_lines(await bot.magazines.of(guild_id, user_id)))
    between = [SECTION_BREAK, heading("Badges")]
    shelf = [SECTION_BREAK, heading("Magazines")] if covers else []
    tail = [box_bottom()]
    framing = "\n".join([*head, *between, *shelf, *tail])
    room = MESSAGE_LIMIT - text_length(framing) - 3
    cover_room = min(_length(covers), room // 4)
    badge_room = min(_length(badges), (room - cover_room) // 2)
    kept = _shown(keepsakes, room - badge_room - cover_room)
    worn = _shown(badges, room - _length(kept) - cover_room)
    read = _shown(covers, room - _length(kept) - _length(worn))
    return "\n".join([*head, *kept, *between, *worn, *shelf, *read, *tail])


def _length(lines: list[str]) -> int:
    """How long `lines` are joined one per line, counted by `text_length`."""
    return text_length("\n".join(lines))


def _shown(lines: list[str], room: int) -> list[str]:
    """As many of `lines` as fit in `room`, then how many more.

    The room is counted by `text_length`.
    """
    if _length(lines) <= room:
        return lines
    for shown in range(len(lines) - 1, -1, -1):
        cut = [*lines[:shown], item(f"and {len(lines) - shown} more")]
        if _length(cut) <= room:
            return cut
    return [item(f"and {len(lines)} more")]


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
        await say_privately(
            interaction, too_poor_text(bot, line, snack.cost, player.balance)
        )
    else:
        await bot.activity_log.add_snack(guild_id, user.id, snack.key)
        await _confirm(
            interaction,
            f"♪ Bought {snack.name} for {snack.cost} WC.",
            "confirming a snack purchase (the purchase went through)",
        )


async def _get_badge(interaction: discord.Interaction, badge: Badge) -> None:
    """Spend the member's points on a badge and give them its role.

    The purchase is made under the guild lock; the role is given after it. If
    the role cannot be given, the purchase is undone in full and the failure
    is reported where it happened. A badge that went through is announced in
    Wisp's House.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    guild = interaction.guild
    await interaction.response.defer()
    if not isinstance(user, discord.Member) or guild is None:
        await _confirm(
            interaction, refusal_text(Blocker.NO_ROLE), "showing a refused badge"
        )
        return
    role = await badge_role(bot, guild, badge)
    if role is None:
        await _confirm(interaction, _BADGE_NOT_READY, "showing a badge not ready")
        return
    try:
        async with bot.guild_lock(guild_id):
            life, player = await _take_badge(
                bot, guild_id, user, badge, discord.utils.utcnow()
            )
    except Refusal as refusal:
        await _confirm(interaction, str(refusal), "showing a refused badge")
        return
    try:
        await user.add_roles(role, reason=_ROLE_REASON)
    except _ROLE_FAILURES as error:
        async with bot.guild_lock(guild_id):
            await _return_badge(bot, guild_id, user.id, badge, life)
        await bot.report_error(
            guild,
            f"giving the {badge.name} badge role",
            error,
            where=where_of(interaction),
        )
        await _confirm(
            interaction,
            f"♪ Your {badge.name} badge didn't go through. Your WC are back.",
            "showing a badge that did not go through",
        )
        return
    await _confirm(
        interaction,
        f"♪ You got the {badge.name} badge ・ bond +{badge.bond}",
        "confirming a badge (the badge went through)",
    )
    name = player.name or user.display_name
    line = bot.lines.pick(Moment.BADGE_BOUGHT, mood(life), name=name)
    await post_in_house(bot, guild_id, f"♪ {name} {badge.phrase}\n{line}")


async def _take_badge(
    bot: "WispBot",
    guild_id: int,
    member: discord.Member,
    badge: Badge,
    now: datetime,
) -> tuple[Life, Player]:
    """Sell the member a badge for the current life. Call this under the guild lock.

    Its bond is outside the daily casual bond cap. The member's purchases of
    the badge for earlier lives are marked done, since they keep the role.
    Returns the life it was bought for and the buyer.

    Raises:
        Refusal: The member is banned or cannot feed Wisp, is below the badge's
            bond tier, already has it this life or is short of points, or there
            is no Wisp to wear it for. Nothing is spent then.
    """
    player = await check_member(bot, guild_id, member, now)
    if badge.needs_tier is not None and tier_for(player.bond) != badge.needs_tier:
        raise Refusal(f"♪ The {badge.name} badge is only for {badge.needs_tier}s.")
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or is_over(life):
        raise Refusal(_NO_WISP)
    if badge.key in await bot.badges.owned(guild_id, member.id, life.id):
        raise Refusal(_already_have(badge, life))
    if not await bot.players.spend(guild_id, member.id, badge.cost):
        name = player.name or member.display_name
        line = bot.lines.pick(Moment.NOT_ENOUGH_POINTS, mood(life), name=name)
        raise Refusal(too_poor_text(bot, line, badge.cost, player.balance))
    if not await bot.badges.record(
        guild_id, member.id, badge.key, life.id, life.version, now
    ):
        await bot.players.refund(guild_id, member.id, badge.cost)
        raise Refusal(_already_have(badge, life))
    await bot.badges.retire_older(guild_id, member.id, badge.key, life.id, now)
    await bot.players.add_bond(guild_id, member.id, badge.bond)
    return life, player


def _already_have(badge: Badge, life: Life) -> str:
    return f"♪ You already have the {badge.name} badge for Wisp v{life.version}."


async def _return_badge(
    bot: "WispBot", guild_id: int, user_id: int, badge: Badge, life: Life
) -> None:
    """Undo a badge sale whose role could not be given: points, record and bond."""
    assert life.id is not None
    await bot.players.refund(guild_id, user_id, badge.cost)
    await bot.badges.forget(guild_id, user_id, badge.key, life.id)
    await bot.players.add_bond(guild_id, user_id, -badge.bond)


async def _get_magazine(interaction: discord.Interaction, magazine: Magazine) -> None:
    """Spend the member's points on a magazine cover, then send them its picture.

    The purchase is made under the guild lock. The Vault is shown again under
    the result, or under the reason it was refused; the picture follows only
    to the buyer. A picture that cannot be sent is reported where it happened,
    and the purchase stands.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    await interaction.response.defer()
    try:
        async with bot.guild_lock(guild_id):
            await _take_magazine(
                bot, guild_id, interaction.user, magazine, discord.utils.utcnow()
            )
    except Refusal as refusal:
        await _confirm(interaction, str(refusal), "showing a refused magazine")
        return
    await _confirm(
        interaction,
        f"♪ You got the {magazine.name}.",
        "confirming a magazine (the purchase went through)",
    )
    try:
        await interaction.followup.send(
            file=discord.File(cover_art(magazine)), ephemeral=True
        )
    except (discord.HTTPException, OSError) as error:
        await report_failure(
            interaction,
            f"sending the {magazine.name} picture (the purchase went through)",
            error,
        )


async def _take_magazine(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    magazine: Magazine,
    now: datetime,
) -> None:
    """Sell the member a magazine for the current life. Call this under the guild lock.

    Raises:
        Refusal: The member is banned or cannot feed Wisp, Wisp is not a living
            Rockstar, the member already has this cover this life or is short
            of points. Nothing is spent then.
    """
    player = await check_member(bot, guild_id, member, now)
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or not on_the_shelf(life):
        raise Refusal(_SHELF_EMPTY)
    if magazine.key in await bot.magazines.owned(guild_id, member.id, life.id):
        raise Refusal(_already_own(magazine, life))
    if not await bot.players.spend(guild_id, member.id, MAGAZINE_COST):
        name = player.name or member.display_name
        line = bot.lines.pick(Moment.NOT_ENOUGH_POINTS, mood(life), name=name)
        raise Refusal(too_poor_text(bot, line, MAGAZINE_COST, player.balance))
    if not await bot.magazines.record(
        guild_id, member.id, magazine.key, life.id, life.version, now
    ):
        await bot.players.refund(guild_id, member.id, MAGAZINE_COST)
        raise Refusal(_already_own(magazine, life))


def _already_own(magazine: Magazine, life: Life) -> str:
    return f"♪ You already have the {magazine.name} for Wisp v{life.version}."


async def _give_medicine(interaction: discord.Interaction) -> None:
    """Spend the member's points on Wisp's medicine, which cures his cold.

    The Vault is shown again under the result, or under the reason it was
    refused. A cure is announced in his House, pinging nobody, with a sleepy
    line while he naps. If the confirmation fails, the error posted says the
    medicine went through.
    """
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    await interaction.response.defer()
    try:
        async with bot.guild_lock(guild_id):
            life, player = await _take_medicine(
                bot, guild_id, user, discord.utils.utcnow()
            )
    except Refusal as refusal:
        await _confirm(interaction, str(refusal), "showing refused medicine")
        return
    await _confirm(
        interaction,
        f"♪ You gave Wisp his medicine ・ +{MEDICINE_POINTS} WC",
        "confirming medicine (the medicine went through)",
    )
    await say_in_house(
        bot,
        guild_id,
        Moment.MEDICINE_ASLEEP if is_napping(life) else Moment.MEDICINE,
        life,
        name=player.name or user.display_name,
        image=moment_image(MEDICINE_PICTURE),
    )


async def _take_medicine(
    bot: "WispBot",
    guild_id: int,
    member: discord.User | discord.Member,
    now: datetime,
) -> tuple[Life, Player]:
    """Sell the member medicine and cure Wisp. Call this under the guild lock.

    Returns the cured life and the buyer.

    Raises:
        Refusal: The member is banned or cannot feed Wisp, Wisp is not alive
            with a cold, or the member is short of points. Nothing is spent
            then.
    """
    await require_unfrozen(bot, guild_id)
    player = await check_member(bot, guild_id, member, now)
    life = await bot.lives.current(guild_id)
    if life is None or life.phase is not Phase.ALIVE:
        raise Refusal(no_wisp_text(life, "Doses of medicine"))
    if not has_sniffles(life):
        raise Refusal(_NO_COLD)
    if not await bot.players.spend(guild_id, member.id, MEDICINE_COST):
        name = player.name or member.display_name
        line = bot.lines.pick(Moment.NOT_ENOUGH_POINTS, mood(life), name=name)
        raise Refusal(too_poor_text(bot, line, MEDICINE_COST, player.balance))
    cure_sniffles(life)
    await bot.lives.save(guild_id, life)
    await bot.players.add_points(guild_id, member.id, MEDICINE_POINTS)
    return life, player


async def _pick_collection(
    interaction: discord.Interaction, collection: GiftCollection
) -> None:
    """Show the Vault again with the picked collection's gifts to choose from.

    A collection nobody can give from any more, such as one someone gave
    from a moment ago, is refused with the reason and the Vault as it is now.
    """
    bot = bot_of(interaction)
    await interaction.response.defer()
    guild_id = require_guild(interaction)
    state = await todays_gifts(bot, guild_id, discord.utils.utcnow())
    reason = closed_reason(await bot.lives.current(guild_id), state, collection)
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
    if given.outcome is Outcome.KEPT:
        await draw_for(bot, guild_id, user, DrawReason.GIFT, discord.utils.utcnow())


# ---
# The Vault and Snack Packs
# ---


async def _open_vault(interaction: discord.Interaction) -> None:
    """Show the Vault with its menus to buy from, only to the member.

    Every private menu is a follow-up sent with `wait`, so discord.py files
    its view under the menu's own message id, never under the key it shares
    with the persistent buttons.
    """
    if not await _admit(interaction):
        return
    vault = await _vault(
        bot_of(interaction), require_guild(interaction), interaction.user.id
    )
    await interaction.followup.send(
        view=vault,
        files=gallery_files(_VAULT_HEADER, FOOTER),
        ephemeral=True,
        allowed_mentions=_NO_PING,
        wait=True,
    )


async def _open_snack_pack(interaction: discord.Interaction) -> None:
    """Show the member's own snacks and keepsakes, with a button to the shop."""
    if not await _admit(interaction):
        return
    view = discord.ui.View(timeout=None)
    view.add_item(ShopButton())
    await send_headed(
        functools.partial(interaction.followup.send, ephemeral=True),
        _PACK_HEADER,
        await _snack_pack_text(
            bot_of(interaction), require_guild(interaction), interaction.user.id
        ),
        view=view,
        allowed_mentions=_NO_PING,
        wait=True,
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

    The status card shows it as Vault. Its custom id is fixed, so the button
    keeps working after the bot restarts, whatever its label.
    """

    def __init__(self, label: str = "Shop the Vault") -> None:
        super().__init__(
            discord.ui.Button(
                label=label,
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
        await press(interaction, "the Vault shop button", _open_vault)


class SnackPackButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(_SNACK_PACK_ID),
):
    """The Open my Snack Pack button, which shows the presser their own Snack Pack.

    The status card shows it as Snack Pack. Its custom id is fixed, so the
    button keeps working after the bot restarts, whatever its label.
    """

    def __init__(self, label: str = "Open my Snack Pack") -> None:
        super().__init__(
            discord.ui.Button(
                label=label,
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
        await press(interaction, "the Snack Pack button", _open_snack_pack)


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
    """A snack Wisp has eaten: his life and the feeder."""

    life: Life
    player: Player
    wellbeing_before: float


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
    await require_unfrozen(bot, guild_id)
    player = await check_member(bot, guild_id, member, now)
    life = await bot.lives.current(guild_id)
    if life is None or life.id is None or life.phase is not Phase.ALIVE:
        raise Refusal(no_wisp_text(life, "Snacks"))
    if snack == _FREE and await log.free_snack_used_today(guild_id, user_id, now):
        raise Refusal(_SINE_USED)
    eaten = await log.meal_points_today(guild_id, user_id, now)
    points = meal_grant(eaten, snack.meal, daily_meal_cap(life))
    if points == 0:
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
    before = life.wellbeing
    change_meter(life, Meter.WELLBEING, WELLBEING_PER_SNACK, ends_stretch=True)
    add_growth(life, snack.growth)
    if bond:
        await bot.players.add_bond(guild_id, user_id, bond)
    await log.record_interaction(guild_id, life.id, user_id, kind, bond, points, now)
    await bot.lives.save(guild_id, life)
    return _Meal(life, player, before)


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
    """Feed Wisp the chosen snack, tell the member, then show it in his House.

    While he naps he eats in his sleep, and his line is a sleepy one.
    """
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
    await interaction.edit_original_response(
        content=(
            f"♪ Wisp ate your {snack.name}. "
            f"{meter_receipt('Wellbeing', meal.wellbeing_before, meal.life.wellbeing)}."
        ),
        view=None,
        allowed_mentions=_NO_PING,
    )
    emoji = bot.emoji(snack.emoji_name)
    moment, gif_name = _reaction(
        snack, meal.player.pickle_stance, meal.life.favorite_snack
    )
    if is_napping(meal.life):
        moment = Moment.SNACK_ASLEEP
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
        _option(bot, snack, f"{snack.name} x{owned[snack.key]}", _wellbeing_gain())
        for snack in _MENU
        if snack.key in owned
    ]
    if not await bot.activity_log.free_snack_used_today(
        guild_id, user_id, discord.utils.utcnow()
    ):
        free = _option(bot, _FREE, f"{_FREE.name} (free today)", _wellbeing_gain())
        options.insert(0, free)
    if not options:
        return None
    return Menu("the snack menu", SnackSelect(options, "Pick a snack", _feed, "feed"))


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
        wait=True,
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
        await press(interaction, "the Feed Wisp button", _offer_snacks)


async def setup(bot: "WispBot") -> None:
    """Register the persistent buttons so they still work after a restart.

    `ClosedMenu` answers a press on a menu sent before the restart.
    """
    bot.add_dynamic_items(
        FeedButton, PokeButton, ShopButton, SnackPackButton, ClosedMenu
    )
