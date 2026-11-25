"""Tests for the ViiBR Vault post: its shelves, its menus and their receipts.

Discord objects are fakes; the repositories are the real ones.
"""

import random
from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import shop, snacks
from cogs.boards import board_for
from cogs.interaction import interaction_lines
from cogs.shop import MENUS, SHELVES, ShelfMenu, ensure_shelves
from cogs.snacks import SHELF_ID_PREFIX, ShopButton
from cogs.studio import post_url
from db.activity import ActivityRepo
from db.badges import BadgeRepo
from db.cravings import CravingRepo
from db.database import Database
from db.drawings import DrawingRepo
from db.gifts import GiftRepo
from db.keepsakes import KeepsakeRepo
from db.lives import LifeRepo
from db.magazines import MagazineRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import Settings, SettingsRepo
from db.story import LifeStoryRepo
from wisp.life import Life, Phase, new_egg
from wisp.rules import (
    BADGES,
    GIFT_COLLECTIONS,
    MAGAZINES,
    PAID_SNACKS,
    Stage,
)

GUILD_ID = 100
HOUSE_ID = 20
SHOP_ID = 60
USER_ID = 1
QUALIFYING_ROLE = 7
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


class FakeShop:
    """Wisp's House and the ViiBR Vault post, which keeps what is sent to it."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.thread = MagicMock(spec=discord.Thread)
        self.thread.id = SHOP_ID
        self.sent: list[dict[str, Any]] = []
        self.deleted: list[int] = []
        self.thread.send = AsyncMock(side_effect=self._send)
        self.thread.get_partial_message.side_effect = self._partial
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get

    async def _send(self, content: str | None = None, **kwargs: Any) -> MagicMock:
        files: list[discord.File] = kwargs.get("files", [])
        self.sent.append(
            {
                "content": content,
                "pictures": [file.filename for file in files],
                "view": kwargs["view"],
                "allowed_mentions": kwargs["allowed_mentions"],
            }
        )
        return MagicMock(spec=discord.Message, id=9000 + len(self.sent))

    def _partial(self, message_id: int) -> MagicMock:
        message = MagicMock(spec=discord.PartialMessage)

        async def delete() -> None:
            self.deleted.append(message_id)

        message.delete = AsyncMock(side_effect=delete)
        return message


@pytest.fixture
def shop_server(monkeypatch: pytest.MonkeyPatch) -> FakeShop:
    server = FakeShop()

    async def thread(_bot: app.WispBot, _guild_id: int, attr: str) -> MagicMock:
        assert attr == "shop_thread_id"
        return server.thread

    monkeypatch.setattr(shop, "studio_thread", thread)
    return server


@pytest.fixture
def bot(
    db: Database, shop_server: FakeShop, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.story = LifeStoryRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.keepsakes = KeepsakeRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.drawings = DrawingRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.magazines = MagazineRepo(db)
    wisp_bot.cravings = CravingRepo(db)
    wisp_bot.notes = NoteRepo(db)
    wisp_bot.report_error = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: shop_server.guild)
    monkeypatch.setattr(snacks, "maybe_meet", AsyncMock())
    monkeypatch.setattr(snacks, "draw_for", AsyncMock())
    monkeypatch.setattr(snacks, "gift_rng", lambda _bot: random.Random(0))
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    await bot.players.activate(GUILD_ID, USER_ID, discord.utils.utcnow())


async def lay(bot: app.WispBot) -> Life:
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=1))
    life.phase = Phase.ALIVE
    life.stage = life.peak_stage = Stage.BABY
    life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


def make_interaction(bot: app.WispBot, menu: str, value: str) -> MagicMock:
    """A member's pick of `value` from the post's `menu`."""
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.data = {
        "custom_id": f"{SHELF_ID_PREFIX}{menu}",
        "component_type": 3,
        "values": [value],
    }
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = USER_ID
    interaction.user.display_name = "Member1"
    interaction.user.roles = [MagicMock(spec=discord.Role, id=QUALIFYING_ROLE)]
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False

    async def answer(*_args: Any, **_kwargs: Any) -> None:
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=answer)
    interaction.response.send_message = AsyncMock(side_effect=answer)
    interaction.edit_original_response = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def pick(bot: app.WispBot, menu: str, value: str) -> MagicMock:
    """Pick `value` from the post's `menu`, as a restarted bot would see it."""
    interaction = make_interaction(bot, menu, value)
    shelf_menu = ShelfMenu(menu)
    shelf_menu.item._values = [value]
    await shelf_menu.callback(interaction)
    return interaction


