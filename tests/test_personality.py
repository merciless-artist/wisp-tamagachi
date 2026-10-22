"""Tests for Wisp's reaction to compliments in his House.

Discord objects are fakes; the repositories are the real ones.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import personality
from cogs.personality import FALLBACK_GIF_URL, Personality
from db.database import Database
from db.lives import LifeRepo
from db.settings import SettingsRepo
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import COMPLIMENT_COOLDOWN, Stage

GUILD_ID = 100
HOUSE_ID = 20
ERRORS_ID = 40
ELSEWHERE_ID = 30
WISP_ID = 999
MEMBER_ID = 1
START = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and an errors channel."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.id = HOUSE_ID
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels = {HOUSE_ID: self.house, ERRORS_ID: self.errors}
        self.guild.get_channel_or_thread.side_effect = channels.get


def make_member(user_id: int = MEMBER_ID, *, bot: bool = False) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = bot
    return member


def make_channel(channel_id: int = HOUSE_ID) -> MagicMock:
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    channel.fetch_message = AsyncMock()
    return channel


def make_thread(parent_id: int, thread_id: int = 777) -> MagicMock:
    thread = MagicMock(spec=discord.Thread)
    thread.id = thread_id
    thread.parent_id = parent_id
    thread.fetch_message = AsyncMock()
    return thread


class MessageFactory:
    """Builds fake messages in the fake guild."""

    def __init__(self, guild: MagicMock, wisp: MagicMock) -> None:
        self._guild = guild
        self._wisp = wisp

    def __call__(
        self,
        content: str,
        *,
        aimed: bool = True,
        author: MagicMock | None = None,
        channel: MagicMock | None = None,
        at: datetime = START,
        in_guild: bool = True,
    ) -> MagicMock:
        message = MagicMock(spec=discord.Message)
        message.guild = self._guild if in_guild else None
        message.author = author if author is not None else make_member()
        message.channel = channel if channel is not None else make_channel()
        message.content = content
        message.created_at = at
        message.mentions = [self._wisp] if aimed else []
        message.reference = None
        message.reply = AsyncMock()
        return message

    def replying_to(self, content: str, target: object, **options: Any) -> MagicMock:
        """A message that mentions nobody and replies to `target`."""
        message = self(content, aimed=False, **options)
        reference = MagicMock(spec=discord.MessageReference)
        reference.message_id = 4242
        reference.resolved = target
        message.reference = reference
        return message


def message_from(author: MagicMock) -> MagicMock:
    sent = MagicMock(spec=discord.Message)
    sent.author = author
    return sent


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def wisp_user() -> MagicMock:
    user = MagicMock(spec=discord.ClientUser)
    user.id = WISP_ID
    return user


@pytest.fixture
def assets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An ASSETS folder holding the no u GIF."""
    (tmp_path / "no_u.gif").write_bytes(b"GIF89a")
    monkeypatch.setattr(personality, "ASSETS_DIR", tmp_path)
    return tmp_path


