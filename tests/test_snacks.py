"""Tests for the Vault and Snack Packs: buying snacks and feeding them to Wisp.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import logging
import re
from collections.abc import Iterator
from datetime import datetime, timedelta
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
from cogs.snacks import (
    FeedButton,
    ShopButton,
    SnackPackButton,
    status_view,
    vault_view,
)
from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo
from db.database import Database
from db.gifts import GiftRepo
from db.keepsakes import KeepsakeKind, KeepsakeRepo
from db.lives import LifeRepo
from db.players import Player, PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.bond import PickleStance
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.rules import SNACKS, Stage
from wisp.text import MESSAGE_LIMIT, USER_ERROR, text_length

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
STATUS_ID = 40
USER_ID = 1
OTHER_USER_ID = 2
NEWCOMER_ID = 3
QUALIFYING_ROLE = 7
CANNOT_FEED = (
    "♪ Only members at Active Lounger or higher who have opened /wisp board "
    "can feed Wisp."
)
VAULT_EDGE = "𝄃𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂"
PACK_TOP = "┌─────────────────┓"
DIVIDER = "├─────────────────•"
PACK_BOTTOM = "└─────────────────┛"
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and the Status thread."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.status = MagicMock(spec=discord.Thread)
        self.status.id = STATUS_ID
        self.status.parent_id = FORUM_ID
        self.status.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild.get_channel_or_thread.side_effect = channels.get


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
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.keepsakes = KeepsakeRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
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
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = display_name
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


async def lay(bot: app.WispBot, phase: Phase = Phase.ALIVE, full: float = 50.0) -> Life:
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=1))
    life.phase = phase
    life.full = full
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
    select = interaction.followup.send.await_args.kwargs["view"].children[0]
    return interaction, select


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


def reply_text(interaction: MagicMock) -> str:
    """The text of the one ephemeral reply the interaction ended with."""
    for method in (
        interaction.edit_original_response,
        interaction.response.send_message,
        interaction.followup.send,
    ):
        if method.await_args is not None:
            call = method.await_args
            assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
            text = call.kwargs["content"] if "content" in call.kwargs else call.args[0]
            return cast(str, text)
    raise AssertionError("the interaction was never answered")


def house_text(server: FakeServer) -> str:
    return cast(str, server.house.send.await_args.args[0])


def say(bot: app.WispBot, line: str = "yum") -> MagicMock:
    bot.lines = MagicMock()
    bot.lines.pick.return_value = line
    return cast(MagicMock, bot.lines.pick)


# ---
# Opening the Vault
# ---


def pack_sections(text: str) -> list[list[str]]:
    """A Snack Pack's sections inside its frame: head, snacks, keepsakes, badges."""
    lines = text.splitlines()
    assert lines[0] == PACK_TOP
    assert lines[-1] == PACK_BOTTOM
    return [
        section.splitlines() for section in "\n".join(lines[1:-1]).split(DIVIDER + "\n")
    ]


async def test_vault_shows_the_snack_box_with_a_buy_select(bot: app.WispBot) -> None:
    give_emojis(bot, "wisp_coin", "snack_cloudwave", "snack_sinewave")
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)

    interaction, select = await open_vault(bot)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    assert isinstance(kwargs["view"], snacks.Menu)
    text = interaction.followup.send.await_args.args[0]
    lines = text.splitlines()
    assert lines[:5] == [
        f"♪ You have {emoji_text('wisp_coin')} 12 points",
        VAULT_EDGE,
        "╔══ 𝆕 𝐕𝐢𝐢𝐁𝐑 𝐕𝐀𝐔𝐋𝐓 𝆕. ══╗",
        "𝄃 **Snacks**",
        f"𝄃 {emoji_text('snack_sinewave', 3)}・free once a day",
    ]
    assert lines[-2:] == ["╚══════════════════╝", VAULT_EDGE]
    paid = [snack for snack in SNACKS if snack.cost > 0]
    assert lines[5 : 5 + len(paid)] == [
        (
            f"𝄃 {emoji_text('snack_cloudwave', 2)}・3 points"
            if snack.key == "cloudwave"
            else f"𝄃 {snack.name}・{snack.cost} points"
        )
        for snack in paid
    ]
    assert "Sine Wave" not in text
    assert "x2" not in text
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)
    assert option_values(select) == [snack.key for snack in paid]


