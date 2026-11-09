"""Tests for the Rhyme Duel: /wisp play rhyme and the Status post's Play button.

Discord objects and the turn-by-turn messages are fakes; the repositories are
the real ones.
"""

import asyncio
import random
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands
from discord.ui.view import ViewStore

import app
from cogs import groups, rhyme_duel
from cogs.rhyme_duel import NoHouseError, PlayButton, RhymeDuelButton
from cogs.vault import render_leaderboard
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import (
    BOND_PER_PLAY,
    GROWTH_PER_PLAY,
    PLAY_POINTS,
    PLAYS_PER_DAY,
    RHYME_TURN,
    WELLBEING_PER_PLAY,
    Stage,
)
from wisp.text import MESSAGE_LIMIT, SEPARATOR, USER_ERROR, count, text_length

GUILD_ID = 100
HOUSE_ID = 20
THREAD_ID = 70
OTHER_CHANNEL_ID = 71
USER_ID = 1
OTHER_USER_ID = 2
QUALIFYING_ROLE = 7
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, which opens one duel thread."""

    def __init__(self) -> None:
        self.thread = MagicMock(spec=discord.Thread)
        self.thread.id = THREAD_ID
        self.thread.mention = f"<#{THREAD_ID}>"
        self.thread.send = AsyncMock()
        self.thread.edit = AsyncMock()
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.create_thread = AsyncMock(return_value=self.thread)
        self.house.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild.get_channel_or_thread.side_effect = channels.get

    def posts(self) -> list[str]:
        """Everything posted in the duel thread, none of it able to ping."""
        sent = []
        for call in self.thread.send.await_args_list:
            assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
            sent.append(cast(str, call.args[0]))
        return sent


class Turns:
    """Stands in for bot.wait_for, handing out scripted messages in order.

    A message the check turns down is skipped, as Discord would. None, or the
    end of the script, is the player going quiet until the turn times out.
    """

    def __init__(self) -> None:
        self._script: list[MagicMock | None] = []

    def load(self, *script: MagicMock | None) -> None:
        """Replace the script with the messages of the next duel."""
        self._script = list(script)

    async def __call__(
        self, event: str, *, check: Callable[[Any], bool], timeout: float
    ) -> MagicMock:
        assert event == "message"
        assert timeout == RHYME_TURN.total_seconds()
        while self._script:
            message = self._script.pop(0)
            if message is None:
                break
            if check(message):
                return message
        raise asyncio.TimeoutError


class Gate:
    """A wait_for that holds every turn until it is opened, then times out."""

    def __init__(self) -> None:
        self.opened = asyncio.Event()
        self.waiting = 0

    async def __call__(
        self, event: str, *, check: Callable[[Any], bool], timeout: float
    ) -> MagicMock:
        self.waiting += 1
        await self.opened.wait()
        raise asyncio.TimeoutError


def said(text: str, user_id: int = USER_ID, channel_id: int = THREAD_ID) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.content = text
    message.author = MagicMock(spec=discord.Member)
    message.author.id = user_id
    message.channel = MagicMock(spec=discord.Thread)
    message.channel.id = channel_id
    return message


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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "wait_for", Turns())
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    for user_id in (USER_ID, OTHER_USER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())


@pytest.fixture(autouse=True)
def meeting(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    meet = AsyncMock()
    monkeypatch.setattr(rhyme_duel, "maybe_meet", meet)
    return meet


@pytest.fixture(autouse=True)
def vault(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    refresh = AsyncMock()
    monkeypatch.setattr(rhyme_duel, "refresh_vault", refresh)
    return refresh


@pytest.fixture(autouse=True)
def opener(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rhyme_duel, "opening_word", lambda _rng: "fire")


@pytest.fixture
def wisp_says(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[Any]]:
    """Script Wisp's answers; returns the list of what he was asked."""

    def script(*replies: str | None) -> list[Any]:
        asked: list[Any] = []
        queue = list(replies)

        def reply(
            word: str, used: set[str], stage: Stage, turn: int, rng: random.Random
        ) -> str | None:
            asked.append((word, set(used), stage, turn))
            return queue.pop(0)

        monkeypatch.setattr(rhyme_duel, "wisp_reply", reply)
        return asked

    return script


