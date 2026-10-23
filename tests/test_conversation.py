"""Tests for Wisp talking in his House: answers, canned talk, cooldowns, chiming in.

Discord objects and the AI voice are fakes; the repositories are the real ones.
"""

import random
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from ai.chain import AllProvidersFailed
from ai.prompt import Prompt
from cogs.conversation import Conversation
from cogs.speech import expressions
from db.activity import ActivityRepo
from db.database import Database
from db.lives import LifeRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp.bond import PickleStance
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import (
    CHIME_IN_CHANCE,
    CHIME_IN_GAP,
    CONTEXT_LINE_CHARS,
    CONTEXT_LINES,
    TALK_COOLDOWN,
    Stage,
)

GUILD_ID = 100
HOUSE_ID = 20
OTHER_CHANNEL_ID = 21
HOUSE_THREAD_ID = 22
ERRORS_ID = 40
WISP_ID = 999
FIRST = 1
SECOND = 2
START = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
NO_PING = discord.AllowedMentions.none().to_dict()
OUTAGE = AllProvidersFailed([("gemini", "timed out"), ("groq", "HTTP 503")])

# ---
# Fakes
# ---


def make_channel(channel_id: int) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.send = AsyncMock()
    return channel


def make_user(user_id: int, name: str, *, bot: bool = False) -> MagicMock:
    user = MagicMock(spec=discord.Member)
    user.id = user_id
    user.display_name = name
    user.bot = bot
    return user


WISP = make_user(WISP_ID, "Wisp", bot=True)
MEMBERS = {FIRST: make_user(FIRST, "Member1"), SECOND: make_user(SECOND, "Member2")}


class FakeServer:
    """A guild with Wisp's House and an errors channel."""

    def __init__(self) -> None:
        self.house = make_channel(HOUSE_ID)
        self.errors = make_channel(ERRORS_ID)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {
            HOUSE_ID: self.house,
            ERRORS_ID: self.errors,
        }.get


class MessageFactory:
    """Builds fake messages in the fake guild, in Wisp's House by default."""

    def __init__(self, server: FakeServer) -> None:
        self._server = server
        self._next_id = 5000

    def __call__(
        self,
        content: str,
        *,
        author: MagicMock = MEMBERS[FIRST],
        channel: MagicMock | None = None,
        mentions: Sequence[MagicMock] = (),
        replying_to: MagicMock | None = None,
    ) -> MagicMock:
        self._next_id += 1
        message = MagicMock(spec=discord.Message)
        message.id = self._next_id
        message.guild = self._server.guild
        message.author = author
        message.channel = self._server.house if channel is None else channel
        message.content = content
        message.mentions = list(mentions)
        message.reference = None
        if replying_to is not None:
            message.reference = MagicMock(spec=discord.MessageReference)
            message.reference.resolved = replying_to
        message.reply = AsyncMock()
        return message

    def to_wisp(self, text: str, author: MagicMock = MEMBERS[FIRST]) -> MagicMock:
        return self(f"<@{WISP_ID}> {text}", author=author, mentions=[WISP])


class FixedRandom(random.Random):
    """A random source whose every roll is the same number."""

    def __init__(self, roll: float) -> None:
        super().__init__()
        self.roll = roll

    def random(self) -> float:
        return self.roll


class Clock:
    """The time Wisp sees, moved forward by the tests."""

    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def ai(bot: app.WispBot, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Wisp's AI voice; each test sets what it answers or raises."""
    complete = AsyncMock(return_value="hey you")
    monkeypatch.setattr(bot.ai, "complete", complete)
    return complete


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fake = Clock()
    monkeypatch.setattr(discord.utils, "utcnow", fake)
    return fake


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.notes = NoteRepo(db)
    monkeypatch.setattr(app.WispBot, "user", WISP)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture
def cog(bot: app.WispBot, ai: AsyncMock, clock: Clock) -> Conversation:
    """The conversation cog, with rolls that never chime in."""
    conversation = Conversation(bot)
    conversation.rng = FixedRandom(1.0)
    return conversation


@pytest.fixture
def message(server: FakeServer) -> MessageFactory:
    return MessageFactory(server)


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, error_channel_id=ERRORS_ID
    )


async def lay(
    bot: app.WispBot,
    stage: Stage = Stage.ADULT,
    phase: Phase = Phase.ALIVE,
    care: float = 80.0,
) -> Life:
    life = new_egg(1, START - timedelta(days=20))
    life.phase = phase
    life.care = care
    if phase not in (Phase.EGG, Phase.HATCHING):
        life.stage = life.peak_stage = stage
        life.hatched_at = life.stage_started_at = START - timedelta(days=19)
    return await bot.lives.insert(GUILD_ID, life)


