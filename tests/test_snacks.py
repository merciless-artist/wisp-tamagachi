"""Tests for the Vault and Snack Packs: buying snacks and feeding them to Wisp.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest
from discord import app_commands

import app
from cogs import groups, snacks
from cogs.conversation import PokeButton
from cogs.interaction import interaction_lines
from cogs.menus import ClosedMenu, menu_id
from cogs.snacks import (
    FeedButton,
    ShopButton,
    SnackPackButton,
    full_text,
    vault_buttons,
)
from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo
from db.cravings import CravingRepo
from db.database import Database
from db.drawings import DrawingRepo
from db.gifts import GiftRepo
from db.keepsakes import KeepsakeKind, KeepsakeRepo
from db.lives import LifeRepo
from db.magazines import MagazineRepo
from db.notes import NoteRepo
from db.players import Player, PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from tests.layout import (
    STYLE_EMOJIS,
    assert_is_a_menu,
    layout_order,
    layout_selects,
    layout_text,
    vault_opened,
    vault_parts,
)
from wisp import rules
from wisp.bond import PickleStance
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.rules import SNACK_BY_KEY, SNACKS, Stage
from wisp.text import (
    LAYOUT_TEXT_LIMIT,
    TITLE_BAR,
    UNICODE_FRAME,
    USER_ERROR,
    daily_reset,
    frame_of,
    text_length,
)

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
STATUS_ID = 40
ROOM_ID = 50
FIRST_POST_ID = 500
USER_ID = 1
OTHER_USER_ID = 2
NEWCOMER_ID = 3
QUALIFYING_ROLE = 7
NO_ROLE = (
    "♪ Wisp can't take that from you: you don't have a role that can feed Wisp: "
    f"<@&{QUALIFYING_ROLE}>."
)
NOT_OPENED = "♪ Wisp can't take that from you: you haven't opened /wisp board yet."
# Without the style's emojis uploaded, every menu is plain text.
FRAME = UNICODE_FRAME
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, the Status thread and the member's room.

    Every post in the room is a fake message with its own id, kept in `posted`.
    """

    def __init__(self) -> None:
        self.room = MagicMock(spec=discord.Thread)
        self.room.id = ROOM_ID
        self.room.parent_id = HOUSE_ID
        self.room.archived = False
        self.room.add_user = AsyncMock()
        self.room.send = AsyncMock(side_effect=self._post)
        self.room.get_partial_message.side_effect = self._partial
        self.posted: dict[int, MagicMock] = {}
        self.made = 0
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.id = HOUSE_ID
        self.house.send = AsyncMock()
        self.house.create_thread = AsyncMock(side_effect=self._create_thread)
        self.status = MagicMock(spec=discord.Thread)
        self.status.id = STATUS_ID
        self.status.parent_id = FORUM_ID
        self.status.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild.get_channel_or_thread.side_effect = channels.get

    def _create_thread(self, *, name: str, **_kwargs: Any) -> MagicMock:
        self.made += 1
        self.room.name = name
        return self.room

    def _post(self, *_args: Any, **kwargs: Any) -> MagicMock:
        message = MagicMock(spec=discord.Message)
        message.id = FIRST_POST_ID + len(self.posted)
        message.view = kwargs.get("view")
        message.allowed_mentions = kwargs.get("allowed_mentions")
        message.pin = AsyncMock()
        message.delete = AsyncMock()
        self.posted[message.id] = message
        return message

    def _partial(self, message_id: int) -> MagicMock:
        if message_id in self.posted:
            return self.posted[message_id]
        gone = MagicMock(spec=discord.PartialMessage)
        gone.delete = AsyncMock(
            side_effect=discord.NotFound(MagicMock(status=404), "Unknown Message")
        )
        return gone

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if not self.made or channel_id != ROOM_ID:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.room

    def packs(self) -> list[MagicMock]:
        """The Snack Packs posted in the room, oldest first."""
        return [message for message in self.posted.values() if message.view]


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
    )
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    for user_id in (USER_ID, OTHER_USER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())


@pytest.fixture(autouse=True)
def no_meeting(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    meeting = AsyncMock()
    monkeypatch.setattr(snacks, "maybe_meet", meeting)
    return meeting


def make_interaction(
    bot: app.WispBot,
    user_id: int = USER_ID,
    display_name: str = "Member1",
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = bot.get_guild(GUILD_ID)
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = display_name
    interaction.user.mention = f"<@{user_id}>"
    interaction.user.roles = [
        MagicMock(spec=discord.Role, id=role_id) for role_id in roles
    ]
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


def give_emojis(bot: app.WispBot, *names: str) -> None:
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(names, start=1)
    }


def emoji_text(name: str, index: int = 1) -> str:
    return f"<:{name}:{index}>"


async def lay(
    bot: app.WispBot, phase: Phase = Phase.ALIVE, health: float = 50.0, version: int = 1
) -> Life:
    life = new_egg(version, discord.utils.utcnow() - timedelta(days=1))
    life.phase = phase
    life.health = health
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


async def run(command: Any, *args: Any) -> None:
    await command.callback(*args)


async def open_vault(
    bot: app.WispBot, user_id: int = USER_ID
) -> tuple[MagicMock, discord.ui.Select[Any]]:
    interaction = make_interaction(bot, user_id)
    await run(snacks.wisp_vault, interaction)
    _, selects = vault_opened(interaction.followup.send)
    return interaction, selects[0]


def vault_text(interaction: MagicMock) -> str:
    """The text of the Vault the interaction was first answered with: every part."""
    parts = vault_parts(interaction.followup.send)
    assert all(isinstance(part, snacks.VaultLayout) for part in parts)
    text, _ = vault_opened(interaction.followup.send)
    return text


async def open_my_snack_pack(
    bot: app.WispBot, user_id: int = USER_ID, display_name: str = "Member1"
) -> MagicMock:
    interaction = make_interaction(bot, user_id, display_name)
    await run(snacks.wisp_snackpack, interaction)
    return interaction


async def vault_command(interaction: MagicMock) -> None:
    await run(snacks.wisp_vault, interaction)


async def snackpack_command(interaction: MagicMock) -> None:
    await run(snacks.wisp_snackpack, interaction)


async def shop_button(interaction: MagicMock) -> None:
    await ShopButton().callback(interaction)


async def snack_pack_button(interaction: MagicMock) -> None:
    await SnackPackButton().callback(interaction)


OPENERS = [vault_command, snackpack_command, shop_button, snack_pack_button]


async def choose(
    bot: app.WispBot,
    select: discord.ui.Select[Any],
    key: str,
    user_id: int = USER_ID,
) -> MagicMock:
    select._values = [key]
    interaction = make_interaction(bot, user_id)
    await select.callback(interaction)
    return interaction


async def buy(bot: app.WispBot, key: str, user_id: int = USER_ID) -> MagicMock:
    _, select = await open_vault(bot, user_id)
    return await choose(bot, select, key, user_id)


async def open_feeding(
    bot: app.WispBot, user_id: int = USER_ID
) -> tuple[MagicMock, discord.ui.Select[Any]]:
    interaction = make_interaction(bot, user_id)
    await FeedButton().callback(interaction)
    select = interaction.followup.send.await_args.kwargs["view"].children[0]
    return interaction, select


async def eat(bot: app.WispBot, key: str, user_id: int = USER_ID) -> MagicMock:
    inventory = await bot.activity_log.inventory(GUILD_ID, user_id)
    if inventory.get(key, 0) == 0 and key != "sinewave":
        await bot.activity_log.add_snack(GUILD_ID, user_id, key)
    _, select = await open_feeding(bot, user_id)
    return await choose(bot, select, key, user_id)


def option_values(select: discord.ui.Select[Any]) -> list[str]:
    return [option.value for option in select.options]


CLOUD_COST = next(snack.cost for snack in SNACKS if snack.key == "cloudwave")
HATCH_FIRST = "♪ Wisp isn't hatched yet. Snacks have to wait until he is."
NOT_ALIVE = "♪ Wisp isn't alive right now, so snacks have to wait."
FROZEN = "♪ Wisp is frozen right now, so nothing can change until staff unfreeze him."


def ate(name: str, meals: int = 1) -> str:
    """The receipt for the `meals`th snack a fresh Wisp has eaten."""
    now = rules.WELLBEING_START + meals * rules.WELLBEING_PER_SNACK
    return (
        f"♪ <@{USER_ID}> fed Wisp {name} ・ "
        f"Wellbeing +{rules.WELLBEING_PER_SNACK} (now {now:.0f})"
    )


def reply_text(interaction: MagicMock) -> str:
    """The text of the one ephemeral reply the interaction ended with.

    A Vault layout is read as its text displays joined in order; it is never
    sent with content of its own.
    """
    for method in (
        interaction.edit_original_response,
        interaction.response.send_message,
        interaction.followup.send,
    ):
        if method.await_args is not None:
            call = method.await_args
            assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
            view = call.kwargs.get("view")
            if isinstance(view, discord.ui.LayoutView):
                assert "content" not in call.kwargs and not call.args
                return layout_text(view)
            text = call.kwargs["content"] if "content" in call.kwargs else call.args[0]
            return cast(str, text)
    raise AssertionError("the interaction was never answered")


def house_text(server: FakeServer) -> str:
    return cast(str, server.house.send.await_args.args[0])


def house_line(server: FakeServer) -> str:
    """What Wisp said, under the line saying who fed him."""
    return house_text(server).splitlines()[-1]


def say(bot: app.WispBot, line: str = "yum") -> MagicMock:
    bot.lines = MagicMock()
    bot.lines.pick.return_value = line
    return cast(MagicMock, bot.lines.pick)


# ---
# Opening the Vault
# ---


def pack_text(interaction: MagicMock) -> str:
    """The text of the Snack Pack layout the interaction was answered with."""
    call = interaction.followup.send.await_args
    assert not call.args and "content" not in call.kwargs
    view = call.kwargs["view"]
    assert isinstance(view, discord.ui.LayoutView)
    return layout_text(view)


def pack_sections(text: str) -> list[list[str]]:
    """A Snack Pack's parts: the head under its title, then each section from
    its heading (snacks, keepsakes, badges); the footer is left out."""
    assert_is_a_menu(text, FRAME, "Snack Pack")
    sections: list[list[str]] = [[]]
    for line in text.splitlines()[1:-1]:
        if line.startswith("## "):
            sections.append([])
        sections[-1].append(line)
    return sections


def vault_snack(key: str, emoji: str, price: str) -> str:
    name = SNACK_BY_KEY[key].name
    return FRAME.item(f"{emoji} {name} ・ {price}" if emoji else f"{name} ・ {price}")


async def test_vault_is_three_layouts_in_the_house_frame(bot: app.WispBot) -> None:
    give_emojis(bot, "wisp_coin", "snack_cloudwave", "snack_sinewave", "wisp_coin_mini")
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)

    interaction, select = await open_vault(bot)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 3
    for call in calls:
        assert not call.args and "content" not in call.kwargs
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["wait"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    text = vault_text(interaction)
    lines = text.splitlines()
    mini = emoji_text("wisp_coin_mini", 4)
    paid = [snack for snack in SNACKS if snack.cost > 0]
    assert lines[: 5 + len(paid)] == [
        FRAME.title("ViiBR Vault"),
        FRAME.note(f"wisp coins: {emoji_text('wisp_coin')} 12"),
        FRAME.heading("Snacks", 0),
        vault_snack("sinewave", emoji_text("snack_sinewave", 3), "free once a day"),
        *(
            vault_snack(
                snack.key,
                emoji_text("snack_cloudwave", 2) if snack.key == "cloudwave" else "",
                f"{mini} {snack.cost} WC",
            )
            for snack in paid
        ),
        FRAME.heading("Badges", 2),
    ]
    assert lines[-1] == FRAME.footer
    assert_is_a_menu(text, FRAME, "ViiBR Vault")
    assert "x2" not in text
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)
    assert option_values(select) == [snack.key for snack in paid]
    assert [option.description for option in select.options][:2] == [
        "6 WC ・ wellbeing +8",
        "6 WC ・ wellbeing +8",
    ]


