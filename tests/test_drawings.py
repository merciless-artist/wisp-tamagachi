"""Tests for Wisp's drawings: when he makes one, the caps, the prompt and the post.

Discord objects are fakes; the repositories are the real ones. The AI and the
image worker are faked, so nothing here reaches either.
"""

import random
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from ai.chain import AllProvidersFailed, ProviderError
from ai.images import ImageMaker
from ai.prompt import Prompt
from cogs import drawings
from cogs.drawings import DailyDrawings, DrawResult, draw_for
from db.activity import ActivityRepo, InteractionKind
from db.database import Database
from db.drawings import DrawingRepo
from db.lives import LifeRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.life import Mood, Phase, new_egg
from wisp.lines import FIELDS, LINES, Moment
from wisp.links import Track, TrackKind
from wisp.rules import (
    DRAWING_FILE_NAME,
    DRAWING_LIKE_WINDOW,
    DRAWINGS_PER_DAY,
    DRAWINGS_PER_MEMBER_PER_DAY,
    IMAGE_PROMPT_MAX_CHARS,
    Stage,
)
from wisp.voice import DrawReason, drawing_prompt, picture_prompt

GUILD_ID = 100
HOUSE_ID = 20
ROLE_ID = 7
USER_ID = 1
OTHER_ID = 2
THIRD_ID = 3
MESSAGE_ID = 555
NOW = datetime(2026, 11, 6, 12, 0, tzinfo=UTC)
MIDNIGHT = datetime(2026, 11, 6, tzinfo=UTC)
JPEG = b"\xff\xd8\xff-doodle"
SCENE = "A smiling fire sprite in purple headphones holding a paper star"
NO_WORDS = "No words, no letters, no text"
ERROR = re.compile(r"Error in making a drawing for Member\d+: \w+: .+")
MOMENTS = {
    DrawReason.GIFT: Moment.DRAWING_GIFT,
    DrawReason.BOND: Moment.DRAWING_BOND,
    DrawReason.TOP_FEEDER: Moment.DRAWING_TOP_FEEDER,
    DrawReason.LIKE: Moment.DRAWING_LIKE,
}

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and its members."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.sent: list[discord.File | None] = []
        self.house.send = AsyncMock(side_effect=self._send)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get
        self.members: dict[int, MagicMock] = {}
        self.guild.get_member.side_effect = self.members.get

    async def _send(self, *_args: Any, **kwargs: Any) -> MagicMock:
        self.sent.append(kwargs.get("file"))
        return MagicMock(spec=discord.Message, id=MESSAGE_ID)

    def add_member(
        self, user_id: int, roles: tuple[int, ...] = (ROLE_ID,)
    ) -> MagicMock:
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = f"Member{user_id}"
        member.roles = [MagicMock(spec=discord.Role, id=role) for role in roles]
        self.members[user_id] = member
        return member

    def posts(self) -> list[str]:
        """The text of every post in the House."""
        return [call.args[0] for call in self.house.send.await_args_list]


class SteadyRandom(random.Random):
    """A random source that picks the same second of the day and never shuffles."""

    def __init__(self, second: int) -> None:
        super().__init__()
        self.second = second

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        return self.second

    def shuffle(self, x: Any) -> None:
        return None


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
    wisp_bot.notes = NoteRepo(db)
    wisp_bot.drawings = DrawingRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot.ai, "complete", AsyncMock(return_value=SCENE))
    wisp_bot.images = ImageMaker("image-worker")
    monkeypatch.setattr(wisp_bot.images, "draw", AsyncMock(return_value=JPEG))
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot, server: FakeServer) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, ROLE_ID)
    for user_id in (USER_ID, OTHER_ID, THIRD_ID):
        server.add_member(user_id)
        await bot.players.activate(GUILD_ID, user_id, NOW)
    await lay(bot)


async def lay(
    bot: app.WispBot, phase: Phase = Phase.ALIVE, stage: Stage = Stage.TEEN
) -> None:
    life = new_egg(1, NOW - timedelta(days=9))
    life.phase = phase
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = stage
        life.health = 80.0
        life.wellbeing = 80.0
        life.hatched_at = life.stage_started_at = NOW - timedelta(days=1)
    await bot.lives.insert(GUILD_ID, life)