async def test_vault_title_shows_the_viibr_logo_when_uploaded(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, "viibr_logo")

    interaction, _ = await open_vault(bot)

    text = interaction.followup.send.await_args.args[0]
    assert text.splitlines()[2] == (
        f"╔══ 𝆕 𝐕𝐢𝐢𝐁𝐑 {emoji_text('viibr_logo')} 𝐕𝐀𝐔𝐋𝐓 𝆕. ══╗"
    )


async def test_vault_without_emojis_stays_tidy(bot: app.WispBot) -> None:
    interaction, _ = await open_vault(bot)

    text = interaction.followup.send.await_args.args[0]
    assert text.splitlines()[:2] == ["♪ You have 0 points", VAULT_EDGE]
    assert "𝄃 Sine Wave・free once a day" in text
    assert text_length(text) <= MESSAGE_LIMIT


# ---
# Opening a Snack Pack
# ---


async def test_snack_pack_shows_snacks_keepsakes_and_shop_button(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, "wisp_coin", "snack_cloudwave", "snack_sinewave")
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)
    await bot.keepsakes.give(
        GUILD_ID, USER_ID, KeepsakeKind.LAST_EMBER, 3, discord.utils.utcnow()
    )

    interaction = await open_my_snack_pack(bot)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    text = interaction.followup.send.await_args.args[0]
    head, snack_lines, keepsakes, badges = pack_sections(text)
    assert head == [
        f"│<@{USER_ID}> snack pack",
        f"│{emoji_text('wisp_coin')} 12 points",
    ]
    assert snack_lines == [
        "│**Snacks**",
        f"│cloudwave {emoji_text('snack_cloudwave', 2)} x2",
        f"│sinewave {emoji_text('snack_sinewave', 3)} free today",
    ]
    assert keepsakes == ["│**Keepsakes**", "│Wisp v3's Last Ember"]
    assert badges == ["│**Badges**", "│ None yet"]
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)
    (button,) = kwargs["view"].children
    assert isinstance(button, ShopButton)


