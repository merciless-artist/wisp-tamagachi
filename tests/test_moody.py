"""Tests for moody phrases: staff's song lines, Wisp grumbling them, the guesses.

Discord objects and the AI voice are fakes; the repositories are the real ones.
The phrases, artists and songs are placeholders.
"""

import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pymysql
import pytest
from discord import app_commands

import app
from cogs import moody, moody_staff
from cogs.conversation import Conversation
from cogs.moody import MoodyMenu, draw, moody_round, post
from cogs.moody_staff import list_messages
from db.activity import ActivityRepo
from db.database import Database
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.moody import MoodyRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from wisp.life import Life, Phase, new_egg
from wisp.moody import (
    Phrase,
    has_phrase,
    is_moody,
    option_label,
    options_for,
    pick_phrase,
    problem,
    with_phrase,
    won_line,
)
from wisp.rules import (
    CRANKY_FOR,
    HANGRY_BELOW,
    LONELY_BELOW,
    MOODY_CREDIT_MAX,
    MOODY_PHRASE_CHANCE,
    MOODY_PHRASE_GAP,
    MOODY_PHRASE_MAX,
    MOODY_PHRASE_REWARD,
    MOODY_ROUND_FOR,
    MOODY_YEAR_MAX,
    MOODY_YEAR_MIN,
    Stage,
)
from wisp.text import MESSAGE_LIMIT, text_length

GUILD_ID = 100
OTHER_GUILD_ID = 101
HOUSE_ID = 20
WISP_ID = 999
OWNER_ID = 998
STAFF_ID = 1
MEMBER_ID = 2
SECOND_ID = 3
STRANGER_ID = 4
POSTED_ID = 7000
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
NO_PING = discord.AllowedMentions.none().to_dict()
PHRASE_ONE = "Phrase One is mine"
SONGS = [
    (PHRASE_ONE, "Artist A", "Song A", 1999),
    ("Phrase Two over here", "Artist B", "Song B", 2001),
    ("Phrase Three right now", "Artist C", "Song C", 1985),
]


def phrase_of(phrase_id: int, artist: str = "Artist A", song: str = "Song A") -> Phrase:
    return Phrase(
        phrase_id, Stage.TEEN.value, f"Phrase {phrase_id}", artist, song, 1999
    )


class FixedRandom(random.Random):
    """Seeded choices, with every plain roll the same number."""

    def __init__(self, roll: float, seed: int = 1) -> None:
        super().__init__(seed)
        self.roll = roll

    def random(self) -> float:
        return self.roll


# ---
# Pure rules
# ---


@pytest.mark.parametrize(
    ("text", "artist", "song", "year", "refusal"),
    [
        ("Phrase One", "Artist A", "Song A", 1999, None),
        ("", "Artist A", "Song A", 1999, "♪ The phrase can't be empty."),
        ("...!!!", "Artist A", "Song A", 1999, "♪ The phrase needs at least one word."),
        ("♪ ♪ ♪", "Artist A", "Song A", 1999, "♪ The phrase needs at least one word."),
        ("Phrase One", "", "Song A", 1999, "♪ The artist can't be empty."),
        ("Phrase One", "Artist A", "", 1999, "♪ The song can't be empty."),
        (
            "x" * (MOODY_PHRASE_MAX + 1),
            "Artist A",
            "Song A",
            1999,
            f"♪ The phrase can be at most {MOODY_PHRASE_MAX} characters.",
        ),
        ("x" * MOODY_PHRASE_MAX, "Artist A", "Song A", 1999, None),
        (
            "Phrase One",
            "a" * (MOODY_CREDIT_MAX + 1),
            "Song A",
            1999,
            f"♪ The artist can be at most {MOODY_CREDIT_MAX} characters.",
        ),
        (
            "Phrase One",
            "Artist A",
            "s" * (MOODY_CREDIT_MAX + 1),
            1999,
            f"♪ The song can be at most {MOODY_CREDIT_MAX} characters.",
        ),
        ("Phrase One", "Artist A", "Song A", MOODY_YEAR_MIN, None),
        ("Phrase One", "Artist A", "Song A", MOODY_YEAR_MAX, None),
        (
            "Phrase One",
            "Artist A",
            "Song A",
            MOODY_YEAR_MIN - 1,
            f"♪ The year must be from {MOODY_YEAR_MIN} to {MOODY_YEAR_MAX}.",
        ),
        (
            "Phrase One",
            "Artist A",
            "Song A",
            MOODY_YEAR_MAX + 1,
            f"♪ The year must be from {MOODY_YEAR_MIN} to {MOODY_YEAR_MAX}.",
        ),
    ],
)
def test_problem_checks_lengths_and_years(
    text: str, artist: str, song: str, year: int, refusal: str | None
) -> None:
    assert problem(text, artist, song, year) == refusal


