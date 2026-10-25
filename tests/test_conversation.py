"""Tests for Wisp talking in his House: answers, fallbacks, cooldowns, chiming in.

Discord objects and the AI voice are fakes; the repositories are the real ones.
"""

import random
from collections.abc import Awaitable, Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest

import app
from ai.chain import AllProvidersFailed
from ai.prompt import Prompt
from cogs.conversation import Conversation, PokeButton
from cogs.speech import expressions
from db.activity import ActivityRepo
from db.database import Database
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp.bond import PickleStance
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.links import Track, TrackKind
from wisp.rules import (
    CHIME_IN_CHANCE,
    CHIME_IN_GAP,
    CONTEXT_LINE_CHARS,
    CONTEXT_LINES,
    POKE_SLEEP_AFTER,
    TALK_COOLDOWN,
    Stage,
)
from wisp.voice import PokeFlavor

GUILD_ID = 100
HOUSE_ID = 20
OTHER_CHANNEL_ID = 21
HOUSE_THREAD_ID = 22
WISP_ID = 999
WISP_ROLE_ID = 998
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


THIRD = 3
WISP = make_user(WISP_ID, "Wisp", bot=True)
MEMBERS = {
    FIRST: make_user(FIRST, "Member1"),
    SECOND: make_user(SECOND, "Member2"),
    THIRD: make_user(THIRD, "Member3"),
}
YOUNG = [
    (Phase.EGG, Stage.EGG, Moment.EGG_POKE),
    (Phase.HATCHING, Stage.EGG, Moment.EGG_POKE),
    (Phase.ALIVE, Stage.BABY, Moment.BABY_TALK),
]


class FakeServer:
    """A guild with Wisp's House."""

    def __init__(self) -> None:
        self.house = make_channel(HOUSE_ID)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.wisp_role = MagicMock(spec=discord.Role)
        self.wisp_role.id = WISP_ROLE_ID
        self.guild.self_role = self.wisp_role
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get


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
        role_mentions: Sequence[MagicMock] = (),
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
        message.role_mentions = list(role_mentions)
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
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
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
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)


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
    """The error lines posted in Wisp's House."""
    lines = [str(call.args[0]) for call in server.house.send.await_args_list]
    return [line for line in lines if line.startswith("Error in ")]


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
    assert prompt.user.endswith("Member1 says to you: hi there")
    assert ":wisp_happy:" in prompt.system
    assert "wisp_coin" not in prompt.system
    assert "snack_cheese" not in prompt.system
    server.house.typing.assert_called_once_with()
    server.house.send.assert_not_awaited()
    assert (await bot.players.get(GUILD_ID, FIRST)).bond == 0
    assert (
        await bot.activity_log.people_since(GUILD_ID, START - timedelta(days=30)) == 0
    )


async def test_expressions_in_replies_are_counted(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    clock: Clock,
) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_happy", "wisp_wink")
    ai.return_value = ":wisp_wink: hey :wisp_gone: :wisp_wink:"

    await cog.on_message(message.to_wisp("hi"))
    ai.return_value = "ok :wisp_happy:"
    clock.advance(TALK_COOLDOWN)
    await cog.on_message(message.to_wisp("again"))

    assert await bot.wisp_lunchbox.favorite_expressions(GUILD_ID) == [
        "wisp_wink",
        "wisp_happy",
    ]