async def test_the_vault_is_in_the_favorites_style_once_its_emojis_are_up(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, *STYLE_EMOJIS)
    frame = frame_of(bot.emoji)

    interaction, _ = await open_vault(bot)

    text = vault_text(interaction)
    lines = text.splitlines()
    bar = "".join(bot.emoji(name) for name in TITLE_BAR)
    assert lines[:3] == [
        f"# {bar} **ViiBR VAULT** {bar}",
        frame.note("wisp coins: 0"),
        f"## {bot.emoji('boing_bass')} **SNACKS**",
    ]
    assert f"## {bot.emoji('wisp_pause')} **BADGES**" in lines
    assert lines[-1] == frame.footer
    assert lines[-1].startswith(f"### ・{bot.emoji('headerbarright')}")
    assert_is_a_menu(text, frame, "ViiBR Vault")
    assert not any(mark in text for mark in "║╠═╚│𝄡𝄚𝄂𝄆")


async def test_the_vaults_menus_sit_between_its_sections(bot: app.WispBot) -> None:
    await lay(bot)

    interaction, _ = await open_vault(bot)

    first, second, third = vault_parts(interaction.followup.send)
    assert layout_order(first) == ["text", "Buy a snack"]
    assert layout_order(second) == ["text"]
    assert layout_order(third) == ["text", "Pick a collection", "text"]
    snacks_part, badges_part, gifts_part, closing = (
        child.content
        for part in (first, second, third)
        for child in part.children
        if isinstance(child, discord.ui.TextDisplay)
    )
    last = SNACKS[-1]
    assert snacks_part.splitlines()[0] == FRAME.title("ViiBR Vault")
    assert snacks_part.splitlines()[-1] == vault_snack(last.key, "", f"{last.cost} WC")
    assert badges_part.splitlines()[0] == FRAME.heading("Badges", 2)
    assert gifts_part.splitlines()[0] == f"{FRAME.heading('Gifts', 4)} ・ 15 WC each"
    assert closing.splitlines() == [FRAME.footer]


async def test_the_vaults_note_comes_before_the_frame(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)

    interaction = await buy(bot, "cheese")

    lines = reply_text(interaction).splitlines()
    assert lines[:3] == [
        "♪ Bought Cheese for 6 WC.",
        FRAME.title("ViiBR Vault"),
        FRAME.note("wisp coins: 4"),
    ]
    view = interaction.edit_original_response.await_args.kwargs["view"]
    note, header = view.children[:2]
    assert isinstance(note, discord.ui.TextDisplay)
    assert isinstance(header, discord.ui.MediaGallery)


async def test_a_vault_that_cannot_be_sent_still_closes_its_pictures(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(bot)
    interaction.followup.send.side_effect = discord.HTTPException(
        MagicMock(status=500), "boom"
    )

    with pytest.raises(discord.HTTPException):
        await vault_command(interaction)

    files = interaction.followup.send.await_args.kwargs["files"]
    assert [file.filename for file in files] == ["vault_title.png"]
    assert all(file.fp.closed for file in files)


async def test_the_vault_opens_with_myras_header_and_closes_with_the_frame(
    bot: app.WispBot,
) -> None:
    interaction, _ = await open_vault(bot)

    first, *rest = interaction.followup.send.await_args_list
    assert len(rest) == 2
    assert [file.filename for file in first.kwargs["files"]] == ["vault_title.png"]
    assert all(file.fp.closed for file in first.kwargs["files"])
    assert all("files" not in call.kwargs for call in rest)
    header = first.kwargs["view"].children[0]
    closing = rest[-1].kwargs["view"].children[-1]
    assert isinstance(header, discord.ui.MediaGallery)
    assert [item.media.url for item in header.items] == ["attachment://vault_title.png"]
    assert isinstance(closing, discord.ui.TextDisplay)
    assert closing.content.splitlines()[-1] == FRAME.footer


async def test_vault_without_emojis_stays_tidy(bot: app.WispBot) -> None:
    interaction, _ = await open_vault(bot)

    text = vault_text(interaction)
    assert FRAME.note("wisp coins: 0") in text.splitlines()
    assert vault_snack("sinewave", "", "free once a day") in text.splitlines()
    assert vault_snack("cheese", "", "6 WC") in text.splitlines()
    assert "<:" not in text
    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    assert_is_a_menu(text, FRAME)


# ---
# Opening a Snack Pack
# ---


async def test_snack_pack_shows_snacks_keepsakes_and_shop_button(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, "wisp_coin_mini", "snack_cloudwave", "snack_sinewave")
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)
    await bot.keepsakes.give(
        GUILD_ID, USER_ID, KeepsakeKind.LAST_EMBER, 3, discord.utils.utcnow()
    )

    interaction = await open_my_snack_pack(bot)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.followup.send.assert_awaited_once()
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    text = pack_text(interaction)
    head, snack_lines, keepsakes, badges = pack_sections(text)
    assert head == [
        FRAME.note(f"<@{USER_ID}> snack pack"),
        FRAME.note(f"{emoji_text('wisp_coin_mini', 1)} 12 WC (wisp coins)"),
        FRAME.note("Drawings from Wisp: 0"),
    ]
    assert snack_lines == [
        FRAME.heading("Snacks", 0),
        FRAME.item(f"{emoji_text('snack_cloudwave', 2)} Cloud Wave x2"),
        FRAME.item(f"{emoji_text('snack_sinewave', 3)} Sine Wave free today"),
    ]
    assert keepsakes == [
        FRAME.heading("Keepsakes", 0),
        FRAME.item("Wisp v3's Last Ember"),
    ]
    assert badges == [FRAME.heading("Badges", 0), FRAME.item("none yet")]
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)
    header, _, row = kwargs["view"].children
    assert isinstance(header, discord.ui.MediaGallery)
    assert isinstance(row, discord.ui.ActionRow)
    (button,) = row.children
    assert isinstance(button, ShopButton)
    assert [file.filename for file in kwargs["files"]] == ["snack_pack_title.png"]


async def test_snack_pack_lists_paid_snacks_in_menu_order(bot: app.WispBot) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese")
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave", 3)

    interaction = await open_my_snack_pack(bot)

    snack_lines = pack_sections(pack_text(interaction))[1]
    assert snack_lines == [
        FRAME.heading("Snacks", 0),
        FRAME.item("Jelly Wave x3"),
        FRAME.item("Cheese x1"),
        FRAME.item("Sine Wave free today"),
    ]


