"""The ViiBR Vault post: Myra's shelf pictures in the Studio, each with its menu.

The post's first message shows the Snacks shelf. Under it come the snack
menu, then one message per shelf picture with its menu, then the medicine and
magazine menus with the Snack Pack button. A pick answers only the member who
made it, with the same purchase the private Vault makes; the post itself never
changes. The menus are persistent, so they keep working after a restart.
"""

import contextlib
import re
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR
from cogs.players import EXPECTED_FAILURES, press
from cogs.snacks import (
    SHELF_ID_PREFIX,
    SnackPackButton,
    buy_snack,
    get_badge,
    get_magazine,
    give_from_vault,
    give_medicine,
)
from cogs.studio import StudioError, studio_thread
from wisp.rules import (
    BADGE_BY_KEY,
    BADGES,
    COLLECTION_BY_KEY,
    GIFT_BY_KEY,
    GIFT_COST,
    MAGAZINE_BY_KEY,
    MAGAZINE_COST,
    MAGAZINES,
    MEDICINE_COST,
    MEDICINE_EMOJI,
    PAID_SNACKS,
    SNACK_BY_KEY,
    WELLBEING_PER_SNACK,
    Stage,
)

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_SHELF_DIR: Final = ASSETS_DIR / "gifts" / "VV_Store"
_CONTEXT: Final = "the ViiBR Vault post"
_GONE: Final = "♪ That isn't in the ViiBR Vault any more."
_LABEL: Final = "ViiBR Vault shelves"

# ---
# The menus
# ---


@dataclass(frozen=True)
class Menu:
    """One of the post's menus: its key, its placeholder and what a pick does.

    `options` lists the menu's choices for a bot whose app emojis are loaded.
    `pick` runs the purchase for a chosen value, or is None for a value the
    Vault no longer sells.
    """

    key: str
    placeholder: str
    options: Callable[["WispBot"], list[discord.SelectOption]]
    pick: Callable[[str], Callable[[discord.Interaction], Awaitable[None]] | None]


def _snack_options(bot: "WispBot") -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=snack.name,
            value=snack.key,
            description=f"{snack.cost} WC ・ wellbeing +{WELLBEING_PER_SNACK}",
            emoji=bot.emojis_by_name.get(snack.emoji_name),
        )
        for snack in PAID_SNACKS
    ]


def _gift_options(
    *collections: str,
) -> Callable[["WispBot"], list[discord.SelectOption]]:
    """The gifts of `collections`, as one menu's options.

    A gift that looks different at each stage shows its Baby emoji.
    """

    def options(bot: "WispBot") -> list[discord.SelectOption]:
        return [
            discord.SelectOption(
                label=gift.title,
                value=gift.key,
                description=f"{GIFT_COST} WC ・ {COLLECTION_BY_KEY[key].name}",
                emoji=bot.emojis_by_name.get(gift.emoji_name(Stage.BABY)),
            )
            for key in collections
            for gift in COLLECTION_BY_KEY[key].gifts
        ]

    return options


def _badge_options(bot: "WispBot") -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=badge.name,
            value=badge.key,
            description=" ・ ".join(
                [
                    f"{badge.cost} WC",
                    f"bond +{badge.bond}",
                    *([] if badge.needs_tier is None else [f"{badge.needs_tier}s"]),
                ]
            ),
            emoji=bot.emojis_by_name.get(badge.emoji_name),
        )
        for badge in BADGES
    ]


def _medicine_options(bot: "WispBot") -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label="Medicine",
            value="medicine",
            description=f"{MEDICINE_COST} WC ・ cures his cold",
            emoji=bot.emojis_by_name.get(MEDICINE_EMOJI),
        )
    ]


def _magazine_options(_bot: "WispBot") -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=magazine.name,
            value=magazine.key,
            description=f"{MAGAZINE_COST} WC ・ while he's a Rockstar",
        )
        for magazine in MAGAZINES
    ]


def _snack_pick(value: str) -> Callable[[discord.Interaction], Awaitable[None]] | None:
    snack = SNACK_BY_KEY.get(value)
    if snack is None or snack.cost == 0:
        return None
    return lambda interaction: buy_snack(interaction, snack)


def _gift_pick(value: str) -> Callable[[discord.Interaction], Awaitable[None]] | None:
    gift = GIFT_BY_KEY.get(value)
    if gift is None:
        return None
    return lambda interaction: give_from_vault(interaction, gift)


def _badge_pick(value: str) -> Callable[[discord.Interaction], Awaitable[None]] | None:
    badge = BADGE_BY_KEY.get(value)
    if badge is None:
        return None
    return lambda interaction: get_badge(interaction, badge)


def _medicine_pick(
    value: str,
) -> Callable[[discord.Interaction], Awaitable[None]] | None:
    return give_medicine if value == "medicine" else None


def _magazine_pick(
    value: str,
) -> Callable[[discord.Interaction], Awaitable[None]] | None:
    magazine = MAGAZINE_BY_KEY.get(value)
    if magazine is None:
        return None
    return lambda interaction: get_magazine(interaction, magazine)


MENUS: Final[dict[str, Menu]] = {
    menu.key: menu
    for menu in (
        Menu("snacks", "Buy a snack", _snack_options, _snack_pick),
        Menu(
            "tamas_tech",
            "Give Wisp a Tamagotchi or Tech gift",
            _gift_options("tamagotchis", "tech"),
            _gift_pick,
        ),
        Menu(
            "dolls_books",
            "Give Wisp an Alien Doll or a Book",
            _gift_options("aliens", "books"),
            _gift_pick,
        ),
        Menu("badges", "Get a badge", _badge_options, _badge_pick),
        Menu("medicine", "Give Wisp medicine", _medicine_options, _medicine_pick),
        Menu("magazines", "Get a magazine cover", _magazine_options, _magazine_pick),
    )
}