def private_replies(interaction: MagicMock) -> list[str]:
    """Every private reply, none able to ping; the post is never edited."""
    interaction.edit_original_response.assert_not_awaited()
    replies = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        replies.append(str(call.args[0]))
    return replies


def custom_ids(view: discord.ui.View) -> list[str | None]:
    return [
        getattr(child.item if isinstance(child, ShelfMenu) else child, "custom_id")
        for child in view.children
    ]


# ---
# The shelves
# ---


async def test_the_shelves_are_posted_in_order_once(
    bot: app.WispBot, shop_server: FakeShop
) -> None:
    await bot.settings.update(GUILD_ID, shop_thread_id=SHOP_ID)

    await ensure_shelves(bot, GUILD_ID)
    await ensure_shelves(bot, GUILD_ID)

    sent = shop_server.sent
    assert [post["pictures"] for post in sent] == [
        ["VV_Snacks.gif"],
        ["VV_Tamas-tech.gif"],
        ["VV_Dolls-Books.png"],
        ["VV_VanityRoles.png"],
        [],
    ]
    assert [post["content"] for post in sent[:4]] == [None, None, None, None]
    assert sent[4]["content"].startswith("♪ Also in the Vault\n・Medicine, 10 WC")
    assert [custom_ids(post["view"]) for post in sent] == [
        ["wisp:shelf:snacks"],
        ["wisp:shelf:tamas_tech"],
        ["wisp:shelf:dolls_books"],
        ["wisp:shelf:badges"],
        ["wisp:shelf:medicine", "wisp:shelf:magazines", "wisp:snackpack"],
    ]
    for post in sent:
        assert post["allowed_mentions"].to_dict() == NO_PING
        assert post["view"].timeout is None
    settings = await bot.settings.get(GUILD_ID)
    assert settings.shop_message_ids == (9001, 9002, 9003, 9004, 9005)
    assert shop_server.deleted == []


async def test_a_post_with_some_shelves_missing_is_posted_again(
    bot: app.WispBot, shop_server: FakeShop
) -> None:
    await bot.settings.update(
        GUILD_ID, shop_thread_id=SHOP_ID, shop_message_ids=(11, 12)
    )

    await ensure_shelves(bot, GUILD_ID)

    assert shop_server.deleted == [11, 12]
    assert len(shop_server.sent) == len(SHELVES)
    assert len((await bot.settings.get(GUILD_ID)).shop_message_ids or ()) == 5


async def test_no_vault_post_means_no_shelves(
    bot: app.WispBot, shop_server: FakeShop
) -> None:
    await ensure_shelves(bot, GUILD_ID)

    assert shop_server.sent == []


async def test_a_failed_shelf_is_reported_once_and_tried_again(
    bot: app.WispBot, shop_server: FakeShop
) -> None:
    await bot.settings.update(GUILD_ID, shop_thread_id=SHOP_ID)
    shop_server.thread.send.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await ensure_shelves(bot, GUILD_ID)
    await ensure_shelves(bot, GUILD_ID)

    report = bot.report_error
    assert isinstance(report, AsyncMock)
    report.assert_awaited_once()
    call = report.await_args
    assert call is not None
    assert call.args[1] == "posting the ViiBR Vault shelves"
    assert shop_server.thread.send.await_count == 2