async def test_snack_pack_shows_each_keepsakes_emoji_in_place_of_its_name(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, "keepsake_eggshell", "keepsake_last_ember")
    at = discord.utils.utcnow()
    for kind in (
        KeepsakeKind.EGGSHELL,
        KeepsakeKind.LAST_EMBER,
        KeepsakeKind.TEEN_SPARK,
    ):
        await bot.keepsakes.give(GUILD_ID, USER_ID, kind, 3, at)

    interaction = await open_my_snack_pack(bot)

    keepsakes = pack_sections(pack_text(interaction))[2]
    assert keepsakes == [
        FRAME.heading("Keepsakes", 0),
        FRAME.item(f"Wisp v3's {emoji_text('keepsake_eggshell', 1)}"),
        FRAME.item(f"Wisp v3's {emoji_text('keepsake_last_ember', 2)}"),
        FRAME.item("Wisp v3's Teen Spark"),
    ]


async def test_snack_pack_lists_the_newest_life_first_in_the_order_given(
    bot: app.WispBot,
) -> None:
    at = discord.utils.utcnow()
    for kind, version, minutes in (
        (KeepsakeKind.LAST_EMBER, 2, 50),
        (KeepsakeKind.TEEN_SPARK, 4, 20),
        (KeepsakeKind.EGGSHELL, 4, 0),
        (KeepsakeKind.FIRST_SPARK, 4, 10),
    ):
        await bot.keepsakes.give(
            GUILD_ID, USER_ID, kind, version, at + timedelta(minutes=minutes)
        )

    interaction = await open_my_snack_pack(bot)

    keepsakes = pack_sections(pack_text(interaction))[2]
    assert keepsakes == [
        FRAME.heading("Keepsakes", 0),
        FRAME.item("Wisp v4's Eggshell"),
        FRAME.item("Wisp v4's First Spark"),
        FRAME.item("Wisp v4's Teen Spark"),
        FRAME.item("Wisp v2's Last Ember"),
    ]


async def test_a_long_keepsake_list_is_cut_to_one_message(bot: app.WispBot) -> None:
    give_emojis(bot, *(f"keepsake_{kind.value}" for kind in KeepsakeKind))
    at = discord.utils.utcnow()
    lives = 30
    for version in range(1, lives + 1):
        for index, kind in enumerate(KeepsakeKind):
            await bot.keepsakes.give(
                GUILD_ID, USER_ID, kind, version, at + timedelta(minutes=index)
            )

    interaction = await open_my_snack_pack(bot)

    text = pack_text(interaction)
    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    keepsakes = pack_sections(text)[2]
    shown = keepsakes[1:-1]
    assert keepsakes[0] == FRAME.heading("Keepsakes", 1)
    assert keepsakes[-1] == FRAME.item(
        f"and {lives * len(KeepsakeKind) - len(shown)} more"
    )
    newest_first = [
        (version, kind) for version in range(lives, 0, -1) for kind in KeepsakeKind
    ]
    assert len(shown) < len(newest_first)
    for line, (version, kind) in zip(shown, newest_first, strict=False):
        assert line.startswith(
            FRAME.item(f"Wisp v{version}'s <:keepsake_{kind.value}:")
        ), line


async def test_empty_snack_pack_says_so(bot: app.WispBot) -> None:
    await bot.activity_log.record_interaction(
        GUILD_ID, 1, USER_ID, InteractionKind.FREE_SNACK, 0, 0, discord.utils.utcnow()
    )

    interaction = await open_my_snack_pack(bot)

    text = pack_text(interaction)
    head, snack_lines, keepsakes, badges = pack_sections(text)
    assert head == [
        FRAME.note(f"<@{USER_ID}> snack pack"),
        FRAME.note("0 WC (wisp coins)"),
        FRAME.note("Drawings from Wisp: 0"),
    ]
    assert snack_lines == [FRAME.heading("Snacks", 0), FRAME.item("nothing saved yet")]
    assert keepsakes == [FRAME.heading("Keepsakes", 0), FRAME.item("none yet")]
    assert badges == [FRAME.heading("Badges", 0), FRAME.item("none yet")]
    assert "free today" not in text


async def test_snack_pack_counts_the_drawings_wisp_made_for_the_member(
    bot: app.WispBot,
) -> None:
    now = discord.utils.utcnow()
    await bot.drawings.record(GUILD_ID, USER_ID, 1, "gift", 11, now)
    await bot.drawings.record(GUILD_ID, USER_ID, 1, "like", 12, now - timedelta(days=3))
    await bot.drawings.record(GUILD_ID, OTHER_USER_ID, 1, "like", 13, now)

    interaction = await open_my_snack_pack(bot)

    head = pack_sections(pack_text(interaction))[0]
    assert head[2] == FRAME.note("Drawings from Wisp: 2")


async def test_snack_pack_is_the_members_own(bot: app.WispBot) -> None:
    await bot.activity_log.add_snack(GUILD_ID, OTHER_USER_ID, "cheese")
    await bot.keepsakes.give(
        GUILD_ID, OTHER_USER_ID, KeepsakeKind.LAST_EMBER, 3, discord.utils.utcnow()
    )

    interaction = await open_my_snack_pack(bot)

    text = pack_text(interaction)
    assert pack_sections(text)[0][0] == FRAME.note(f"<@{USER_ID}> snack pack")
    assert f"<@{OTHER_USER_ID}>" not in text
    assert "cheese" not in text
    assert "Last Ember" not in text


@pytest.mark.parametrize("opener", OPENERS)
@pytest.mark.parametrize(
    ("banned_until", "banned_forever"),
    [(None, True), (discord.utils.utcnow() + timedelta(days=1), False)],
)
async def test_banned_member_cannot_open_vault_or_snack_pack(
    bot: app.WispBot,
    opener: Any,
    banned_until: datetime | None,
    banned_forever: bool,
) -> None:
    await bot.players.set_offense(GUILD_ID, USER_ID, 1, banned_until, banned_forever)
    interaction = make_interaction(bot)

    await opener(interaction)

    assert "not taking snacks" in reply_text(interaction)
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert "view" not in interaction.followup.send.await_args.kwargs


# ---
# The Vault buttons
# ---


async def test_shop_button_opens_the_vault_privately(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    interaction = make_interaction(bot)

    await ShopButton().callback(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    assert vault_text(interaction).splitlines()[1] == FRAME.note("wisp coins: 12")


async def test_snack_pack_button_opens_the_members_own_snack_pack(
    bot: app.WispBot,
) -> None:
    await bot.activity_log.add_snack(GUILD_ID, OTHER_USER_ID, "cheese")
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)
    interaction = make_interaction(bot, display_name="Member1")

    await SnackPackButton().callback(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    (button,) = kwargs["view"].children[-1].children
    assert isinstance(button, ShopButton)
    text = pack_text(interaction)
    assert pack_sections(text)[0][0] == FRAME.note(f"<@{USER_ID}> snack pack")
    assert FRAME.item("Cloud Wave x2") in text
    assert "cheese" not in text


async def test_vault_buttons_are_one_row_of_both_persistent_buttons() -> None:
    (row,) = vault_buttons()

    shop, mine = row
    assert isinstance(shop, ShopButton)
    assert (shop.item.label, shop.item.custom_id) == ("Shop the Vault", "wisp:vault")
    assert isinstance(mine, SnackPackButton)
    assert (mine.item.label, mine.item.custom_id) == (
        "Open my Snack Pack",
        "wisp:snackpack",
    )


@pytest.mark.parametrize(
    ("button", "custom_id"),
    [(ShopButton, "wisp:vault"), (SnackPackButton, "wisp:snackpack")],
)
async def test_vault_buttons_survive_restart(
    bot: app.WispBot, button: Any, custom_id: str
) -> None:
    match = button.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert match is not None

    restored = await button.from_custom_id(
        make_interaction(bot), MagicMock(spec=discord.ui.Button), match
    )

    assert isinstance(restored, button)


@pytest.mark.parametrize(
    ("opener", "context"),
    [
        (shop_button, "the Vault shop button"),
        (snack_pack_button, "the Snack Pack button"),
    ],
)
@pytest.mark.parametrize(
    "error",
    [
        pymysql.err.OperationalError(2013, "Lost connection"),
        discord.Forbidden(MagicMock(status=403), "Missing Access"),
    ],
)
async def test_a_failing_vault_button_reports_where_it_was_pressed(
    bot: app.WispBot,
    monkeypatch: pytest.MonkeyPatch,
    opener: Any,
    context: str,
    error: Exception,
) -> None:
    interaction = make_interaction(bot)
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    monkeypatch.setattr(bot.players, "get", AsyncMock(side_effect=error))

    await opener(interaction)

    reported.assert_awaited_once_with(
        interaction.guild, context, error, where=interaction.channel
    )
    interaction.followup.send.assert_awaited_once_with(USER_ERROR, ephemeral=True)


@pytest.mark.parametrize(
    ("opener", "context"),
    [
        (shop_button, "the Vault shop button"),
        (snack_pack_button, "the Snack Pack button"),
    ],
)
async def test_a_vault_button_that_cannot_acknowledge_is_reported(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch, opener: Any, context: str
) -> None:
    interaction = make_interaction(bot)
    expired = discord.NotFound(MagicMock(status=404), "Unknown interaction")
    interaction.response.defer.side_effect = expired
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await opener(interaction)

    reported.assert_awaited_once_with(
        interaction.guild, context, expired, where=interaction.channel
    )


# ---
# The Snack Pack in the room
# ---


@pytest.mark.parametrize("opener", [snackpack_command, snack_pack_button])
async def test_opening_the_snack_pack_also_pins_it_in_the_room(
    bot: app.WispBot, server: FakeServer, opener: Any
) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave")
    interaction = make_interaction(bot)

    await opener(interaction)

    (pack,) = server.packs()
    assert layout_text(pack.view) == pack_text(interaction)
    assert pack.allowed_mentions.to_dict() == NO_PING
    pack.pin.assert_awaited_once_with()
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.room_thread_id, player.room_pack_message_id) == (ROOM_ID, pack.id)


async def test_the_room_pack_is_reposted_not_duplicated(
    bot: app.WispBot, server: FakeServer
) -> None:
    await open_my_snack_pack(bot)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave")

    interaction = await open_my_snack_pack(bot)

    first, second = server.packs()
    first.delete.assert_awaited_once_with()
    second.delete.assert_not_awaited()
    second.pin.assert_awaited_once_with()
    assert layout_text(second.view) == pack_text(interaction)
    assert server.made == 1
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert player.room_pack_message_id == second.id


async def test_a_room_pack_deleted_by_hand_is_simply_replaced(
    bot: app.WispBot, server: FakeServer
) -> None:
    await open_my_snack_pack(bot)
    await bot.players.set_room_pack(GUILD_ID, USER_ID, 999)

    await open_my_snack_pack(bot)

    assert len(server.packs()) == 2
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert player.room_pack_message_id == server.packs()[-1].id


@pytest.mark.parametrize("opener", [snackpack_command, snack_pack_button])
async def test_a_member_who_has_not_joined_gets_no_room(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch, opener: Any
) -> None:
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    interaction = make_interaction(bot, OTHER_USER_ID + 1)

    await opener(interaction)

    assert pack_text(interaction)
    assert server.made == 0
    assert not server.packs()
    reported.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, OTHER_USER_ID + 1)).room_thread_id is None


