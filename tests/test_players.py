"""Tests for activation, the Billboard and Wisp learning members' names.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs import groups, players
from cogs.players import (
    NameButton,
    NameModal,
    maybe_meet,
    refresh_billboard,
    render_billboard,
)
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.links import Track, TrackKind
from wisp.rules import Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
ERRORS_ID = 40
BOARD_ID = 61
BOARD_MESSAGE_ID = 778
FIRST_USER = 1
SECOND_USER = 2
LONG_ID = 10**17
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
SEPARATOR = "・♪ ────────・──────── ♪・"

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, an errors channel and the Billboard thread."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.board_edit: Any = AsyncMock()
        self.board = MagicMock(spec=discord.Thread)
        self.board.id = BOARD_ID
        self.board.parent_id = FORUM_ID
        self.board.archived = False
        self.board.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, edit=self.board_edit
        )
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house, ERRORS_ID: self.errors}
        self.guild.get_channel_or_thread.side_effect = channels.get

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if channel_id != BOARD_ID:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.board


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
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


async def configure(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        error_channel_id=ERRORS_ID,
        billboard_thread_id=BOARD_ID,
        billboard_message_id=BOARD_MESSAGE_ID,
    )


def make_interaction(
    bot: app.WispBot, user_id: int = FIRST_USER, display_name: str = "Member1"
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
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.send_modal = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def run(command: Any, *args: Any) -> None:
    await command.callback(*args)


def followups(interaction: MagicMock) -> list[str]:
    """Texts sent as ephemeral follow-ups that cannot ping anyone."""
    sent = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == (
            discord.AllowedMentions.none().to_dict()
        )
        sent.append(call.args[0])
    return sent


def make_life(
    version: int,
    phase: Phase,
    *,
    hatched_ago: timedelta | None = None,
    lived: timedelta | None = None,
    peak: Stage = Stage.BABY,
    hatched_by: int | None = None,
) -> Life:
    life = new_egg(version, NOW - timedelta(days=90))
    life.phase = phase
    life.peak_stage = peak
    life.stage = peak if phase is Phase.ALIVE else Stage.EGG
    life.hatched_by = hatched_by
    life.care = 50.0
    if hatched_ago is not None:
        life.hatched_at = NOW - hatched_ago
        if lived is not None:
            life.ended_at = life.hatched_at + lived
    return life


async def lay(bot: app.WispBot, phase: Phase = Phase.ALIVE, version: int = 1) -> Life:
    life = make_life(version, phase, hatched_ago=timedelta(hours=1))
    life.hatched_at = discord.utils.utcnow() - timedelta(hours=1)
    return await bot.lives.insert(GUILD_ID, life)


async def play_on_days(
    bot: app.WispBot, life: Life, user_id: int, days_ago: list[int]
) -> None:
    assert life.id is not None
    now = discord.utils.utcnow()
    for days in days_ago:
        await bot.activity_log.record_interaction(
            GUILD_ID,
            life.id,
            user_id,
            InteractionKind.PLAY,
            0,
            0,
            now - timedelta(days=days),
        )


async def feed_points(
    bot: app.WispBot, life: Life, user_id: int, points: int, key: str
) -> None:
    assert life.id is not None
    track = Track(TrackKind.SUNO, key, f"https://suno.com/song/{key}")
    await bot.activity_log.record_feed(
        GUILD_ID, life.id, user_id, track, points, 1, NOW
    )
    await bot.players.add_points(GUILD_ID, user_id, points)


# ---
# Activation and the board command
# ---


async def test_board_activates_once(bot: app.WispBot, server: FakeServer) -> None:
    await configure(bot)
    await lay(bot)

    first = make_interaction(bot)
    await run(players.wisp_board, first)
    activated = (await bot.players.get(GUILD_ID, FIRST_USER)).activated_at
    assert activated is not None
    first.response.defer.assert_awaited_once_with(ephemeral=True)
    radar, board = followups(first)
    assert "radar" in radar
    assert board.startswith("♪ The Billboard")

    second = make_interaction(bot)
    await run(players.wisp_board, second)
    (board_only,) = followups(second)
    assert board_only.startswith("♪ The Billboard")
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).activated_at == activated


async def test_board_works_before_any_life_exists(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)

    await run(players.wisp_board, interaction)

    assert "Nobody" in followups(interaction)[-1]


# ---
# Status command
# ---


async def test_status_shows_the_card_privately(bot: app.WispBot) -> None:
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [0])
    interaction = make_interaction(bot)

    await run(players.wisp_status, interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    (text,) = followups(interaction)
    assert text.startswith("♪ WISP v1 ・ BABY")
    assert "fed today by 1 person" in text


async def test_status_without_a_life_says_so(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)

    await run(players.wisp_status, interaction)

    (text,) = followups(interaction)
    assert "no life" in text


async def test_status_while_between_lives_says_so(bot: app.WispBot) -> None:
    await lay(bot, Phase.DEAD)
    interaction = make_interaction(bot)

    await run(players.wisp_status, interaction)

    (text,) = followups(interaction)
    assert "no life" in text


# ---
# Billboard
# ---


async def test_billboard_lists_versions_including_never_hatched(
    bot: app.WispBot,
) -> None:
    await bot.lives.insert(
        GUILD_ID,
        make_life(
            1,
            Phase.DEAD,
            hatched_ago=timedelta(days=40),
            lived=timedelta(days=18, hours=3),
            peak=Stage.TEEN,
            hatched_by=SECOND_USER,
        ),
    )
    await bot.lives.insert(GUILD_ID, make_life(2, Phase.COLD))
    await bot.lives.insert(
        GUILD_ID,
        make_life(3, Phase.ALIVE, hatched_ago=timedelta(days=12, hours=1)),
    )

    text = await render_billboard(bot, GUILD_ID, NOW)

    versions = text.split("\n")[-3:]
    assert versions == [
        "v3 ・ going strong ・ 12 days",
        "v2 ・ never hatched",
        f"v1 ・ lived 18 days ・ reached Teen ・ hatched by <@{SECOND_USER}>",
    ]


async def test_billboard_describes_eggs_and_a_lone_day(bot: app.WispBot) -> None:
    await bot.lives.insert(
        GUILD_ID,
        make_life(
            1,
            Phase.DEAD,
            hatched_ago=timedelta(days=5),
            lived=timedelta(days=1),
            peak=Stage.BABY,
        ),
    )
    await bot.lives.insert(GUILD_ID, make_life(2, Phase.EGG))
    await bot.lives.insert(GUILD_ID, make_life(3, Phase.HATCHING))

    text = await render_billboard(bot, GUILD_ID, NOW)

    assert text.split("\n")[-3:] == [
        "v3 ・ hatching now",
        "v2 ・ still an egg",
        "v1 ・ lived 1 day ・ reached Baby",
    ]


async def test_billboard_ranks_this_life_and_all_time(bot: app.WispBot) -> None:
    life = await bot.lives.insert(
        GUILD_ID, make_life(2, Phase.ALIVE, hatched_ago=timedelta(days=1))
    )
    await feed_points(bot, life, FIRST_USER, 1, "aaaa")
    await feed_points(bot, life, SECOND_USER, 5, "bbbb")
    await bot.players.add_points(GUILD_ID, FIRST_USER, 200)
    await bot.players.add_bond(GUILD_ID, FIRST_USER, 150)

    text = await render_billboard(bot, GUILD_ID, NOW)

    this_life, all_time, _versions = text.split(SEPARATOR + "\n")[1:]
    assert this_life.splitlines() == [
        "This life",
        f"・1. <@{SECOND_USER}> ・ 5 points",
        f"・2. <@{FIRST_USER}> ・ 1 point",
    ]
    assert all_time.splitlines() == [
        "All time",
        f"・1. <@{FIRST_USER}> ・ 201 points ・ Friend",
        f"・2. <@{SECOND_USER}> ・ 5 points ・ New face",
    ]


async def test_billboard_is_empty_but_tidy_for_a_new_server(bot: app.WispBot) -> None:
    text = await render_billboard(bot, GUILD_ID, NOW)

    assert text == "\n".join(
        [
            "♪ The Billboard",
            SEPARATOR,
            "This life",
            "・Nobody has fed him yet",
            SEPARATOR,
            "All time",
            "・Nobody has points yet",
            SEPARATOR,
            "Versions",
            "・None yet",
        ]
    )


async def test_billboard_uses_bot_style(bot: app.WispBot) -> None:
    life = await lay(bot)
    await feed_points(bot, life, FIRST_USER, 3, "cccc")

    text = await render_billboard(bot, GUILD_ID, NOW)

    assert "・" in text
    assert "♪" in text
    assert SEPARATOR in text
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)


async def test_billboard_fits_one_message(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = await bot.lives.insert(
        GUILD_ID, make_life(61, Phase.ALIVE, hatched_ago=timedelta(days=3))
    )
    for offset in range(10):
        member = LONG_ID + offset
        await feed_points(bot, life, member, 100 + offset, f"track{offset}")
        await bot.players.add_bond(GUILD_ID, member, 400)
    history = [life] + [
        make_life(
            version,
            Phase.DEAD,
            hatched_ago=timedelta(days=90),
            lived=timedelta(days=18),
            peak=Stage.ROCKSTAR,
            hatched_by=LONG_ID,
        )
        for version in range(60, 0, -1)
    ]
    monkeypatch.setattr(bot.lives, "history", AsyncMock(return_value=history))

    text = await render_billboard(bot, GUILD_ID, NOW)

    assert len(text) <= 2000
    lines = text.splitlines()
    assert sum(line.startswith("・") and ". <@" in line for line in lines) == 20
    version_lines = [line for line in lines if re.match(r"v\d+ ・", line)]
    assert 0 < len(version_lines) < len(history)
    assert version_lines[0].startswith("v61 ・ going strong")
    assert version_lines[1].startswith("v60 ・")
    expected = [f"v{n} ・" for n in range(61, 61 - len(version_lines), -1)]
    assert [line[: len(prefix)] for line, prefix in zip(version_lines, expected)] == (
        expected
    )
    assert all(line.endswith(f"hatched by <@{LONG_ID}>") for line in version_lines[1:])


async def test_refresh_billboard_edits_the_pinned_message(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)

    await refresh_billboard(bot, GUILD_ID)

    server.board.get_partial_message.assert_called_once_with(BOARD_MESSAGE_ID)
    kwargs = server.board_edit.await_args.kwargs
    assert kwargs["content"].startswith("♪ The Billboard")
    assert "v1 ・ going strong" in kwargs["content"]
    assert kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.errors.send.assert_not_awaited()


# ---
# Meeting Wisp
# ---


async def test_meet_fires_on_third_distinct_day(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [2, 1])

    await maybe_meet(bot, GUILD_ID, FIRST_USER, display_name="Member1")
    server.house.send.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).met_at is None

    await play_on_days(bot, life, FIRST_USER, [0])
    await maybe_meet(bot, GUILD_ID, FIRST_USER, display_name="Member1")

    server.house.send.assert_awaited_once()
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).met_at is not None
    kwargs = server.house.send.await_args.kwargs
    assert kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    (button,) = kwargs["view"].children
    assert isinstance(button, NameButton)
    assert button.item.custom_id == f"wisp:name:{FIRST_USER}"
    assert button.item.label == "Tell Wisp your name"


async def test_meeting_happens_once(bot: app.WispBot, server: FakeServer) -> None:
    await configure(bot)
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [2, 1, 0])

    await maybe_meet(bot, GUILD_ID, FIRST_USER)
    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    server.house.send.assert_awaited_once()
    assert (await current_life(bot)).growth == rules.GROWTH_PER_BOND_MOMENT


async def test_simultaneous_interactions_meet_once(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [2, 1, 0])

    await asyncio.gather(
        maybe_meet(bot, GUILD_ID, FIRST_USER), maybe_meet(bot, GUILD_ID, FIRST_USER)
    )

    server.house.send.assert_awaited_once()
    assert (await current_life(bot)).growth == rules.GROWTH_PER_BOND_MOMENT


async def test_meeting_gives_no_growth_to_an_egg(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    egg = await bot.lives.insert(GUILD_ID, make_life(1, Phase.EGG))
    await play_on_days(bot, egg, FIRST_USER, [2, 1, 0])

    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    server.house.send.assert_awaited_once()
    assert (await current_life(bot)).growth == 0


async def test_no_life_means_no_meeting(bot: app.WispBot, server: FakeServer) -> None:
    await configure(bot)

    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    server.house.send.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).met_at is None


async def test_unnamed_player_shows_display_name(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [2, 1, 0])
    bot.lines = MagicMock()
    bot.lines.pick.return_value = "a meeting line"

    await maybe_meet(bot, GUILD_ID, FIRST_USER, display_name="Server Nick")

    bot.lines.pick.assert_called_once_with(Moment.MEET, Mood.HAPPY, name="Server Nick")
    assert server.house.send.await_args.args == ("a meeting line",)


async def test_named_player_is_called_by_name(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [2, 1, 0])
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Zed")
    bot.lines = MagicMock()
    bot.lines.pick.return_value = "a meeting line"

    await maybe_meet(bot, GUILD_ID, FIRST_USER, display_name="Server Nick")

    bot.lines.pick.assert_called_once_with(Moment.MEET, Mood.HAPPY, name="Zed")


async def test_unnamed_player_without_a_display_name_is_mentioned(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    life = await lay(bot)
    await play_on_days(bot, life, FIRST_USER, [2, 1, 0])
    bot.lines = MagicMock()
    bot.lines.pick.return_value = "a meeting line"

    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    bot.lines.pick.assert_called_once_with(
        Moment.MEET, Mood.HAPPY, name=f"<@{FIRST_USER}>"
    )


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


# ---
# Naming
# ---


def fill(modal: NameModal, text: str) -> None:
    payload: Any = {"value": text}
    modal.name._refresh_state(MagicMock(), payload)


async def test_name_is_saved_trimmed(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, "  Zed  ")

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name == "Zed"
    interaction.response.send_message.assert_awaited_once()
    text = interaction.response.send_message.await_args.args[0]
    assert "Zed" in text
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_name_of_exactly_the_limit_is_accepted(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)
    modal = NameModal()
    name = "x" * rules.NAME_MAX
    fill(modal, name)

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name == name


async def test_name_over_24_rejected(bot: app.WispBot) -> None:
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Old")
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, "x" * (rules.NAME_MAX + 1))

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name == "Old"
    text = interaction.response.send_message.await_args.args[0]
    assert str(rules.NAME_MAX) in text
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.parametrize("text", ["", "   "])
async def test_empty_name_is_rejected(bot: app.WispBot, text: str) -> None:
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Old")
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, text)

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name == "Old"
    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


def test_modal_input_matches_the_name_limit() -> None:
    assert NameModal.name.max_length == rules.NAME_MAX


async def test_modal_failure_is_reported_to_staff(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("boom")

    await NameModal().on_error(interaction, error)

    bot.report_error.assert_awaited_once_with(
        interaction.guild, "the naming form", error
    )
    interaction.response.send_message.assert_awaited_once()


# ---
# The name button
# ---


async def test_button_id_carries_the_user_and_survives_a_restart(
    bot: app.WispBot,
) -> None:
    sent = NameButton(FIRST_USER)
    match = NameButton.__discord_ui_compiled_template__.fullmatch(
        sent.item.custom_id or ""
    )
    assert match is not None

    restored = await NameButton.from_custom_id(
        make_interaction(bot), MagicMock(spec=discord.ui.Button), match
    )

    assert restored.user_id == FIRST_USER
    assert restored.item.custom_id == sent.item.custom_id


async def test_only_the_named_member_may_press_it(bot: app.WispBot) -> None:
    button = NameButton(FIRST_USER)

    stranger = make_interaction(bot, user_id=SECOND_USER)
    assert not await button.interaction_check(stranger)
    stranger.response.send_message.assert_awaited_once()
    assert stranger.response.send_message.await_args.kwargs["ephemeral"] is True

    owner = make_interaction(bot, user_id=FIRST_USER)
    assert await button.interaction_check(owner)
    owner.response.send_message.assert_not_awaited()


async def test_pressing_it_opens_the_name_form(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)

    await NameButton(FIRST_USER).callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
    (modal,) = interaction.response.send_modal.await_args.args
    assert isinstance(modal, NameModal)


# ---
# Extension
# ---


async def test_setup_registers_the_button_for_restarts(bot: app.WispBot) -> None:
    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]

    await players.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(NameButton)


def test_member_commands_hang_off_the_wisp_group() -> None:
    assert groups.wisp.get_command("status") is players.wisp_status
    assert groups.wisp.get_command("board") is players.wisp_board
    assert isinstance(players.wisp_board, app_commands.Command)


def test_players_is_a_loaded_extension() -> None:
    assert "cogs.players" in app.EXTENSIONS