def member_of(server: FakeServer, user_id: int = USER_ID) -> MagicMock:
    return server.members[user_id]


async def draw(
    bot: app.WispBot,
    server: FakeServer,
    user_id: int = USER_ID,
    reason: DrawReason = DrawReason.GIFT,
    now: datetime = NOW,
) -> DrawResult:
    return await draw_for(bot, GUILD_ID, member_of(server, user_id), reason, now)


async def fed(bot: app.WispBot, user_id: int, at: datetime, tracks: int = 1) -> None:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None and life.id is not None
    for number in range(tracks):
        track = Track(TrackKind.VIIBR, f"{user_id}-{at.isoformat()}-{number}", "u")
        await bot.activity_log.record_feed(
            GUILD_ID, life.id, user_id, track, 5, 1, at + timedelta(minutes=number)
        )


async def did(
    bot: app.WispBot, user_id: int, kind: InteractionKind, at: datetime
) -> None:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None and life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID, life.id, user_id, kind, 0, 0, at
    )


# ---
# Making one
# ---


async def test_a_drawing_is_posted_with_a_ping_and_the_picture(
    bot: app.WispBot, server: FakeServer
) -> None:
    assert await draw(bot, server) is DrawResult.MADE

    (text,) = server.posts()
    assert text.startswith("♪ ") and f"<@{USER_ID}>" in text
    (call,) = server.house.send.await_args_list
    assert call.kwargs["allowed_mentions"].to_dict() == {
        "parse": [],
        "users": [USER_ID],
    }
    (art,) = server.sent
    assert art is not None
    assert art.filename == DRAWING_FILE_NAME == "wisp_drawing.jpg"
    assert art.fp.read() == JPEG
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)


async def test_the_picture_prompt_always_asks_for_a_crayon_doodle_with_no_words(
    bot: app.WispBot, server: FakeServer
) -> None:
    await draw(bot, server)

    drawn = bot.images.draw
    assert isinstance(drawn, AsyncMock)
    (text,) = drawn.await_args.args
    assert text.startswith(SCENE)
    assert "crayon" in text and NO_WORDS in text
    assert len(text) <= IMAGE_PROMPT_MAX_CHARS


@pytest.mark.parametrize("reason", list(DrawReason))
async def test_each_reason_has_its_own_line_in_his_voice(
    bot: app.WispBot, server: FakeServer, reason: DrawReason
) -> None:
    await draw(bot, server, reason=reason)

    moment = MOMENTS[reason]
    (text,) = server.posts()
    candidates = {
        line.format(name=f"<@{USER_ID}>") for line in LINES[(moment, Mood.HAPPY)]
    }
    assert text.removeprefix("♪ ") in candidates
    assert FIELDS[moment] == {"name"}