async def test_a_room_that_fails_still_shows_the_private_pack(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = discord.Forbidden(MagicMock(status=403), "Missing Access")
    server.house.create_thread.side_effect = error
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    interaction = await open_my_snack_pack(bot)

    assert pack_text(interaction)
    assert not server.packs()
    reported.assert_awaited_once_with(
        server.guild,
        "showing the Snack Pack in a room",
        error,
        where=interaction.channel,
    )


async def test_a_failed_pin_keeps_the_room_pack(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    error = discord.Forbidden(MagicMock(status=403), "Missing Permissions")
    real_post = server.room.send.side_effect

    def unpinnable(*args: Any, **kwargs: Any) -> MagicMock:
        message = cast(MagicMock, real_post(*args, **kwargs))
        message.pin.side_effect = error
        return message

    server.room.send.side_effect = unpinnable
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await open_my_snack_pack(bot)

    (pack,) = server.packs()
    pack.delete.assert_not_awaited()
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert player.room_pack_message_id == pack.id
    report = reported.await_args
    assert report is not None
    assert report.args[1:] == ("showing the Snack Pack in a room", error)


# ---
# Buying
# ---


async def test_buy_spends_balance_not_lifetime(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)

    interaction = await buy(bot, "cloudwave")

    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.lifetime_points) == (4, 10)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    interaction.response.defer.assert_awaited_once_with()
    interaction.edit_original_response.assert_awaited_once()
    interaction.followup.send.assert_not_awaited()
    text = reply_text(interaction)
    assert text.startswith("♪ Bought Cloud Wave for 6 WC.")
    assert FRAME.note("wisp coins: 4") in text.splitlines()
    assert isinstance(
        interaction.edit_original_response.await_args.kwargs["view"],
        snacks.VaultLayout,
    )


async def test_buying_twice_stacks_the_snack(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 15)
    _, select = await open_vault(bot)

    await choose(bot, select, "jellywave")
    await choose(bot, select, "jellywave")

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"jellywave": 2}
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 3


async def test_buy_refused_when_short(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 2)
    pick = say(bot, "not enough points for that one")

    interaction = await buy(bot, "cloudwave")

    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 2
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    pick.assert_called_once_with(Moment.NOT_ENOUGH_POINTS, Mood.HAPPY, name="Member1")
    interaction.followup.send.assert_awaited_once()
    assert reply_text(interaction) == (
        "not enough points for that one"
        f"\n♪ That costs {CLOUD_COST} WC and you have 2."
    )
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    interaction.edit_original_response.assert_not_awaited()


async def test_buy_uses_the_chosen_name(bot: app.WispBot) -> None:
    await bot.players.set_name(GUILD_ID, USER_ID, "Zed")
    pick = say(bot)

    await buy(bot, "cloudwave")

    pick.assert_called_once_with(Moment.NOT_ENOUGH_POINTS, Mood.HAPPY, name="Zed")


async def test_ban_issued_after_opening_blocks_buying(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    _, select = await open_vault(bot)
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await choose(bot, select, "cloudwave")

    assert "not taking snacks" in reply_text(interaction)
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 10
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}


# ---
# The Feed Wisp button
# ---


async def test_the_interaction_vault_button_answers_like_wisp_vault(
    bot: app.WispBot,
) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    _, vault = interaction_lines(None)[2]
    pressed = make_interaction(bot)
    asked = make_interaction(bot)

    await vault.callback(pressed)
    await vault_command(asked)

    pressed.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert pressed.followup.send.await_args.kwargs["ephemeral"] is True
    assert vault_text(pressed) == vault_text(asked)


async def test_the_interaction_snack_pack_button_answers_like_wisp_snackpack(
    bot: app.WispBot,
) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)
    _, pack = interaction_lines(None)[3]
    pressed = make_interaction(bot)
    asked = make_interaction(bot)

    await pack.callback(pressed)
    await snackpack_command(asked)

    pressed.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert pressed.followup.send.await_args.kwargs["ephemeral"] is True
    assert pack_text(pressed) == pack_text(asked)
    assert FRAME.item("Cloud Wave x2") in pack_text(pressed)


async def test_a_banned_member_pressing_the_interaction_vault_is_told_why(
    bot: app.WispBot,
) -> None:
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)
    interaction = make_interaction(bot)

    _, vault = interaction_lines(None)[2]
    await vault.callback(interaction)

    assert reply_text(interaction) == (
        "♪ Wisp is not taking snacks or gifts from you right now."
    )
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True


async def test_feed_button_survives_restart(bot: app.WispBot) -> None:
    match = FeedButton.__discord_ui_compiled_template__.fullmatch("wisp:feed")
    assert match is not None
    restored = await FeedButton.from_custom_id(
        make_interaction(bot), MagicMock(spec=discord.ui.Button), match
    )
    assert isinstance(restored, FeedButton)

    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]
    await snacks.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(
        FeedButton, PokeButton, ShopButton, SnackPackButton, ClosedMenu
    )


async def open_feed_menu(interaction: MagicMock) -> None:
    await FeedButton().callback(interaction)


@pytest.mark.parametrize(
    "opener", [vault_command, shop_button, snackpack_command, open_feed_menu]
)
async def test_every_private_menu_is_filed_under_its_message(
    bot: app.WispBot, opener: Any
) -> None:
    await lay(bot)
    interaction = make_interaction(bot)

    await opener(interaction)

    sent = [
        call
        for call in interaction.followup.send.await_args_list
        if "view" in call.kwargs
    ]
    assert sent
    for call in sent:
        assert call.kwargs["wait"] is True
        assert call.kwargs["ephemeral"] is True


async def test_the_vaults_selects_carry_this_runs_token(bot: app.WispBot) -> None:
    life = await lay(bot)
    life.sniffles_left = 60.0
    await bot.lives.save(GUILD_ID, life)
    interaction = make_interaction(bot)

    await vault_command(interaction)

    _, selects = vault_opened(interaction.followup.send)
    assert [select.custom_id for select in selects] == [
        menu_id(slot) for slot in ("snacks", "medicine", "collections")
    ]


async def test_pressing_feed_lists_inventory_and_the_free_sine(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, "snack_cheese")
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese", 3)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")

    interaction, select = await open_feeding(bot)

    assert option_values(select) == ["sinewave", "cloudwave", "cheese"]
    labels = {option.value: option.label for option in select.options}
    assert labels["cheese"] == "Cheese x3"
    assert labels["sinewave"] == "Sine Wave (free today)"
    descriptions = {option.value: option.description for option in select.options}
    assert descriptions == {
        snack.key: "wellbeing +8"
        for snack in SNACKS
        if snack.key in ("sinewave", "cloudwave", "cheese")
    }
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    cheese = next(option for option in select.options if option.value == "cheese")
    assert str(cheese.emoji) == emoji_text("snack_cheese")


