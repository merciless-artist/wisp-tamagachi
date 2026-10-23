"""Tests for the lunchbox: buying snacks and feeding them to Wisp.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
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
from cogs import groups, lunchbox
from cogs.lunchbox import FeedButton, feed_view
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import Player, PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.rules import SNACKS, Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
ERRORS_ID = 40
USER_ID = 1
OTHER_USER_ID = 2
SEPARATOR = "・♪ ────────・──────── ♪・"
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and an errors channel."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house, ERRORS_ID: self.errors}
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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        error_channel_id=ERRORS_ID,
    )


@pytest.fixture(autouse=True)
def no_meeting(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    meeting = AsyncMock()
    monkeypatch.setattr(lunchbox, "maybe_meet", meeting)
    return meeting


def make_interaction(
    bot: app.WispBot, user_id: int = USER_ID, display_name: str = "Member1"
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = display_name
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


async def lay(bot: app.WispBot, phase: Phase = Phase.ALIVE, care: float = 50.0) -> Life:
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=1))
    life.phase = phase
    life.care = care
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


async def open_lunchbox(
    bot: app.WispBot, user_id: int = USER_ID
) -> tuple[MagicMock, discord.ui.Select[Any]]:
    interaction = make_interaction(bot, user_id)
    await run(lunchbox.wisp_lunchbox, interaction)
    select = interaction.followup.send.await_args.kwargs["view"].children[0]
    return interaction, select


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
    _, select = await open_lunchbox(bot, user_id)
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
# Opening the lunchbox
# ---


async def test_lunchbox_shows_balance_menu_and_inventory(bot: app.WispBot) -> None:
    give_emojis(bot, "wisp_coin", "snack_cloudwave", "snack_sinewave")
    await bot.players.add_points(GUILD_ID, USER_ID, 12)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave", 2)

    interaction, select = await open_lunchbox(bot)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    text = interaction.followup.send.await_args.args[0]
    lines = text.splitlines()
    assert lines[:2] == ["♪ The Lunchbox", f"{emoji_text('wisp_coin')} 12 points"]
    menu, owned = text.split(SEPARATOR + "\n")[1:]
    assert menu.splitlines()[0] == "Snack Box"
    assert (
        f"・{emoji_text('snack_cloudwave', 2)} Cloud Wave ・ 3 points ・ care +5"
        in text
    )
    assert "・Glitter Wave ・ 8 points ・ care +12" in menu
    assert "Sine Wave" not in menu
    assert owned.splitlines() == [
        "Your snacks",
        f"・{emoji_text('snack_cloudwave', 2)} Cloud Wave x2",
    ]
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)
    paid = [snack.key for snack in SNACKS if snack.cost > 0]
    assert option_values(select) == paid


async def test_lunchbox_without_emojis_or_snacks_stays_tidy(bot: app.WispBot) -> None:
    interaction, _ = await open_lunchbox(bot)

    text = interaction.followup.send.await_args.args[0]
    assert text.splitlines()[:2] == ["♪ The Lunchbox", "0 points"]
    assert text.endswith("Your snacks\n・Nothing yet")
    assert len(text) < 2000


async def test_banned_member_cannot_open_the_lunchbox(bot: app.WispBot) -> None:
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)
    interaction = make_interaction(bot)

    await run(lunchbox.wisp_lunchbox, interaction)

    assert "not taking snacks" in reply_text(interaction)
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    assert "view" not in interaction.followup.send.await_args.kwargs


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
    assert "・Cloud Wave x1" in text


async def test_buying_twice_stacks_the_snack(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    _, select = await open_lunchbox(bot)

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
    _, select = await open_lunchbox(bot)
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await choose(bot, select, "cloudwave")

    assert "not taking snacks" in reply_text(interaction)
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 10
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}


# ---
# The Feed Wisp button
# ---


async def test_feed_view_is_a_persistent_feed_button() -> None:
    view = feed_view()

    (button,) = view.children
    assert isinstance(button, FeedButton)
    assert button.item.label == "Feed Wisp"
    assert button.item.custom_id == "wisp:feed"
    assert view.timeout is None


async def test_feed_button_survives_restart(bot: app.WispBot) -> None:
    match = FeedButton.__discord_ui_compiled_template__.fullmatch("wisp:feed")
    assert match is not None
    restored = await FeedButton.from_custom_id(
        make_interaction(bot), MagicMock(spec=discord.ui.Button), match
    )
    assert isinstance(restored, FeedButton)

    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]
    await lunchbox.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(FeedButton)


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


# ---
# Feeding
# ---


async def test_feed_takes_one_and_adds_care_growth_bond(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, care=50.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "spicywave", 2)

    interaction = await eat(bot, "spicywave")

    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"spicywave": 1}
    life = await current_life(bot)
    assert life.care == 50.0 + 8
    assert life.growth == 2
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == rules.BOND_PER_SNACK
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, USER_ID, now) == 8
    assert await bot.activity_log.casual_bond_today(GUILD_ID, USER_ID, now) == 1
    assert not await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    interaction.response.defer.assert_awaited_once_with()
    assert reply_text(interaction) == "♪ Wisp ate your Spicy Wave ・ care +8"
    assert interaction.edit_original_response.await_args.kwargs["view"] is None
    server.house.send.assert_awaited_once()


async def test_free_sine_once_a_day(bot: app.WispBot) -> None:
    await lay(bot, care=50.0)

    first = await eat(bot, "sinewave")

    now = discord.utils.utcnow()
    assert await bot.activity_log.free_snack_used_today(GUILD_ID, USER_ID, now)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    life = await current_life(bot)
    assert (life.care, life.growth) == (52.0, 1)
    assert reply_text(first) == "♪ Wisp ate your Sine Wave ・ care +2"

    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)
    assert option_values(select) == ["cloudwave"]
    select._values = ["sinewave"]
    again = make_interaction(bot)
    await select.callback(again)

    assert "free Sine Wave" in reply_text(again)
    assert (await current_life(bot)).care == 52.0
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
    assert (life.care, life.growth) == (55.0, 1)


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
    life = await lay(bot, care=40.0)
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
    assert (life.care, life.growth) == (43.0, 1)
    assert (
        reply_text(capped) == "♪ Wisp ate your Cloud Wave ・ care +3 (daily meal limit)"
    )
    now = discord.utils.utcnow()
    assert await bot.activity_log.meal_points_today(GUILD_ID, USER_ID, now) == 15

    await eat(bot, "cloudwave")

    life = await current_life(bot)
    assert (life.care, life.growth) == (43.0, 2)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 2


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
async def test_cannot_feed_egg_with_snacks(
    bot: app.WispBot, server: FakeServer, phase: Phase
) -> None:
    await lay(bot, phase=phase, care=0.0)
    await bot.activity_log.add_snack(GUILD_ID, USER_ID, "cloudwave")
    _, select = await open_feeding(bot)

    interaction = await choose(bot, select, "cloudwave")

    assert "isn't hatched" in reply_text(interaction)
    assert interaction.edit_original_response.await_args.kwargs["view"] is None
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {"cloudwave": 1}
    life = await current_life(bot)
    assert (life.care, life.growth, life.egg_food) == (0.0, 0, 0)
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
    await lay(bot, care=40.0)
    for user in (USER_ID, OTHER_USER_ID):
        await bot.activity_log.add_snack(GUILD_ID, user, "cloudwave")
    selects = [(await open_feeding(bot, user))[1] for user in (USER_ID, OTHER_USER_ID)]

    await asyncio.gather(
        choose(bot, selects[0], "cloudwave", USER_ID),
        choose(bot, selects[1], "cloudwave", OTHER_USER_ID),
    )

    life = await current_life(bot)
    assert (life.care, life.growth) == (50.0, 2)


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
    await lay(bot, care=50.0)
    pick = say(bot)

    await eat(bot, key)

    pick.assert_called_once_with(moment, Mood.HAPPY, name="Member1")


def test_fancy_starts_at_the_fancy_cost() -> None:
    fancy = {snack.key for snack in SNACKS if snack.cost >= rules.FANCY_SNACK_COST}

    assert fancy == {"glitterwave", "viibrwave"}


async def test_house_post_has_the_snack_emoji_and_line(
    bot: app.WispBot, server: FakeServer
) -> None:
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
    await lay(bot, care=5.0)
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
    monkeypatch.setattr(lunchbox, "ASSETS_DIR", tmp_path)
    await lay(bot)

    await eat(bot, "cloudwave")
    await eat(bot, "cheese")

    first, second = server.house.send.await_args_list
    attached = first.kwargs["file"]
    assert isinstance(attached, discord.File)
    assert attached.filename == "eat_cloudwave.gif"
    assert "file" not in second.kwargs


async def test_pickles_attach_the_hedge_gif_while_stance_unknown(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "eating").mkdir()
    (tmp_path / "eating" / "eat_pickles.gif").write_bytes(b"GIF89a")
    monkeypatch.setattr(lunchbox, "ASSETS_DIR", tmp_path)
    await lay(bot)
    pick = say(bot, "no comment on the pickle")

    await eat(bot, "pickles")

    pick.assert_called_once_with(Moment.PICKLE_HEDGE, Mood.HAPPY, name="Member1")
    assert house_text(server) == "no comment on the pickle"
    attached = server.house.send.await_args.kwargs["file"]
    assert isinstance(attached, discord.File)
    assert attached.filename == "eat_pickles.gif"


async def test_feeding_lets_wisp_meet_the_member(
    bot: app.WispBot, no_meeting: AsyncMock
) -> None:
    await lay(bot)

    await eat(bot, "cloudwave")

    no_meeting.assert_awaited_once_with(bot, GUILD_ID, USER_ID, display_name="Member1")


async def test_a_refused_feed_does_not_meet_anyone(
    bot: app.WispBot, no_meeting: AsyncMock
) -> None:
    await lay(bot, phase=Phase.EGG, care=0.0)

    await eat(bot, "cloudwave")

    no_meeting.assert_not_awaited()


async def test_a_missing_house_is_reported_and_the_snack_still_counts(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    await lay(bot)

    interaction = await eat(bot, "cloudwave")

    assert (await current_life(bot)).growth == 1
    assert reply_text(interaction).startswith("♪ Wisp ate your Cloud Wave")
    server.errors.send.assert_awaited_once()


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
async def test_a_failing_feed_button_reports_to_staff_and_the_member(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    interaction = make_interaction(bot)
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    monkeypatch.setattr(bot.activity_log, "inventory", AsyncMock(side_effect=error))

    await FeedButton().callback(interaction)

    reported.assert_awaited_once_with(interaction.guild, "the Feed Wisp button", error)
    interaction.followup.send.assert_awaited_once_with(
        "Something went wrong. Staff have been told.", ephemeral=True
    )


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
        interaction.guild, "the Feed Wisp button", expired
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
    _, select = await open_lunchbox(bot)
    interaction = make_interaction(bot)

    async def get(guild_id: int, user_id: int) -> Player:
        interaction.response.defer.assert_awaited_once()
        return Player(user_id=user_id)

    monkeypatch.setattr(bot.players, "get", get)
    select._values = ["cloudwave"]

    await select.callback(interaction)

    interaction.followup.send.assert_awaited_once()


async def test_a_failed_confirmation_tells_staff_the_purchase_went_through(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, 10)
    _, select = await open_lunchbox(bot)
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
    )
    interaction.followup.send.assert_not_awaited()


async def test_a_failing_menu_is_reported_to_staff_and_the_member(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(bot)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("boom")
    menu = lunchbox.SnackMenu([], "Pick", AsyncMock())

    await menu.on_error(interaction, error, menu.children[0])

    bot.report_error.assert_awaited_once_with(interaction.guild, "the lunchbox", error)
    interaction.response.send_message.assert_awaited_once_with(
        "Something went wrong. Staff have been told.", ephemeral=True
    )


# ---
# Extension
# ---


def test_lunchbox_hangs_off_the_wisp_group() -> None:
    assert groups.wisp.get_command("lunchbox") is lunchbox.wisp_lunchbox
    assert isinstance(lunchbox.wisp_lunchbox, app_commands.Command)


def test_lunchbox_is_a_loaded_extension() -> None:
    assert "cogs.lunchbox" in app.EXTENSIONS