async def test_snack_pack_lists_paid_snacks_in_menu_order(bot: app.WispBot) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cheese")
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "jellywave", 3)

    interaction = await open_my_snack_pack(bot)

    snack_lines = pack_sections(interaction.followup.send.await_args.args[0])[1]
    assert snack_lines == [
        "│**Snacks**",
        "│jellywave x3",
        "│cheese x1",
        "│sinewave free today",
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

    keepsakes = pack_sections(interaction.followup.send.await_args.args[0])[2]
    assert keepsakes == [
        "│**Keepsakes**",
        f"│Wisp v3's {emoji_text('keepsake_eggshell', 1)}",
        f"│Wisp v3's {emoji_text('keepsake_last_ember', 2)}",
        "│Wisp v3's Teen Spark",
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

    keepsakes = pack_sections(interaction.followup.send.await_args.args[0])[2]
    assert keepsakes == [
        "│**Keepsakes**",
        "│Wisp v4's Eggshell",
        "│Wisp v4's First Spark",
        "│Wisp v4's Teen Spark",
        "│Wisp v2's Last Ember",
    ]


async def test_a_long_keepsake_list_is_cut_to_one_message(bot: app.WispBot) -> None:
    give_emojis(bot, *(f"keepsake_{kind.value}" for kind in KeepsakeKind))
    at = discord.utils.utcnow()
    lives = 12
    for version in range(1, lives + 1):
        for index, kind in enumerate(KeepsakeKind):
            await bot.keepsakes.give(
                GUILD_ID, USER_ID, kind, version, at + timedelta(minutes=index)
            )

    interaction = await open_my_snack_pack(bot)

    text = interaction.followup.send.await_args.args[0]
    assert text_length(text) <= MESSAGE_LIMIT
    keepsakes = pack_sections(text)[2]
    shown = keepsakes[1:-1]
    assert keepsakes[0] == "│**Keepsakes**"
    assert keepsakes[-1] == f"│ and {lives * len(KeepsakeKind) - len(shown)} more"
    newest_first = [
        (version, kind) for version in range(lives, 0, -1) for kind in KeepsakeKind
    ]
    assert len(shown) < len(newest_first)
    for line, (version, kind) in zip(shown, newest_first, strict=False):
        assert line.startswith(f"│Wisp v{version}'s <:keepsake_{kind.value}:"), line


async def test_empty_snack_pack_says_so(bot: app.WispBot) -> None:
    await bot.activity_log.record_interaction(
        GUILD_ID, 1, USER_ID, InteractionKind.FREE_SNACK, 0, 0, discord.utils.utcnow()
    )

    interaction = await open_my_snack_pack(bot)

    text = interaction.followup.send.await_args.args[0]
    head, snack_lines, keepsakes, badges = pack_sections(text)
    assert head == [f"│<@{USER_ID}> snack pack", "│0 points"]
    assert snack_lines == ["│**Snacks**", "│ Nothing saved yet"]
    assert keepsakes == ["│**Keepsakes**", "│ None yet"]
    assert badges == ["│**Badges**", "│ None yet"]
    assert "free today" not in text


async def test_snack_pack_is_the_members_own(bot: app.WispBot) -> None:
    await bot.activity_log.add_snack(GUILD_ID, OTHER_USER_ID, "cheese")
    await bot.keepsakes.give(
        GUILD_ID, OTHER_USER_ID, KeepsakeKind.LAST_EMBER, 3, discord.utils.utcnow()
    )

    interaction = await open_my_snack_pack(bot)

    text = interaction.followup.send.await_args.args[0]
    assert pack_sections(text)[0][0] == f"│<@{USER_ID}> snack pack"
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
    assert isinstance(kwargs["view"], snacks.Menu)
    text = interaction.followup.send.await_args.args[0]
    assert text.splitlines()[:2] == ["♪ You have 12 points", VAULT_EDGE]


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
    (button,) = kwargs["view"].children
    assert isinstance(button, ShopButton)
    text = interaction.followup.send.await_args.args[0]
    assert pack_sections(text)[0][0] == f"│<@{USER_ID}> snack pack"
    assert "│cloudwave x2" in text
    assert "cheese" not in text


async def test_vault_view_holds_both_persistent_buttons() -> None:
    view = vault_view()

    shop, mine = view.children
    assert isinstance(shop, ShopButton)
    assert (shop.item.label, shop.item.custom_id) == ("Shop the Vault", "wisp:vault")
    assert isinstance(mine, SnackPackButton)
    assert (mine.item.label, mine.item.custom_id) == (
        "Open my Snack Pack",
        "wisp:snackpack",
    )
    assert view.timeout is None


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
# Buying
# ---


async def test_buy_spends_balance_not_lifetime(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)

    interaction = await buy(bot, "cloudwave")

    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.lifetime_points) == (7, 10)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    interaction.response.defer.assert_awaited_once_with()
    interaction.edit_original_response.assert_awaited_once()
    interaction.followup.send.assert_not_awaited()
    text = reply_text(interaction)
    assert text.startswith("♪ Bought Cloud Wave for 3 points.")
    assert "7 points" in text


async def test_buying_twice_stacks_the_snack(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    _, select = await open_vault(bot)

    await choose(bot, select, "jellywave")
    await choose(bot, select, "jellywave")

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"jellywave": 2}
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 4


async def test_buy_refused_when_short(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 2)
    pick = say(bot, "not enough points for that one")

    interaction = await buy(bot, "cloudwave")

    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 2
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    pick.assert_called_once_with(Moment.NOT_ENOUGH_POINTS, Mood.HAPPY, name="Member1")
    interaction.followup.send.assert_awaited_once()
    assert reply_text(interaction) == "not enough points for that one"
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


async def test_status_view_has_persistent_feed_and_poke_buttons() -> None:
    view = status_view()

    feed, poke = view.children
    assert isinstance(feed, FeedButton)
    assert feed.item.label == "Feed Wisp"
    assert feed.item.custom_id == "wisp:feed"
    assert isinstance(poke, PokeButton)
    assert poke.item.label == "Poke Wisp"
    assert poke.item.custom_id == "wisp:poke"
    assert view.timeout is None


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
        FeedButton, PokeButton, ShopButton, SnackPackButton
    )


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
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    cheese = next(option for option in select.options if option.value == "cheese")
    assert str(cheese.emoji) == emoji_text("snack_cheese")


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
    ("user_id", "roles"),
    [
        (USER_ID, ()),
        (USER_ID, (QUALIFYING_ROLE + 1,)),
        (NEWCOMER_ID, (QUALIFYING_ROLE,)),
    ],
)
async def test_only_qualifying_members_get_a_menu_from_the_button(
    bot: app.WispBot, server: FakeServer, user_id: int, roles: tuple[int, ...]
) -> None:
    await lay(bot)
    await bot.activity_log.add_snack(GUILD_ID, user_id, "cloudwave")
    interaction = make_interaction(bot, user_id, roles=roles)

    await FeedButton().callback(interaction)

    assert reply_text(interaction) == CANNOT_FEED
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

    assert reply_text(interaction) == CANNOT_FEED
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    assert (await current_life(bot)).growth == 0
    server.house.send.assert_not_awaited()


