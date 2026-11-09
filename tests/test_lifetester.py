"""Tests for `!wisp testlife`, the whole-life tester for staff.

Discord objects and the clock are fakes; the repositories are the real ones
and every step runs the real code. Steps do not pause here, and buttons are
pressed through their real handlers.
"""

import asyncio
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import app
from ai.images import ImageMaker
from cogs import life_loop, lifetest_runs, lifetester
from cogs.chores import ChoreButton
from cogs.life_loop import BeginButton, LifeLoop
from cogs.lifetester import LifeTest
from db.activity import ActivityRepo
from db.badges import BadgeRepo
from db.database import Database
from db.drawings import DrawingRepo
from db.gifts import GiftRepo
from db.keepsakes import KeepsakeKind, KeepsakeRepo
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.magazines import MagazineRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from wisp.chores import is_open
from wisp.life import Life, Phase, new_egg
from wisp.rules import Chore, Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
STATUS_ID = 60
VAULT_ID = 61
MEALTIME_ID = 62
CARD_ID = 777
VAULT_MESSAGE_ID = 778
FIRST_POST_ID = 5000
COMMAND_ID = 4000
RUNNER_ID = 1
OTHER_ID = 2
FEEDER_ROLE = 7
WISP = MagicMock(spec=discord.ClientUser, id=3000)
# Midnight, so neither a nap, a tantrum nor the daily "I like you" drawing
# comes due on its own while a run's ticks happen.
NOW = datetime(2026, 10, 22, 0, 0, tzinfo=UTC)
FROZEN = "♪ Wisp is frozen right now, so nothing can change until staff unfreeze him."
FULL_STEPS = [
    "a new egg is laid.",
    "he is fed until he hatches into a Baby "
    "(the daily meal limit is lifted for the test).",
    "he catches Monster Pox, then gets better.",
    "he makes a mess. Waiting for Runner to press its button.",
    "a second mess is left too long, so he catches a cold.",
    "medicine cures his cold (free for the test).",
    "he throws a tantrum. Waiting for Runner to press Scold.",
    "he takes a nap. Waiting for Runner to press Lights off.",
    "one stretch passes with nobody caring for him, so his meters drop.",
    "his Wellbeing drops below the lonely line.",
    "he grows into a Child (First Spark).",
    "he grows into a Teen (Teen Spark).",
    "he grows into an Adult (Adult Spark).",
    "he makes a drawing for Runner.",
    "he becomes a Rockstar (Guitar Pick, and the magazines go on the shelf).",
    "he grows into an Old Fogey (Time Piece).",
    "his farewell (Last Ember). Waiting for Runner to press Begin again.",
]
STARVE_STEPS = [
    *FULL_STEPS[:2],
    "nobody feeds him, so his Health runs out.",
    "Waiting for Runner to press Begin again.",
]

# ---
# Fakes
# ---


@dataclass
class Sent:
    """One post in Wisp's House: its words, what it was sent with and the post."""

    text: str
    kwargs: dict[str, Any]
    post: MagicMock

    def labels(self) -> list[str]:
        """The labels of the post's buttons, persistent ones included."""
        view = self.kwargs.get("view")
        if view is None:
            return []
        found = []
        for child in view.children:
            button = child.item if isinstance(child, discord.ui.DynamicItem) else child
            if isinstance(button, discord.ui.Button) and button.label:
                found.append(button.label)
        return found

    def picture(self) -> str | None:
        file = self.kwargs.get("file")
        if file is None:
            return None
        file.close()
        return str(file.filename)