class ShelfMenu(
    discord.ui.DynamicItem[discord.ui.Select[Any]],
    template=re.compile(rf"{re.escape(SHELF_ID_PREFIX)}(?P<menu>[a-z_]+)"),
):
    """A menu of the ViiBR Vault post, which works the same after a restart.

    Its custom id names the menu, so a pick is routed to its purchase
    whichever run of the bot posted it.
    """

    def __init__(
        self, menu: str, options: list[discord.SelectOption] | None = None
    ) -> None:
        spec = MENUS.get(menu)
        super().__init__(
            discord.ui.Select(
                custom_id=f"{SHELF_ID_PREFIX}{menu}",
                placeholder=spec.placeholder if spec is not None else None,
                options=options or [],
            )
        )
        self.menu = menu

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> "ShelfMenu":
        """Rebuild the menu a pick reached."""
        return cls(match["menu"])

    async def callback(self, interaction: discord.Interaction) -> None:
        """Make the purchase the pick names, answering only the member."""
        values = self.item.values
        spec = MENUS.get(self.menu)
        action = None if spec is None or not values else spec.pick(values[0])
        if action is None:
            await interaction.response.send_message(_GONE, ephemeral=True)
            return
        await press(interaction, _CONTEXT, action)


def _menu(bot: "WispBot", key: str) -> ShelfMenu:
    return ShelfMenu(key, MENUS[key].options(bot))


# ---
# The shelves
# ---


@dataclass(frozen=True)
class Shelf:
    """One message of the post: an optional picture, its words and its menus.

    `picture` is a file in ASSETS/gifts/VV_Store. `snack_pack` adds the Open
    my Snack Pack button under the menus.
    """

    picture: str | None
    text: str
    menus: tuple[str, ...]
    snack_pack: bool = False


SHELVES: Final[tuple[Shelf, ...]] = (
    Shelf(None, "♪ Snacks for your Snack Pack", ("snacks",)),
    Shelf("VV_Tamas-tech.gif", "", ("tamas_tech",)),
    Shelf("VV_Dolls-Books.png", "", ("dolls_books",)),
    Shelf("VV_VanityRoles.png", "", ("badges",)),
    Shelf(
        None,
        "\n".join(
            [
                "♪ Also in the Vault",
                f"・Medicine, {MEDICINE_COST} WC: cures his cold while he has one",
                f"・Magazine covers, {MAGAZINE_COST} WC each: on the shelf while "
                "he's a Rockstar",
                "・Your wisp coins, snacks and keepsakes are in your Snack Pack",
            ]
        ),
        ("medicine", "magazines"),
        snack_pack=True,
    ),
)


def shelf_view(bot: "WispBot", shelf: Shelf) -> discord.ui.View:
    """The shelf's menus, each on its own row, then any Snack Pack button."""
    view = discord.ui.View(timeout=None)
    for key in shelf.menus:
        view.add_item(_menu(bot, key))
    if shelf.snack_pack:
        view.add_item(SnackPackButton())
    return view


@contextlib.contextmanager
def _pictures(shelf: Shelf) -> Iterator[list[discord.File]]:
    """The shelf's picture, if it has one, as files to send; closed after the send.

    Raises:
        FileNotFoundError: The shelf's picture is missing.
    """
    if shelf.picture is None:
        yield []
        return
    picture = discord.File(_SHELF_DIR / shelf.picture)
    try:
        yield [picture]
    finally:
        picture.close()


async def _post_shelves(bot: "WispBot", guild_id: int, thread: discord.Thread) -> None:
    """Delete the stored shelves, then post every shelf in order and store them.

    What was posted is stored even when posting stops part way, so the next
    try deletes it first.
    """
    settings = await bot.settings.get(guild_id)
    for message_id in settings.shop_message_ids or ():
        with contextlib.suppress(discord.NotFound):
            await thread.get_partial_message(message_id).delete()
    posted: list[int] = []
    try:
        for shelf in SHELVES:
            with _pictures(shelf) as pictures:
                message = await thread.send(
                    shelf.text or None,
                    files=pictures,
                    view=shelf_view(bot, shelf),
                    allowed_mentions=_NO_PING,
                )
            posted.append(message.id)
    finally:
        await bot.settings.update(guild_id, shop_message_ids=tuple(posted))


async def ensure_shelves(bot: "WispBot", guild_id: int) -> None:
    """Post the ViiBR Vault's shelves when its post does not have them all.

    Once the Studio is set up, a guild without a stored shelf per shelf gets
    them posted again: a new post, a release with other shelves, or a post
    that stopped part way. A failure is posted in the Vault post, or in
    Wisp's House when it cannot be reached, once per streak of failures; it
    is never raised.
    """
    settings = await bot.settings.get(guild_id)
    if settings.shop_thread_id is None:
        return
    if len(settings.shop_message_ids or ()) == len(SHELVES):
        return
    key = (guild_id, _LABEL)
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild_id, "shop_thread_id")
        await _post_shelves(bot, guild_id, thread)
    except (*EXPECTED_FAILURES, StudioError, OSError) as error:
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                bot.get_guild(guild_id), f"posting the {_LABEL}", error, where=thread
            )
    else:
        bot.failing_displays.discard(key)


def shop_url(guild_id: int, thread_id: int | None) -> str | None:
    """A link that jumps to the ViiBR Vault post, or None before it exists."""
    if thread_id is None:
        return None
    return f"https://discord.com/channels/{guild_id}/{thread_id}"


async def setup(bot: "WispBot") -> None:
    """Register the post's menus so they still work after a restart."""
    bot.add_dynamic_items(ShelfMenu)
