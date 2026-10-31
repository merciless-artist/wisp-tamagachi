"""Tests for the status card text, chat credit and Wisp learning members' names.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from cogs import players
from cogs.players import NameButton, NameModal, maybe_meet
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.bond import happiness
from wisp.card import bar
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.links import Track, TrackKind
from wisp.rules import Stage
from wisp.text import USER_ERROR

GUILD_ID = 100
HOUSE_ID = 20
FIRST_USER = 1
SECOND_USER = 2
QUALIFYING_ROLE = 555
WISP_ID = 5000
WISP = MagicMock(spec=discord.ClientUser, id=WISP_ID)
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
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
    monkeypatch.setattr(app.WispBot, "user", WISP)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


async def configure(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
    )


def make_interaction(
    bot: app.WispBot, user_id: int = FIRST_USER, display_name: str = "Member1"
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.TextChannel)
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


def make_member(
    user_id: int = FIRST_USER, roles: tuple[int, ...] = (QUALIFYING_ROLE,)
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.roles = [MagicMock(spec=discord.Role, id=role_id) for role_id in roles]
    return member


async def enroll(bot: app.WispBot, user_id: int = FIRST_USER) -> None:
    """Let a member feed Wisp: the qualifying role is set and they opened the board."""
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    await bot.players.activate(GUILD_ID, user_id, NOW)


async def run(command: Any, *args: Any) -> None:
    await command.callback(*args)


def make_life(
    version: int,
    phase: Phase,
    *,
    hatched_ago: timedelta | None = None,
) -> Life:
    life = new_egg(version, NOW - timedelta(days=90))
    life.phase = phase
    life.peak_stage = Stage.BABY
    life.stage = Stage.BABY if phase is Phase.ALIVE else Stage.EGG
    life.full = 50.0
    if hatched_ago is not None:
        life.hatched_at = NOW - hatched_ago
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


# ---
# Status card text
# ---


async def test_status_text_shows_the_card(bot: app.WispBot) -> None:
    life = await lay(bot)

    text = await players.status_text(
        bot, GUILD_ID, life, discord.utils.utcnow(), happiness(0)
    )

    assert "**life stage**・𝐁𝐀𝐁𝐘・" in text
    assert f"tag <@{WISP_ID}> in his House to say hi!!" in text


async def test_status_text_counts_todays_feeders_and_tracks(bot: app.WispBot) -> None:
    await configure(bot)
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    log = bot.activity_log
    for user_id, kind, at in [
        (FIRST_USER, InteractionKind.FEED, now),
        (FIRST_USER, InteractionKind.SNACK, now),
        (SECOND_USER, InteractionKind.FREE_SNACK, midnight),
        (3, InteractionKind.PLAY, now),
        (4, InteractionKind.CHAT, now),
        (5, InteractionKind.FEED, midnight - timedelta(seconds=1)),
    ]:
        await log.record_interaction(GUILD_ID, life.id, user_id, kind, 0, 0, at)
    for index, (track_kind, fed_at) in enumerate(
        [
            (TrackKind.VIIBR, now),
            (TrackKind.SUNO, now),
            (TrackKind.SUNO, midnight),
            (TrackKind.VIIBR, midnight - timedelta(seconds=1)),
        ]
    ):
        track = Track(
            track_kind, f"{track_kind}:{index}", f"https://example.test/{index}"
        )
        await log.record_feed(GUILD_ID, life.id, FIRST_USER, track, 1, index, fed_at)

    text = await players.status_text(bot, GUILD_ID, life, now, happiness(0))

    assert "> 𝄡𝄚𝄂 Fed by 02 people today・♬‿♩. ♪" in text.splitlines()
    assert "> 𝄡𝄚𝄂 1 ViiBR track and 2 Suno tracks ・♪‿♫ ♪" in text.splitlines()
    assert f"tag <@{WISP_ID}> in <#{HOUSE_ID}> to say hi!!" in text


# ---
# Chat credit and happiness
# ---


async def test_chat_credit_is_once_a_day(bot: app.WispBot) -> None:
    life = await lay(bot)
    await enroll(bot)
    member = make_member()

    assert await players.credit_chat(bot, GUILD_ID, member, life, NOW) is True
    player = await bot.players.get(GUILD_ID, FIRST_USER)
    assert (player.balance, player.lifetime_points) == (rules.CHAT_POINTS,) * 2

    later = NOW + timedelta(hours=5)
    assert await players.credit_chat(bot, GUILD_ID, member, life, later) is False
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).balance == rules.CHAT_POINTS

    tomorrow = NOW.replace(hour=0, minute=0) + timedelta(days=1)
    assert await players.credit_chat(bot, GUILD_ID, member, life, tomorrow) is True
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).balance == (
        2 * rules.CHAT_POINTS
    )


async def test_chat_credit_records_a_chat_with_no_bond_or_meal(
    bot: app.WispBot, db: Database
) -> None:
    life = await lay(bot)
    await enroll(bot)

    await players.credit_chat(bot, GUILD_ID, make_member(), life, NOW)

    rows = await db.fetchall(
        f"SELECT user_id, life_id, kind, bond, meal_points FROM {db.t('interactions')}"
    )
    assert rows == [
        {
            "user_id": FIRST_USER,
            "life_id": life.id,
            "kind": InteractionKind.CHAT.value,
            "bond": 0,
            "meal_points": 0,
        }
    ]
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).bond == 0


@pytest.mark.parametrize(
    ("roles", "activated", "banned"),
    [
        ((), True, False),
        ((QUALIFYING_ROLE,), False, False),
        ((QUALIFYING_ROLE,), True, True),
    ],
    ids=["no-role", "board-not-opened", "banned"],
)
async def test_only_feeders_get_chat_credit(
    bot: app.WispBot,
    db: Database,
    roles: tuple[int, ...],
    activated: bool,
    banned: bool,
) -> None:
    life = await lay(bot)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    if activated:
        await bot.players.activate(GUILD_ID, FIRST_USER, NOW)
    if banned:
        await bot.players.set_offense(
            GUILD_ID, FIRST_USER, 1, NOW + timedelta(days=1), False
        )

    given = await players.credit_chat(
        bot, GUILD_ID, make_member(roles=roles), life, NOW
    )

    assert given is False
    assert await db.fetchall(f"SELECT id FROM {db.t('interactions')}") == []
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).balance == 0


async def test_chat_credit_needs_a_life_that_is_stored(bot: app.WispBot) -> None:
    await enroll(bot)
    unsaved = make_life(1, Phase.ALIVE, hatched_ago=timedelta(hours=1))

    assert (
        await players.credit_chat(bot, GUILD_ID, make_member(), unsaved, NOW) is False
    )
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).balance == 0


async def test_happy_counts_only_chatters(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    log = bot.activity_log
    for user_id, kind in [
        (FIRST_USER, InteractionKind.FEED),
        (SECOND_USER, InteractionKind.SNACK),
        (3, InteractionKind.CHAT),
    ]:
        await log.record_interaction(GUILD_ID, life.id, user_id, kind, 0, 0, now)

    happy = await players.current_happiness(bot, GUILD_ID, now)
    assert happy == happiness(1)
    text = await players.status_text(bot, GUILD_ID, life, now, happy)
    lines = text.splitlines()
    assert lines[lines.index("> 𝄡 Happy") + 1] == f"> {bar(happiness(1), '', '')}"


async def test_chats_older_than_a_day_do_not_make_him_happy(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        FIRST_USER,
        InteractionKind.CHAT,
        0,
        0,
        now - rules.HAPPINESS_WINDOW - timedelta(minutes=1),
    )

    assert await players.current_happiness(bot, GUILD_ID, now) == happiness(0)


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
    assert server.house.send.await_args.args[0].startswith(f"<@{FIRST_USER}> ")
    kwargs = server.house.send.await_args.kwargs
    assert kwargs["allowed_mentions"].to_dict() == {
        "parse": [],
        "users": [FIRST_USER],
    }
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


async def test_an_already_met_player_is_a_cheap_no_op(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await configure(bot)
    await lay(bot)
    await bot.players.mark_met(GUILD_ID, FIRST_USER, discord.utils.utcnow())
    take_lock = MagicMock(side_effect=AssertionError("took the guild lock"))
    distinct_days = AsyncMock()
    monkeypatch.setattr(bot, "guild_lock", take_lock)
    monkeypatch.setattr(bot.activity_log, "distinct_days", distinct_days)

    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    take_lock.assert_not_called()
    distinct_days.assert_not_awaited()
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING])
async def test_an_egg_meets_nobody_until_he_hatches(
    bot: app.WispBot, server: FakeServer, phase: Phase
) -> None:
    await configure(bot)
    egg = await bot.lives.insert(GUILD_ID, make_life(1, phase))
    await play_on_days(bot, egg, FIRST_USER, [2, 1, 0])

    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    server.house.send.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).met_at is None

    egg.phase = Phase.ALIVE
    egg.stage = Stage.BABY
    await bot.lives.save(GUILD_ID, egg)
    await maybe_meet(bot, GUILD_ID, FIRST_USER)

    server.house.send.assert_awaited_once()
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).met_at is not None
    assert (await current_life(bot)).growth == rules.GROWTH_PER_BOND_MOMENT


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
    assert server.house.send.await_args.args == (f"<@{FIRST_USER}> a meeting line",)


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
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, "x" * (rules.NAME_MAX + 1))

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name is None
    text = interaction.response.send_message.await_args.args[0]
    assert str(rules.NAME_MAX) in text
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.parametrize("text", ["", "   "])
async def test_empty_name_is_rejected(bot: app.WispBot, text: str) -> None:
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, text)

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name is None
    interaction.response.send_message.assert_awaited_once()
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_name_set_while_the_form_was_open_is_not_overwritten(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, "Mine")
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Zed")

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name == "Zed"
    text = interaction.response.send_message.await_args.args[0]
    assert "already knows your name" in text


async def test_ban_issued_while_the_form_was_open_blocks_the_name(
    bot: app.WispBot,
) -> None:
    interaction = make_interaction(bot)
    modal = NameModal()
    fill(modal, "Mine")
    await bot.players.set_offense(GUILD_ID, FIRST_USER, 3, None, True)

    await modal.on_submit(interaction)

    assert (await bot.players.get(GUILD_ID, FIRST_USER)).name is None
    text = interaction.response.send_message.await_args.args[0]
    assert "not taking names" in text


def test_modal_input_matches_the_name_limit() -> None:
    assert NameModal.name.max_length == rules.NAME_MAX


async def test_modal_failure_is_reported_where_it_happened(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)
    bot.report_error = AsyncMock()  # type: ignore[method-assign]
    error = ValueError("boom")

    await NameModal().on_error(interaction, error)

    bot.report_error.assert_awaited_once_with(
        interaction.guild, "the naming form", error, where=interaction.channel
    )
    interaction.response.send_message.assert_awaited_once_with(
        USER_ERROR, ephemeral=True
    )


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


async def test_a_named_member_is_refused_the_button(bot: app.WispBot) -> None:
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Zed")
    interaction = make_interaction(bot)

    assert not await NameButton(FIRST_USER).interaction_check(interaction)

    interaction.response.send_message.assert_awaited_once()
    text = interaction.response.send_message.await_args.args[0]
    assert "already knows your name" in text
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


@pytest.mark.parametrize(
    ("banned_until", "banned_forever"),
    [(None, True), (discord.utils.utcnow() + timedelta(days=1), False)],
)
async def test_a_banned_member_is_refused_the_button(
    bot: app.WispBot, banned_until: datetime | None, banned_forever: bool
) -> None:
    await bot.players.set_offense(GUILD_ID, FIRST_USER, 1, banned_until, banned_forever)
    interaction = make_interaction(bot)

    assert not await NameButton(FIRST_USER).interaction_check(interaction)

    text = interaction.response.send_message.await_args.args[0]
    assert "not taking names" in text
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_an_expired_ban_does_not_block_the_button(bot: app.WispBot) -> None:
    past = discord.utils.utcnow() - timedelta(days=1)
    await bot.players.set_offense(GUILD_ID, FIRST_USER, 1, past, False)

    assert await NameButton(FIRST_USER).interaction_check(make_interaction(bot))


async def test_button_works_again_once_staff_clear_the_name(bot: app.WispBot) -> None:
    await bot.players.set_name(GUILD_ID, FIRST_USER, "Zed")
    button = NameButton(FIRST_USER)
    assert not await button.interaction_check(make_interaction(bot))

    await bot.players.set_name(GUILD_ID, FIRST_USER, None)

    assert await button.interaction_check(make_interaction(bot))


async def test_pressing_it_opens_the_name_form(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)

    await NameButton(FIRST_USER).callback(interaction)

    interaction.response.send_modal.assert_awaited_once()
    (modal,) = interaction.response.send_modal.await_args.args
    assert isinstance(modal, NameModal)


# ---
# Failures in the persistent button
# ---


@pytest.mark.parametrize(
    "error",
    [
        pymysql.err.OperationalError(2013, "Lost connection"),
        discord.Forbidden(MagicMock(status=403), "Missing Access"),
    ],
)
async def test_a_failing_name_check_is_reported_and_turns_the_member_away(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    interaction = make_interaction(bot)
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    monkeypatch.setattr(bot.players, "get", AsyncMock(side_effect=error))

    assert not await NameButton(FIRST_USER).interaction_check(interaction)

    reported.assert_awaited_once_with(
        interaction.guild, "the name button", error, where=interaction.channel
    )
    interaction.response.send_message.assert_awaited_once_with(
        USER_ERROR, ephemeral=True
    )


async def test_a_failing_name_form_opening_is_reported(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    interaction = make_interaction(bot)
    expired = discord.NotFound(MagicMock(status=404), "Unknown interaction")
    interaction.response.send_modal.side_effect = expired
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await NameButton(FIRST_USER).callback(interaction)

    reported.assert_awaited_once_with(
        interaction.guild, "the name button", expired, where=interaction.channel
    )


# ---
# Extension
# ---


async def test_setup_registers_the_button_for_restarts(bot: app.WispBot) -> None:
    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]

    await players.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(NameButton)


def test_players_is_a_loaded_extension() -> None:
    assert "cogs.players" in app.EXTENSIONS