@pytest.fixture
def bot(
    db: Database,
    server: FakeServer,
    wisp_user: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    monkeypatch.setattr(wisp_bot._connection, "user", wisp_user)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture
def cog(bot: app.WispBot) -> Personality:
    return Personality(bot)


@pytest.fixture
def message(server: FakeServer, wisp_user: MagicMock) -> MessageFactory:
    return MessageFactory(server.guild, wisp_user)


async def start_life(
    bot: app.WispBot, *, phase: Phase = Phase.ALIVE, care: float = 50.0
) -> Life:
    life = new_egg(1, START)
    life.phase = phase
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = START
    life.care = care
    return await bot.lives.insert(GUILD_ID, life)


async def set_house(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, error_channel_id=ERRORS_ID
    )


@pytest.fixture
async def ready(bot: app.WispBot, assets: Path) -> Life:
    """A configured guild with a living, well fed Wisp and the GIF in place."""
    await set_house(bot)
    return await start_life(bot)


def sends_without_pinging(kwargs: dict[str, Any]) -> bool:
    mentions = kwargs["allowed_mentions"]
    return kwargs["mention_author"] is False and (
        mentions.to_dict() == discord.AllowedMentions.none().to_dict()
    )


def reply_kwargs(reply: AsyncMock) -> dict[str, Any]:
    """The keyword arguments of the one awaited reply."""
    assert reply.await_args is not None
    return dict(reply.await_args.kwargs)


def answered_with_gif(reply: AsyncMock) -> bool:
    if reply.await_count != 1:
        return False
    kwargs = reply_kwargs(reply)
    return (
        isinstance(kwargs["file"], discord.File)
        and kwargs["file"].filename == "no_u.gif"
        and sends_without_pinging(kwargs)
    )


# ---
# Who gets answered
# ---


@pytest.mark.usefixtures("ready")
async def test_compliment_aimed_at_wisp_gets_no_u(
    cog: Personality, message: MessageFactory
) -> None:
    compliment = message("Wisp you are so cute")
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


@pytest.mark.usefixtures("ready")
async def test_compliment_not_aimed_at_wisp_ignored(
    cog: Personality, message: MessageFactory
) -> None:
    chatter = message("that song is so cute", aimed=False)
    await cog.on_message(chatter)
    chatter.reply.assert_not_awaited()


@pytest.mark.usefixtures("ready")
async def test_other_channels_ignored(
    cog: Personality, message: MessageFactory
) -> None:
    elsewhere = message("so cute", channel=make_channel(ELSEWHERE_ID))
    stray_thread = message("so cute", channel=make_thread(ELSEWHERE_ID))
    await cog.on_message(elsewhere)
    await cog.on_message(stray_thread)
    elsewhere.reply.assert_not_awaited()
    stray_thread.reply.assert_not_awaited()


@pytest.mark.usefixtures("ready")
async def test_thread_in_the_house_counts(
    cog: Personality, message: MessageFactory
) -> None:
    compliment = message("so cute", channel=make_thread(HOUSE_ID))
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


async def test_house_not_set_ignored(cog: Personality, message: MessageFactory) -> None:
    compliment = message("so cute")
    await cog.on_message(compliment)
    compliment.reply.assert_not_awaited()


@pytest.mark.usefixtures("ready")
async def test_bots_and_direct_messages_ignored(
    cog: Personality, message: MessageFactory
) -> None:
    from_bot = message("so cute", author=make_member(5, bot=True))
    direct = message("so cute", in_guild=False)
    await cog.on_message(from_bot)
    await cog.on_message(direct)
    from_bot.reply.assert_not_awaited()
    direct.reply.assert_not_awaited()


# ---
# What counts as a compliment
# ---


@pytest.mark.usefixtures("ready")
@pytest.mark.parametrize(
    "text",
    [
        "CUTE",
        "you're ADORABLE",
        "I love you",
        "i  love   you",
        "good boy!",
        "the best.",
        "so sweet",
        "amazing",
        "precious",
    ],
)
async def test_compliment_words_match(
    cog: Personality, message: MessageFactory, text: str
) -> None:
    compliment = message(text)
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


@pytest.mark.usefixtures("ready")
@pytest.mark.parametrize(
    "text",
    [
        "hello wisp",
        "bestie",
        "sweetest",
        "cuter",
        "preciousness",
        "a love of you",
        "good, boy",
        "",
    ],
)
async def test_other_words_do_not_match(
    cog: Personality, message: MessageFactory, text: str
) -> None:
    chatter = message(text)
    await cog.on_message(chatter)
    chatter.reply.assert_not_awaited()


# ---
# Replying to Wisp
# ---


@pytest.mark.usefixtures("ready")
async def test_reply_to_wisp_counts(
    cog: Personality, message: MessageFactory, wisp_user: MagicMock
) -> None:
    compliment = message.replying_to("so cute", message_from(wisp_user))
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


@pytest.mark.usefixtures("ready")
async def test_reply_to_someone_else_ignored(
    cog: Personality, message: MessageFactory
) -> None:
    chatter = message.replying_to("so cute", message_from(make_member(5)))
    await cog.on_message(chatter)
    chatter.reply.assert_not_awaited()


@pytest.mark.usefixtures("ready")
async def test_unresolved_reply_is_fetched_once(
    cog: Personality, message: MessageFactory, wisp_user: MagicMock
) -> None:
    channel = make_channel()
    channel.fetch_message.return_value = message_from(wisp_user)
    compliment = message.replying_to("so cute", None, channel=channel)
    await cog.on_message(compliment)
    channel.fetch_message.assert_awaited_once_with(4242)
    assert answered_with_gif(compliment.reply)


@pytest.mark.usefixtures("ready")
async def test_reply_to_a_deleted_message_ignored(
    cog: Personality, message: MessageFactory
) -> None:
    channel = make_channel()
    channel.fetch_message.side_effect = discord.NotFound(
        MagicMock(status=404), "Unknown Message"
    )
    chatter = message.replying_to("so cute", None, channel=channel)
    await cog.on_message(chatter)
    chatter.reply.assert_not_awaited()


# ---
# Cooldown
# ---


@pytest.mark.usefixtures("ready")
async def test_cooldown(cog: Personality, message: MessageFactory) -> None:
    first = message("so cute")
    soon = message("so adorable", at=START + COMPLIMENT_COOLDOWN / 2)
    later = message("so sweet", at=START + COMPLIMENT_COOLDOWN)
    await cog.on_message(first)
    await cog.on_message(soon)
    await cog.on_message(later)
    assert answered_with_gif(first.reply)
    soon.reply.assert_not_awaited()
    assert answered_with_gif(later.reply)


@pytest.mark.usefixtures("ready")
async def test_cooldown_is_per_channel(
    cog: Personality, message: MessageFactory
) -> None:
    first = message("so cute")
    in_thread = message("so cute", channel=make_thread(HOUSE_ID))
    await cog.on_message(first)
    await cog.on_message(in_thread)
    assert answered_with_gif(first.reply)
    assert answered_with_gif(in_thread.reply)


@pytest.mark.usefixtures("ready")
async def test_chatter_does_not_start_the_cooldown(
    cog: Personality, message: MessageFactory
) -> None:
    unaimed = message("so cute", aimed=False)
    compliment = message("so cute")
    await cog.on_message(unaimed)
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


# ---
# What Wisp says
# ---


@pytest.mark.usefixtures("assets")
async def test_hangry_reply(
    cog: Personality, message: MessageFactory, bot: app.WispBot
) -> None:
    await set_house(bot)
    await start_life(bot, care=5.0)
    compliment = message("so cute")
    await cog.on_message(compliment)
    compliment.reply.assert_awaited_once()
    kwargs = reply_kwargs(compliment.reply)
    assert kwargs["content"] in LINES[(Moment.COMPLIMENT_HANGRY, Mood.HANGRY)]
    assert "file" not in kwargs
    assert sends_without_pinging(kwargs)


@pytest.mark.usefixtures("assets")
@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD, Phase.COLD])
async def test_wisp_without_a_living_life_says_no_u(
    cog: Personality, message: MessageFactory, bot: app.WispBot, phase: Phase
) -> None:
    await set_house(bot)
    await start_life(bot, phase=phase, care=0.0)
    compliment = message("so cute")
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