def give_emojis(bot: app.WispBot, *names: str) -> None:
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(names, start=1)
    }


def prompts(ai: AsyncMock) -> list[Prompt]:
    return [call.args[0] for call in ai.await_args_list]


def reply_text(message: MagicMock) -> str:
    """The one reply to `message`, checked to ping nobody."""
    message.reply.assert_awaited_once()
    kwargs = message.reply.await_args.kwargs
    assert kwargs["mention_author"] is False
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    (text,) = message.reply.await_args.args
    return str(text)


def is_line(text: str, moment: Moment) -> bool:
    return any(text in LINES[(moment, feeling)] for feeling in Mood)


def reports(server: FakeServer) -> list[str]:
    return [call.args[0] for call in server.errors.send.await_args_list]


# ---
# Who Wisp answers
# ---


async def test_mention_gets_an_ai_reply_without_pings(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_happy", "wisp_coin", "snack_cheese")
    ai.return_value = "hey you :wisp_happy:"
    said = message.to_wisp("hi there")

    await cog.on_message(said)

    assert reply_text(said) == "hey you <:wisp_happy:1>"
    (prompt,) = prompts(ai)
    assert prompt.user.endswith("Member1 says to you: Wisp hi there")
    assert ":wisp_happy:" in prompt.system
    assert "wisp_coin" not in prompt.system
    assert "snack_cheese" not in prompt.system
    server.house.typing.assert_called_once_with()
    server.house.send.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, FIRST)).bond == 0
    assert (
        await bot.activity_log.people_since(GUILD_ID, START - timedelta(days=30)) == 0
    )