@pytest.mark.parametrize(
    ("reply", "found"),
    [
        ("ugh. Phrase One is mine!", True),
        ("PHRASE   one, is... MINE", True),
        ("phrase one is", False),
        ("nothing like it", False),
    ],
)
def test_the_phrase_is_found_ignoring_case_punctuation_and_spaces(
    reply: str, found: bool
) -> None:
    assert has_phrase(reply, PHRASE_ONE) is found


def test_a_reply_saying_the_phrase_is_kept_as_it_is() -> None:
    phrase = Phrase(1, "teen", PHRASE_ONE, "Artist A", "Song A", 1999)

    assert with_phrase("hmph. phrase one IS mine.", phrase, MESSAGE_LIMIT) == (
        "hmph. phrase one IS mine."
    )


def test_a_reply_without_the_phrase_ends_with_it() -> None:
    phrase = Phrase(1, "teen", PHRASE_ONE, "Artist A", "Song A", 1999)

    assert with_phrase("hmph.", phrase, MESSAGE_LIMIT) == f"hmph.\n{PHRASE_ONE}"


def test_a_long_reply_is_cut_never_the_phrase_and_leaves_room_to_win() -> None:
    phrase = Phrase(1, "teen", "y" * MOODY_PHRASE_MAX, "A" * 100, "S" * 100, 2000)

    text = with_phrase("word " * 600, phrase, MESSAGE_LIMIT)

    assert text.endswith("\n" + phrase.text)
    assert text.startswith("word word")
    winner = won_line(2**64 - 1, phrase)
    assert text_length(f"{text}\n{winner}") <= MESSAGE_LIMIT


def test_a_long_reply_opening_with_the_phrase_is_cut_without_a_second_copy() -> None:
    phrase = Phrase(1, "teen", PHRASE_ONE, "Artist A", "Song A", 1999)

    text = with_phrase(f"{PHRASE_ONE}! " + "word " * 600, phrase, MESSAGE_LIMIT)

    assert text.startswith(f"{PHRASE_ONE}! word")
    assert text.count(PHRASE_ONE) == 1
    winner = won_line(2**64 - 1, phrase)
    assert text_length(f"{text}\n{winner}") <= MESSAGE_LIMIT


def test_option_labels_fit_discords_limit() -> None:
    phrase = Phrase(1, "teen", "Phrase One", "A" * 100, "S" * 100, 1999)

    assert len(option_label(phrase)) == 100
    assert option_label(phrase_of(1)) == "Artist A, Song A (1999)"


def test_a_stage_needs_three_different_songs() -> None:
    same_song = [phrase_of(1), phrase_of(2), phrase_of(3, song="Song B")]
    assert pick_phrase(same_song, None, random.Random(1)) is None
    three = [*same_song, phrase_of(4, artist="Artist C", song="Song C")]
    assert pick_phrase(three, None, random.Random(1)) is not None