async def test_the_ai_is_told_why_who_and_what_he_remembers(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.notes.add(GUILD_ID, USER_ID, "plays the cello", NOW)

    await draw(bot, server, reason=DrawReason.BOND)

    complete = bot.ai.complete
    assert isinstance(complete, AsyncMock)
    (prompt,) = complete.await_args.args
    assert isinstance(prompt, Prompt)
    assert "Member1" in prompt.user and "plays the cello" in prompt.user
    assert "Teen" in prompt.user and "happy" in prompt.user
    assert "closer" in prompt.user
    assert NO_WORDS.lower() in prompt.system.lower()
    assert "crayon" in prompt.system


async def test_the_member_is_called_by_the_name_wisp_knows(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.players.set_name(GUILD_ID, USER_ID, "Myra")

    await draw(bot, server)

    complete = bot.ai.complete
    assert isinstance(complete, AsyncMock)
    assert "Myra" in complete.await_args.args[0].user


async def test_a_drawing_is_recorded_for_the_caps_and_the_snack_pack(
    bot: app.WispBot, server: FakeServer, db: Database
) -> None:
    await draw(bot, server, reason=DrawReason.LIKE)

    assert await bot.drawings.count_for(GUILD_ID, USER_ID) == 1
    assert await bot.drawings.count_for(GUILD_ID, OTHER_ID) == 0
    assert await bot.drawings.count_today(GUILD_ID, NOW) == 1
    assert await bot.drawings.reason_made_today(GUILD_ID, "like", NOW)
    assert not await bot.drawings.reason_made_today(GUILD_ID, "gift", NOW)
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    row = await db.fetchone(
        f"SELECT user_id, life_id, reason, message_id FROM {db.t('drawings')}"
    )
    assert row == {
        "user_id": USER_ID,
        "life_id": life.id,
        "reason": "like",
        "message_id": MESSAGE_ID,
    }


# ---
# The caps
# ---


async def test_a_member_gets_one_drawing_a_utc_day(
    bot: app.WispBot, server: FakeServer
) -> None:
    assert DRAWINGS_PER_MEMBER_PER_DAY == 1
    late = datetime(2026, 11, 6, 23, 59, tzinfo=UTC)
    assert await draw(bot, server, now=MIDNIGHT) is DrawResult.MADE
    assert await draw(bot, server, now=late) is DrawResult.SKIPPED
    assert len(server.posts()) == 1

    tomorrow = MIDNIGHT + timedelta(days=1)
    assert await draw(bot, server, now=tomorrow) is DrawResult.MADE
    assert len(server.posts()) == 2


async def test_a_server_gets_six_drawings_a_utc_day(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert DRAWINGS_PER_DAY == 6
    monkeypatch.setattr(drawings, "DRAWINGS_PER_DAY", 2)
    assert await draw(bot, server, USER_ID) is DrawResult.MADE
    assert await draw(bot, server, OTHER_ID) is DrawResult.MADE
    assert await draw(bot, server, THIRD_ID) is DrawResult.SKIPPED
    assert len(server.posts()) == 2

    tomorrow = NOW + timedelta(days=1)
    assert await draw(bot, server, THIRD_ID, now=tomorrow) is DrawResult.MADE


async def test_a_capped_member_costs_the_ai_and_the_worker_nothing(
    bot: app.WispBot, server: FakeServer
) -> None:
    await draw(bot, server)
    await draw(bot, server)

    complete, drawn = bot.ai.complete, bot.images.draw
    assert isinstance(complete, AsyncMock) and isinstance(drawn, AsyncMock)
    assert complete.await_count == 1 and drawn.await_count == 1


# ---
# Who gets one
# ---


async def test_nothing_is_drawn_for_an_egg_or_a_dead_wisp(
    bot: app.WispBot, server: FakeServer, db: Database
) -> None:
    await db.execute(f"DELETE FROM {db.t('lives')}")
    await lay(bot, Phase.EGG)
    assert await draw(bot, server) is DrawResult.SKIPPED
    await db.execute(f"DELETE FROM {db.t('lives')}")
    await lay(bot, Phase.DEAD)
    assert await draw(bot, server) is DrawResult.SKIPPED
    await db.execute(f"DELETE FROM {db.t('lives')}")
    assert await draw(bot, server) is DrawResult.SKIPPED
    assert server.posts() == []


async def test_nothing_is_drawn_while_he_is_frozen(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, frozen=True)

    assert await draw(bot, server) is DrawResult.SKIPPED
    assert server.posts() == []


async def test_nothing_is_drawn_for_a_banned_member(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.players.set_offense(GUILD_ID, USER_ID, 1, NOW + timedelta(days=1), False)

    assert await draw(bot, server) is DrawResult.SKIPPED
    assert server.posts() == []


async def test_nothing_is_drawn_for_a_member_who_cannot_feed_him(
    bot: app.WispBot, server: FakeServer
) -> None:
    no_role = server.add_member(10, roles=(99,))
    not_opened = server.add_member(11)

    assert await draw_for(bot, GUILD_ID, no_role, DrawReason.GIFT, NOW) is (
        DrawResult.SKIPPED
    )
    assert await draw_for(bot, GUILD_ID, not_opened, DrawReason.GIFT, NOW) is (
        DrawResult.SKIPPED
    )
    assert server.posts() == []


async def test_nothing_is_drawn_for_someone_who_is_not_a_member(
    bot: app.WispBot,
) -> None:
    stranger = MagicMock(spec=discord.User)
    stranger.id = 77

    assert await draw_for(bot, GUILD_ID, stranger, DrawReason.GIFT, NOW) is (
        DrawResult.SKIPPED
    )


# ---
# Failures
# ---


@pytest.mark.parametrize(
    "error",
    [
        ProviderError("HTTP 502 Image generation failed: boom"),
        ProviderError("timed out"),
    ],
)
async def test_a_worker_failure_is_posted_and_nothing_is_recorded(
    bot: app.WispBot, server: FakeServer, error: ProviderError
) -> None:
    drawn = bot.images.draw
    assert isinstance(drawn, AsyncMock)
    drawn.side_effect = error

    assert await draw(bot, server) is DrawResult.FAILED

    (text,) = server.posts()
    assert text == f"Error in making a drawing for Member1: ProviderError: {error}"
    assert ERROR.fullmatch(text)
    assert server.sent == [None]
    assert await bot.drawings.count_today(GUILD_ID, NOW) == 0

    drawn.side_effect = None
    drawn.return_value = JPEG
    assert await draw(bot, server) is DrawResult.MADE
    assert await bot.drawings.count_for(GUILD_ID, USER_ID) == 1


async def test_no_worker_address_skips_quietly_before_any_ai_call(
    bot: app.WispBot, server: FakeServer
) -> None:
    complete = bot.ai.complete
    assert isinstance(complete, AsyncMock)
    bot.images = ImageMaker(None)

    assert await draw(bot, server) is DrawResult.SKIPPED

    complete.assert_not_awaited()
    assert server.posts() == []
    assert await bot.drawings.count_today(GUILD_ID, NOW) == 0


async def test_an_ai_failure_is_posted_the_same_way(
    bot: app.WispBot, server: FakeServer
) -> None:
    complete = bot.ai.complete
    assert isinstance(complete, AsyncMock)
    complete.side_effect = AllProvidersFailed([("groq", "HTTP 500")])

    assert await draw(bot, server) is DrawResult.FAILED

    (text,) = server.posts()
    assert text.startswith(
        "Error in making a drawing for Member1: AllProvidersFailed: groq: HTTP 500"
    )
    drawn = bot.images.draw
    assert isinstance(drawn, AsyncMock)
    drawn.assert_not_awaited()
    assert await bot.drawings.count_today(GUILD_ID, NOW) == 0


async def test_a_post_that_fails_is_not_recorded(
    bot: app.WispBot, server: FakeServer
) -> None:
    sent: list[discord.File] = []

    async def send(*_args: Any, **kwargs: Any) -> None:
        if "file" in kwargs:
            sent.append(kwargs["file"])
        raise discord.HTTPException(MagicMock(status=500), "boom")

    server.house.send = AsyncMock(side_effect=send)

    assert await draw(bot, server) is DrawResult.FAILED

    assert sent[0].fp.read() == JPEG
    assert await bot.drawings.count_today(GUILD_ID, NOW) == 0


# ---
# The picture prompt
# ---


def test_the_picture_prompt_is_cut_to_fit_with_the_style_kept() -> None:
    long = "a very long scene " * 80

    text = picture_prompt(long)

    assert len(text) <= IMAGE_PROMPT_MAX_CHARS
    assert text.endswith("No words, no letters, no text anywhere in the picture.")
    assert "crayon" in text
    assert text.startswith("a very long scene")


def test_the_picture_prompt_collapses_whitespace_and_keeps_a_short_scene_whole() -> (
    None
):
    text = picture_prompt("  A star\n\n  and a moon  ")

    assert text.startswith("A star and a moon ")
    assert "\n" not in text


@pytest.mark.parametrize("reason", list(DrawReason))
def test_the_ai_prompt_asks_for_a_prompt_with_no_words_in_the_picture(
    reason: DrawReason,
) -> None:
    prompt = drawing_prompt(reason, "Myra", [], Stage.CHILD, Mood.HANGRY)

    assert "hangry" in prompt.user
    assert "Myra" in prompt.user
    assert str(IMAGE_PROMPT_MAX_CHARS) in prompt.system
    assert "no words" in prompt.system.lower()
    assert "remember" not in prompt.user


def test_the_four_reasons_are_the_four_triggers() -> None:
    assert {reason.value for reason in DrawReason} == {
        "gift",
        "bond",
        "top_feeder",
        "like",
    }


# ---
# A new bond tier
# ---


async def test_reaching_a_new_bond_tier_is_noticed_once(bot: app.WispBot) -> None:
    familiar = rules.BOND_TIERS[1][1]

    await bot.players.add_bond(GUILD_ID, USER_ID, familiar - 1)
    assert bot.players.take_tier_ups(GUILD_ID) == []
    await bot.players.add_bond(GUILD_ID, USER_ID, 1)
    await bot.players.add_bond(GUILD_ID, OTHER_ID, familiar + 5)

    assert bot.players.take_tier_ups(GUILD_ID) == [USER_ID, OTHER_ID]
    assert bot.players.take_tier_ups(GUILD_ID) == []


async def test_more_bond_inside_a_tier_or_less_bond_is_not_a_new_tier(
    bot: app.WispBot,
) -> None:
    familiar = rules.BOND_TIERS[1][1]
    await bot.players.add_bond(GUILD_ID, USER_ID, familiar)
    bot.players.take_tier_ups(GUILD_ID)

    await bot.players.add_bond(GUILD_ID, USER_ID, 3)
    await bot.players.add_bond(GUILD_ID, USER_ID, -2)
    await bot.players.add_bond(GUILD_ID, USER_ID, 0)

    assert bot.players.take_tier_ups(GUILD_ID) == []


async def test_a_new_bond_tier_makes_a_drawing_on_the_next_tick(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.players.add_bond(GUILD_ID, USER_ID, rules.BOND_TIERS[1][1])
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, NOW)

    (text,) = server.posts()
    assert f"<@{USER_ID}>" in text
    assert await bot.drawings.reason_made_today(GUILD_ID, "bond", NOW)


async def test_a_tier_reached_while_he_is_frozen_makes_none(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.settings.update(GUILD_ID, frozen=True)
    await bot.players.add_bond(GUILD_ID, USER_ID, rules.BOND_TIERS[1][1])
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, NOW)

    assert server.posts() == []
    assert bot.players.take_tier_ups(GUILD_ID) == []


# ---
# The top feeder
# ---


async def test_the_top_feeder_of_yesterday_gets_one_at_the_first_tick_of_the_day(
    bot: app.WispBot, server: FakeServer
) -> None:
    yesterday = MIDNIGHT - timedelta(hours=10)
    await fed(bot, USER_ID, yesterday, tracks=1)
    await fed(bot, OTHER_ID, yesterday, tracks=3)
    await fed(bot, THIRD_ID, MIDNIGHT + timedelta(hours=1), tracks=9)
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=2))
    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=7))

    (text,) = server.posts()
    assert f"<@{OTHER_ID}>" in text
    assert await bot.drawings.count_for(GUILD_ID, OTHER_ID) == 1
    assert await bot.drawings.reason_made_today(
        GUILD_ID, "top_feeder", MIDNIGHT + timedelta(minutes=7)
    )