class FakeServer:
    """A guild with Wisp's House, his Status, Vault and Mealtime threads."""

    def __init__(self) -> None:
        self.sent: list[Sent] = []
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock(side_effect=self._send)
        self.house.fetch_message = AsyncMock(side_effect=self._fetch)
        self.card = MagicMock(spec=discord.Message, id=888, pin=AsyncMock())
        self.title = MagicMock(spec=discord.Message, id=889)
        self.card_edit = AsyncMock()
        self.status = self._thread(STATUS_ID)
        self.status.send = AsyncMock(
            side_effect=lambda *args, **_: self.card if args else self.title
        )
        self.status.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, edit=self.card_edit, delete=AsyncMock()
        )
        self.vault = self._thread(VAULT_ID)
        self.vault.send = AsyncMock(
            side_effect=lambda *_, **__: MagicMock(id=9999, pin=AsyncMock())
        )
        self.vault.fetch_message = AsyncMock(
            return_value=MagicMock(spec=discord.Message, content="")
        )
        self.vault.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, delete=AsyncMock()
        )
        self.mealtime = self._thread(MEALTIME_ID)
        self.mealtime.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get
        self.guild.get_member.return_value = None

    @staticmethod
    def _thread(thread_id: int) -> MagicMock:
        thread = MagicMock(spec=discord.Thread)
        thread.id = thread_id
        thread.parent_id = FORUM_ID
        thread.archived = False
        return thread

    async def _send(self, text: str, **kwargs: Any) -> MagicMock:
        post = MagicMock(spec=discord.Message)
        post.id = FIRST_POST_ID + len(self.sent)
        post.content = text
        post.edit = AsyncMock()
        self.sent.append(Sent(text, kwargs, post))
        return post

    async def _fetch(self, message_id: int) -> MagicMock:
        for sent in self.sent:
            if sent.post.id == message_id:
                return sent.post
        raise discord.NotFound(MagicMock(status=404), "Unknown Message")

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        threads = {
            STATUS_ID: self.status,
            VAULT_ID: self.vault,
            MEALTIME_ID: self.mealtime,
        }
        if channel_id not in threads:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return threads[channel_id]

    def texts(self) -> list[str]:
        return [sent.text for sent in self.sent]

    def step_lines(self) -> list[str]:
        return [text for text in self.texts() if text.startswith("♪ Test life, ")]

    def reports(self) -> list[str]:
        return [text for text in self.texts() if text.startswith("Error in ")]

    def with_button(self, label: str) -> list[Sent]:
        return [sent for sent in self.sent if label in sent.labels()]


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
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.notes = NoteRepo(db)
    wisp_bot.drawings = DrawingRepo(db)
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.magazines = MagazineRepo(db)
    monkeypatch.setattr(app.WispBot, "user", WISP)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture(autouse=True)
def frozen_clock_and_no_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord.utils, "utcnow", lambda: NOW)
    monkeypatch.setattr(lifetester, "TEST_STEP_PAUSE", timedelta(0))


@pytest.fixture
def cog(bot: app.WispBot) -> LifeTest:
    return LifeTest(bot, LifeLoop(bot))


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        status_thread_id=STATUS_ID,
        status_message_id=CARD_ID,
        vault_thread_id=VAULT_ID,
        vault_message_id=VAULT_MESSAGE_ID,
        mealtime_thread_id=MEALTIME_ID,
    )
    await bot.settings.add_role(GUILD_ID, FEEDER_ROLE)
    for user_id in (RUNNER_ID, OTHER_ID):
        await bot.players.activate(GUILD_ID, user_id, NOW - timedelta(days=1))