# ---
# Feeding
# ---


async def test_feed_takes_one_and_adds_full_growth_bond(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, full=50.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "spicywave", 2)

    interaction = await eat(bot, "spicywave")

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"spicywave": 1}
    life = await current_life(bot)
    assert life.full == 50.0 + 8
    assert life.growth == 2
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == rules.BOND_PER_SNACK
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, USER_ID, now) == 8
    assert await bot.activity_log.casual_bond_today(GUILD_ID, USER_ID, now) == 1
    assert not await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    interaction.response.defer.assert_awaited_once_with()
    assert reply_text(interaction) == "♪ Wisp ate your Spicy Wave ・ full +8"
    assert interaction.edit_original_response.await_args.kwargs["view"] is None
    server.house.send.assert_awaited_once()


async def test_free_sine_once_a_day(bot: app.WispBot) -> None:
    await lay(bot, full=50.0)

    first = await eat(bot, "sinewave")

    now = discord.utils.utcnow()
    assert await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    life = await current_life(bot)
    assert (life.full, life.growth) == (52.0, 1)
    assert reply_text(first) == "♪ Wisp ate your Sine Wave ・ full +2"

    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    assert option_values(select) == ["cloudwave"]
    select._values = ["sinewave"]
    again = make_interaction(bot)
    await select.callback(again)

    assert "free Sine Wave" in reply_text(again)
    assert (await current_life(bot)).full == 52.0
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
    assert (life.full, life.growth) == (55.0, 1)


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


async def test_snack_counts_toward_daily_meal_cap(bot: app.WispBot) -> None:
    life = await lay(bot, full=40.0)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.FEED,
        0,
        rules.DAILY_MEAL_CAP - 3,
        discord.utils.utcnow(),
    )

    capped = await eat(bot, "cloudwave")

    life = await current_life(bot)
    assert (life.full, life.growth) == (43.0, 1)
    assert (
        reply_text(capped) == "♪ Wisp ate your Cloud Wave ・ full +3 (daily meal limit)"
    )
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, USER_ID, now) == 15