async def test_the_top_feeder_is_picked_again_the_next_day(
    bot: app.WispBot, server: FakeServer
) -> None:
    await fed(bot, USER_ID, MIDNIGHT - timedelta(hours=5))
    await fed(bot, OTHER_ID, MIDNIGHT + timedelta(hours=5))
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=1))
    await daily.run(GUILD_ID, MIDNIGHT + timedelta(days=1, minutes=1))

    assert [await bot.drawings.count_for(GUILD_ID, u) for u in (USER_ID, OTHER_ID)] == [
        1,
        1,
    ]


async def test_a_banned_top_feeder_is_passed_over_for_the_next_one(
    bot: app.WispBot, server: FakeServer
) -> None:
    yesterday = MIDNIGHT - timedelta(hours=10)
    await fed(bot, USER_ID, yesterday, tracks=5)
    await fed(bot, OTHER_ID, yesterday, tracks=2)
    await bot.players.set_offense(GUILD_ID, USER_ID, 1, NOW + timedelta(days=1), False)
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=2))

    (text,) = server.posts()
    assert f"<@{OTHER_ID}>" in text


async def test_a_day_nobody_fed_makes_no_top_feeder_drawing(
    bot: app.WispBot, server: FakeServer
) -> None:
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=2))

    assert server.posts() == []