async def test_the_feed_command_offers_the_same_snacks_as_the_button(
    bot: app.WispBot,
) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese", 2)
    interaction = make_interaction(bot)

    await run(snacks.wisp_feed, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert option_values(kwargs["view"].children[0]) == ["sinewave", "cheese"]


async def test_pressing_feed_with_nothing_to_feed_says_so(bot: app.WispBot) -> None:
    await lay(bot)
    await eat(bot, "sinewave")
    interaction = make_interaction(bot)

    await FeedButton().callback(interaction)

    assert "no snacks" in reply_text(interaction)
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert "view" not in interaction.followup.send.await_args.kwargs


@pytest.mark.parametrize(
    ("banned_until", "banned_forever"),
    [(None, True), (discord.utils.utcnow() + timedelta(days=1), False)],
)
async def test_a_banned_member_gets_no_menu_from_the_button(
    bot: app.WispBot, banned_until: datetime | None, banned_forever: bool
) -> None:
    await bot.players.set_offense(GUILD_ID, USER_ID, 1, banned_until, banned_forever)
    interaction = make_interaction(bot)

    await FeedButton().callback(interaction)

    assert "not taking snacks" in reply_text(interaction)
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert "view" not in interaction.followup.send.await_args.kwargs


@pytest.mark.parametrize(
    ("user_id", "roles", "reason"),
    [
        (USER_ID, (), NO_ROLE),
        (USER_ID, (QUALIFYING_ROLE + 1,), NO_ROLE),
        (NEWCOMER_ID, (QUALIFYING_ROLE,), NOT_OPENED),
    ],
)
async def test_only_qualifying_members_get_a_menu_from_the_button(
    bot: app.WispBot,
    server: FakeServer,
    user_id: int,
    roles: tuple[int, ...],
    reason: str,
) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, user_id, "cloudwave")
    interaction = make_interaction(bot, user_id, roles=roles)

    await FeedButton().callback(interaction)

    assert reply_text(interaction) == reason
    assert "view" not in interaction.followup.send.await_args.kwargs
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize("opener", OPENERS)
async def test_members_who_cannot_feed_still_open_the_vault_and_snack_pack(
    bot: app.WispBot, opener: Any
) -> None:
    interaction = make_interaction(bot, NEWCOMER_ID, roles=())

    await opener(interaction)

    assert "view" in interaction.followup.send.await_args.kwargs


async def test_losing_the_role_after_the_menu_opened_blocks_eating(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    select._values = ["cloudwave"]
    interaction = make_interaction(bot, roles=())

    await select.callback(interaction)

    assert reply_text(interaction) == NO_ROLE
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    assert (await current_life(bot)).growth == 0
    server.house.send.assert_not_awaited()


# ---
# Buying the snack he craved
# ---

BOUGHT_ANYWAY = "they lost my Craving but bought me the Jelly Wave anyway"


async def craving(
    bot: app.WispBot, snack: str, *, won: bool, at: datetime | None = None
) -> None:
    now = at or discord.utils.utcnow()
    round_ = await bot.cravings.start(GUILD_ID, USER_ID, snack, now)
    await bot.cravings.end(GUILD_ID, USER_ID, round_.day, won=won, now=now)


async def notes(bot: app.WispBot) -> list[str]:
    return await bot.notes.recent(GUILD_ID, USER_ID)


async def test_buying_the_craved_snack_after_losing_leaves_one_note(
    bot: app.WispBot,
) -> None:
    await craving(bot, "jellywave", won=False)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)
    _, select = await open_vault(bot)

    await choose(bot, select, "jellywave")
    await choose(bot, select, "jellywave")

    assert await notes(bot) == [BOUGHT_ANYWAY]
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"jellywave": 2}


async def test_buying_another_snack_after_losing_leaves_no_note(
    bot: app.WispBot,
) -> None:
    await craving(bot, "jellywave", won=False)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    await buy(bot, "cloudwave")

    assert await notes(bot) == []


@pytest.mark.parametrize("ended", [True, False])
async def test_buying_after_a_win_or_mid_round_leaves_no_note(
    bot: app.WispBot, ended: bool
) -> None:
    now = discord.utils.utcnow()
    if ended:
        await craving(bot, "jellywave", won=True)
    else:
        await bot.cravings.start(GUILD_ID, USER_ID, "jellywave", now)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    await buy(bot, "jellywave")

    assert await notes(bot) == []


async def test_buying_after_a_round_lost_past_midnight_leaves_a_note(
    bot: app.WispBot,
) -> None:
    midnight = datetime.combine(discord.utils.utcnow().date(), time(), tzinfo=UTC)
    round_ = await bot.cravings.start(
        GUILD_ID, USER_ID, "jellywave", midnight - timedelta(minutes=2)
    )
    await bot.cravings.end(GUILD_ID, USER_ID, round_.day, won=False, now=midnight)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    await buy(bot, "jellywave")

    assert await notes(bot) == [BOUGHT_ANYWAY]


async def test_buying_the_snack_of_an_earlier_loss_today_leaves_a_note(
    bot: app.WispBot,
) -> None:
    midnight = datetime.combine(discord.utils.utcnow().date(), time(), tzinfo=UTC)
    yesterday = await bot.cravings.start(
        GUILD_ID, USER_ID, "jellywave", midnight - timedelta(minutes=2)
    )
    await bot.cravings.end(GUILD_ID, USER_ID, yesterday.day, won=False, now=midnight)
    today = await bot.cravings.start(
        GUILD_ID, USER_ID, "cloudwave", midnight + timedelta(seconds=1)
    )
    await bot.cravings.end(
        GUILD_ID, USER_ID, today.day, won=False, now=midnight + timedelta(seconds=2)
    )
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    await buy(bot, "jellywave")

    assert await notes(bot) == [BOUGHT_ANYWAY]


async def test_buying_the_day_after_losing_leaves_no_note(bot: app.WispBot) -> None:
    await craving(
        bot, "jellywave", won=False, at=discord.utils.utcnow() - timedelta(days=1)
    )
    await bot.players.add_points(GUILD_ID, USER_ID, 20)

    await buy(bot, "jellywave")

    assert await notes(bot) == []


# ---
# Feeding
# ---


async def test_feed_takes_one_and_adds_full_growth_bond(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, health=50.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "spicywave", 2)

    interaction = await eat(bot, "spicywave")

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"spicywave": 1}
    life = await current_life(bot)
    assert life.health == 50.0
    assert life.wellbeing == 50.0 + 8
    assert life.growth == 2
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == rules.BOND_PER_SNACK
    now = discord.utils.utcnow()
    assert await bot.activity_log.snack_points_today(GUILD_ID, USER_ID, now) == 8
    assert await bot.activity_log.track_points_today(GUILD_ID, USER_ID, now) == 0
    assert await bot.activity_log.casual_bond_today(GUILD_ID, USER_ID, now) == 1
    assert not await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    interaction.response.defer.assert_awaited_once_with()
    interaction.delete_original_response.assert_awaited_once_with()
    server.house.send.assert_awaited_once()
    assert house_text(server).startswith(f"{ate('Spicy Wave')}\n")


@pytest.mark.parametrize("key", ["sinewave", "cheese"])
async def test_a_snack_fills_wellbeing_by_eight_not_health(
    bot: app.WispBot, key: str
) -> None:
    await lay(bot, health=50.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese")

    await eat(bot, key)

    life = await current_life(bot)
    assert life.health == 50.0
    assert life.wellbeing == 58.0


@pytest.mark.parametrize("key", ["sinewave", "cheese"])
async def test_a_snack_is_counted_as_eaten_this_life(
    bot: app.WispBot, key: str
) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese")

    await eat(bot, key)

    assert await bot.activity_log.most_eaten_snack(GUILD_ID, life.id) == key


async def test_a_snack_restarts_the_wellbeing_stretch(bot: app.WispBot) -> None:
    life = await lay(bot)
    life.wellbeing_stretch = 10800.0
    life.health_stretch = 10800.0
    await bot.lives.save(GUILD_ID, life)

    await eat(bot, "sinewave")

    life = await current_life(bot)
    assert life.wellbeing_stretch == 0.0
    assert life.health_stretch == 10800.0


async def test_a_full_day_of_tracks_does_not_stop_a_snack(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.FEED,
        0,
        rules.DAILY_MEAL_CAP,
        discord.utils.utcnow(),
    )
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese")

    await eat(bot, "cheese")

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    assert (await current_life(bot)).wellbeing == 58.0


async def test_the_snack_limit_message_says_tracks_still_feed_him() -> None:
    now = discord.utils.utcnow()

    assert full_text(now) == (
        "♪ Wisp is full of snacks from you today. Your tracks still feed him. "
        f"Snacks reset at {daily_reset(now)}."
    )


async def test_the_snack_post_says_wellbeing(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "spicywave")

    await eat(bot, "spicywave")

    assert house_text(server).startswith(f"{ate('Spicy Wave')}\n")


async def test_free_sine_once_a_day(bot: app.WispBot, server: FakeServer) -> None:
    await lay(bot, health=50.0)

    await eat(bot, "sinewave")

    now = discord.utils.utcnow()
    assert await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    life = await current_life(bot)
    assert (life.health, life.growth) == (50.0, 1)
    assert house_text(server).startswith(f"{ate('Sine Wave')}\n")

    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    assert option_values(select) == ["cloudwave"]
    select._values = ["sinewave"]
    again = make_interaction(bot)
    await select.callback(again)

    assert "free Sine Wave" in reply_text(again)
    assert (await current_life(bot)).wellbeing == 58.0
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}


async def test_the_free_sine_comes_back_the_next_day(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    await bot.activity_log.record_interaction(
        GUILD_ID, life.id, USER_ID, InteractionKind.FREE_SNACK, 1, 2, yesterday
    )

    _, select = await open_feeding(bot)

    assert option_values(select) == ["sinewave"]


async def test_casual_bond_capped_at_seven(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.PLAY,
        rules.DAILY_CASUAL_BOND_CAP,
        0,
        discord.utils.utcnow(),
    )

    await eat(bot, "cloudwave")

    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 0
    now = discord.utils.utcnow()
    assert await bot.activity_log.casual_bond_today(GUILD_ID, USER_ID, now) == 7
    life = await current_life(bot)
    assert (life.health, life.growth) == (50.0, 1)


async def test_the_last_bond_point_of_the_day_still_lands(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.PLAY,
        rules.DAILY_CASUAL_BOND_CAP - 1,
        0,
        discord.utils.utcnow(),
    )

    await eat(bot, "cloudwave")
    await eat(bot, "cloudwave")

    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 1


async def test_the_last_snack_of_the_day_counts_only_what_fits(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot, health=40.0)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.SNACK,
        0,
        rules.DAILY_SNACK_CAP - 3,
        discord.utils.utcnow(),
    )

    await eat(bot, "cloudwave")

    life = await current_life(bot)
    assert (life.health, life.growth) == (40.0, 1)
    assert house_text(server).startswith(f"{ate('Cloud Wave')}\n")
    now = discord.utils.utcnow()
    assert (
        await bot.activity_log.snack_points_today(GUILD_ID, USER_ID, now)
        == rules.DAILY_SNACK_CAP
    )