def make_interaction(
    bot: app.WispBot,
    server: FakeServer,
    user_id: int = USER_ID,
    display_name: str = "Member1",
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.duel_server = server
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = display_name
    interaction.user.roles = [
        MagicMock(spec=discord.Role, id=role_id) for role_id in roles
    ]
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.is_expired = MagicMock(return_value=False)
    interaction.edit_original_response = AsyncMock()
    return interaction


def receipt(interaction: MagicMock) -> str:
    """The receipt, the last thing the duel posts in its thread."""
    interaction.edit_original_response.assert_not_awaited()
    return interaction.duel_server.posts()[-1]


def replies(interaction: MagicMock) -> list[str]:
    """The private replies the member got, none of them able to ping."""
    sent = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        sent.append(cast(str, call.args[0]))
    return sent


async def lay(bot: app.WispBot, phase: Phase = Phase.ALIVE) -> Life:
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=1))
    life.phase = phase
    life.health = 50.0
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


async def start(interaction: MagicMock) -> None:
    command: Any = rhyme_duel.play_rhyme
    await command.callback(interaction)


async def duel(
    bot: app.WispBot, server: FakeServer, *script: MagicMock | None
) -> MagicMock:
    """Run one duel for the first member, who sends the scripted messages."""
    cast(Turns, bot.wait_for).load(*script)
    interaction = make_interaction(bot, server)
    await start(interaction)
    return interaction


def lines_for(moment: Moment, mood: Mood = Mood.HAPPY, **fields: str) -> set[str]:
    return {line.format(**fields) for line in LINES[(moment, mood)]}


# ---
# Playing
# ---


async def test_duel_scores_perfect_and_slant(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    asked = wisp_says("higher", None)

    interaction = await duel(bot, server, said("Choir!"), said("mine"))

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert replies(interaction) == [f"♪ Your Rhyme Duel is on in <#{THREAD_ID}>."]
    server.house.create_thread.assert_awaited_once_with(
        name="Rhyme Duel ・ Member1",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )
    start, wisp_turn, summary, _receipt = server.posts()
    assert start in lines_for(Moment.RHYME_START, word="fire")
    assert wisp_turn == "♪ higher"
    ending, separator, chain, points = summary.splitlines()
    assert ending in lines_for(Moment.RHYME_WISP_STUCK)
    assert separator == SEPARATOR
    assert chain == "・fire ・ choir ・ higher ・ mine"
    assert points == "・Score: 3 points"
    assert asked == [
        ("choir", {"fire", "choir"}, Stage.BABY, 1),
        ("mine", {"fire", "choir", "higher", "mine"}, Stage.BABY, 2),
    ]
    server.thread.edit.assert_awaited_once_with(archived=True, locked=True)


async def test_a_named_player_gets_their_name_on_the_thread(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.players.set_name(GUILD_ID, USER_ID, "Zed")

    await duel(bot, server)

    assert server.house.create_thread.await_args.kwargs["name"] == "Rhyme Duel ・ Zed"


async def test_timeout_ends_duel(bot: app.WispBot, server: FakeServer) -> None:
    await lay(bot)

    await duel(bot, server)

    start, summary, _receipt = server.posts()
    assert start in lines_for(Moment.RHYME_START, word="fire")
    ending, *rest = summary.splitlines()
    assert ending in lines_for(Moment.RHYME_PLAYER_STUCK)
    assert rest == [SEPARATOR, "・Time ran out", "・fire", "・Score: 0 points"]
    server.thread.edit.assert_awaited_once_with(archived=True, locked=True)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ("water", "・water doesn't rhyme with fire"),
        ("blorptang", "・blorptang doesn't rhyme with fire"),
        ("FIRE", "・fire was already used"),
        ("big fire", "・That wasn't one word"),
    ],
)
async def test_a_wrong_answer_ends_duel(
    bot: app.WispBot,
    server: FakeServer,
    wisp_says: Callable[..., list[Any]],
    answer: str,
    reason: str,
) -> None:
    await lay(bot)
    asked = wisp_says()

    await duel(bot, server, said(answer), said("choir"))

    _start, summary, _receipt = server.posts()
    lines = summary.splitlines()
    assert lines[0] in lines_for(Moment.RHYME_PLAYER_STUCK)
    assert lines[2:] == [reason, "・fire", "・Score: 0 points"]
    assert asked == []