async def test_expressions_in_chime_ins_are_counted(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_happy")
    ai.return_value = "y'all are cooking :wisp_happy:"
    cog.rng = FixedRandom(0.0)

    await cog.on_message(message("this mix is wild"))

    assert await bot.wisp_lunchbox.favorite_expressions(GUILD_ID) == ["wisp_happy"]


@pytest.mark.parametrize("stage", [Stage.BABY, Stage.ADULT])
async def test_canned_lines_count_no_expressions(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    stage: Stage,
) -> None:
    await lay(bot, stage)
    give_emojis(bot, "wisp_happy")
    ai.side_effect = OUTAGE
    said = message.to_wisp("hi")

    await cog.on_message(said)

    said.reply.assert_awaited_once()
    assert await bot.wisp_lunchbox.favorite_expressions(GUILD_ID) == []


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


async def test_mentioning_wisps_role_counts_as_talking_to_him(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    said = message(f"<@&{WISP_ROLE_ID}> hi there", role_mentions=[server.wisp_role])

    await cog.on_message(said)

    assert reply_text(said) == "hey you"
    assert prompts(ai)[0].user.endswith("Member1 says to you: hi there")


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


@pytest.mark.parametrize(("phase", "stage", "moment"), YOUNG)
async def test_egg_and_baby_answer_through_the_ai(
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
    ai.return_value = "*the shell wobbles toward you*"
    said = message.to_wisp("hello little one")

    await cog.on_message(said)

    assert reply_text(said) == "*the shell wobbles toward you*"
    (prompt,) = prompts(ai)
    if stage is Stage.EGG:
        assert prompt.user.endswith("Member1 pokes the egg and says: hello little one")
    else:
        assert "You're a Baby" in prompt.system
        assert prompt.user.endswith("Member1 says to you: hello little one")
    server.house.typing.assert_called_once_with()


@pytest.mark.parametrize(("phase", "stage", "moment"), YOUNG)
async def test_egg_and_baby_fall_back_to_their_own_lines(
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
    ai.side_effect = OUTAGE
    said = message.to_wisp("hello little one")

    await cog.on_message(said)

    assert is_line(reply_text(said), moment)
    (report,) = reports(server)
    assert report.startswith("Error in Wisp's AI voice: AllProvidersFailed")


@pytest.mark.parametrize(("phase", "stage", "moment"), YOUNG)
async def test_egg_and_baby_fall_back_when_no_words_are_left(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    phase: Phase,
    stage: Stage,
    moment: Moment,
) -> None:
    await lay(bot, stage, phase)
    ai.return_value = "<pickles>love</pickles>"
    said = message.to_wisp("poke")

    await cog.on_message(said)

    assert is_line(reply_text(said), moment)


async def test_egg_knows_who_has_been_feeding_it(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
) -> None:
    life = await lay(bot, Stage.EGG, Phase.EGG)
    assert life.id is not None
    for index, (user_id, points) in enumerate(((FIRST, 5), (SECOND, 1))):
        track = Track(TrackKind.SUNO, f"suno:{index}", f"https://suno.test/{index}")
        await bot.activity_log.record_feed(
            GUILD_ID, life.id, user_id, track, points, index, START
        )

    for user_id in (FIRST, SECOND, THIRD):
        await cog.on_message(message.to_wisp("hi egg", author=MEMBERS[user_id]))

    top, some, none = (prompt.system for prompt in prompts(ai))
    assert "Member1's songs have fed it more than anyone's." in top
    assert "Member2's songs have been feeding it." in some
    assert "Member3 hasn't fed it any songs yet." in none


async def test_egg_posts_its_own_emoji_and_keeps_nothing(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
) -> None:
    await lay(bot, Stage.EGG, Phase.EGG)
    give_emojis(bot, "wisp_egg", "wisp_happy")
    ai.return_value = "*wobble* :wisp_egg: <pickles>love</pickles><note>eggs</note>"
    said = message.to_wisp("I love pickles")

    await cog.on_message(said)

    assert reply_text(said) == "*wobble* <:wisp_egg:1>"
    (prompt,) = prompts(ai)
    assert ":wisp_egg:" in prompt.system
    assert ":wisp_happy:" not in prompt.system
    assert await bot.wisp_lunchbox.favorite_expressions(GUILD_ID) == []
    assert (await bot.players.get(GUILD_ID, FIRST)).pickle_stance is None
    assert await bot.notes.recent(GUILD_ID, FIRST) == []


async def test_egg_without_its_emoji_uploaded_is_not_offered_one(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot, Stage.EGG, Phase.EGG)
    give_emojis(bot, "wisp_happy")

    await cog.on_message(message.to_wisp("hi"))

    (prompt,) = prompts(ai)
    assert "wisp_egg" not in prompt.system


async def test_baby_saves_a_pickle_stance_but_no_note(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
) -> None:
    await lay(bot, Stage.BABY)
    give_emojis(bot, "wisp_happy", "wisp_egg")
    ai.return_value = "ew! :wisp_happy: <pickles>love</pickles><note>pickles</note>"
    said = message.to_wisp("I love pickles")

    await cog.on_message(said)

    assert reply_text(said) == "ew! <:wisp_happy:1>"
    (prompt,) = prompts(ai)
    assert ":wisp_happy:" in prompt.system and "wisp_egg" not in prompt.system
    assert "<note>" not in prompt.system
    player = await bot.players.get(GUILD_ID, FIRST)
    assert player.pickle_stance is PickleStance.LOVE
    assert await bot.notes.recent(GUILD_ID, FIRST) == []
    assert await bot.wisp_lunchbox.favorite_expressions(GUILD_ID) == ["wisp_happy"]


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


async def test_cooldown_applies_to_the_egg_too(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    clock: Clock,
) -> None:
    await lay(bot, Stage.EGG, Phase.EGG)
    first = message.to_wisp("poke")
    second = message.to_wisp("poke again")

    await cog.on_message(first)
    clock.advance(TALK_COOLDOWN - timedelta(seconds=1))
    await cog.on_message(second)

    assert reply_text(first) == "hey you"
    second.reply.assert_not_awaited()
    assert ai.await_count == 1


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
    server.house.send.assert_not_awaited()


async def test_failed_reply_is_posted_in_the_house(
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
    server.house.send.assert_awaited_once()
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )


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
    assert prompt.user.endswith("Aria says to you: hi")


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


async def test_failed_chime_in_says_nothing_but_the_report(
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

    server.house.send.assert_awaited_once()
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
    await cog.on_message(
        message(
            f"hi <@{WISP_ID}>  beep",
            author=make_user(3, "Helper", bot=True),
            mentions=[WISP],
        )
    )
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
            "Helper: hi beep",
            f"Member2: {'x' * CONTEXT_LINE_CHARS}",
        )
    )
    assert f"{chat}\n\n" in prompt.user
    assert prompt.user.count("thoughts on") == 1
    assert prompt.user.endswith("Member1 says to you: thoughts on Member2?")


async def test_staff_commands_are_not_talk(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    server: FakeServer,
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(0.0)
    commands = [
        message("!wisp freeze"),
        message("!WISP Roles list", author=MEMBERS[SECOND]),
        message(f"!wisp <@{WISP_ID}> are you there", mentions=[WISP]),
    ]
    for command in commands:
        await cog.on_message(command)

    ai.assert_not_awaited()
    server.house.send.assert_not_awaited()
    for command in commands:
        command.reply.assert_not_awaited()

    cog.rng = FixedRandom(1.0)
    await cog.on_message(message("!wispy is a word", author=MEMBERS[SECOND]))
    await cog.on_message(message.to_wisp("you there?"))

    (prompt,) = prompts(ai)
    assert "Member2: !wispy is a word" in prompt.user
    assert "freeze" not in prompt.user
    assert "Roles" not in prompt.user
    assert "are you there" not in prompt.user


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


def test_expressions_are_wisp_faces_without_the_coin_or_the_egg(
    bot: app.WispBot,
) -> None:
    give_emojis(bot, "wisp_sad", "snack_cheese", "wisp_coin", "wisp_egg", "wisp_happy")

    assert expressions(bot) == ["wisp_happy", "wisp_sad"]


# ---
# His own emojis
# ---


async def test_wisps_own_emojis_are_pointed_out_in_the_prompt(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_happy", "snack_cheese")
    said = message.to_wisp("look <:wisp_happy:1> <a:WispDance:77> <:pepe:5>")

    await cog.on_message(said)

    (prompt,) = prompts(ai)
    assert prompt.user.endswith(
        "Member1 says to you: look :wisp_happy: :WispDance: :pepe: "
        "(they used your own emojis: wisp_happy, which is your happy face; "
        "WispDance, which is a ViiBR emote of Wisp)"
    )


async def test_only_emoji_names_discord_allows_are_read(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    overlong = "wisp" + "x" * 30
    said = message.to_wisp(f"hi <:wïsp:1> <:{overlong}:2> <:wisp_say_everyone:3>")

    await cog.on_message(said)

    (prompt,) = prompts(ai)
    assert prompt.user.endswith(
        f"Member1 says to you: hi <:wïsp:1> <:{overlong}:2> :wisp_say_everyone: "
        "(they used your own emoji: wisp_say_everyone, which is a ViiBR emote of Wisp)"
    )


async def test_the_egg_sees_its_own_emoji_in_a_message(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot, Stage.EGG, Phase.EGG)
    give_emojis(bot, "wisp_egg")

    await cog.on_message(message.to_wisp("is this you <:wisp_egg:1>"))

    (prompt,) = prompts(ai)
    assert prompt.user.endswith(
        "(they used Wisp's own emoji: wisp_egg, which is Wisp's egg face)"
    )


async def test_messages_without_his_emojis_get_no_note(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, message: MessageFactory
) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_happy")

    await cog.on_message(message.to_wisp("hi <:pepe:5>"))

    (prompt,) = prompts(ai)
    assert prompt.user.endswith("Member1 says to you: hi :pepe:")


# ---
# The Poke Wisp button
# ---


def make_interaction(
    server: FakeServer, bot: app.WispBot, user_id: int = FIRST
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = server.house
    interaction.user = MEMBERS[user_id]
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False

    async def answer(*_args: Any, **_kwargs: Any) -> None:
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=answer)
    interaction.response.send_message = AsyncMock(side_effect=answer)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def private_reply(interaction: MagicMock) -> str:
    """The one private answer to a pressed button, checked to ping nobody."""
    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    interaction.followup.send.assert_awaited_once()
    kwargs = interaction.followup.send.await_args.kwargs
    assert kwargs["ephemeral"] is True
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    (text,) = interaction.followup.send.await_args.args
    return str(text)


def house_posts(server: FakeServer) -> list[str]:
    """What Wisp posted in his House, each checked to ping nobody."""
    posts = server.house.send.await_args_list
    assert all(post.kwargs["allowed_mentions"].to_dict() == NO_PING for post in posts)
    return [str(post.args[0]) for post in posts]


class HeaviestChoice(random.Random):
    """Picks the most heavily weighted poke flavor."""

    def choices(  # type: ignore[override]
        self,
        population: Sequence[PokeFlavor],
        weights: Sequence[float] | None = None,
        *,
        cum_weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[PokeFlavor]:
        assert weights is not None
        heaviest = max(range(len(population)), key=lambda index: weights[index])
        return [population[heaviest]]


@pytest.fixture
def poke(
    bot: app.WispBot, ai: AsyncMock, clock: Clock, server: FakeServer
) -> Callable[..., Awaitable[MagicMock]]:
    """Press Poke Wisp as a member, with pokes that roll their likeliest flavor."""
    bot.talk.rng = HeaviestChoice()
    button = PokeButton()

    async def press(user_id: int = FIRST) -> MagicMock:
        interaction = make_interaction(server, bot, user_id)
        await button.callback(interaction)
        return interaction

    return press


Press = Callable[..., Awaitable[MagicMock]]


async def test_poke_posts_who_poked_and_his_reaction_in_the_house(
    bot: app.WispBot, ai: AsyncMock, server: FakeServer, poke: Press
) -> None:
    await lay(bot, Stage.TEEN)
    await bot.players.set_name(GUILD_ID, FIRST, "Aria")
    ai.return_value = "hehe stop that tickles"

    pressed = await poke()

    assert house_posts(server) == ["♪ Aria poked Wisp\nhehe stop that tickles"]
    assert private_reply(pressed) == "♪ You poked Wisp."
    (prompt,) = prompts(ai)
    assert "You're a Teen" in prompt.system
    assert "Aria just poked you." in prompt.user
    assert "It tickled, and you giggle." in prompt.user


async def test_poking_the_egg_uses_the_egg_voice(
    bot: app.WispBot, ai: AsyncMock, server: FakeServer, poke: Press
) -> None:
    await lay(bot, Stage.EGG, Phase.EGG)
    ai.return_value = "*the shell giggles and rolls*"

    pressed = await poke()

    assert house_posts(server) == [
        "♪ Member1 poked the egg\n*the shell giggles and rolls*"
    ]
    assert private_reply(pressed) == "♪ You poked Wisp."
    (prompt,) = prompts(ai)
    assert "Member1 pokes the egg. The poke tickled: a ticklish egg." in prompt.user


async def test_a_quiet_house_means_the_poke_wakes_him(
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    cog: Conversation,
    clock: Clock,
    poke: Press,
) -> None:
    await lay(bot)
    await cog.on_message(message("anyone here", author=MEMBERS[SECOND]))
    clock.advance(POKE_SLEEP_AFTER)

    await poke()

    (prompt,) = prompts(ai)
    assert "this poke woke you up" in prompt.user


async def test_a_flurry_of_pokes_annoys_him(
    bot: app.WispBot, ai: AsyncMock, clock: Clock, poke: Press
) -> None:
    await lay(bot)
    await poke(FIRST)
    await poke(SECOND)
    clock.advance(timedelta(seconds=1))
    await poke(THIRD)

    first, second, third = prompts(ai)
    assert "It tickled" in first.user and "It tickled" in second.user
    assert "annoyed at being poked again" in third.user


@pytest.mark.parametrize(
    ("phase", "stage", "moment"),
    [
        (Phase.EGG, Stage.EGG, Moment.EGG_POKE),
        (Phase.ALIVE, Stage.BABY, Moment.POKED),
        (Phase.ALIVE, Stage.ADULT, Moment.POKED),
    ],
)
async def test_poke_falls_back_to_a_canned_line_when_the_ai_fails(
    bot: app.WispBot,
    ai: AsyncMock,
    server: FakeServer,
    poke: Press,
    phase: Phase,
    stage: Stage,
    moment: Moment,
) -> None:
    await lay(bot, stage, phase)
    ai.side_effect = OUTAGE

    pressed = await poke()

    report, post = house_posts(server)
    assert report.startswith("Error in Wisp's AI voice: AllProvidersFailed")
    heading, line = post.split("\n")
    assert heading.startswith("♪ Member1 poked")
    assert any(
        line in {text.format(name="Member1") for text in LINES[(moment, feeling)]}
        for feeling in Mood
    )
    assert private_reply(pressed) == "♪ You poked Wisp."


async def test_banned_members_cannot_poke(
    bot: app.WispBot, ai: AsyncMock, server: FakeServer, poke: Press
) -> None:
    await lay(bot)
    await bot.players.set_offense(GUILD_ID, FIRST, 1, START + timedelta(days=1), False)

    pressed = await poke()

    assert private_reply(pressed) == "♪ Wisp isn't answering you right now."
    server.house.send.assert_not_awaited()
    ai.assert_not_awaited()


@pytest.mark.parametrize("phase", [None, Phase.DEAD])
async def test_nobody_to_poke_without_a_life(
    bot: app.WispBot,
    ai: AsyncMock,
    server: FakeServer,
    poke: Press,
    phase: Phase | None,
) -> None:
    if phase is not None:
        await lay(bot, Stage.ADULT, phase)

    pressed = await poke()

    assert private_reply(pressed) == "♪ There's nobody to poke right now."
    server.house.send.assert_not_awaited()
    ai.assert_not_awaited()


async def test_a_poke_waits_out_the_cooldown(
    bot: app.WispBot, ai: AsyncMock, server: FakeServer, clock: Clock, poke: Press
) -> None:
    await lay(bot)
    await poke()
    clock.advance(TALK_COOLDOWN - timedelta(seconds=1))

    again = await poke()

    assert private_reply(again) == "♪ Give him a second."
    assert len(house_posts(server)) == 1
    assert ai.await_count == 1

    clock.advance(timedelta(seconds=1))
    await poke()
    assert ai.await_count == 2


async def test_pokes_and_mentions_share_one_cooldown(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    message: MessageFactory,
    clock: Clock,
    poke: Press,
) -> None:
    await lay(bot)
    await poke()
    said = message.to_wisp("hi again")
    await cog.on_message(said)

    said.reply.assert_not_awaited()

    clock.advance(TALK_COOLDOWN)
    await cog.on_message(message.to_wisp("hello"))
    pressed = await poke()

    assert private_reply(pressed) == "♪ Give him a second."
    assert ai.await_count == 2


async def test_a_poke_earns_nothing(
    bot: app.WispBot, ai: AsyncMock, poke: Press
) -> None:
    life = await lay(bot)
    ai.return_value = "hey! <pickles>love</pickles><note>pokes a lot</note>"

    await poke()

    player = await bot.players.get(GUILD_ID, FIRST)
    assert (player.bond, player.pickle_stance) == (0, None)
    assert await bot.notes.recent(GUILD_ID, FIRST) == []
    assert (
        await bot.activity_log.people_since(GUILD_ID, START - timedelta(days=30)) == 0
    )
    after = await bot.lives.current(GUILD_ID)
    assert after is not None
    assert (after.care, after.growth) == (life.care, life.growth)


async def test_a_failed_house_post_is_reported_and_the_poke_still_answered(
    bot: app.WispBot, server: FakeServer, poke: Press
) -> None:
    await lay(bot)
    server.house.send.side_effect = [
        discord.Forbidden(MagicMock(status=403), "Missing Permissions"),
        None,
    ]

    pressed = await poke()

    report = server.house.send.await_args_list[1].args[0]
    assert report.startswith("Error in posting to Wisp's House: Forbidden")
    assert private_reply(pressed) == "♪ You poked Wisp."


async def test_a_database_failure_is_reported_where_the_button_was_pressed(
    bot: app.WispBot, server: FakeServer, poke: Press, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = AsyncMock(side_effect=pymysql.err.OperationalError(2003, "down"))
    monkeypatch.setattr(bot.lives, "current", broken)

    pressed = await poke()

    (report,) = reports(server)
    assert report.startswith("Error in the Poke Wisp button: OperationalError")
    pressed.followup.send.assert_awaited_once()


async def test_poke_button_survives_restart(
    bot: app.WispBot, server: FakeServer
) -> None:
    button = PokeButton()
    assert (button.item.label, button.item.custom_id) == ("Poke Wisp", "wisp:poke")
    match = PokeButton.__discord_ui_compiled_template__.fullmatch("wisp:poke")
    assert match is not None
    restored = await PokeButton.from_custom_id(
        make_interaction(server, bot), MagicMock(spec=discord.ui.Button), match
    )
    assert isinstance(restored, PokeButton)