async def test_the_snack_limit_stays_the_same_while_sick(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot, health=40.0)
    assert life.id is not None
    life.cold_left = rules.SICK_FOR.total_seconds()
    life.had_cold = True
    await bot.lives.save(GUILD_ID, life)
    now = discord.utils.utcnow()

    for meals in (1, 2, 3):
        await eat(bot, "cloudwave")
        assert house_text(server).startswith(f"{ate('Cloud Wave', meals)}\n")
    full = await eat(bot, "cloudwave")

    assert reply_text(full) == full_text(now)
    assert (await current_life(bot)).health == 40.0
    assert (
        await bot.activity_log.snack_points_today(GUILD_ID, USER_ID, now)
        == rules.DAILY_SNACK_CAP
    )


@pytest.mark.parametrize("key", ["cloudwave", "sinewave"])
async def test_a_snack_at_the_daily_cap_is_refused_and_kept(
    bot: app.WispBot, server: FakeServer, db: Database, key: str
) -> None:
    life = await lay(bot, health=40.0)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.SNACK,
        0,
        rules.DAILY_SNACK_CAP,
        discord.utils.utcnow(),
    )

    full = await eat(bot, key)

    now = discord.utils.utcnow()
    assert reply_text(full) == full_text(now)
    inventory = {} if key == "sinewave" else {key: 1}
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == inventory
    assert not await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    rows = await db.fetchall(f"SELECT kind FROM {db.t('interactions')}")
    assert rows == [{"kind": InteractionKind.SNACK.value}]
    life = await current_life(bot)
    assert (life.health, life.growth) == (40.0, 0)
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 0
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize(
    ("phase", "reason"),
    [(Phase.EGG, HATCH_FIRST), (Phase.HATCHING, HATCH_FIRST), (Phase.DEAD, NOT_ALIVE)],
)
async def test_cannot_feed_egg_with_snacks(
    bot: app.WispBot, server: FakeServer, phase: Phase, reason: str
) -> None:
    await lay(bot, phase=phase, health=0.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)

    interaction = await choose(bot, select, "cloudwave")

    assert reply_text(interaction) == reason
    assert interaction.edit_original_response.await_args.kwargs["view"] is None
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    life = await current_life(bot)
    assert (life.health, life.growth, life.egg_food) == (0.0, 0, 0)
    assert (
        await bot.activity_log.snack_points_today(
            GUILD_ID, USER_ID, discord.utils.utcnow()
        )
        == 0
    )
    server.house.send.assert_not_awaited()


async def test_cannot_feed_while_frozen(bot: app.WispBot, server: FakeServer) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    await bot.settings.update(GUILD_ID, frozen=True)

    interaction = await choose(bot, select, "cloudwave")

    assert reply_text(interaction) == FROZEN
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    assert (await current_life(bot)).wellbeing == rules.WELLBEING_START
    server.house.send.assert_not_awaited()


async def test_cannot_feed_before_any_life_exists(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)

    interaction = await choose(bot, select, "cloudwave")

    assert reply_text(interaction) == NOT_ALIVE
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    server.house.send.assert_not_awaited()