async def test_a_failed_top_feeder_drawing_is_not_retried_every_tick(
    bot: app.WispBot, server: FakeServer
) -> None:
    drawn = bot.images.draw
    assert isinstance(drawn, AsyncMock)
    drawn.side_effect = ProviderError("HTTP 502 down")
    await fed(bot, USER_ID, MIDNIGHT - timedelta(hours=5))
    daily = DailyDrawings(bot, SteadyRandom(NOW.hour * 3600 + 7200))

    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=2))
    await daily.run(GUILD_ID, MIDNIGHT + timedelta(minutes=7))

    assert len(server.posts()) == 1 and ERROR.fullmatch(server.posts()[0])
    assert await bot.drawings.count_for(GUILD_ID, USER_ID) == 0


# ---
# "I like you"
# ---


async def test_a_member_who_was_around_is_liked_at_a_random_time_once_a_day(
    bot: app.WispBot, server: FakeServer
) -> None:
    sixish = MIDNIGHT + timedelta(hours=6, minutes=1)
    await did(bot, THIRD_ID, InteractionKind.CHAT, sixish - timedelta(hours=2))
    outside = sixish - DRAWING_LIKE_WINDOW - timedelta(minutes=1)
    await did(bot, USER_ID, InteractionKind.FEED, outside)
    await did(bot, OTHER_ID, InteractionKind.POKE, sixish - timedelta(hours=1))
    daily = DailyDrawings(bot, SteadyRandom(6 * 3600))

    await daily.run(GUILD_ID, MIDNIGHT + timedelta(hours=5, minutes=59))
    assert server.posts() == []

    await daily.run(GUILD_ID, sixish)
    await daily.run(GUILD_ID, MIDNIGHT + timedelta(hours=9))

    (text,) = server.posts()
    assert f"<@{THIRD_ID}>" in text
    assert await bot.drawings.reason_made_today(GUILD_ID, "like", NOW)