@pytest.fixture
def drawn(bot: app.WispBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Give Wisp an AI voice and an image worker that always answer."""
    monkeypatch.setattr(bot.ai, "complete", AsyncMock(return_value="a sunny day"))
    monkeypatch.setattr(bot, "images", ImageMaker("image-worker"))
    monkeypatch.setattr(bot.images, "draw", AsyncMock(return_value=b"picture"))


def make_member(user_id: int, name: str) -> MagicMock:
    """A staff member who can feed Wisp."""
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.display_name = name
    member.mention = f"<@{user_id}>"
    member.guild_permissions = discord.Permissions(manage_guild=True)
    role = MagicMock(spec=discord.Role, id=FEEDER_ROLE)
    role.is_default.return_value = False
    member.roles = [role]
    return member


RUNNER = make_member(RUNNER_ID, "Runner")
OTHER = make_member(OTHER_ID, "Other")


def staff_context(
    bot: app.WispBot, server: FakeServer, member: MagicMock = RUNNER
) -> MagicMock:
    """A staff command typed by `member` in Wisp's House."""
    ctx = MagicMock(spec=commands.Context)
    ctx.bot = bot
    ctx.guild = server.guild
    ctx.channel = server.house
    ctx.author = member
    ctx.message = MagicMock(spec=discord.Message, id=COMMAND_ID)
    return ctx


async def type_testlife(
    cog: LifeTest, server: FakeServer, *words: str, member: MagicMock = RUNNER
) -> None:
    """Type `!wisp testlife [word]` as `member`, read as the command reads it."""
    word = lifetester._word(words[0]) if words else None
    await cog.testlife.callback(cog, staff_context(cog.bot, server, member), word)


def make_interaction(
    bot: app.WispBot, server: FakeServer, member: MagicMock, post: MagicMock
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = server.house
    interaction.user = member
    interaction.message = post
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False

    async def answer(*_args: Any, **_kwargs: Any) -> None:
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=answer)
    interaction.response.send_message = AsyncMock(side_effect=answer)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def press(
    bot: app.WispBot, server: FakeServer, sent: Sent, member: MagicMock
) -> MagicMock:
    """Press the one button on a House post as `member`; return the interaction."""
    interaction = make_interaction(bot, server, member, sent.post)
    (child,) = sent.kwargs["view"].children
    if isinstance(child, ChoreButton):
        await child.callback(interaction)
    else:
        await BeginButton().callback(interaction)
    return interaction


def private_text(interaction: MagicMock) -> str:
    (text,) = interaction.followup.send.await_args.args
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True
    return str(text)


async def until(condition: Callable[[], bool]) -> None:
    """Let the run go on until `condition` holds."""
    async with asyncio.timeout(300):
        while not condition():
            await asyncio.sleep(0.01)


async def next_button(server: FakeServer, label: str, seen: int) -> Sent:
    """Wait for the House post after the first `seen` ones with a `label` button."""
    await until(lambda: len(server.with_button(label)) > seen)
    return server.with_button(label)[seen]


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


async def lay(bot: app.WispBot, phase: Phase) -> Life:
    """Insert a life that last ticked just now."""
    life = new_egg(1, NOW - timedelta(days=2))
    life.last_tick_at = NOW
    life.phase = phase
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.health = 80.0
        life.hatched_at = life.stage_started_at = NOW - timedelta(days=1)
    if phase is Phase.DEAD:
        life.ended_at = NOW
    return await bot.lives.insert(GUILD_ID, life)


@pytest.fixture
async def waiting_run(
    cog: LifeTest, server: FakeServer
) -> AsyncIterator[asyncio.Task[None]]:
    """A full run that has reached step 4 and waits for its Clean up press."""
    run = asyncio.create_task(type_testlife(cog, server))
    await next_button(server, "Clean up", 0)
    yield run
    if not run.done():
        await type_testlife(cog, server, "stop")
        await run


async def press_through_a_full_run(
    bot: app.WispBot, server: FakeServer, run: asyncio.Task[None]
) -> None:
    """Press every button a full run waits for, as its runner, in order.

    The second mess, of step 5, is left alone: it is meant to run out.
    """
    for label in ("Clean up", "Scold", "Lights off", "Begin again"):
        await press(bot, server, await next_button(server, label, 0), RUNNER)
    await run


# ---
# A whole life
# ---


async def test_a_full_run_plays_every_step_in_order_on_the_real_wisp(
    cog: LifeTest, bot: app.WispBot, server: FakeServer, drawn: None
) -> None:
    run = asyncio.create_task(type_testlife(cog, server))

    await press_through_a_full_run(bot, server, run)

    assert server.step_lines() == [
        f"♪ Test life, step {number} of 17: {what}"
        for number, what in enumerate(FULL_STEPS, start=1)
    ]
    assert server.texts()[-1] == "♪ Test life done: 17 steps passed, 0 failed."
    assert server.reports() == []
    ended, egg = await bot.lives.history(GUILD_ID), await current_life(bot)
    assert [(life.version, life.phase) for life in ended] == [
        (2, Phase.EGG),
        (1, Phase.PASSED),
    ]
    assert egg.from_coal
    assert not egg.is_test
    assert ended[1].is_test
    kinds = {keepsake.kind for keepsake in await bot.keepsakes.of(GUILD_ID, RUNNER_ID)}
    assert kinds == {
        KeepsakeKind.EGGSHELL,
        KeepsakeKind.FIRST_SPARK,
        KeepsakeKind.TEEN_SPARK,
        KeepsakeKind.ADULT_SPARK,
        KeepsakeKind.GUITAR_PICK,
        KeepsakeKind.TIME_PIECE,
        KeepsakeKind.LAST_EMBER,
    }
    assert await bot.drawings.count_today_for(GUILD_ID, RUNNER_ID, NOW) == 1
    pictures = [picture for sent in server.sent if (picture := sent.picture())]
    for name in ("poop.gif", "wispsick.gif", "medicine.png", "wisp_drawing.jpg"):
        assert name in pictures
    assert any(text.startswith("♪ Wisp's meters dropped") for text in server.texts())
    assert bot.test_runs == {}


async def test_a_failing_step_is_reported_and_the_run_goes_on(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    bot.images = ImageMaker("image-worker")
    run = asyncio.create_task(type_testlife(cog, server))

    await press_through_a_full_run(bot, server, run)

    step_reports = [
        report for report in server.reports() if report.startswith("Error in test")
    ]
    assert step_reports == [
        "Error in test life step 14: StepFailed: Wisp made no drawing; "
        "why is posted above."
    ]
    assert len(server.step_lines()) == 17
    assert server.texts()[-1] == (
        "♪ Test life done: 16 steps passed, 1 failed (step 14)."
    )
    assert (await current_life(bot)).from_coal


async def test_the_drawing_step_says_when_no_worker_address_is_set(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    run = asyncio.create_task(type_testlife(cog, server))

    await press_through_a_full_run(bot, server, run)

    step_reports = [
        report for report in server.reports() if report.startswith("Error in test")
    ]
    assert step_reports == [
        "Error in test life step 14: StepFailed: Wisp made no drawing: the picture "
        "worker address (CF_IMAGE_WORKER_URL) is not set."
    ]
    assert server.texts()[-1] == (
        "♪ Test life done: 16 steps passed, 1 failed (step 14)."
    )


async def test_starve_ends_with_the_wisp_dead_and_then_a_new_egg(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    run = asyncio.create_task(type_testlife(cog, server, "starve"))
    question = await next_button(server, "Begin again", 0)
    await until(lambda: len(server.step_lines()) == 4)

    assert server.step_lines() == [
        f"♪ Test life, step {number} of 4: {what}"
        for number, what in enumerate(STARVE_STEPS, start=1)
    ]
    starved = await current_life(bot)
    assert (starved.version, starved.phase) == (1, Phase.DEAD)

    await press(bot, server, question, RUNNER)
    await run

    egg = await current_life(bot)
    assert (egg.version, egg.phase, egg.from_coal) == (2, Phase.EGG, False)
    assert server.texts()[-1] == "♪ Test life done: 4 steps passed, 0 failed."
    assert server.reports() == []


# ---
# The confirm guard
# ---


async def test_a_living_wisp_is_only_ended_after_confirm(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    living = await lay(bot, Phase.ALIVE)

    await type_testlife(cog, server, "starve")

    assert server.texts() == [
        "♪ This ends the current Wisp (v1). Type !wisp testlife confirm to go on."
    ]
    assert (await current_life(bot)).phase is Phase.ALIVE
    assert bot.test_runs == {}

    run = asyncio.create_task(type_testlife(cog, server, "confirm"))
    question = await next_button(server, "Begin again", 0)
    await until(lambda: len(server.step_lines()) == 4)
    cut, starved = [
        (life.id, life.phase) for life in reversed(await bot.lives.history(GUILD_ID))
    ]
    assert cut == (living.id, Phase.DEAD)
    assert starved[1] is Phase.DEAD
    await press(bot, server, question, RUNNER)
    await run
    assert server.texts()[-1] == "♪ Test life done: 4 steps passed, 0 failed."


async def test_confirm_with_nothing_asked_does_nothing(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, Phase.ALIVE)

    await type_testlife(cog, server, "confirm")

    assert server.texts() == ["♪ Nothing to confirm. Type !wisp testlife first."]
    assert (await current_life(bot)).phase is Phase.ALIVE


async def test_confirm_is_used_up_once_it_runs(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, Phase.ALIVE)
    await type_testlife(cog, server)
    run = asyncio.create_task(type_testlife(cog, server, "confirm"))
    await next_button(server, "Clean up", 0)
    await type_testlife(cog, server, "stop")
    await run

    await type_testlife(cog, server, "confirm")

    assert server.texts()[-1] == "♪ Nothing to confirm. Type !wisp testlife first."


@pytest.mark.parametrize("phase", [None, Phase.EGG, Phase.HATCHING, Phase.DEAD])
async def test_an_egg_a_dead_wisp_or_no_life_needs_no_confirm(
    cog: LifeTest, bot: app.WispBot, server: FakeServer, phase: Phase | None
) -> None:
    if phase is not None:
        await lay(bot, phase)

    run = asyncio.create_task(type_testlife(cog, server))
    await next_button(server, "Clean up", 0)
    await type_testlife(cog, server, "stop")
    await run

    assert server.step_lines()[0] == "♪ Test life, step 1 of 17: a new egg is laid."
    assert not any("confirm" in text for text in server.texts())
    versions = [life.version for life in await bot.lives.history(GUILD_ID)]
    assert versions == ([1] if phase is None else [2, 1])


# ---
# Button waits
# ---


async def test_anyone_but_the_runner_is_refused_and_the_step_keeps_waiting(
    waiting_run: asyncio.Task[None], bot: app.WispBot, server: FakeServer
) -> None:
    (mess,) = server.with_button("Clean up")

    refused = await press(bot, server, mess, OTHER)

    assert private_text(refused) == "♪ This button is for Runner's test run."
    mess.post.edit.assert_not_awaited()
    life = await current_life(bot)
    assert is_open(life, Chore.MESS)
    await asyncio.sleep(0.05)
    assert not waiting_run.done()
    assert len(server.step_lines()) == 4

    await press(bot, server, mess, RUNNER)
    await next_button(server, "Scold", 0)

    assert not is_open(await current_life(bot), Chore.MESS)
    assert len(server.step_lines()) == 7


async def test_anyone_but_the_runner_is_refused_begin_again(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    run = asyncio.create_task(type_testlife(cog, server, "starve"))
    question = await next_button(server, "Begin again", 0)

    refused = await press(bot, server, question, OTHER)

    assert private_text(refused) == "♪ This button is for Runner's test run."
    assert (await current_life(bot)).phase is Phase.DEAD
    assert not run.done()
    await press(bot, server, question, RUNNER)
    await run


# ---
# Stop, one run at a time and freezing
# ---


async def test_stop_ends_a_waiting_run_at_once_and_leaves_the_life(
    waiting_run: asyncio.Task[None],
    cog: LifeTest,
    bot: app.WispBot,
    server: FakeServer,
) -> None:
    await type_testlife(cog, server, "stop")
    await waiting_run

    assert "♪ Stopping the test life." in server.texts()
    assert server.texts()[-1] == "♪ Test life done: 3 steps passed, 0 failed."
    assert is_open(await current_life(bot), Chore.MESS)
    assert bot.test_runs == {}


async def test_stop_with_no_run_says_so(cog: LifeTest, server: FakeServer) -> None:
    await type_testlife(cog, server, "stop")

    assert server.texts() == ["♪ No test life is running."]


@pytest.mark.parametrize("words", [(), ("starve",)])
async def test_one_run_at_a_time(
    waiting_run: asyncio.Task[None],
    cog: LifeTest,
    bot: app.WispBot,
    server: FakeServer,
    words: tuple[str, ...],
) -> None:
    await type_testlife(cog, server, *words, member=OTHER)

    assert server.texts()[-1] == "♪ A test life is already running."
    assert bot.test_runs[GUILD_ID].runner_id == RUNNER_ID


async def test_a_frozen_server_refuses_to_start(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, frozen=True)

    await type_testlife(cog, server)

    assert server.texts() == [FROZEN]
    assert await bot.lives.current(GUILD_ID) is None


async def test_freezing_mid_run_ends_the_run(
    cog: LifeTest,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_credit = lifetester.credit_feed

    async def credit_then_freeze(*args: Any, **kwargs: Any) -> Any:
        events = await real_credit(*args, **kwargs)
        await bot.settings.update(GUILD_ID, frozen=True)
        return events

    monkeypatch.setattr(lifetester, "credit_feed", credit_then_freeze)

    await type_testlife(cog, server, "starve")

    assert len(server.step_lines()) == 2
    assert server.reports() == [
        "Error in test life step 2: StepFailed: Wisp did not hatch."
    ]
    assert server.texts()[-2:] == [
        FROZEN,
        "♪ Test life done: 1 step passed, 1 failed (step 2).",
    ]
    assert bot.test_runs == {}


# ---
# The preflight
# ---


async def test_a_runner_who_cannot_feed_wisp_is_refused_before_anything_changes(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    living = await lay(bot, Phase.ALIVE)
    roleless = make_member(RUNNER_ID, "Runner")
    roleless.roles = []

    async with asyncio.timeout(60):
        await type_testlife(cog, server, member=roleless)
        await type_testlife(cog, server, "confirm", member=roleless)

    assert server.texts() == [
        "♪ You can't run a test life: you don't have a role that can feed Wisp: "
        f"<@&{FEEDER_ROLE}>.",
        "♪ Nothing to confirm. Type !wisp testlife first.",
    ]
    life = await current_life(bot)
    assert (life.id, life.phase) == (living.id, Phase.ALIVE)
    assert bot.test_runs == {}


@pytest.mark.parametrize(
    ("unset", "missing"),
    [
        (("house_channel_id",), "Wisp's House is not set"),
        (("status_thread_id",), "the Status post is not set"),
        (
            ("house_channel_id", "status_thread_id"),
            "Wisp's House and the Status post are not set",
        ),
    ],
)
async def test_a_server_that_is_not_set_up_is_refused_before_anything_changes(
    cog: LifeTest,
    bot: app.WispBot,
    server: FakeServer,
    unset: tuple[str, ...],
    missing: str,
) -> None:
    living = await lay(bot, Phase.ALIVE)
    await bot.settings.update(GUILD_ID, **{name: None for name in unset})

    await type_testlife(cog, server, "starve")

    assert server.texts() == [
        f"♪ You can't run a test life: {missing}. Run !wisp setup first."
    ]
    life = await current_life(bot)
    assert (life.id, life.phase) == (living.id, Phase.ALIVE)
    assert bot.test_runs == {}


async def test_a_refused_confirm_keeps_the_ask(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, Phase.ALIVE)
    await type_testlife(cog, server)
    await bot.settings.update(GUILD_ID, frozen=True)
    await type_testlife(cog, server, "confirm")
    await bot.settings.update(GUILD_ID, frozen=False)

    run = asyncio.create_task(type_testlife(cog, server, "confirm"))
    await until(lambda: bool(server.with_button("Clean up")) or run.done())
    assert not run.done()
    await type_testlife(cog, server, "stop")
    await run

    assert server.texts()[1] == FROZEN
    assert server.step_lines()[0] == "♪ Test life, step 1 of 17: a new egg is laid."


# ---
# Typed Begin again
# ---


async def test_typed_begin_is_refused_for_anyone_but_the_runner(
    cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    run = asyncio.create_task(type_testlife(cog, server, "starve"))
    await next_button(server, "Begin again", 0)

    await life_loop.begin(staff_context(bot, server, OTHER))

    assert server.texts()[-1] == (
        "♪ A test life is running, so only Runner can begin again."
    )
    assert (await current_life(bot)).phase is Phase.DEAD
    await asyncio.sleep(0.05)
    assert not run.done()

    await life_loop.begin(staff_context(bot, server, RUNNER))
    await run

    assert (await current_life(bot)).phase is Phase.EGG
    assert server.texts()[-1] == "♪ Test life done: 4 steps passed, 0 failed."


# ---
# Any failure, unload and stopping mid-step
# ---


async def test_any_error_in_a_step_is_reported_and_the_run_goes_on(
    cog: LifeTest,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lifetester, "credit_feed", AsyncMock(side_effect=KeyError("boom"))
    )

    await type_testlife(cog, server, "starve")

    reports = [text for text in server.reports() if text.startswith("Error in test")]
    assert reports[0] == "Error in test life step 2: KeyError: 'boom'"
    assert len(server.step_lines()) == 4
    assert server.texts()[-1] == (
        "♪ Test life done: 1 step passed, 3 failed (steps 2, 3, 4)."
    )
    assert bot.test_runs == {}


async def test_unloading_the_cog_releases_a_waiting_run(
    waiting_run: asyncio.Task[None], cog: LifeTest, bot: app.WispBot, server: FakeServer
) -> None:
    await cog.cog_unload()
    await waiting_run

    assert server.texts()[-1] == "♪ Test life done: 3 steps passed, 0 failed."
    assert bot.test_runs == {}


async def test_a_stop_during_a_step_ends_the_run_after_that_step(
    cog: LifeTest,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_credit = lifetester.credit_feed

    async def credit_then_stop(*args: Any, **kwargs: Any) -> Any:
        events = await real_credit(*args, **kwargs)
        await type_testlife(cog, server, "stop")
        return events

    monkeypatch.setattr(lifetester, "credit_feed", credit_then_stop)

    await type_testlife(cog, server, "starve")

    assert len(server.step_lines()) == 2
    assert (await current_life(bot)).phase is Phase.ALIVE
    assert server.texts()[-1] == "♪ Test life done: 2 steps passed, 0 failed."


# ---
# The scheduled tick
# ---


async def test_the_scheduled_tick_skips_a_guild_under_test(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot, Phase.ALIVE)
    life.last_tick_at = NOW - timedelta(minutes=10)
    await bot.lives.save(GUILD_ID, life)
    loop = LifeLoop(bot)
    bot.test_runs[GUILD_ID] = lifetest_runs.LifeTestRun(GUILD_ID, RUNNER_ID, "Runner")

    await loop.run_tick(NOW)

    assert (await current_life(bot)).last_tick_at == NOW - timedelta(minutes=10)
    server.card_edit.assert_not_awaited()

    del bot.test_runs[GUILD_ID]
    await loop.run_tick(NOW)

    assert (await current_life(bot)).last_tick_at == NOW
    server.card_edit.assert_awaited()


# ---
# Commands
# ---


async def test_testlife_is_a_staff_command_with_its_words(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop = LifeLoop(bot)
    monkeypatch.setattr(bot, "get_cog", lambda name: loop)

    await lifetester.setup(bot)

    command = bot.get_command("testlife")
    assert command is not None
    assert command.usage == "[starve | confirm | stop]"
    assert command.ignore_extra is False
    assert [lifetester._word(typed) for typed in ("Starve", "CONFIRM", "stop")] == [
        lifetester.Word.STARVE,
        lifetester.Word.CONFIRM,
        lifetester.Word.STOP,
    ]
    with pytest.raises(commands.BadArgument):
        lifetester._word("stpo")


def test_the_old_test_commands_are_gone(bot: app.WispBot) -> None:
    assert LifeLoop(bot).get_commands() == []