async def test_reply_to_wisp_counts_as_talking_to_him(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    wisp_line = MagicMock(spec=discord.Message)
    wisp_line.author = WISP
    member_line = MagicMock(spec=discord.Message)
    member_line.author = MEMBERS[FIRST]
    to_wisp = message("what do you mean", replying_to=wisp_line)
    to_member = message("lol same", author=MEMBERS[SECOND], replying_to=member_line)

    await cog.on_message(to_wisp)
    await cog.on_message(to_member)

    assert reply_text(to_wisp) == "hey you"
    assert prompts(ai)[0].user.endswith("Member1 says to you: what do you mean")
    to_member.reply.assert_not_awaited()
    assert ai.await_count == 1


async def test_messages_outside_the_house_are_ignored(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    house_thread = MagicMock(spec=discord.Thread)
    house_thread.id = HOUSE_THREAD_ID
    house_thread.parent_id = HOUSE_ID
    elsewhere = message(
        f"<@{WISP_ID}> elsewhere",
        channel=make_channel(OTHER_CHANNEL_ID),
        mentions=[WISP],
    )
    in_thread = message(
        f"<@{WISP_ID}> in a duel thread", channel=house_thread, mentions=[WISP]
    )

    await cog.on_message(elsewhere)
    await cog.on_message(in_thread)

    ai.assert_not_awaited()
    elsewhere.reply.assert_not_awaited()
    in_thread.reply.assert_not_awaited()

    await cog.on_message(message.to_wisp("you there?"))

    (prompt,) = prompts(ai)
    assert "elsewhere" not in prompt.user
    assert "duel thread" not in prompt.user


@pytest.mark.parametrize(
    ("phase", "stage", "moment"),
    [
        (Phase.EGG, Stage.EGG, Moment.EGG_POKE),
        (Phase.HATCHING, Stage.EGG, Moment.EGG_POKE),
        (Phase.ALIVE, Stage.BABY, Moment.BABY_TALK),
    ],
)
async def test_egg_wobbles_and_baby_babbles_without_ai(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
    phase: Phase,
    stage: Stage,
    moment: Moment,
) -> None:
    await lay(bot, stage, phase)
    said = message.to_wisp("hello little one")

    await cog.on_message(said)

    assert is_line(reply_text(said), moment)
    ai.assert_not_awaited()
    server.house.typing.assert_not_called()


@pytest.mark.parametrize("phase", [None, Phase.DEAD])
async def test_no_life_means_silence(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    phase: Phase | None,
) -> None:
    if phase is not None:
        await lay(bot, Stage.ADULT, phase)
    said = message.to_wisp("anyone home?")

    await cog.on_message(said)

    said.reply.assert_not_awaited()
    ai.assert_not_awaited()


async def test_banned_member_is_ignored(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    await bot.players.set_offense(GUILD_ID, FIRST, 1, START + timedelta(days=1), False)
    cog.rng = FixedRandom(0.0)
    said = message.to_wisp("hey wisp")

    await cog.on_message(said)
    await cog.on_message(message("just chatting"))

    said.reply.assert_not_awaited()
    server.house.send.assert_not_awaited()
    ai.assert_not_awaited()


async def test_bots_are_never_answered(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    other_bot = make_user(SECOND, "Helper", bot=True)
    said = message.to_wisp("beep", author=other_bot)

    await cog.on_message(said)

    said.reply.assert_not_awaited()
    ai.assert_not_awaited()


# ---
# Cooldowns and outages
# ---


async def test_cooldown_stops_mention_spam(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    clock: Clock,
) -> None:
    await lay(bot)
    spam = [message.to_wisp(f"hey {index}") for index in range(3)]

    for gap, said in zip((0, 2, 3), spam):
        clock.advance(timedelta(seconds=gap))
        await cog.on_message(said)

    assert ai.await_count == 1
    assert reply_text(spam[0]) == "hey you"
    spam[1].reply.assert_not_awaited()
    spam[2].reply.assert_not_awaited()

    someone_else = message.to_wisp("my turn", author=MEMBERS[SECOND])
    await cog.on_message(someone_else)
    assert reply_text(someone_else) == "hey you"

    clock.advance(TALK_COOLDOWN - timedelta(seconds=5))
    later = message.to_wisp("ok now?")
    await cog.on_message(later)
    assert reply_text(later) == "hey you"
    assert ai.await_count == 3


async def test_cooldown_applies_to_canned_talk_too(
    cog: Conversation, bot: app.WispBot, message: MessageFactory, clock: Clock
) -> None:
    await lay(bot, Stage.EGG, Phase.EGG)
    first = message.to_wisp("poke")
    second = message.to_wisp("poke again")

    await cog.on_message(first)
    clock.advance(TALK_COOLDOWN - timedelta(seconds=1))
    await cog.on_message(second)

    assert is_line(reply_text(first), Moment.EGG_POKE)
    second.reply.assert_not_awaited()


async def test_ai_outage_falls_back_and_reports_once(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
    clock: Clock,
) -> None:
    await lay(bot)
    ai.side_effect = OUTAGE

    first = message.to_wisp("hello?")
    await cog.on_message(first)
    clock.advance(TALK_COOLDOWN)
    second = message.to_wisp("hello??")
    await cog.on_message(second)

    assert is_line(reply_text(first), Moment.CHAT_FALLBACK)
    assert is_line(reply_text(second), Moment.CHAT_FALLBACK)
    assert reports(server) == [
        "Error in Wisp's AI voice: AllProvidersFailed: "
        "gemini: timed out; groq: HTTP 503"
    ]

    ai.side_effect = None
    ai.return_value = "back online"
    clock.advance(TALK_COOLDOWN)
    third = message.to_wisp("you ok?")
    await cog.on_message(third)
    assert reply_text(third) == "back online"

    ai.side_effect = OUTAGE
    clock.advance(TALK_COOLDOWN)
    await cog.on_message(message.to_wisp("and now?"))
    assert len(reports(server)) == 2


async def test_reply_with_no_words_left_falls_back(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    ai.return_value = "<note>plays bass</note>"
    said = message.to_wisp("hey")

    await cog.on_message(said)

    assert is_line(reply_text(said), Moment.CHAT_FALLBACK)
    assert await bot.notes.recent(GUILD_ID, FIRST) == []
    server.errors.send.assert_not_awaited()


async def test_failed_reply_is_reported_to_staff(
    cog: Conversation,
    bot: app.WispBot,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    said = message.to_wisp("hey")
    said.reply.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )

    await cog.on_message(said)

    (report,) = reports(server)
    assert report.startswith("Error in talking in Wisp's House: Forbidden")


# ---
# What Wisp keeps
# ---


async def test_pickle_stance_from_a_reply_is_saved(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    clock: Clock,
) -> None:
    await lay(bot, Stage.TEEN)
    ai.return_value = "pickles? gross. <pickles>love</pickles>"
    said = message.to_wisp("I love pickles")

    await cog.on_message(said)

    assert reply_text(said) == "pickles? gross."
    player = await bot.players.get(GUILD_ID, FIRST)
    assert player.pickle_stance is PickleStance.LOVE

    clock.advance(TALK_COOLDOWN)
    await cog.on_message(message.to_wisp("so about pickles"))
    assert "Member1 loves pickles" in prompts(ai)[1].system


async def test_notes_saved_only_from_adult_on(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    clock: Clock,
) -> None:
    life = await lay(bot, Stage.TEEN)
    ai.return_value = "nice <note>plays bass</note>"
    teen_heard = message.to_wisp("I play bass")

    await cog.on_message(teen_heard)

    assert reply_text(teen_heard) == "nice"
    assert await bot.notes.recent(GUILD_ID, FIRST) == []

    life.stage = Stage.ADULT
    await bot.lives.save(GUILD_ID, life)
    clock.advance(TALK_COOLDOWN)
    await cog.on_message(message.to_wisp("I play bass"))
    assert await bot.notes.recent(GUILD_ID, FIRST) == ["plays bass"]

    clock.advance(TALK_COOLDOWN)
    await cog.on_message(message.to_wisp("guess what I play"))
    assert "- plays bass" in prompts(ai)[2].system


async def test_named_member_is_called_by_their_wisp_name(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    await bot.players.set_name(GUILD_ID, FIRST, "Aria")

    await cog.on_message(message.to_wisp("hi"))

    (prompt,) = prompts(ai)
    assert "You're talking to Aria." in prompt.system
    assert prompt.user.endswith("Aria says to you: Wisp hi")


# ---
# Chiming in
# ---


async def test_adult_chimes_in_rarely_and_not_back_to_back(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
    clock: Clock,
) -> None:
    await lay(bot)
    ai.return_value = (
        "y'all are cooking <note>likes mixes</note><pickles>hate</pickles>"
    )

    cog.rng = FixedRandom(CHIME_IN_CHANCE)
    await cog.on_message(message("warming up"))
    ai.assert_not_awaited()

    cog.rng = FixedRandom(0.0)
    first = message("this mix is wild")
    await cog.on_message(first)

    server.house.send.assert_awaited_once()
    assert server.house.send.await_args.args == ("y'all are cooking",)
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        NO_PING
    )
    first.reply.assert_not_awaited()
    (prompt,) = prompts(ai)
    assert "<note>" not in prompt.system
    assert "<pickles>" not in prompt.system
    assert "Member1: this mix is wild" in prompt.user
    assert await bot.notes.recent(GUILD_ID, FIRST) == []
    assert (await bot.players.get(GUILD_ID, FIRST)).pickle_stance is None

    clock.advance(CHIME_IN_GAP - timedelta(seconds=1))
    await cog.on_message(message("still going"))
    assert server.house.send.await_count == 1

    clock.advance(timedelta(seconds=1))
    await cog.on_message(message("one more"))
    assert server.house.send.await_count == 2


async def test_failed_chime_in_stays_quiet_and_reports(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    ai.side_effect = OUTAGE
    cog.rng = FixedRandom(0.0)

    await cog.on_message(message("anyone around"))

    server.house.send.assert_not_awaited()
    (report,) = reports(server)
    assert report.startswith("Error in Wisp's AI voice")


@pytest.mark.parametrize("stage", [Stage.BABY, Stage.CHILD, Stage.TEEN])
async def test_teen_never_chimes_in(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
    stage: Stage,
) -> None:
    await lay(bot, stage)
    cog.rng = FixedRandom(0.0)

    await cog.on_message(message("this mix is wild"))

    server.house.send.assert_not_awaited()
    ai.assert_not_awaited()


# ---
# Context
# ---


async def test_context_includes_recent_house_lines(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    long_line = "x" * (CONTEXT_LINE_CHARS + 100)
    await cog.on_message(message("first line"))
    await cog.on_message(
        message(
            f"hey <@{FIRST}> <@3>  look <@&5> at <#7>\nthis",
            author=MEMBERS[SECOND],
            mentions=[MEMBERS[FIRST]],
        )
    )
    await cog.on_message(message("my own line <:wisp_happy:1>", author=WISP))
    await cog.on_message(message(long_line, author=MEMBERS[SECOND]))
    await cog.on_message(
        message(
            f"<@!{WISP_ID}> thoughts on <@{SECOND}>?",
            mentions=[WISP, MEMBERS[SECOND]],
        )
    )

    (prompt,) = prompts(ai)
    chat = "\n".join(
        (
            "Member1: first line",
            "Member2: hey Member1 look at this",
            "Wisp: my own line :wisp_happy:",
            f"Member2: {'x' * CONTEXT_LINE_CHARS}",
        )
    )
    assert f"{chat}\n\n" in prompt.user
    assert prompt.user.count("thoughts on") == 1
    assert prompt.user.endswith("Member1 says to you: Wisp thoughts on Member2?")


async def test_context_keeps_only_the_latest_lines(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    for index in range(CONTEXT_LINES + 2):
        await cog.on_message(message(f"line {index:02}", author=MEMBERS[SECOND]))

    await cog.on_message(message.to_wisp("you following?"))

    (prompt,) = prompts(ai)
    assert "line 01" not in prompt.user
    assert "line 02" in prompt.user
    assert f"line {CONTEXT_LINES + 1:02}" in prompt.user


def test_expressions_are_wisp_faces_without_the_coin(bot: app.WispBot) -> None:
    give_emojis(bot, "wisp_sad", "snack_cheese", "wisp_coin", "wisp_happy")

    assert expressions(bot) == ["wisp_happy", "wisp_sad"]