@pytest.mark.parametrize(
    "kind",
    [
        InteractionKind.FEED,
        InteractionKind.SNACK,
        InteractionKind.FREE_SNACK,
        InteractionKind.CHAT,
        InteractionKind.PLAY,
    ],
)
async def test_feeding_chatting_or_playing_makes_a_member_likeable(
    bot: app.WispBot, server: FakeServer, kind: InteractionKind
) -> None:
    await did(bot, OTHER_ID, kind, NOW - timedelta(hours=3))
    daily = DailyDrawings(bot, SteadyRandom(6 * 3600))

    await daily.run(GUILD_ID, NOW)

    (text,) = server.posts()
    assert f"<@{OTHER_ID}>" in text


async def test_a_restart_does_not_give_a_second_like_that_day(
    bot: app.WispBot, server: FakeServer
) -> None:
    await did(bot, OTHER_ID, InteractionKind.CHAT, NOW - timedelta(hours=3))
    await did(bot, THIRD_ID, InteractionKind.CHAT, NOW - timedelta(hours=3))
    await DailyDrawings(bot, SteadyRandom(6 * 3600)).run(GUILD_ID, NOW)

    await DailyDrawings(bot, SteadyRandom(6 * 3600)).run(
        GUILD_ID, NOW + timedelta(hours=1)
    )

    assert len(server.posts()) == 1


async def test_nobody_around_means_no_like(
    bot: app.WispBot, server: FakeServer
) -> None:
    await DailyDrawings(bot, SteadyRandom(6 * 3600)).run(GUILD_ID, NOW)

    assert server.posts() == []


async def test_a_member_who_left_is_skipped_for_the_next_one(
    bot: app.WispBot, server: FakeServer
) -> None:
    await did(bot, OTHER_ID, InteractionKind.CHAT, NOW - timedelta(hours=3))
    await did(bot, THIRD_ID, InteractionKind.CHAT, NOW - timedelta(hours=3))
    del server.members[OTHER_ID]

    await DailyDrawings(bot, SteadyRandom(6 * 3600)).run(GUILD_ID, NOW)

    (text,) = server.posts()
    assert f"<@{THIRD_ID}>" in text


async def test_the_daily_caps_hold_across_all_four_reasons(
    bot: app.WispBot, server: FakeServer
) -> None:
    await did(bot, USER_ID, InteractionKind.CHAT, NOW - timedelta(hours=3))
    await bot.players.add_bond(GUILD_ID, USER_ID, rules.BOND_TIERS[1][1])
    await fed(bot, USER_ID, MIDNIGHT - timedelta(hours=5))

    await DailyDrawings(bot, SteadyRandom(6 * 3600)).run(GUILD_ID, NOW)

    assert len(server.posts()) == 1
    assert await bot.drawings.count_for(GUILD_ID, USER_ID) == 1
