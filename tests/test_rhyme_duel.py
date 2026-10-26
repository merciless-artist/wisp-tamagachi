"""Tests for the Rhyme Duel: /wisp play rhyme.

Discord objects and the turn-by-turn messages are fakes; the repositories are
the real ones.
"""

import asyncio
import random
from collections.abc import Callable, Iterator
from datetime import timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs import groups, rhyme_duel
from cogs.vault import render_leaderboard
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import (
    BOND_PER_PLAY,
    GROWTH_PER_PLAY,
    PLAY_POINTS,
    PLAYS_PER_DAY,
    RHYME_TURN,
    Stage,
)
from wisp.text import SEPARATOR

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
            word: str, used: set[str], stage: Stage, rng: random.Random
        ) -> str | None:
            asked.append((word, set(used), stage))
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
    return interaction


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
    life.full = 50.0
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

    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    assert replies(interaction) == [f"♪ Your Rhyme Duel is on in <#{THREAD_ID}>."]
    server.house.create_thread.assert_awaited_once_with(
        name="Rhyme Duel ・ Member1",
        type=discord.ChannelType.public_thread,
        auto_archive_duration=60,
    )
    start, wisp_turn, summary = server.posts()
    assert start in lines_for(Moment.RHYME_START, word="fire")
    assert wisp_turn == "♪ higher"
    ending, separator, chain, points = summary.splitlines()
    assert ending in lines_for(Moment.RHYME_WISP_STUCK)
    assert separator == SEPARATOR
    assert chain == "・fire ・ choir ・ higher ・ mine"
    assert points == "・Score: 3 points"
    assert asked == [
        ("choir", {"fire", "choir"}, Stage.BABY),
        ("mine", {"fire", "choir", "higher", "mine"}, Stage.BABY),
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

    start, summary = server.posts()
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

    _start, summary = server.posts()
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

    lines = server.posts()[-1].splitlines()
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

    lines = server.posts()[-1].splitlines()
    assert lines[0] in lines_for(Moment.RHYME_WISP_STUCK)
    assert lines[2:] == ["・fire ・ choir", "・Score: 2 points"]


async def test_wisp_answers_in_his_mood(bot: app.WispBot, server: FakeServer) -> None:
    life = await lay(bot)
    life.full = 5.0
    await bot.lives.save(GUILD_ID, life)

    await duel(bot, server)

    start, summary = server.posts()
    assert start in lines_for(Moment.RHYME_START, Mood.HANGRY, word="fire")
    assert summary.splitlines()[0] in lines_for(Moment.RHYME_PLAYER_STUCK, Mood.HANGRY)


async def test_a_huge_answer_ends_the_duel_cleanly(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    await duel(bot, server, said("a" * 2000))

    summary = server.posts()[-1]
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

    assert len(summary) == 2000


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


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
async def test_no_duel_unless_wisp_is_alive(
    bot: app.WispBot, server: FakeServer, phase: Phase
) -> None:
    await lay(bot, phase)

    interaction = await duel(bot, server)

    assert replies(interaction) == [
        "♪ Wisp isn't hatched yet. Rhymes have to wait until he is."
    ]
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

    with pytest.raises(LookupError):
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
    assert f"Rhyme Duel\n・1. <@{USER_ID}> ・ 2 points" in board

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
    server.house.send.assert_not_awaited()


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