async def test_the_meal_cap_doubles_while_sick(bot: app.WispBot) -> None:
    life = await lay(bot, full=40.0)
    assert life.id is not None
    life.cold_left = rules.SICK_FOR.total_seconds()
    life.had_cold = True
    await bot.lives.save(GUILD_ID, life)
    now = discord.utils.utcnow()
    await bot.activity_log.record_interaction(
        GUILD_ID, life.id, USER_ID, InteractionKind.FEED, 0, rules.DAILY_MEAL_CAP, now
    )

    replies = [reply_text(await eat(bot, "cloudwave")) for _ in range(4)]

    assert replies == [
        "♪ Wisp ate your Cloud Wave ・ full +5",
        "♪ Wisp ate your Cloud Wave ・ full +5",
        "♪ Wisp ate your Cloud Wave ・ full +5",
        "♪ Wisp is full from you today. Save it for tomorrow.",
    ]
    assert (await current_life(bot)).full == 55.0
    cap = rules.DAILY_MEAL_CAP + rules.SICK_EXTRA_MEAL_CAP
    assert await bot.activity_log.meal_points_today(GUILD_ID, USER_ID, now) == cap


@pytest.mark.parametrize("key", ["cloudwave", "sinewave"])
async def test_a_snack_at_the_daily_cap_is_refused_and_kept(
    bot: app.WispBot, server: FakeServer, db: Database, key: str
) -> None:
    life = await lay(bot, full=40.0)
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

    full = await eat(bot, key)

    assert reply_text(full) == "♪ Wisp is full from you today. Save it for tomorrow."
    inventory = {} if key == "sinewave" else {key: 1}
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == inventory
    now = discord.utils.utcnow()
    assert not await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    rows = await db.fetchall(f"SELECT kind FROM {db.t('interactions')}")
    assert rows == [{"kind": InteractionKind.FEED.value}]
    life = await current_life(bot)
    assert (life.full, life.growth) == (40.0, 0)
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 0
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
async def test_cannot_feed_egg_with_snacks(
    bot: app.WispBot, server: FakeServer, phase: Phase
) -> None:
    await lay(bot, phase=phase, full=0.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)

    interaction = await choose(bot, select, "cloudwave")

    assert "isn't hatched" in reply_text(interaction)
    assert interaction.edit_original_response.await_args.kwargs["view"] is None
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    life = await current_life(bot)
    assert (life.full, life.growth, life.egg_food) == (0.0, 0, 0)
    assert (
        await bot.activity_log.meal_points_today(
            GUILD_ID, USER_ID, discord.utils.utcnow()
        )
        == 0
    )
    server.house.send.assert_not_awaited()


async def test_cannot_feed_before_any_life_exists(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)

    interaction = await choose(bot, select, "cloudwave")

    assert "isn't hatched" in reply_text(interaction)
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
    await lay(bot, full=40.0)
    for user in (USER_ID, OTHER_USER_ID):
        await bot.activity_log.add_snack(GUILD_ID, user, "cloudwave")
    selects = [(await open_feeding(bot, user))[1] for user in (USER_ID, OTHER_USER_ID)]

    await asyncio.gather(
        choose(bot, selects[0], "cloudwave", USER_ID),
        choose(bot, selects[1], "cloudwave", OTHER_USER_ID),
    )

    life = await current_life(bot)
    assert (life.full, life.growth) == (50.0, 2)


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
        ("glitterwave", Moment.SNACK_FANCY),
        ("viibrwave", Moment.SNACK_FANCY),
    ],
)
async def test_snack_line_matches_the_snack(
    bot: app.WispBot, key: str, moment: Moment
) -> None:
    await lay(bot, full=50.0)
    pick = say(bot)

    await eat(bot, key)

    pick.assert_called_once_with(moment, Mood.HAPPY, name="Member1")