def test_the_last_phrase_is_skipped_while_there_is_another() -> None:
    phrases = [
        phrase_of(1),
        phrase_of(2, "Artist B", "Song B"),
        phrase_of(3, "Artist C", "Song C"),
    ]
    picks = {pick_phrase(phrases, 2, random.Random(seed)) for seed in range(40)}
    assert {pick.id for pick in picks if pick is not None} == {1, 3}


def test_options_hold_the_answer_and_two_other_songs_shuffled() -> None:
    phrases = [
        phrase_of(1),
        phrase_of(2),
        phrase_of(3, "Artist B", "Song B"),
        phrase_of(4, "Artist B", "Song B"),
        phrase_of(5, "Artist C", "Song C"),
        phrase_of(6, "Artist D", "Song D"),
    ]
    answer = phrases[0]
    orders = set()
    for seed in range(40):
        options = options_for(answer, phrases, random.Random(seed))
        assert len(options) == 3
        assert answer in options
        assert len({option.song_key for option in options}) == 3
        orders.add(options.index(answer))
    assert orders == {0, 1, 2}


def make_life(stage: Stage = Stage.TEEN, health: float = 80.0) -> Life:
    life = new_egg(1, NOW - timedelta(days=20))
    life.phase = Phase.ALIVE
    life.stage = life.peak_stage = stage
    life.hatched_at = life.stage_started_at = NOW - timedelta(days=19)
    life.health = health
    life.wellbeing = 80.0
    return life


def test_he_is_moody_when_hangry_lonely_or_feeling_anything() -> None:
    happy = make_life()
    assert not is_moody(happy, NOW)
    assert is_moody(make_life(health=HANGRY_BELOW - 1), NOW)
    lonely = make_life()
    lonely.wellbeing = LONELY_BELOW - 1
    assert is_moody(lonely, NOW)
    cranky = make_life()
    cranky.cranky_until = NOW + CRANKY_FOR
    assert is_moody(cranky, NOW)
    poxy = make_life()
    poxy.cold_left = 60.0
    assert is_moody(poxy, NOW)


@pytest.mark.parametrize("chore", ["tantrum_left", "mess_left"])
def test_he_is_moody_while_a_tantrum_or_a_mess_waits(chore: str) -> None:
    life = make_life()
    setattr(life, chore, 60.0)
    assert is_moody(life, NOW)


@pytest.mark.parametrize("stage", [Stage.BABY, Stage.CHILD, Stage.OLD_FOGEY])
def test_only_child_on_plays(stage: Stage) -> None:
    life = make_life(stage, health=HANGRY_BELOW - 1)
    assert is_moody(life, NOW) is (stage is not Stage.BABY)


# ---
# Fakes
# ---


def make_member(user_id: int, *, manage_guild: bool = False) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = False
    member.display_name = f"Member{user_id}"
    member.guild_permissions = discord.Permissions(manage_guild=manage_guild)
    member.roles = []
    return member


WISP = make_member(WISP_ID)
WISP.bot = True


class FakeServer:
    """A guild with Wisp's House."""

    def __init__(self, guild_id: int = GUILD_ID) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.id = HOUSE_ID
        self.house.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = guild_id
        self.guild.self_role = MagicMock(spec=discord.Role)
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get
        self.guild.get_channel.return_value = None


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """Wisp's clock: set `clock[0]` to move time."""
    now = [NOW]
    monkeypatch.setattr(discord.utils, "utcnow", lambda: now[0])
    return now


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
    wisp_bot.notes = NoteRepo(db)
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
    wisp_bot.moody = MoodyRepo(db)
    wisp_bot.owner_id = OWNER_ID
    monkeypatch.setattr(app.WispBot, "user", WISP)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture
def ai(bot: app.WispBot, monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    complete = AsyncMock(return_value="hmph")
    monkeypatch.setattr(bot.ai, "complete", complete)
    return complete


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    for user_id in (MEMBER_ID, SECOND_ID):
        await bot.players.activate(GUILD_ID, user_id, NOW - timedelta(days=1))


async def add_songs(bot: app.WispBot, stage: Stage = Stage.TEEN) -> list[int]:
    return [
        await bot.moody.add(GUILD_ID, stage, text, artist, song, year, STAFF_ID, NOW)
        for text, artist, song, year in SONGS
    ]


async def lay(bot: app.WispBot, stage: Stage = Stage.TEEN) -> Life:
    return await bot.lives.insert(GUILD_ID, make_life(stage, HANGRY_BELOW - 5))


def slash(bot: app.WispBot, server: FakeServer, user: MagicMock) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.user = user
    user.guild = server.guild
    interaction.guild = server.guild
    interaction.guild_id = server.guild.id
    interaction.channel = server.house
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=True)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    return interaction


def private(interaction: MagicMock) -> list[str]:
    """The private answers, none of them able to ping."""
    sent = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        sent.append(str(call.args[0]))
    return sent


def stage_choice(stage: Stage) -> app_commands.Choice[str]:
    return app_commands.Choice(name=stage.label, value=stage.value)


async def run_add(
    bot: app.WispBot,
    server: FakeServer,
    user: MagicMock,
    phrase: str = "Phrase One",
    year: int = 1999,
) -> MagicMock:
    interaction = slash(bot, server, user)
    command: Any = moody_staff.add_phrase
    await command.callback(
        interaction, stage_choice(Stage.TEEN), phrase, " Artist A ", "Song A", year
    )
    return interaction


# ---
# Staff commands
# ---


async def test_staff_add_list_and_remove_phrases_privately(
    bot: app.WispBot, server: FakeServer
) -> None:
    staff = make_member(STAFF_ID, manage_guild=True)

    added = await run_add(bot, server, staff, "  Phrase One  ")

    added.response.defer.assert_awaited_once_with(ephemeral=True)
    (phrase,) = await bot.moody.for_stage(GUILD_ID, Stage.TEEN)
    assert (phrase.text, phrase.artist, phrase.song, phrase.year) == (
        "Phrase One",
        "Artist A",
        "Song A",
        1999,
    )
    assert private(added) == [f"♪ Moody phrase #{phrase.id} added for Teen."]

    listed = slash(bot, server, staff)
    list_command: Any = moody_staff.list_phrases
    await list_command.callback(listed, stage_choice(Stage.TEEN))
    assert private(listed) == [
        "♪ Moody phrases for Teen\n"
        "・Wisp needs 2 more different songs to use them.\n"
        f"#{phrase.id} ・ Phrase One ・ Artist A, Song A (1999)"
    ]

    removed = slash(bot, server, staff)
    remove_command: Any = moody_staff.remove_phrase
    await remove_command.callback(removed, phrase.id)
    assert private(removed) == [f"♪ Moody phrase #{phrase.id} removed."]
    assert await bot.moody.for_stage(GUILD_ID, Stage.TEEN) == []

    again = slash(bot, server, staff)
    await remove_command.callback(again, phrase.id)
    assert private(again) == [f"♪ There is no moody phrase #{phrase.id} here."]


async def test_an_empty_stage_says_so(bot: app.WispBot, server: FakeServer) -> None:
    listed = slash(bot, server, make_member(STAFF_ID, manage_guild=True))
    command: Any = moody_staff.list_phrases

    await command.callback(listed, stage_choice(Stage.ROCKSTAR))

    assert private(listed) == ["♪ There are no moody phrases for Rockstar yet."]