@pytest.mark.usefixtures("assets")
async def test_no_life_says_no_u(
    cog: Personality, message: MessageFactory, bot: app.WispBot
) -> None:
    await set_house(bot)
    compliment = message("so cute")
    await cog.on_message(compliment)
    assert answered_with_gif(compliment.reply)


@pytest.mark.usefixtures("ready")
async def test_missing_gif_falls_back_to_the_link(
    cog: Personality, message: MessageFactory, assets: Path
) -> None:
    (assets / "no_u.gif").unlink()
    compliment = message("so cute")
    await cog.on_message(compliment)
    compliment.reply.assert_awaited_once()
    kwargs = reply_kwargs(compliment.reply)
    assert kwargs["content"] == FALLBACK_GIF_URL
    assert "file" not in kwargs
    assert sends_without_pinging(kwargs)


# ---
# Failures
# ---


@pytest.mark.usefixtures("ready")
async def test_send_failure_is_reported_to_staff(
    cog: Personality, message: MessageFactory, server: FakeServer
) -> None:
    compliment = message("so cute")
    compliment.reply.side_effect = discord.Forbidden(
        MagicMock(status=403), "Missing Permissions"
    )
    await cog.on_message(compliment)
    server.errors.send.assert_awaited_once()
    report = server.errors.send.await_args.args[0]
    assert report.startswith("Error in answering a compliment: Forbidden")