def test_every_menu_sells_what_the_rules_do() -> None:
    bot = app.WispBot()
    values = {key: [o.value for o in menu.options(bot)] for key, menu in MENUS.items()}
    assert values["snacks"] == [snack.key for snack in PAID_SNACKS]
    gifts = values["tamas_tech"] + values["dolls_books"]
    every_gift = [gift.key for c in GIFT_COLLECTIONS for gift in c.gifts]
    assert sorted(gifts) == sorted(every_gift)
    assert len(set(gifts)) == len(gifts)
    assert values["badges"] == [badge.key for badge in BADGES]
    assert values["medicine"] == ["medicine"]
    assert values["magazines"] == [magazine.key for magazine in MAGAZINES]
    for menu in MENUS.values():
        assert len(menu.options(bot)) <= 25


# ---
# Picking from a shelf
# ---


async def test_a_snack_from_the_post_is_bought_with_a_private_receipt(
    bot: app.WispBot,
) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    interaction = await pick(bot, "snacks", "cheese")

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert private_replies(interaction) == [
        "♪ Bought Cheese for 6 WC.\n♪ You have 14 WC."
    ]
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cheese": 1}


async def test_a_member_short_of_coins_is_told_privately(bot: app.WispBot) -> None:
    interaction = await pick(bot, "snacks", "cheese")

    (reply,) = private_replies(interaction)
    assert reply.endswith("♪ That costs 6 WC and you have 0.")
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}


async def test_a_gift_from_the_post_goes_to_wisp(
    bot: app.WispBot, shop_server: FakeShop
) -> None:
    await lay(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    interaction = await pick(bot, "tamas_tech", "tama_nano")

    (reply,) = private_replies(interaction)
    assert reply.endswith("♪ You have 5 WC.")
    shop_server.house.send.assert_awaited()
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 5


async def test_medicine_without_a_cold_is_refused_privately(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    interaction = await pick(bot, "medicine", "medicine")

    assert private_replies(interaction) == [
        "♪ Wisp doesn't have a cold right now.\n♪ You have 20 WC."
    ]


async def test_a_magazine_off_the_shelf_is_refused_privately(
    bot: app.WispBot,
) -> None:
    await lay(bot)

    interaction = await pick(bot, "magazines", "viibrations")

    assert private_replies(interaction) == [
        "♪ The magazines are gone from the shelf.\n♪ You have 0 WC."
    ]


@pytest.mark.parametrize(
    ("menu", "value"),
    [("snacks", "sinewave"), ("snacks", "nope"), ("badges", "nope"), ("gone", "x")],
)
async def test_something_the_vault_does_not_sell_is_turned_away(
    bot: app.WispBot, menu: str, value: str
) -> None:
    interaction = await pick(bot, menu, value)

    interaction.response.send_message.assert_awaited_once_with(
        "♪ That isn't in the ViiBR Vault any more.", ephemeral=True
    )
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}


# ---
# Finding the post
# ---


def test_the_interaction_vault_button_jumps_to_the_post() -> None:
    link = post_url(GUILD_ID, SHOP_ID)
    assert link == f"https://discord.com/channels/{GUILD_ID}/{SHOP_ID}"

    _, vault = interaction_lines(link)[2]

    assert isinstance(vault, discord.ui.Button)
    assert (vault.label, vault.url) == ("ViiBR Vault", link)
    assert vault.style is discord.ButtonStyle.link


def test_before_the_post_exists_the_vault_button_opens_it_privately() -> None:
    assert post_url(GUILD_ID, None) is None

    _, vault = interaction_lines(None)[2]

    assert isinstance(vault, ShopButton)
    assert vault.item.label == "ViiBR Vault"


def test_chat_in_the_vault_post_is_cleared() -> None:
    board = board_for(Settings(shop_thread_id=SHOP_ID), SHOP_ID)

    assert board is not None
    assert (board.title, board.purpose) == ("ViiBR Vault", "shopping")