async def test_the_moody_commands_refuse_anyone_but_staff(
    bot: app.WispBot, server: FakeServer
) -> None:
    member = make_member(MEMBER_ID)
    phrase_id = await bot.moody.add(
        GUILD_ID, Stage.TEEN, "Phrase One", "Artist A", "Song A", 1999, STAFF_ID, NOW
    )
    used = [slash(bot, server, member) for _ in range(3)]
    add_command: Any = moody_staff.add_phrase
    list_command: Any = moody_staff.list_phrases
    remove_command: Any = moody_staff.remove_phrase

    await add_command.callback(
        used[0], stage_choice(Stage.TEEN), "Phrase Two", "Artist B", "Song B", 2001
    )
    await list_command.callback(used[1], stage_choice(Stage.TEEN))
    await remove_command.callback(used[2], phrase_id)

    for interaction in used:
        interaction.response.send_message.assert_awaited_once_with(
            "That command is for staff.", ephemeral=True
        )
        interaction.followup.send.assert_not_awaited()
    assert [p.id for p in await bot.moody.for_stage(GUILD_ID, Stage.TEEN)] == [
        phrase_id
    ]


async def test_phrases_belong_to_their_server(bot: app.WispBot) -> None:
    elsewhere = FakeServer(OTHER_GUILD_ID)
    staff = make_member(STAFF_ID, manage_guild=True)
    phrase_id = await bot.moody.add(
        GUILD_ID, Stage.TEEN, "Phrase One", "Artist A", "Song A", 1999, STAFF_ID, NOW
    )
    listed = slash(bot, elsewhere, staff)
    removed = slash(bot, elsewhere, staff)
    list_command: Any = moody_staff.list_phrases
    remove_command: Any = moody_staff.remove_phrase

    await list_command.callback(listed, stage_choice(Stage.TEEN))
    await remove_command.callback(removed, phrase_id)

    assert private(listed) == ["♪ There are no moody phrases for Teen yet."]
    assert private(removed) == [f"♪ There is no moody phrase #{phrase_id} here."]
    assert len(await bot.moody.for_stage(GUILD_ID, Stage.TEEN)) == 1


@pytest.mark.parametrize(
    ("phrase", "year", "refusal"),
    [
        ("x" * (MOODY_PHRASE_MAX + 1), 1999, "♪ The phrase can be at most 300"),
        ("   ", 1999, "♪ The phrase can't be empty."),
        ("Phrase One", MOODY_YEAR_MAX + 1, "♪ The year must be from"),
    ],
)
async def test_a_bad_phrase_is_refused_and_not_saved(
    bot: app.WispBot, server: FakeServer, phrase: str, year: int, refusal: str
) -> None:
    added = await run_add(
        bot, server, make_member(STAFF_ID, manage_guild=True), phrase, year
    )

    (answer,) = private(added)
    assert answer.startswith(refusal)
    assert await bot.moody.for_stage(GUILD_ID, Stage.TEEN) == []


def test_a_long_list_is_split_under_the_message_limit() -> None:
    phrases = [
        Phrase(index, "teen", "p" * 300, f"Artist {index}", "Song A", 1999)
        for index in range(30)
    ]

    messages = list_messages(Stage.TEEN, phrases)

    assert len(messages) > 1
    assert all(text_length(text) <= MESSAGE_LIMIT for text in messages)
    lines = "\n".join(messages).splitlines()
    assert lines[0] == "♪ Moody phrases for Teen"
    assert [line.split(" ・ ")[0] for line in lines[1:]] == [
        f"#{index}" for index in range(30)
    ]


# ---
# Drawing a round
# ---


async def test_no_round_without_three_different_songs(bot: app.WispBot) -> None:
    life = await lay(bot)
    for index in range(3):
        await bot.moody.add(
            GUILD_ID, Stage.TEEN, f"Phrase {index}", "Artist A", "Song A", 1999, 1, NOW
        )
    await bot.moody.add(
        GUILD_ID, Stage.TEEN, "Phrase B", "Artist B", "Song B", 1999, 1, NOW
    )

    assert await draw(bot, GUILD_ID, life, NOW, FixedRandom(0.0)) is None

    await bot.moody.add(
        GUILD_ID, Stage.TEEN, "Phrase C", "Artist C", "Song C", 1999, 1, NOW
    )
    assert await draw(bot, GUILD_ID, life, NOW, FixedRandom(0.0)) is not None