async def test_a_snack_eaten_elsewhere_is_not_eaten_twice(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    await choose(bot, select, "cloudwave")

    interaction = await choose(bot, select, "cloudwave")

    assert "out of Cloud Wave" in reply_text(interaction)
    assert (await current_life(bot)).growth == 1
    server.house.send.assert_awaited_once()


async def test_ban_issued_after_the_menu_opened_blocks_feeding(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await choose(bot, select, "cloudwave")

    assert "not taking snacks" in reply_text(interaction)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    server.house.send.assert_not_awaited()


async def test_simultaneous_feeds_both_count(bot: app.WispBot) -> None:
    await lay(bot, health=40.0)
    for user in (USER_ID, OTHER_USER_ID):
        await bot.activity_log.add_snack(GUILD_ID, user, "cloudwave")
    selects = [(await open_feeding(bot, user))[1] for user in (USER_ID, OTHER_USER_ID)]

    await asyncio.gather(
        choose(bot, selects[0], "cloudwave", USER_ID),
        choose(bot, selects[1], "cloudwave", OTHER_USER_ID),
    )

    life = await current_life(bot)
    assert (life.health, life.growth) == (40.0, 2)


# ---
# Medicine
# ---


async def catch_cold(bot: app.WispBot) -> None:
    life = await current_life(bot)
    life.sniffles_left = rules.SNIFFLES_FOR.total_seconds()
    await bot.lives.save(GUILD_ID, life)


async def medicine_select(
    bot: app.WispBot, user_id: int = USER_ID
) -> discord.ui.Select[Any]:
    interaction = make_interaction(bot, user_id)
    await run(snacks.wisp_vault, interaction)
    _, selects = vault_opened(interaction.followup.send)
    (select,) = [
        found for found in selects if found.placeholder == "Give Wisp medicine"
    ]
    return select


async def test_medicine_shows_in_the_vault_only_while_he_has_a_cold(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    well, _ = await open_vault(bot)
    await catch_cold(bot)
    sick, _ = await open_vault(bot)

    well_view, *_ = vault_parts(well.followup.send)
    sick_view, *_ = vault_parts(sick.followup.send)
    assert "Medicine" not in layout_text(well_view)
    assert "Give Wisp medicine" not in layout_order(well_view)
    sections = [
        line for line in layout_text(sick_view).splitlines() if line.startswith("## ")
    ]
    assert sections.index(FRAME.heading("Medicine", 1)) == 1
    assert sections[0] == FRAME.heading("Snacks", 0)
    order = layout_order(sick_view)
    assert order.index("Buy a snack") + 2 == order.index("Give Wisp medicine")
    select = next(
        found
        for found in layout_selects(sick_view)
        if found.placeholder == "Give Wisp medicine"
    )
    assert option_values(select) == ["medicine"]
    assert select.options[0].description == "10 WC ・ cures his cold"


async def test_buying_medicine_cures_him_and_pays_three(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await catch_cold(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    select = await medicine_select(bot)

    interaction = await choose(bot, select, "medicine")

    assert (await current_life(bot)).sniffles_left == 0
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == -10 + 10 + 3
    assert reply_text(interaction).startswith("♪ You gave Wisp his medicine ・ +3 WC")
    post = server.house.send.await_args
    assert post.kwargs["file"].filename == "medicine.png"
    assert post.kwargs["allowed_mentions"].to_dict() == NO_PING
    life = await current_life(bot)
    assert life.id is not None
    (given,) = await bot.story.recent(GUILD_ID, life.id)
    assert (given.kind, given.member_id) == ("medicine", USER_ID)


async def test_medicine_while_he_naps_gets_a_sleepy_line(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await catch_cold(bot)
    life = await current_life(bot)
    life.nap_left = 1800.0
    await bot.lives.save(GUILD_ID, life)
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    select = await medicine_select(bot)
    pick = say(bot, "*gulp* zzz")

    await choose(bot, select, "medicine")

    assert (await current_life(bot)).sniffles_left == 0
    pick.assert_called_once_with(Moment.MEDICINE_ASLEEP, Mood.HAPPY, name="Member1")
    assert house_text(server) == "*gulp* zzz"


async def test_a_second_buyer_is_refused_before_paying(bot: app.WispBot) -> None:
    await lay(bot)
    await catch_cold(bot)
    for user in (USER_ID, OTHER_USER_ID):
        await bot.players.add_points(GUILD_ID, user, 10)
    first = await medicine_select(bot, USER_ID)
    second = await medicine_select(bot, OTHER_USER_ID)

    await choose(bot, first, "medicine", USER_ID)
    refused = await choose(bot, second, "medicine", OTHER_USER_ID)

    assert (await bot.players.get(GUILD_ID, OTHER_USER_ID)).balance == 10
    assert "♪ Wisp doesn't have a cold right now." in reply_text(refused)


async def test_two_buyers_at_once_pay_once(bot: app.WispBot) -> None:
    await lay(bot)
    await catch_cold(bot)
    for user in (USER_ID, OTHER_USER_ID):
        await bot.players.add_points(GUILD_ID, user, 10)
    first = await medicine_select(bot, USER_ID)
    second = await medicine_select(bot, OTHER_USER_ID)

    await asyncio.gather(
        choose(bot, first, "medicine", USER_ID),
        choose(bot, second, "medicine", OTHER_USER_ID),
    )

    balances = sorted(
        [
            (await bot.players.get(GUILD_ID, USER_ID)).balance,
            (await bot.players.get(GUILD_ID, OTHER_USER_ID)).balance,
        ]
    )
    assert balances == [3, 10]


async def test_medicine_needs_enough_coins(bot: app.WispBot) -> None:
    await lay(bot)
    await catch_cold(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 9)
    select = await medicine_select(bot)
    pick = say(bot, "not enough points for that one")

    interaction = await choose(bot, select, "medicine")

    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 9
    assert (await current_life(bot)).sniffles_left > 0
    pick.assert_any_call(Moment.NOT_ENOUGH_POINTS, Mood.HAPPY, name="Member1")
    assert reply_text(interaction).startswith(
        "not enough points for that one"
        f"\n♪ That costs {rules.MEDICINE_COST} WC and you have 9."
    )


@pytest.mark.parametrize(
    ("phase", "reason"),
    [
        (
            Phase.EGG,
            "♪ Wisp isn't hatched yet. Doses of medicine have to wait until he is.",
        ),
        (
            Phase.DEAD,
            "♪ Wisp isn't alive right now, so doses of medicine have to wait.",
        ),
    ],
)
async def test_medicine_needs_a_living_wisp(
    bot: app.WispBot, phase: Phase, reason: str
) -> None:
    await lay(bot)
    await catch_cold(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    select = await medicine_select(bot)
    await lay(bot, phase=phase, health=0.0, version=2)

    interaction = await choose(bot, select, "medicine")

    assert reply_text(interaction).startswith(reason)
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 10


async def test_medicine_while_frozen_says_he_is_frozen(bot: app.WispBot) -> None:
    await lay(bot)
    await catch_cold(bot)
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    select = await medicine_select(bot)
    await bot.settings.update(GUILD_ID, frozen=True)

    interaction = await choose(bot, select, "medicine")

    assert reply_text(interaction).startswith(FROZEN)
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 10
    assert (await current_life(bot)).sniffles_left > 0


# ---
# Wisp's House
# ---


@pytest.mark.parametrize(
    ("key", "moment"),
    [
        ("cloudwave", Moment.SNACK),
        ("cheese", Moment.SNACK),
        ("spicywave", Moment.SPICY),
        ("juicewave", Moment.JUICE),
        ("pickles", Moment.PICKLE_HEDGE),
        ("glitterwave", Moment.SNACK),
        ("viibrwave", Moment.SNACK_FANCY),
    ],
)
async def test_snack_line_matches_the_snack(
    bot: app.WispBot, key: str, moment: Moment
) -> None:
    await lay(bot, health=50.0)
    pick = say(bot)

    await eat(bot, key)

    pick.assert_called_once_with(moment, Mood.HAPPY, name="Member1")


@pytest.mark.parametrize("stance", [None, *PickleStance])
@pytest.mark.parametrize("key", ["cheese", "pickles", "sinewave", "viibrwave"])
async def test_his_favorite_snack_gets_its_own_line(
    bot: app.WispBot, server: FakeServer, key: str, stance: PickleStance | None
) -> None:
    life = await lay(bot, health=50.0)
    life.favorite_snack = key
    await bot.lives.save(GUILD_ID, life)
    await bot.players.set_pickle_stance(GUILD_ID, USER_ID, stance)
    pick = say(bot, "my favorite")

    await eat(bot, key)

    pick.assert_called_once_with(Moment.SNACK_FAVORITE, Mood.HAPPY, name="Member1")
    assert house_line(server) == "my favorite"


@pytest.mark.parametrize("key", ["cheese", "pickles", "spicywave", "sinewave"])
async def test_a_snack_while_he_naps_is_eaten_in_his_sleep(
    bot: app.WispBot, server: FakeServer, key: str
) -> None:
    life = await lay(bot, health=50.0)
    life.favorite_snack = "cheese"
    life.nap_left = 1800.0
    await bot.lives.save(GUILD_ID, life)
    pick = say(bot, "*munch* zzz")

    await eat(bot, key)

    pick.assert_called_once_with(Moment.SNACK_ASLEEP, Mood.HAPPY, name="Member1")
    assert house_text(server).endswith("*munch* zzz")
    assert house_text(server).startswith(f"♪ <@{USER_ID}> fed Wisp ")


async def test_a_snack_that_is_not_his_favorite_gets_the_usual_line(
    bot: app.WispBot,
) -> None:
    life = await lay(bot, health=5.0)
    life.favorite_snack = "cheese"
    await bot.lives.save(GUILD_ID, life)
    pick = say(bot)

    await eat(bot, "cloudwave")

    pick.assert_called_once_with(Moment.SNACK, Mood.HANGRY, name="Member1")


async def test_his_favorite_snack_line_follows_his_mood(bot: app.WispBot) -> None:
    life = await lay(bot, health=5.0)
    life.favorite_snack = "cloudwave"
    await bot.lives.save(GUILD_ID, life)
    pick = say(bot)

    await eat(bot, "cloudwave")

    pick.assert_called_once_with(Moment.SNACK_FAVORITE, Mood.HANGRY, name="Member1")


async def test_a_won_snack_is_eaten_first_then_it_is_ordinary(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, health=50.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave")
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave", won=True)
    pick = say(bot, "the one you won!")

    await eat(bot, "jellywave")
    await eat(bot, "jellywave")

    assert [(said.args, said.kwargs) for said in pick.call_args_list] == [
        ((Moment.SNACK_WON, Mood.HAPPY), {"name": "Member1", "snack": "Jelly Wave"}),
        ((Moment.SNACK, Mood.HAPPY), {"name": "Member1"}),
    ]
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    assert server.house.send.await_args_list[0].args[0].endswith("the one you won!")


async def lost_and_bought(bot: app.WispBot, snack: str) -> None:
    await craving(bot, snack, won=False)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)
    await buy(bot, snack)


async def test_the_craved_snack_bought_after_losing_gets_its_line_once(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, health=50.0)
    await lost_and_bought(bot, "jellywave")
    pick = say(bot, "you got it for me anyway")

    await eat(bot, "jellywave")
    await eat(bot, "jellywave")

    assert [(said.args, said.kwargs) for said in pick.call_args_list] == [
        (
            (Moment.SNACK_CRAVING_BOUGHT, Mood.HAPPY),
            {"name": "Member1", "snack": "Jelly Wave"},
        ),
        ((Moment.SNACK, Mood.HAPPY), {"name": "Member1"}),
    ]
    first = server.house.send.await_args_list[0].args[0]
    assert first.endswith("you got it for me anyway")


async def test_a_won_snack_comes_before_the_bought_craving(bot: app.WispBot) -> None:
    await lay(bot, health=50.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave", won=True)
    await lost_and_bought(bot, "jellywave")
    pick = say(bot)

    await eat(bot, "jellywave")
    await eat(bot, "jellywave")

    assert [said.args[0] for said in pick.call_args_list] == [
        Moment.SNACK_WON,
        Moment.SNACK_CRAVING_BOUGHT,
    ]


async def test_the_bought_craving_beats_his_favorite_and_his_nap(
    bot: app.WispBot,
) -> None:
    life = await lay(bot, health=50.0)
    life.favorite_snack = "jellywave"
    life.nap_left = 1800.0
    await bot.lives.save(GUILD_ID, life)
    await lost_and_bought(bot, "jellywave")
    pick = say(bot)

    await eat(bot, "jellywave")

    pick.assert_called_once_with(
        Moment.SNACK_CRAVING_BOUGHT, Mood.HAPPY, name="Member1", snack="Jelly Wave"
    )


async def test_a_lost_craving_not_bought_is_an_ordinary_snack(
    bot: app.WispBot,
) -> None:
    await lay(bot, health=50.0)
    await craving(bot, "jellywave", won=False)
    await bot.players.add_points(GUILD_ID, USER_ID, 20)
    await buy(bot, "cloudwave")
    pick = say(bot)

    await eat(bot, "jellywave")
    await eat(bot, "cloudwave")

    assert [said.args[0] for said in pick.call_args_list] == [
        Moment.SNACK,
        Moment.SNACK,
    ]


async def test_a_won_snack_beats_his_favorite_and_his_nap(bot: app.WispBot) -> None:
    life = await lay(bot, health=50.0)
    life.favorite_snack = "jellywave"
    life.nap_left = 1800.0
    await bot.lives.save(GUILD_ID, life)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave", won=True)
    pick = say(bot)

    await eat(bot, "jellywave")

    pick.assert_called_once_with(
        Moment.SNACK_WON, Mood.HAPPY, name="Member1", snack="Jelly Wave"
    )


def test_fancy_starts_at_the_fancy_cost() -> None:
    fancy = {snack.key for snack in SNACKS if snack.cost >= rules.FANCY_SNACK_COST}

    assert fancy == {"viibrwave"}


async def test_house_post_has_the_snack_emoji_and_line(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(snacks, "_eating_gif", lambda gif_name: None)
    give_emojis(bot, "snack_cloudwave")
    await lay(bot)
    say(bot, "yum")

    await eat(bot, "cloudwave")

    server.house.send.assert_awaited_once()
    assert house_line(server) == f"{emoji_text('snack_cloudwave')} yum"
    kwargs = server.house.send.await_args.kwargs
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    assert "file" not in kwargs


async def test_house_post_without_the_emoji_is_just_the_line(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    say(bot, "yum")

    await eat(bot, "cloudwave")

    assert house_line(server) == "yum"


async def test_his_mood_after_the_snack_picks_the_line(bot: app.WispBot) -> None:
    await lay(bot, health=5.0)
    hangry = say(bot)

    await eat(bot, "cloudwave")

    hangry.assert_called_once_with(Moment.SNACK, Mood.HANGRY, name="Member1")


async def test_the_chosen_name_is_used_over_the_display_name(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    await bot.players.set_name(GUILD_ID, USER_ID, "Zed")
    pick = say(bot)

    await eat(bot, "cloudwave")

    pick.assert_called_once_with(Moment.SNACK, Mood.HAPPY, name="Zed")


async def test_eating_gif_attached_when_present(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "eating").mkdir()
    (tmp_path / "eating" / "eat_cloudwave.gif").write_bytes(b"GIF89a")
    monkeypatch.setattr(snacks, "ASSETS_DIR", tmp_path)
    await lay(bot)

    await eat(bot, "cloudwave")
    await eat(bot, "cheese")

    first, second = server.house.send.await_args_list
    attached = first.kwargs["file"]
    assert isinstance(attached, discord.File)
    assert attached.filename == "eat_cloudwave.gif"
    assert "file" not in second.kwargs


@pytest.mark.parametrize(
    ("stance", "moment", "gif"),
    [
        (None, Moment.PICKLE_HEDGE, "eat_pickles.gif"),
        (PickleStance.LOVE, Moment.PICKLE_HATE, "eat_pickles_hate.gif"),
        (PickleStance.HATE, Moment.PICKLE_LOVE, "eat_pickles_love.gif"),
    ],
)
async def test_pickles_follow_the_members_stance(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stance: PickleStance | None,
    moment: Moment,
    gif: str,
) -> None:
    (tmp_path / "eating").mkdir()
    for name in ("eat_pickles", "eat_pickles_hate", "eat_pickles_love"):
        (tmp_path / "eating" / f"{name}.gif").write_bytes(b"GIF89a")
    monkeypatch.setattr(snacks, "ASSETS_DIR", tmp_path)
    await lay(bot)
    await bot.players.set_pickle_stance(GUILD_ID, USER_ID, stance)
    pick = say(bot, "a pickle take")

    await eat(bot, "pickles")

    pick.assert_called_once_with(moment, Mood.HAPPY, name="Member1")
    assert house_line(server) == "a pickle take"
    attached = server.house.send.await_args.kwargs["file"]
    assert isinstance(attached, discord.File)
    assert attached.filename == gif


async def test_a_missing_stance_gif_means_text_only(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "eating").mkdir()
    (tmp_path / "eating" / "eat_pickles.gif").write_bytes(b"GIF89a")
    monkeypatch.setattr(snacks, "ASSETS_DIR", tmp_path)
    await lay(bot)
    await bot.players.set_pickle_stance(GUILD_ID, USER_ID, PickleStance.LOVE)
    pick = say(bot)

    await eat(bot, "pickles")

    pick.assert_called_once_with(Moment.PICKLE_HATE, Mood.HAPPY, name="Member1")
    assert "file" not in server.house.send.await_args.kwargs


@pytest.mark.parametrize("stance", list(PickleStance))
async def test_the_stance_only_changes_pickles(
    bot: app.WispBot, stance: PickleStance
) -> None:
    await lay(bot)
    await bot.players.set_pickle_stance(GUILD_ID, USER_ID, stance)
    pick = say(bot)

    await eat(bot, "cheese")

    pick.assert_called_once_with(Moment.SNACK, Mood.HAPPY, name="Member1")


async def test_feeding_lets_wisp_meet_the_member(
    bot: app.WispBot, no_meeting: AsyncMock
) -> None:
    await lay(bot)

    await eat(bot, "cloudwave")

    no_meeting.assert_awaited_once_with(bot, GUILD_ID, USER_ID, display_name="Member1")


async def test_a_refused_feed_does_not_meet_anyone(
    bot: app.WispBot, no_meeting: AsyncMock
) -> None:
    await lay(bot, phase=Phase.EGG, health=0.0)

    await eat(bot, "cloudwave")

    no_meeting.assert_not_awaited()


async def test_a_missing_house_is_logged_and_the_snack_still_counts(
    bot: app.WispBot, server: FakeServer, caplog: pytest.LogCaptureFixture
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    await lay(bot)

    with caplog.at_level(logging.ERROR, logger="wisp"):
        interaction = await eat(bot, "cloudwave")

    assert (await current_life(bot)).growth == 1
    interaction.delete_original_response.assert_awaited_once_with()
    server.house.send.assert_not_awaited()
    assert "Error in posting to Wisp's House" in caplog.text


# ---
# Failures
# ---


@pytest.mark.parametrize(
    "error",
    [
        pymysql.err.OperationalError(2013, "Lost connection"),
        discord.Forbidden(MagicMock(status=403), "Missing Access"),
    ],
)
async def test_a_failing_feed_button_reports_where_it_was_pressed(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    interaction = make_interaction(bot)
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    monkeypatch.setattr(bot.activity_log, "inventory", AsyncMock(side_effect=error))

    await FeedButton().callback(interaction)

    reported.assert_awaited_once_with(
        interaction.guild, "the Feed WiSP button", error, where=interaction.channel
    )
    interaction.followup.send.assert_awaited_once_with(USER_ERROR, ephemeral=True)


async def test_a_feed_button_failure_is_posted_in_the_status_thread(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    interaction = make_interaction(bot)
    interaction.guild = server.guild
    interaction.channel = server.status
    error = pymysql.err.OperationalError(2013, "Lost connection")
    monkeypatch.setattr(bot.activity_log, "inventory", AsyncMock(side_effect=error))

    await FeedButton().callback(interaction)

    server.status.send.assert_awaited_once()
    report = server.status.send.await_args
    assert report.args == (
        "Error in the Feed WiSP button: OperationalError: (2013, 'Lost connection')",
    )
    assert report.kwargs["allowed_mentions"].to_dict() == NO_PING
    server.house.send.assert_not_awaited()
    interaction.followup.send.assert_awaited_once_with(USER_ERROR, ephemeral=True)


async def test_a_feed_button_that_cannot_even_acknowledge_is_reported(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    interaction = make_interaction(bot)
    expired = discord.NotFound(MagicMock(status=404), "Unknown interaction")
    interaction.response.defer.side_effect = expired
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await FeedButton().callback(interaction)

    reported.assert_awaited_once_with(
        interaction.guild, "the Feed WiSP button", expired, where=interaction.channel
    )


async def test_the_feed_button_acknowledges_before_touching_storage(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    interaction = make_interaction(bot)

    async def inventory(guild_id: int, user_id: int) -> dict[str, int]:
        interaction.response.defer.assert_awaited_once()
        return {}

    monkeypatch.setattr(bot.activity_log, "inventory", inventory)

    await FeedButton().callback(interaction)

    interaction.followup.send.assert_awaited_once()


async def test_buying_acknowledges_before_touching_storage(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, select = await open_vault(bot)
    interaction = make_interaction(bot)

    async def get(guild_id: int, user_id: int) -> Player:
        interaction.response.defer.assert_awaited_once()
        return Player(user_id=user_id)

    monkeypatch.setattr(bot.players, "get", get)
    select._values = ["cloudwave"]

    await select.callback(interaction)

    interaction.followup.send.assert_awaited_once()


async def test_a_failed_confirmation_says_the_purchase_went_through(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    _, select = await open_vault(bot)
    select._values = ["cloudwave"]
    interaction = make_interaction(bot)
    expired = discord.NotFound(MagicMock(status=404), "Unknown interaction")
    interaction.edit_original_response.side_effect = expired
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await select.callback(interaction)

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 4
    reported.assert_awaited_once_with(
        interaction.guild,
        "confirming a snack purchase (the purchase went through)",
        expired,
        where=interaction.channel,
    )
    interaction.followup.send.assert_not_awaited()


async def test_a_failing_menu_is_reported_where_it_was_used(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(bot)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("boom")
    menu = snacks.Menu(
        "the snack menu", snacks.SnackSelect([], "Pick", AsyncMock(), "feed")
    )

    await menu.on_error(interaction, error, menu.children[0])

    bot.report_error.assert_awaited_once_with(
        interaction.guild, "the snack menu", error, where=interaction.channel
    )
    interaction.response.send_message.assert_awaited_once_with(
        USER_ERROR, ephemeral=True
    )


async def test_a_failing_vault_menu_is_reported_where_it_was_used(
    bot: app.WispBot,
) -> None:
    _, select = await open_vault(bot)
    interaction = make_interaction(bot)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("boom")
    assert isinstance(select.view, snacks.VaultLayout)

    await select.view.on_error(interaction, error, select)

    bot.report_error.assert_awaited_once_with(
        interaction.guild, "the ViiBR Vault menu", error, where=interaction.channel
    )
    interaction.response.send_message.assert_awaited_once_with(
        USER_ERROR, ephemeral=True
    )


# ---
# Extension
# ---


def test_snack_pack_and_vault_hang_off_the_wisp_group() -> None:
    assert groups.wisp.get_command("snackpack") is snacks.wisp_snackpack
    assert groups.wisp.get_command("feed") is snacks.wisp_feed
    assert groups.wisp.get_command("vault") is snacks.wisp_vault
    assert groups.wisp.get_command("gift") is snacks.wisp_gift
    assert isinstance(snacks.wisp_gift, app_commands.Command)
    assert isinstance(snacks.wisp_snackpack, app_commands.Command)
    assert isinstance(snacks.wisp_vault, app_commands.Command)


def test_the_commands_say_what_they_do() -> None:
    assert snacks.wisp_snackpack.description == "See your snacks and keepsakes."
    assert snacks.wisp_vault.description == (
        "Buy snacks and gifts for Wisp in the ViiBR Vault."
    )
    assert snacks.wisp_gift.description == "Give Wisp a gift from the ViiBR Vault."


def test_snacks_is_a_loaded_extension() -> None:
    assert "cogs.snacks" in app.EXTENSIONS