async def test_a_repeat_later_in_the_chain_ends_duel(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    wisp_says("higher")

    await duel(bot, server, said("choir"), said("choir"))

    lines = server.posts()[-2].splitlines()
    assert lines[2:] == [
        "・choir was already used",
        "・fire ・ choir ・ higher",
        "・Score: 2 points",
    ]


async def test_only_the_player_counts(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    wisp_says(None)

    await duel(
        bot,
        server,
        said("hire", user_id=OTHER_USER_ID),
        said("wire", channel_id=OTHER_CHANNEL_ID),
        said("choir"),
    )

    lines = server.posts()[-2].splitlines()
    assert lines[0] in lines_for(Moment.RHYME_WISP_STUCK)
    assert lines[2:] == ["・fire ・ choir", "・Score: 2 points"]


async def test_wisp_answers_in_his_mood(bot: app.WispBot, server: FakeServer) -> None:
    life = await lay(bot)
    life.health = 5.0
    await bot.lives.save(GUILD_ID, life)

    await duel(bot, server)

    start, summary, _receipt = server.posts()
    assert start in lines_for(Moment.RHYME_START, Mood.HANGRY, word="fire")
    assert summary.splitlines()[0] in lines_for(Moment.RHYME_PLAYER_STUCK, Mood.HANGRY)


async def test_a_huge_answer_ends_the_duel_cleanly(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    await duel(bot, server, said("a" * 2000))

    summary = server.posts()[-2]
    assert len(summary) <= 2000
    assert summary.splitlines()[2:] == [
        "・That wasn't one word",
        "・fire",
        "・Score: 0 points",
    ]
    server.thread.edit.assert_awaited_once_with(archived=True, locked=True)


@pytest.mark.parametrize(
    ("line", "reason"),
    [("good game", "x" * 2500), ("w" * 2500, "x" * 2500), ("w" * 2500, None)],
)
def test_an_over_long_summary_is_still_returned_in_one_message(
    line: str, reason: str | None
) -> None:
    summary = rhyme_duel.summary_text(line, reason, ["fire", "choir"], 2)

    assert text_length(summary) == MESSAGE_LIMIT


def test_an_over_long_reason_is_cut_but_the_score_stays() -> None:
    summary = rhyme_duel.summary_text("good game", "x" * 2500, ["fire"], 2)

    lines = summary.splitlines()
    assert lines[2].startswith("・xxx") and lines[2].endswith("...")
    assert lines[3:] == ["・... ", "・Score: 2 points"]


def test_a_long_chain_still_fits_one_message() -> None:
    chain = ["fire", *(f"word{index}" for index in range(400))]

    summary = rhyme_duel.summary_text("good game", "Time ran out", chain, 9)

    assert len(summary) <= 2000
    lines = summary.splitlines()
    assert lines[:3] == ["good game", SEPARATOR, "・Time ran out"]
    assert lines[3].startswith("・... word")
    assert lines[3].endswith(" ・ word398 ・ word399")
    assert lines[4] == "・Score: 9 points"


def test_a_chain_of_wide_characters_fits_by_utf16_units() -> None:
    chain = [SEPARATOR * 2 for _ in range(60)]

    summary = rhyme_duel.summary_text("good game", "Time ran out", chain, 9)

    assert text_length(summary) <= MESSAGE_LIMIT
    assert len(summary) < MESSAGE_LIMIT // 2 + 100
    lines = summary.splitlines()
    assert lines[3].startswith("・... ")
    assert lines[3].endswith(SEPARATOR * 2)
    assert lines[4] == "・Score: 9 points"


def test_the_last_resort_cut_keeps_wide_characters_whole() -> None:
    line = SEPARATOR * 100

    summary = rhyme_duel.summary_text(line, None, [], 0)

    assert text_length(summary) == MESSAGE_LIMIT
    whole, half = divmod(MESSAGE_LIMIT, text_length(SEPARATOR))
    assert summary == line[: whole * len(SEPARATOR) + half // 2]


# ---
# Who may duel
# ---


async def test_one_duel_per_player(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    gate = Gate()
    monkeypatch.setattr(bot, "wait_for", gate)
    first = asyncio.create_task(start(make_interaction(bot, server)))
    other = asyncio.create_task(start(make_interaction(bot, server, OTHER_USER_ID)))
    while gate.waiting < 2:
        await asyncio.sleep(0.01)

    again = make_interaction(bot, server)
    await start(again)

    assert replies(again) == [
        "♪ You already have a Rhyme Duel going. Finish that one first."
    ]
    assert server.house.create_thread.await_count == 2
    gate.opened.set()
    await asyncio.gather(first, other)

    await start(make_interaction(bot, server))

    assert server.house.create_thread.await_count == 3


async def test_banned_player_cannot_duel(bot: app.WispBot, server: FakeServer) -> None:
    await lay(bot)
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await duel(bot, server)

    assert replies(interaction) == ["♪ Wisp is not dueling with you right now."]
    server.house.create_thread.assert_not_awaited()
    assert await bot.players.top_rhyme(GUILD_ID, 5) == []


@pytest.mark.parametrize(
    ("phase", "reason"),
    [
        (Phase.EGG, "♪ Wisp isn't hatched yet. Rhymes have to wait until he is."),
        (Phase.HATCHING, "♪ Wisp isn't hatched yet. Rhymes have to wait until he is."),
        (Phase.DEAD, "♪ Wisp isn't alive right now, so rhymes have to wait."),
    ],
)
async def test_no_duel_unless_wisp_is_alive(
    bot: app.WispBot, server: FakeServer, phase: Phase, reason: str
) -> None:
    await lay(bot, phase)

    interaction = await duel(bot, server)

    assert replies(interaction) == [reason]
    server.house.create_thread.assert_not_awaited()


async def test_no_duel_before_any_life(bot: app.WispBot, server: FakeServer) -> None:
    interaction = await duel(bot, server)

    assert len(replies(interaction)) == 1
    server.house.create_thread.assert_not_awaited()


async def test_missing_house_fails_and_frees_the_player(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.settings.update(GUILD_ID, house_channel_id=None)

    with pytest.raises(NoHouseError):
        await duel(bot, server)

    assert (GUILD_ID, USER_ID) not in bot.rhyme_duels


# ---
# Rewards
# ---


async def test_duel_counts_as_play(
    bot: app.WispBot,
    server: FakeServer,
    db: Database,
    meeting: AsyncMock,
    wisp_says: Callable[..., list[Any]],
) -> None:
    life = await lay(bot)
    wisp_says(None)

    await duel(bot, server, said("choir"))

    now = discord.utils.utcnow()
    assert await bot.activity_log.casual_bond_today(GUILD_ID, USER_ID, now) == (
        BOND_PER_PLAY
    )
    rows = await db.fetchall(
        f"SELECT kind, meal_points, life_id FROM {db.t('interactions')}"
    )
    assert rows == [
        {"kind": InteractionKind.PLAY.value, "meal_points": 0, "life_id": life.id}
    ]
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == BOND_PER_PLAY
    current = await bot.lives.current(GUILD_ID)
    assert current is not None
    assert current.growth == life.growth + GROWTH_PER_PLAY
    meeting.assert_awaited_once_with(bot, GUILD_ID, USER_ID, display_name="Member1")


@pytest.mark.parametrize(
    ("roles", "activated"), [((), True), ((QUALIFYING_ROLE,), False)]
)
async def test_a_duel_by_someone_who_cannot_feed_keeps_only_the_score(
    bot: app.WispBot,
    server: FakeServer,
    db: Database,
    wisp_says: Callable[..., list[Any]],
    roles: tuple[int, ...],
    activated: bool,
) -> None:
    life = await lay(bot)
    wisp_says(None)
    newcomer = OTHER_USER_ID + 1
    if activated:
        await bot.players.activate(GUILD_ID, newcomer, discord.utils.utcnow())
    cast(Turns, bot.wait_for).load(said("choir", user_id=newcomer))

    await start(make_interaction(bot, server, newcomer, roles=roles))

    assert await db.fetchall(f"SELECT id FROM {db.t('interactions')}") == []
    player = await bot.players.get(GUILD_ID, newcomer)
    assert (player.bond, player.best_rhyme_score) == (0, 2)
    assert (player.balance, player.lifetime_points) == (0, 0)
    current = await bot.lives.current(GUILD_ID)
    assert current is not None
    assert current.growth == life.growth


async def test_a_counted_duel_adds_ten_wellbeing_and_restarts_its_stretch(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    life.wellbeing_stretch = 7200.0
    await bot.lives.save(GUILD_ID, life)
    wisp_says(None)

    await duel(bot, server, said("choir"))

    current = await bot.lives.current(GUILD_ID)
    assert current is not None
    assert current.wellbeing == life.wellbeing + WELLBEING_PER_PLAY == 60.0
    assert current.wellbeing_stretch == 0.0
    assert current.health == life.health


async def test_a_counted_duel_pays_one_point(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    wisp_says(None, None)

    await duel(bot, server, said("choir"))
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.lifetime_points) == (PLAY_POINTS, PLAY_POINTS)

    await duel(bot, server, said("higher"))
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.lifetime_points) == (2 * PLAY_POINTS,) * 2


async def test_no_point_past_the_daily_play_limit(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    assert life.id is not None
    for _ in range(PLAYS_PER_DAY):
        await bot.activity_log.record_interaction(
            GUILD_ID,
            life.id,
            USER_ID,
            InteractionKind.PLAY,
            0,
            0,
            discord.utils.utcnow(),
        )
    wisp_says(None)

    await duel(bot, server, said("choir"))

    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 0


async def test_a_duel_without_a_rhyme_pays_no_point(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    await duel(bot, server, said("water"))

    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 0


async def test_play_bond_respects_the_daily_cap(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    wisp_says(None)
    life = await lay(bot)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID,
        life.id,
        USER_ID,
        InteractionKind.SNACK,
        6,
        0,
        discord.utils.utcnow(),
    )

    await duel(bot, server, said("choir"))

    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 1


async def test_a_duel_without_a_rhyme_is_not_play(
    bot: app.WispBot, server: FakeServer, meeting: AsyncMock
) -> None:
    life = await lay(bot)

    await duel(bot, server, said("water"))

    assert await bot.activity_log.distinct_days(GUILD_ID, USER_ID) == 0
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 0
    current = await bot.lives.current(GUILD_ID)
    assert current is not None
    assert current.growth == life.growth
    assert current.wellbeing == life.wellbeing
    meeting.assert_awaited_once()


async def test_only_the_first_scoring_duels_of_the_day_are_play(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    wisp_says(*[None] * (PLAYS_PER_DAY + 1))
    answers = ["choir", "higher", "hire", "wire", "desire", "entire"]

    for answer in answers[:PLAYS_PER_DAY]:
        await duel(bot, server, said(answer))
    after_limit = await bot.lives.current(GUILD_ID)
    await duel(bot, server, said("entire"))

    assert await bot.activity_log.plays_today(
        GUILD_ID, USER_ID, discord.utils.utcnow()
    ) == (PLAYS_PER_DAY)
    current = await bot.lives.current(GUILD_ID)
    assert after_limit is not None and current is not None
    assert after_limit.growth == life.growth + PLAYS_PER_DAY * GROWTH_PER_PLAY
    assert current.growth == after_limit.growth
    assert (await bot.players.get(GUILD_ID, USER_ID)).best_rhyme_score == 2


async def test_best_score_still_counts_past_the_play_limit(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    assert life.id is not None
    for _ in range(PLAYS_PER_DAY):
        await bot.activity_log.record_interaction(
            GUILD_ID,
            life.id,
            USER_ID,
            InteractionKind.PLAY,
            0,
            0,
            discord.utils.utcnow(),
        )
    wisp_says("higher", None)

    await duel(bot, server, said("choir"), said("wire"))

    assert (await bot.players.get(GUILD_ID, USER_ID)).best_rhyme_score == 4
    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 0


async def test_no_play_credit_when_wisp_died_during_the_duel(
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    wisp_says: Callable[..., list[Any]],
) -> None:
    life = await lay(bot)
    wisp_says(None)
    turns = cast(Turns, bot.wait_for)
    turns.load(said("choir"))

    async def die_then_answer(
        event: str, *, check: Callable[[Any], bool], timeout: float
    ) -> MagicMock:
        life.phase = Phase.DEAD
        await bot.lives.save(GUILD_ID, life)
        return await turns(event, check=check, timeout=timeout)

    monkeypatch.setattr(bot, "wait_for", die_then_answer)
    await start(make_interaction(bot, server))

    assert await bot.activity_log.distinct_days(GUILD_ID, USER_ID) == 0
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.bond, player.best_rhyme_score) == (0, 2)
    current = await bot.lives.current(GUILD_ID)
    assert current is not None
    assert current.growth == life.growth


async def test_new_best_goes_on_the_vault(
    bot: app.WispBot,
    server: FakeServer,
    vault: AsyncMock,
    wisp_says: Callable[..., list[Any]],
) -> None:
    await lay(bot)
    wisp_says(None)

    await duel(bot, server, said("choir"))

    vault.assert_awaited_once_with(bot, GUILD_ID)
    board = await render_leaderboard(bot, GUILD_ID, discord.utils.utcnow())
    assert f"║𝄡𝄚𝄂𝄆 **Rhyme Duel**\n║𝄡 1. <@{USER_ID}> ・ 2 points" in board

    await duel(bot, server)

    vault.assert_awaited_once()
    assert (await bot.players.get(GUILD_ID, USER_ID)).best_rhyme_score == 2


async def test_a_thread_that_cannot_close_still_finishes_the_duel(
    bot: app.WispBot,
    server: FakeServer,
    vault: AsyncMock,
    meeting: AsyncMock,
    wisp_says: Callable[..., list[Any]],
) -> None:
    await lay(bot)
    wisp_says(None)
    server.thread.edit.side_effect = discord.Forbidden(
        MagicMock(status=403, reason="Forbidden"), "Missing Permissions"
    )

    await duel(bot, server, said("choir"))

    vault.assert_awaited_once_with(bot, GUILD_ID)
    meeting.assert_awaited_once()
    report = server.posts()[-1]
    assert report.startswith("Error in closing a Rhyme Duel thread: Forbidden")
    assert len(server.house.send.await_args_list) == 1


# ---
# Receipts and reasons
# ---


async def test_a_counted_duel_says_what_it_did_and_what_is_left(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    wisp_says(None)

    interaction = await duel(bot, server, said("choir"))

    now = life.wellbeing + WELLBEING_PER_PLAY
    assert receipt(interaction) == (
        f"♪ Your duel counted. Wellbeing +{WELLBEING_PER_PLAY} (now {now:.0f}). "
        f"+{PLAY_POINTS} WC. "
        f"{count(PLAYS_PER_DAY - 1, 'counted game')} left today."
    )


async def test_a_duel_without_a_rhyme_says_so(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    interaction = await duel(bot, server, said("water"))

    assert receipt(interaction) == (
        "♪ This duel didn't count toward his Wellbeing: you didn't score a rhyme."
    )


async def test_a_duel_past_the_daily_limit_says_so(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    assert life.id is not None
    for _ in range(PLAYS_PER_DAY):
        await bot.activity_log.record_interaction(
            GUILD_ID,
            life.id,
            USER_ID,
            InteractionKind.PLAY,
            0,
            0,
            discord.utils.utcnow(),
        )
    wisp_says(None)

    interaction = await duel(bot, server, said("choir"))

    assert receipt(interaction) == (
        "♪ This duel didn't count toward his Wellbeing: you've already played "
        f"{count(PLAYS_PER_DAY, 'counted game')} today (resets at 00:00 UTC)."
    )


@pytest.mark.parametrize(
    ("roles", "activated", "reason"),
    [
        ((), True, f"you don't have a role that can feed Wisp: <@&{QUALIFYING_ROLE}>."),
        ((QUALIFYING_ROLE,), False, "you haven't opened /wisp board yet."),
    ],
)
async def test_a_duel_by_someone_who_cannot_feed_says_why(
    bot: app.WispBot,
    server: FakeServer,
    wisp_says: Callable[..., list[Any]],
    roles: tuple[int, ...],
    activated: bool,
    reason: str,
) -> None:
    await lay(bot)
    wisp_says(None)
    newcomer = OTHER_USER_ID + 1
    if activated:
        await bot.players.activate(GUILD_ID, newcomer, discord.utils.utcnow())
    cast(Turns, bot.wait_for).load(said("choir", user_id=newcomer))
    interaction = make_interaction(bot, server, newcomer, roles=roles)

    await start(interaction)

    assert receipt(interaction) == (
        f"♪ This duel didn't count toward his Wellbeing: {reason}"
    )


async def test_a_duel_when_wisp_died_says_he_isnt_alive(
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    wisp_says: Callable[..., list[Any]],
) -> None:
    life = await lay(bot)
    wisp_says(None)
    turns = cast(Turns, bot.wait_for)
    turns.load(said("choir"))

    async def die_then_answer(
        event: str, *, check: Callable[[Any], bool], timeout: float
    ) -> MagicMock:
        life.phase = Phase.DEAD
        await bot.lives.save(GUILD_ID, life)
        return await turns(event, check=check, timeout=timeout)

    monkeypatch.setattr(bot, "wait_for", die_then_answer)
    interaction = make_interaction(bot, server)
    await start(interaction)

    assert receipt(interaction) == (
        "♪ This duel didn't count toward his Wellbeing: Wisp isn't alive right now."
    )


async def test_a_member_banned_during_the_duel_gets_it_uncounted(
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    wisp_says: Callable[..., list[Any]],
) -> None:
    await lay(bot)
    wisp_says(None)
    turns = cast(Turns, bot.wait_for)
    turns.load(said("choir"))

    async def ban_then_answer(
        event: str, *, check: Callable[[Any], bool], timeout: float
    ) -> MagicMock:
        await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)
        return await turns(event, check=check, timeout=timeout)

    monkeypatch.setattr(bot, "wait_for", ban_then_answer)
    interaction = make_interaction(bot, server)
    await start(interaction)

    assert receipt(interaction) == (
        "♪ This duel didn't count toward his Wellbeing: "
        "you are banned from feeding Wisp right now."
    )
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 0


async def test_a_duel_while_frozen_says_he_is_frozen(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    life = await lay(bot)
    await bot.settings.update(GUILD_ID, frozen=True)
    wisp_says(None)

    interaction = await duel(bot, server, said("choir"))

    assert receipt(interaction) == (
        "♪ This duel didn't count toward his Wellbeing: "
        "Wisp is frozen right now, so nothing can change until staff unfreeze him."
    )
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 0
    current = await bot.lives.current(GUILD_ID)
    assert current is not None and current.wellbeing == life.wellbeing


async def test_a_receipt_that_cannot_be_sent_is_reported_in_the_thread(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    wisp_says(None)
    cast(Turns, bot.wait_for).load(said("choir"))
    interaction = make_interaction(bot, server)
    gone = discord.NotFound(MagicMock(status=404, reason="Not Found"), "Unknown")

    async def refuse_receipts(text: str, **_kwargs: Any) -> None:
        if text.startswith(("♪ Your duel", "♪ This duel")):
            raise gone

    server.thread.send.side_effect = refuse_receipts

    await start(interaction)

    assert server.posts()[-1].startswith(
        "Error in sending a Rhyme Duel receipt: NotFound"
    )


# ---
# The Play button
# ---


async def press_rhyme_duel(interaction: MagicMock) -> None:
    await RhymeDuelButton().callback(interaction)


async def test_play_opens_a_private_menu_of_the_games(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = make_interaction(bot, server)

    await PlayButton().callback(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    call = interaction.followup.send.await_args
    assert call.args == ("♪ Pick a game to play with Wisp.",)
    assert call.kwargs["ephemeral"] is True
    assert call.kwargs["wait"] is True
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    (game,) = call.kwargs["view"].children
    assert isinstance(game, RhymeDuelButton)
    assert (game.item.label, game.item.custom_id) == ("Rhyme Duel", "wisp:play:rhyme")
    server.house.create_thread.assert_not_awaited()


async def test_a_games_menu_timing_out_keeps_the_rhyme_duel_button_working(
    bot: app.WispBot, server: FakeServer
) -> None:
    """discord.py files a waited follow-up's view under its message id.

    A view filed under the shared key beside an ordinary item would, on
    timing out, unregister the Rhyme Duel button for every open menu.
    """
    interaction = make_interaction(bot, server)
    await PlayButton().callback(interaction)
    menu = interaction.followup.send.await_args.kwargs["view"]
    store = ViewStore(MagicMock())
    other = discord.ui.View(timeout=None)
    other.add_item(discord.ui.Button(label="Other", custom_id="other"))
    store.add_view(other)
    store.add_view(menu, 1234)

    store.remove_view(menu)

    template = RhymeDuelButton.__discord_ui_compiled_template__
    assert store._dynamic_items[template] is RhymeDuelButton


async def test_the_rhyme_duel_button_plays_a_duel_like_the_command(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    wisp_says("higher", None)
    cast(Turns, bot.wait_for).load(said("Choir!"), said("mine"))
    interaction = make_interaction(bot, server)

    await press_rhyme_duel(interaction)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert replies(interaction) == [f"♪ Your Rhyme Duel is on in <#{THREAD_ID}>."]
    assert receipt(interaction).startswith("♪ Your duel counted.")
    _, wisp_turn, summary, _receipt = server.posts()
    assert wisp_turn == "♪ higher"
    assert summary.splitlines()[-1] == "・Score: 3 points"
    server.thread.edit.assert_awaited_once_with(archived=True, locked=True)
    assert (GUILD_ID, USER_ID) not in bot.rhyme_duels


@pytest.mark.parametrize(
    ("phase", "banned", "reason"),
    [
        (Phase.ALIVE, True, "♪ Wisp is not dueling with you right now."),
        (
            Phase.EGG,
            False,
            "♪ Wisp isn't hatched yet. Rhymes have to wait until he is.",
        ),
        (Phase.DEAD, False, "♪ Wisp isn't alive right now, so rhymes have to wait."),
    ],
)
async def test_the_rhyme_duel_button_gives_the_commands_reasons(
    bot: app.WispBot, server: FakeServer, phase: Phase, banned: bool, reason: str
) -> None:
    await lay(bot, phase)
    if banned:
        await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)
    interaction = make_interaction(bot, server)

    await press_rhyme_duel(interaction)

    assert replies(interaction) == [reason]
    server.house.create_thread.assert_not_awaited()


@pytest.mark.parametrize("opener", ["command", "button"])
async def test_a_duel_while_he_naps_is_refused_until_he_wakes(
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    opener: str,
) -> None:
    life = await lay(bot)
    life.nap_left = 1800.0
    await bot.lives.save(GUILD_ID, life)
    monkeypatch.setattr(
        discord.utils, "utcnow", lambda: datetime(2026, 11, 6, 10, 15, 30, tzinfo=UTC)
    )
    interaction = make_interaction(bot, server)

    await (start if opener == "command" else press_rhyme_duel)(interaction)

    assert replies(interaction) == [
        "♪ Wisp is napping until 2:46am Pacific. Poke him awake first."
    ]
    server.house.create_thread.assert_not_awaited()
    assert (GUILD_ID, USER_ID) not in bot.rhyme_duels


async def test_the_button_and_the_command_share_one_duel_per_player(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    gate = Gate()
    monkeypatch.setattr(bot, "wait_for", gate)
    first = asyncio.create_task(start(make_interaction(bot, server)))
    while gate.waiting < 1:
        await asyncio.sleep(0.01)

    again = make_interaction(bot, server)
    await press_rhyme_duel(again)

    assert replies(again) == [
        "♪ You already have a Rhyme Duel going. Finish that one first."
    ]
    gate.opened.set()
    await first
    assert server.house.create_thread.await_count == 1


async def test_a_rhyme_duel_button_with_no_house_is_reported_where_pressed(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    interaction = make_interaction(bot, server)
    interaction.channel = MagicMock(spec=discord.Thread)

    await press_rhyme_duel(interaction)

    guild, context, error = reported.await_args.args
    assert (guild, context) == (server.guild, "the Rhyme Duel button")
    assert isinstance(error, NoHouseError)
    assert reported.await_args.kwargs == {"where": interaction.channel}
    interaction.followup.send.assert_awaited_with(USER_ERROR, ephemeral=True)
    assert (GUILD_ID, USER_ID) not in bot.rhyme_duels


async def test_the_rhyme_duel_button_catches_only_a_missing_house(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)
    monkeypatch.setattr(rhyme_duel, "_duel", AsyncMock(side_effect=KeyError("bug")))

    with pytest.raises(KeyError):
        await press_rhyme_duel(make_interaction(bot, server))

    reported.assert_not_awaited()
    assert (GUILD_ID, USER_ID) not in bot.rhyme_duels


async def test_a_play_button_that_cannot_answer_is_reported(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    interaction = make_interaction(bot, server)
    interaction.channel = MagicMock(spec=discord.Thread)
    expired = discord.NotFound(MagicMock(status=404), "Unknown interaction")
    interaction.response.defer.side_effect = expired
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await PlayButton().callback(interaction)

    reported.assert_awaited_once_with(
        server.guild, "the Play button", expired, where=interaction.channel
    )


@pytest.mark.parametrize(
    ("button", "custom_id"),
    [(PlayButton, "wisp:play"), (RhymeDuelButton, "wisp:play:rhyme")],
)
async def test_the_play_buttons_survive_a_restart(
    bot: app.WispBot, server: FakeServer, button: Any, custom_id: str
) -> None:
    match = button.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert match is not None

    restored = await button.from_custom_id(
        make_interaction(bot, server), MagicMock(spec=discord.ui.Button), match
    )

    assert isinstance(restored, button)


def test_the_play_and_rhyme_duel_ids_never_match_each_other() -> None:
    assert (
        PlayButton.__discord_ui_compiled_template__.fullmatch("wisp:play:rhyme") is None
    )
    assert (
        RhymeDuelButton.__discord_ui_compiled_template__.fullmatch("wisp:play") is None
    )


async def test_the_play_buttons_are_registered_at_startup(bot: app.WispBot) -> None:
    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]

    await rhyme_duel.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(PlayButton, RhymeDuelButton)


# ---
# Wiring
# ---


def test_rhyme_hangs_off_the_play_group() -> None:
    assert groups.play.parent is groups.wisp
    assert groups.wisp.get_command("play") is groups.play
    assert groups.play.get_command("rhyme") is rhyme_duel.play_rhyme
    assert isinstance(rhyme_duel.play_rhyme, app_commands.Command)


def test_rhyme_duel_is_a_loaded_extension() -> None:
    assert "cogs.rhyme_duel" in app.EXTENSIONS


async def test_the_house_is_told_who_started_a_duel(
    bot: app.WispBot, server: FakeServer, wisp_says: Callable[..., list[Any]]
) -> None:
    await lay(bot)
    wisp_says(None)

    await duel(bot, server, said("choir"))

    call = server.house.send.await_args
    assert call.args[0] == f"♪ <@{USER_ID}> started a Rhyme Duel in <#{THREAD_ID}>"
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