async def test_only_another_stages_phrases_draw_nothing(bot: app.WispBot) -> None:
    life = await lay(bot, Stage.ADULT)
    await add_songs(bot, Stage.TEEN)

    assert await draw(bot, GUILD_ID, life, NOW, FixedRandom(0.0)) is None


@pytest.mark.parametrize(
    ("roll", "drawn"),
    [(0.0, True), (MOODY_PHRASE_CHANCE - 0.01, True), (MOODY_PHRASE_CHANCE, False)],
)
async def test_a_round_needs_the_chance_roll(
    bot: app.WispBot, roll: float, drawn: bool
) -> None:
    life = await lay(bot)
    await add_songs(bot)

    got = await draw(bot, GUILD_ID, life, NOW, FixedRandom(roll))

    assert (got is not None) is drawn


async def test_a_happy_wisp_draws_nothing(bot: app.WispBot) -> None:
    life = await bot.lives.insert(GUILD_ID, make_life())
    await add_songs(bot)

    assert await draw(bot, GUILD_ID, life, NOW, FixedRandom(0.0)) is None


async def test_one_round_per_gap_and_never_the_same_phrase_twice(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    await add_songs(bot)

    first = await draw(bot, GUILD_ID, life, NOW, FixedRandom(0.0))
    assert first is not None
    soon = NOW + MOODY_PHRASE_GAP - timedelta(seconds=1)
    assert await draw(bot, GUILD_ID, life, soon, FixedRandom(0.0)) is None
    later = NOW + MOODY_PHRASE_GAP
    second = await draw(bot, GUILD_ID, life, later, FixedRandom(0.0))
    assert second is not None
    assert second.phrase.id != first.phrase.id
    stored = await bot.moody.last_round(GUILD_ID)
    assert stored is not None and stored.id == second.round_id
    assert stored.options == tuple(option.id for option in second.options)


# ---
# Wisp's answer
# ---


def to_wisp(server: FakeServer, text: str) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.id = 5000
    message.guild = server.guild
    message.author = make_member(MEMBER_ID)
    message.channel = server.house
    message.content = f"<@{WISP_ID}> {text}"
    message.mentions = [WISP]
    message.role_mentions = []
    message.reference = None
    message.attachments = []
    message.stickers = []
    message.embeds = []
    posted = MagicMock(spec=discord.Message)
    posted.id = POSTED_ID
    message.reply = AsyncMock(return_value=posted)
    return message


@pytest.fixture
def cog(bot: app.WispBot, ai: AsyncMock) -> Conversation:
    conversation = Conversation(bot)
    conversation.rng = FixedRandom(0.0)
    return conversation


def the_menu(message: MagicMock) -> MoodyMenu:
    view = message.reply.await_args.kwargs["view"]
    (menu,) = view.children
    assert isinstance(menu, MoodyMenu)
    return menu


@pytest.mark.parametrize(
    ("said", "posted"),
    [
        ("ugh, phrase one IS MINE!", "ugh, phrase one IS MINE!"),
        ("ugh, leave me be", f"ugh, leave me be\n{PHRASE_ONE}"),
    ],
)
async def test_a_moody_answer_carries_the_phrase_and_its_menu(
    cog: Conversation,
    bot: app.WispBot,
    ai: AsyncMock,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    said: str,
    posted: str,
) -> None:
    await lay(bot)
    ids = await add_songs(bot)
    monkeypatch.setattr(moody, "pick_phrase", lambda phrases, _last, _rng: phrases[0])
    ai.return_value = said
    message = to_wisp(server, "hi")

    await cog.on_message(message)

    (prompt,) = [call.args[0] for call in ai.await_args_list]
    assert "word for word, as your own grumpy outburst" in prompt.system
    assert PHRASE_ONE in prompt.system
    (text,) = message.reply.await_args.args
    assert text == posted
    assert message.reply.await_args.kwargs["allowed_mentions"].to_dict() == NO_PING
    menu = the_menu(message)
    stored = await bot.moody.last_round(GUILD_ID)
    assert stored is not None
    assert (stored.phrase_id, stored.message_id) == (ids[0], POSTED_ID)
    assert menu.item.custom_id == f"wisp:moody:{stored.id}"
    assert menu.item.placeholder == "♪ Name that song"
    assert [option.value for option in menu.item.options] == [
        str(option) for option in stored.options
    ]
    assert sorted(option.label for option in menu.item.options) == [
        "Artist A, Song A (1999)",
        "Artist B, Song B (2001)",
        "Artist C, Song C (1985)",
    ]


async def test_a_failed_ai_answer_drops_its_round(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, server: FakeServer
) -> None:
    await lay(bot)
    await add_songs(bot)
    ai.return_value = ""
    message = to_wisp(server, "hi")

    await cog.on_message(message)

    assert "view" not in message.reply.await_args.kwargs
    assert await bot.moody.last_round(GUILD_ID) is None


async def test_a_round_whose_answer_never_went_out_is_dropped(
    cog: Conversation,
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await lay(bot)
    await add_songs(bot)
    broken = AsyncMock(side_effect=pymysql.err.OperationalError(2003, "down"))
    monkeypatch.setattr("cogs.conversation._story", broken)

    with pytest.raises(pymysql.err.OperationalError):
        await cog.on_message(to_wisp(server, "hi"))

    broken.assert_awaited_once()
    assert await bot.moody.last_round(GUILD_ID) is None


async def test_a_refused_answer_drops_its_round(bot: app.WispBot) -> None:
    life = await lay(bot)
    await add_songs(bot)
    refused = discord.HTTPException(MagicMock(status=400), "refused")

    async def send(_text: str, _view: discord.ui.View | None) -> discord.Message:
        raise refused

    with pytest.raises(discord.HTTPException):
        async with moody_round(bot, GUILD_ID, life, NOW, FixedRandom(0.0)) as drawn:
            assert drawn is not None
            await post(bot, drawn, "grr", send)

    assert await bot.moody.last_round(GUILD_ID) is None


async def test_a_posted_round_is_kept(bot: app.WispBot) -> None:
    life = await lay(bot)
    await add_songs(bot)
    posted = MagicMock(spec=discord.Message)
    posted.id = POSTED_ID

    async def send(_text: str, _view: discord.ui.View | None) -> discord.Message:
        return posted

    async with moody_round(bot, GUILD_ID, life, NOW, FixedRandom(0.0)) as drawn:
        await post(bot, drawn, "grr", send)

    stored = await bot.moody.last_round(GUILD_ID)
    assert stored is not None and stored.message_id == POSTED_ID


async def test_a_happy_answer_has_no_phrase(
    cog: Conversation, bot: app.WispBot, ai: AsyncMock, server: FakeServer
) -> None:
    await bot.lives.insert(GUILD_ID, make_life())
    await add_songs(bot)
    message = to_wisp(server, "hi")

    await cog.on_message(message)

    assert message.reply.await_args.args == ("hmph",)
    assert "view" not in message.reply.await_args.kwargs
    (prompt,) = [call.args[0] for call in ai.await_args_list]
    assert "grumpy outburst" not in prompt.system


# ---
# Guessing
# ---


async def open_round(bot: app.WispBot) -> tuple[int, int, int]:
    """A round on the first song; its id, the answer and a wrong option."""
    ids = await add_songs(bot)
    round_id = await bot.moody.open_round(GUILD_ID, ids[0], ids, NOW)
    await bot.moody.set_message(round_id, POSTED_ID)
    return round_id, ids[0], ids[1]


async def guess(
    bot: app.WispBot, server: FakeServer, round_id: int, pick: int, user_id: int
) -> MagicMock:
    interaction = slash(bot, server, make_member(user_id))
    interaction.message = MagicMock(spec=discord.Message)
    interaction.message.content = "grr\nPhrase One is mine"
    menu = MoodyMenu(round_id)
    menu.item._values = [str(pick)]
    await menu.callback(interaction)
    return interaction


async def balance(bot: app.WispBot, user_id: int) -> int:
    return (await bot.players.get(GUILD_ID, user_id)).balance


async def test_a_wrong_guess_is_the_members_only_one(
    bot: app.WispBot, server: FakeServer
) -> None:
    round_id, answer, wrong = await open_round(bot)

    first = await guess(bot, server, round_id, wrong, MEMBER_ID)
    second = await guess(bot, server, round_id, answer, MEMBER_ID)

    assert private(first) == ["♪ Nope, not that one."]
    assert private(second) == ["♪ You already took your guess."]
    first.edit_original_response.assert_not_awaited()
    second.edit_original_response.assert_not_awaited()
    assert await balance(bot, MEMBER_ID) == 0


async def test_the_first_right_guess_wins_and_pays_once(
    bot: app.WispBot, server: FakeServer
) -> None:
    round_id, answer, _wrong = await open_round(bot)

    won = await guess(bot, server, round_id, answer, MEMBER_ID)
    late = await guess(bot, server, round_id, answer, SECOND_ID)

    assert private(won) == [f"♪ That's it! +{MOODY_PHRASE_REWARD} wisp coins"]
    assert private(late) == ["♪ Too late, this one's done."]
    assert await balance(bot, MEMBER_ID) == MOODY_PHRASE_REWARD
    assert await balance(bot, SECOND_ID) == 0
    won.response.defer.assert_awaited_once_with()
    kwargs = won.edit_original_response.await_args.kwargs
    assert kwargs["content"] == (
        f"grr\nPhrase One is mine\n♪ <@{MEMBER_ID}> named it: Artist A, Song A (1999)"
    )
    assert kwargs["allowed_mentions"].to_dict() == {
        "parse": [],
        "users": [MEMBER_ID],
    }
    (menu,) = kwargs["view"].children
    assert isinstance(menu, MoodyMenu) and menu.item.disabled
    assert len(menu.item.options) == 3
    stored = await bot.moody.get_round(GUILD_ID, round_id)
    assert stored is not None and stored.winner_id == MEMBER_ID


async def test_a_round_past_its_time_is_done(
    bot: app.WispBot, server: FakeServer, clock: list[datetime]
) -> None:
    round_id, answer, _wrong = await open_round(bot)
    clock[0] = NOW + MOODY_ROUND_FOR + timedelta(seconds=1)

    late = await guess(bot, server, round_id, answer, MEMBER_ID)

    assert private(late) == ["♪ Too late, this one's done."]
    assert await balance(bot, MEMBER_ID) == 0


async def test_a_round_from_another_server_is_done(bot: app.WispBot) -> None:
    round_id, answer, _wrong = await open_round(bot)
    await bot.players.activate(OTHER_GUILD_ID, MEMBER_ID, NOW)

    late = await guess(bot, FakeServer(OTHER_GUILD_ID), round_id, answer, MEMBER_ID)

    assert private(late) == ["♪ Too late, this one's done."]


async def test_a_member_who_never_opened_the_board_is_refused(
    bot: app.WispBot, server: FakeServer
) -> None:
    round_id, answer, _wrong = await open_round(bot)

    refused = await guess(bot, server, round_id, answer, STRANGER_ID)

    assert private(refused) == [
        "♪ Open /wisp board first so Wisp can give you a storage locker."
    ]
    assert await bot.moody.take_guess(round_id, STRANGER_ID) is True
    stored = await bot.moody.get_round(GUILD_ID, round_id)
    assert stored is not None and stored.winner_id is None


async def test_the_menu_is_registered_to_survive_restarts(bot: app.WispBot) -> None:
    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]

    await moody.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(MoodyMenu)