@pytest.mark.parametrize("stance", [None, *PickleStance])
@pytest.mark.parametrize("key", ["cheese", "pickles", "sinewave", "viibrwave"])
async def test_his_favorite_snack_gets_its_own_line(
    bot: app.WispBot, server: FakeServer, key: str, stance: PickleStance | None
) -> None:
    life = await lay(bot, full=50.0)
    life.favorite_snack = key
    await bot.lives.save(GUILD_ID, life)
    await bot.players.set_pickle_stance(GUILD_ID, USER_ID, stance)
    pick = say(bot, "my favorite")

    await eat(bot, key)

    pick.assert_called_once_with(Moment.SNACK_FAVORITE, Mood.HAPPY, name="Member1")
    assert house_text(server) == "my favorite"


async def test_a_snack_that_is_not_his_favorite_gets_the_usual_line(
    bot: app.WispBot,
) -> None:
    life = await lay(bot, full=5.0)
    life.favorite_snack = "cheese"
    await bot.lives.save(GUILD_ID, life)
    pick = say(bot)

    await eat(bot, "cloudwave")

    pick.assert_called_once_with(Moment.SNACK, Mood.HANGRY, name="Member1")


async def test_his_favorite_snack_line_follows_his_mood(bot: app.WispBot) -> None:
    life = await lay(bot, full=5.0)
    life.favorite_snack = "cloudwave"
    await bot.lives.save(GUILD_ID, life)
    pick = say(bot)

    await eat(bot, "cloudwave")

    pick.assert_called_once_with(Moment.SNACK_FAVORITE, Mood.HANGRY, name="Member1")


def test_fancy_starts_at_the_fancy_cost() -> None:
    fancy = {snack.key for snack in SNACKS if snack.cost >= rules.FANCY_SNACK_COST}

    assert fancy == {"glitterwave", "viibrwave"}


async def test_house_post_has_the_snack_emoji_and_line(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(snacks, "_eating_gif", lambda gif_name: None)
    give_emojis(bot, "snack_cloudwave")
    await lay(bot)
    say(bot, "yum")

    await eat(bot, "cloudwave")

    server.house.send.assert_awaited_once()
    assert house_text(server) == f"{emoji_text('snack_cloudwave')} yum"
    kwargs = server.house.send.await_args.kwargs
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    assert "file" not in kwargs


async def test_house_post_without_the_emoji_is_just_the_line(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    say(bot, "yum")

    await eat(bot, "cloudwave")

    assert house_text(server) == "yum"


async def test_his_mood_after_the_snack_picks_the_line(bot: app.WispBot) -> None:
    await lay(bot, full=5.0)
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
    assert house_text(server) == "a pickle take"
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
    await lay(bot, phase=Phase.EGG, full=0.0)

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
    assert reply_text(interaction).startswith("♪ Wisp ate your Cloud Wave")
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
        interaction.guild, "the Feed Wisp button", error, where=interaction.channel
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
        "Error in the Feed Wisp button: OperationalError: (2013, 'Lost connection')",
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
        interaction.guild, "the Feed Wisp button", expired, where=interaction.channel
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
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 7
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
    menu = snacks.Menu("the snack menu", snacks.SnackSelect([], "Pick", AsyncMock()))

    await menu.on_error(interaction, error, menu.children[0])

    bot.report_error.assert_awaited_once_with(
        interaction.guild, "the snack menu", error, where=interaction.channel
    )
    interaction.response.send_message.assert_awaited_once_with(
        USER_ERROR, ephemeral=True
    )


# ---
# Extension
# ---


def test_snack_pack_and_vault_hang_off_the_wisp_group() -> None:
    assert groups.wisp.get_command("snackpack") is snacks.wisp_snackpack
    assert groups.wisp.get_command("vault") is snacks.wisp_vault
    assert isinstance(snacks.wisp_snackpack, app_commands.Command)
    assert isinstance(snacks.wisp_vault, app_commands.Command)


def test_the_commands_say_what_they_do() -> None:
    assert snacks.wisp_snackpack.description == "See your snacks and keepsakes."
    assert snacks.wisp_vault.description == (
        "Buy snacks and gifts for Wisp in the ViiBR Vault."
    )


def test_snacks_is_a_loaded_extension() -> None:
    assert "cogs.snacks" in app.EXTENSIONS
