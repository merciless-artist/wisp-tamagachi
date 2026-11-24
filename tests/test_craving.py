"""Tests for Wisp's Craving: the daily snack guess in the member's room.

Discord objects are fakes; the repositories are the real ones.
"""

import random
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs import craving, groups, rhyme_duel
from cogs.craving import CravingButton, GuessMenu, end_idle_cravings
from cogs.games import craving_live
from db.activity import ActivityRepo, InteractionKind
from db.cravings import CravingRepo
from db.database import Database
from db.lives import LifeRepo
from db.notes import NoteRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from wisp.craving import (
    Verdict,
    guesses_left,
    hint_for,
    is_idle,
    judge,
    pick_craving,
    snacks_left,
)
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import CRAVING_HINTS, LINES, Moment
from wisp.rules import (
    CRAVING_GUESSES,
    CRAVING_TIMEOUT,
    DAILY_CASUAL_BOND_CAP,
    PAID_SNACKS,
    PLAY_POINTS,
    SNACK_BY_KEY,
    WELLBEING_PER_PLAY,
    Stage,
)
from wisp.text import daily_reset

GUILD_ID = 100
HOUSE_ID = 20
THREAD_ID = 70
USER_ID = 1
OTHER_USER_ID = 2
QUALIFYING_ROLE = 7
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)
DAY = NOW.date()
CRAVED = "jellywave"
NO_PING = discord.AllowedMentions.none().to_dict()
WELCOME = "♪ This is your storage locker with Wisp"
ROOM_BUSY = (
    "♪ You already have a game going in your storage locker. Finish that one first."
)
STARTED = f"♪ Your Craving is on in <#{THREAD_ID}>."

# ---
# Pure rules
# ---


def test_judge_right_wrong_and_out() -> None:
    assert judge("jellywave", (), "jellywave") is Verdict.RIGHT
    assert judge("jellywave", (), "cheese") is Verdict.WRONG
    assert judge("jellywave", ("cheese",), "pickles") is Verdict.WRONG
    assert judge("jellywave", ("cheese", "pickles"), "spicywave") is Verdict.OUT
    assert judge("jellywave", ("cheese", "pickles"), "jellywave") is Verdict.RIGHT


def test_hints_get_clearer_with_each_wrong_guess() -> None:
    hints = CRAVING_HINTS[CRAVED]
    assert [hint_for(CRAVED, wrong) for wrong in range(4)] == [
        hints[0],
        hints[1],
        hints[2],
        hints[2],
    ]


def test_never_craves_the_free_snack() -> None:
    rng = random.Random(7)
    picks = [pick_craving(rng) for _ in range(200)]
    assert all(snack.cost > 0 for snack in picks)
    assert {snack.key for snack in picks} == {snack.key for snack in PAID_SNACKS}


def test_wrong_guesses_leave_the_menu_in_order() -> None:
    left = snacks_left(("cheese", "cloudwave"))
    assert [snack.key for snack in left] == [
        snack.key for snack in PAID_SNACKS if snack.key not in ("cheese", "cloudwave")
    ]
    assert guesses_left(("cheese",)) == CRAVING_GUESSES - 1


def test_a_round_is_idle_only_past_the_timeout() -> None:
    assert not is_idle(NOW, NOW + CRAVING_TIMEOUT)
    assert is_idle(NOW, NOW + CRAVING_TIMEOUT + timedelta(seconds=1))


# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, which makes the member's room once."""

    def __init__(self) -> None:
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.thread = MagicMock(spec=discord.Thread)
        self.thread.id = THREAD_ID
        self.thread.parent_id = HOUSE_ID
        self.thread.archived = False
        self.thread.guild = self.guild
        self.thread.mention = f"<#{THREAD_ID}>"
        self.thread.send = AsyncMock()
        self.thread.add_user = AsyncMock()
        self.made = False
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.id = HOUSE_ID
        self.house.create_thread = AsyncMock(side_effect=self._create_thread)
        self.house.send = AsyncMock()
        self.member = member_of(USER_ID)
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house}
        self.guild.get_channel_or_thread.side_effect = channels.get
        self.guild.get_member.side_effect = {USER_ID: self.member}.get

    def _create_thread(self, **_kwargs: Any) -> MagicMock:
        self.made = True
        return self.thread

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if not self.made or channel_id != THREAD_ID:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.thread

    def sends(self) -> list[Any]:
        """Every post in the room but its welcome, none of them able to ping."""
        sent = []
        for call in self.thread.send.await_args_list:
            if str(call.args[0]).startswith(WELCOME):
                continue
            assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
            sent.append(call)
        return sent

    def posts(self) -> list[str]:
        return [str(call.args[0]) for call in self.sends()]

    def last_menu(self) -> GuessMenu:
        """The menu of the latest round post."""
        menus = [call.kwargs["view"] for call in self.sends() if "view" in call.kwargs]
        (menu,) = menus[-1].children
        assert isinstance(menu, GuessMenu)
        return menu


def member_of(user_id: int, roles: tuple[int, ...] = (QUALIFYING_ROLE,)) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.display_name = f"Member{user_id}"
    member.mention = f"<@{user_id}>"
    member.roles = [MagicMock(spec=discord.Role, id=role_id) for role_id in roles]
    return member


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
    wisp_bot.notes = NoteRepo(db)
    wisp_bot.cravings = CravingRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    for user_id in (USER_ID, OTHER_USER_ID):
        await bot.players.activate(GUILD_ID, user_id, NOW - timedelta(days=1))


@pytest.fixture(autouse=True)
def clock(monkeypatch: pytest.MonkeyPatch) -> list[datetime]:
    """Wisp's clock: set `clock[0]` to move time."""
    now = [NOW]
    monkeypatch.setattr(discord.utils, "utcnow", lambda: now[0])
    return now


@pytest.fixture(autouse=True)
def craves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(craving, "pick_craving", lambda _rng: SNACK_BY_KEY[CRAVED])


@pytest.fixture(autouse=True)
def pack(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    shown = AsyncMock()
    monkeypatch.setattr(craving, "show_pack_in_room", shown)
    return shown


def make_interaction(
    bot: app.WispBot, server: FakeServer, member: MagicMock | None = None
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = server.thread
    interaction.user = member or server.member
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.is_done = MagicMock(return_value=True)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    interaction.edit_original_response = AsyncMock()
    return interaction


def replies(interaction: MagicMock) -> list[str]:
    """The private replies the member got, none of them able to ping."""
    sent = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        sent.append(str(call.args[0]))
    return sent


async def cravings_counted(db: Database) -> int:
    """How many Craving rounds were logged as interactions."""
    rows = await db.fetchall(
        f"SELECT kind FROM {db.t('interactions')} WHERE kind = %s",
        (InteractionKind.CRAVING.value,),
    )
    return len(rows)


async def lay(bot: app.WispBot, phase: Phase = Phase.ALIVE) -> Life:
    life = new_egg(1, NOW - timedelta(days=1))
    life.phase = phase
    life.health = 50.0
    life.wellbeing = 40.0
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = NOW - timedelta(hours=1)
    return await bot.lives.insert(GUILD_ID, life)


async def start(bot: app.WispBot, server: FakeServer) -> MagicMock:
    interaction = make_interaction(bot, server)
    command: Any = craving.play_craving
    await command.callback(interaction)
    return interaction


async def guess(
    bot: app.WispBot,
    server: FakeServer,
    snack: str,
    member: MagicMock | None = None,
) -> MagicMock:
    """Pick `snack` from the latest menu in the room."""
    menu = server.last_menu()
    menu.item._values = [snack]
    interaction = make_interaction(bot, server, member)
    if await menu.interaction_check(interaction):
        await menu.callback(interaction)
    return interaction


def lines_for(moment: Moment, **fields: str) -> set[str]:
    return {
        line.format(**fields)
        for feeling in Mood
        for line in LINES.get((moment, feeling), ())
    }


def round_text(line: str, wrong: int) -> str:
    return (
        f"{line}\n・Hint: {CRAVING_HINTS[CRAVED][wrong]}\n"
        f"・Guesses left: {CRAVING_GUESSES - wrong}"
    )


def option_keys(menu: GuessMenu) -> list[str]:
    return [option.value for option in menu.item.options]


# ---
# Playing a round
# ---


async def test_a_round_starts_in_the_room_with_a_hint_and_a_menu(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    interaction = await start(bot, server)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    assert replies(interaction) == [STARTED]
    server.house.create_thread.assert_awaited_once()
    (post,) = server.posts()
    line, _hint, _left = post.splitlines()
    assert line in lines_for(Moment.CRAVING_START, name="Member1")
    assert post == round_text(line, 0)
    menu = server.last_menu()
    assert menu.item.custom_id == f"wisp:craving:{USER_ID}:{DAY.isoformat()}"
    assert option_keys(menu) == [snack.key for snack in PAID_SNACKS]
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None
    assert (stored.snack, stored.guesses, stored.ended_at) == (CRAVED, (), None)


async def test_a_right_guess_wins_the_snack_free_and_marked_won(
    bot: app.WispBot, server: FakeServer, pack: AsyncMock
) -> None:
    await lay(bot)
    await start(bot, server)
    balance = (await bot.players.get(GUILD_ID, USER_ID)).balance

    pressed = await guess(bot, server, CRAVED)

    pressed.edit_original_response.assert_awaited_once_with(view=None)
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {CRAVED: 1}
    assert await bot.activity_log.take_won_snack(GUILD_ID, USER_ID, CRAVED) is True
    line = server.posts()[-1].splitlines()[0]
    assert line in lines_for(Moment.CRAVING_WON, name="Member1", snack="Jelly Wave")
    pack.assert_awaited_once_with(bot, server.guild, server.member, where=server.thread)
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.won and stored.ended_at == NOW
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == balance + PLAY_POINTS


async def test_a_wrong_guess_leaves_the_menu_and_gives_the_next_hint(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)

    pressed = await guess(bot, server, "cheese")

    pressed.edit_original_response.assert_awaited_once_with(view=None)
    post = server.posts()[-1]
    line = post.splitlines()[0]
    assert line in lines_for(Moment.CRAVING_NOPE, snack="Cheese")
    assert post == round_text(line, 1)
    assert option_keys(server.last_menu()) == [
        snack.key for snack in PAID_SNACKS if snack.key != "cheese"
    ]
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.guesses == ("cheese",)


async def test_three_wrong_guesses_lose_and_name_the_snack(
    bot: app.WispBot, server: FakeServer, pack: AsyncMock
) -> None:
    await lay(bot)
    await start(bot, server)

    for wrong in ("cheese", "pickles", "spicywave"):
        await guess(bot, server, wrong)

    line = server.posts()[-1].splitlines()[0]
    assert line in lines_for(Moment.CRAVING_LOST, snack="Jelly Wave")
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None
    assert stored.guesses == ("cheese", "pickles", "spicywave")
    assert stored.ended_at == NOW and not stored.won
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}
    pack.assert_not_awaited()


async def test_one_round_a_day(
    bot: app.WispBot, server: FakeServer, clock: list[datetime]
) -> None:
    await lay(bot)
    await start(bot, server)
    await guess(bot, server, CRAVED)
    posted = len(server.posts())

    again = await start(bot, server)

    assert replies(again) == [
        f"♪ You've already had today's Craving. Next one {daily_reset(NOW)}."
    ]
    assert len(server.posts()) == posted
    clock[0] = NOW + timedelta(days=1)
    tomorrow = await start(bot, server)
    assert replies(tomorrow) == [STARTED]


async def test_starting_again_resumes_the_same_round(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    await start(bot, server)
    await guess(bot, server, "cheese")
    monkeypatch.setattr(craving, "pick_craving", lambda _rng: SNACK_BY_KEY["cheese"])

    again = await start(bot, server)

    assert replies(again) == [STARTED]
    assert server.posts()[-1] == round_text("♪ Your Craving is still on.", 1)
    assert "cheese" not in option_keys(server.last_menu())
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and (stored.snack, stored.guesses) == (
        CRAVED,
        ("cheese",),
    )
    server.house.create_thread.assert_awaited_once()


async def test_a_menu_rebuilt_after_a_restart_still_judges(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    custom_id = server.last_menu().item.custom_id
    match = GuessMenu.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert match is not None

    rebuilt = await GuessMenu.from_custom_id(
        make_interaction(bot, server), MagicMock(spec=discord.ui.Select), match
    )
    rebuilt.item._values = [CRAVED]
    await rebuilt.callback(make_interaction(bot, server))

    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.won


async def test_a_pick_from_an_old_menu_posts_the_round_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    first = server.last_menu()
    await guess(bot, server, "cheese")
    first.item._values = ["cheese"]

    await first.callback(make_interaction(bot, server))

    assert server.posts()[-1] == round_text("♪ Your Craving is still on.", 1)
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.guesses == ("cheese",)


async def test_a_pick_after_the_round_ended_says_it_is_over(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    first = server.last_menu()
    await guess(bot, server, CRAVED)
    first.item._values = ["cheese"]
    pressed = make_interaction(bot, server)

    await first.callback(pressed)

    assert replies(pressed) == ["♪ This Craving is over."]


async def test_only_the_rooms_owner_can_guess(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    posted = len(server.posts())
    stranger = member_of(OTHER_USER_ID)

    pressed = await guess(bot, server, CRAVED, member=stranger)

    pressed.response.send_message.assert_awaited_once_with(
        "♪ This is someone else's Craving.", ephemeral=True
    )
    pressed.edit_original_response.assert_not_awaited()
    assert len(server.posts()) == posted
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.ended_at is None and stored.guesses == ()


# ---
# Timing out
# ---


async def test_an_idle_round_times_out_as_a_loss(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    later = NOW + CRAVING_TIMEOUT + timedelta(seconds=1)

    await end_idle_cravings(bot, later)

    line = server.posts()[-1].splitlines()[0]
    assert line in lines_for(Moment.CRAVING_TIMED_OUT, snack="Jelly Wave")
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.ended_at == later and not stored.won
    assert await bot.notes.recent(GUILD_ID, USER_ID) == [
        "I was craving a Jelly Wave and they couldn't guess it"
    ]
    posted = len(server.posts())
    await end_idle_cravings(bot, later + CRAVING_TIMEOUT)
    assert len(server.posts()) == posted


async def test_a_round_still_in_time_is_left_open(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)

    await end_idle_cravings(bot, NOW + CRAVING_TIMEOUT)

    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.ended_at is None


async def test_an_idle_round_of_a_member_who_left_ends_quietly(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    await start(bot, server)
    posted = len(server.posts())
    server.guild.get_member.side_effect = None
    server.guild.get_member.return_value = None
    server.guild.fetch_member = AsyncMock(
        side_effect=discord.NotFound(MagicMock(status=404), "Unknown Member")
    )
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await end_idle_cravings(bot, NOW + timedelta(hours=1))

    assert len(server.posts()) == posted
    reported.assert_not_awaited()
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.ended_at is not None


@pytest.mark.parametrize(
    "refused",
    [
        discord.Forbidden(MagicMock(status=403), "Missing Access"),
        discord.NotFound(MagicMock(status=404), "Unknown Channel"),
    ],
)
async def test_an_idle_round_that_cannot_be_posted_is_reported(
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    refused: discord.HTTPException,
) -> None:
    await lay(bot)
    await start(bot, server)
    server.thread.send.side_effect = refused
    reported = AsyncMock()
    monkeypatch.setattr(bot, "report_error", reported)

    await end_idle_cravings(bot, NOW + timedelta(hours=1))

    reported.assert_awaited_once_with(server.guild, "ending an idle Craving", refused)


async def test_a_late_press_after_the_timeout_counts_as_a_loss(
    bot: app.WispBot, server: FakeServer, clock: list[datetime]
) -> None:
    await lay(bot)
    await start(bot, server)
    clock[0] = NOW + CRAVING_TIMEOUT + timedelta(seconds=1)

    await guess(bot, server, CRAVED)

    line = server.posts()[-1].splitlines()[0]
    assert line in lines_for(Moment.CRAVING_TIMED_OUT, snack="Jelly Wave")
    stored = await bot.cravings.today(GUILD_ID, USER_ID, NOW)
    assert stored is not None and stored.ended_at is not None and not stored.won
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {}


async def test_starting_after_an_idle_round_ends_it_and_refuses(
    bot: app.WispBot, server: FakeServer, clock: list[datetime]
) -> None:
    await lay(bot)
    await start(bot, server)
    clock[0] = NOW + timedelta(hours=1)

    again = await start(bot, server)

    line = server.posts()[-1].splitlines()[0]
    assert line in lines_for(Moment.CRAVING_TIMED_OUT, snack="Jelly Wave")
    assert replies(again) == [
        f"♪ You've already had today's Craving. Next one {daily_reset(clock[0])}."
    ]


# ---
# What a finished round gives
# ---


@pytest.mark.parametrize(
    ("picks", "note"),
    [
        ([CRAVED], "I was craving a Jelly Wave and they guessed it"),
        (
            ["cheese", "pickles", "spicywave"],
            "I was craving a Jelly Wave and they couldn't guess it",
        ),
    ],
)
async def test_every_finished_round_leaves_a_note_and_a_receipt(
    bot: app.WispBot,
    db: Database,
    server: FakeServer,
    picks: list[str],
    note: str,
) -> None:
    await lay(bot)
    await start(bot, server)

    for pick in picks:
        await guess(bot, server, pick)

    assert await bot.notes.recent(GUILD_ID, USER_ID) == [note]
    receipt = server.posts()[-1].splitlines()[-1]
    assert receipt.startswith("♪ Your Craving counted ・ Wellbeing ")
    assert f"Wellbeing +{WELLBEING_PER_PLAY}" in receipt
    assert " ・ bond +" in receipt
    assert receipt.endswith("+1 WC")
    life = await bot.lives.current(GUILD_ID)
    assert life is not None and life.wellbeing == 40.0 + WELLBEING_PER_PLAY
    assert await cravings_counted(db) == 1


async def test_a_round_past_the_bond_cap_says_the_bond_is_full(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.activity_log.record_interaction(
        GUILD_ID, life.id, USER_ID, InteractionKind.PLAY, DAILY_CASUAL_BOND_CAP, 0, NOW
    )
    await start(bot, server)

    await guess(bot, server, CRAVED)

    receipt = server.posts()[-1].splitlines()[-1]
    assert " ・ your bond with him is full for today ・ " in receipt
    assert f"Wellbeing +{WELLBEING_PER_PLAY}" in receipt


async def test_a_round_ending_while_frozen_does_not_count(
    bot: app.WispBot, db: Database, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    await bot.settings.update(GUILD_ID, frozen=True)

    await guess(bot, server, CRAVED)

    receipt = server.posts()[-1].splitlines()[-1]
    assert receipt.startswith("♪ This Craving didn't count toward his Wellbeing: ")
    assert await cravings_counted(db) == 0
    assert await bot.activity_log.inventory(GUILD_ID, USER_ID) == {CRAVED: 1}


# ---
# Refusals
# ---


@pytest.mark.parametrize("why", ["frozen", "napping", "banned", "no role", "dead"])
async def test_refused_while_frozen_napping_banned_or_unable_to_feed(
    bot: app.WispBot, server: FakeServer, why: str
) -> None:
    life = await lay(bot, Phase.DEAD if why == "dead" else Phase.ALIVE)
    if why == "frozen":
        await bot.settings.update(GUILD_ID, frozen=True)
    if why == "napping":
        life.nap_left = 1800.0
        await bot.lives.save(GUILD_ID, life)
    if why == "banned":
        await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)
    if why == "no role":
        server.member.roles = []

    interaction = await start(bot, server)

    (reply,) = replies(interaction)
    expected = {
        "frozen": "♪ Wisp is frozen right now",
        "napping": "♪ Wisp is napping until ",
        "banned": "♪ Wisp is not playing with you right now.",
        "no role": "♪ You can't play Wisp's Craving: you don't have a role",
        "dead": "♪ Wisp isn't alive right now, so cravings have to wait.",
    }[why]
    assert reply.startswith(expected)
    server.house.create_thread.assert_not_awaited()
    assert await bot.cravings.today(GUILD_ID, USER_ID, NOW) is None


async def test_a_room_game_already_running_is_refused(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    bot.room_games.add((GUILD_ID, USER_ID))

    interaction = await start(bot, server)

    assert replies(interaction) == [ROOM_BUSY]
    assert await bot.cravings.today(GUILD_ID, USER_ID, NOW) is None
    assert (GUILD_ID, USER_ID) in bot.room_games


async def test_a_duel_is_refused_while_a_craving_is_on(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    duel = make_interaction(bot, server)
    command: Any = rhyme_duel.play_rhyme

    await command.callback(duel)

    assert replies(duel) == [ROOM_BUSY]


async def test_an_idle_or_finished_craving_frees_the_room(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await start(bot, server)
    later = NOW + CRAVING_TIMEOUT + timedelta(seconds=1)

    assert await craving_live(bot, GUILD_ID, USER_ID, NOW) is True
    assert await craving_live(bot, GUILD_ID, USER_ID, later) is False
    await guess(bot, server, CRAVED)
    assert await craving_live(bot, GUILD_ID, USER_ID, NOW) is False


async def test_a_round_from_before_midnight_keeps_the_room_busy(
    bot: app.WispBot, server: FakeServer, clock: list[datetime]
) -> None:
    await lay(bot)
    clock[0] = NOW.replace(hour=23, minute=58)
    await start(bot, server)
    clock[0] += timedelta(minutes=3)
    duel = make_interaction(bot, server)
    command: Any = rhyme_duel.play_rhyme

    again = await start(bot, server)
    await command.callback(duel)

    assert replies(again) == [ROOM_BUSY]
    assert replies(duel) == [ROOM_BUSY]
    assert await bot.cravings.today(GUILD_ID, USER_ID, clock[0]) is None
    assert (GUILD_ID, USER_ID) not in bot.room_games


async def test_no_room_refuses_with_the_reason(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    await bot.settings.update(GUILD_ID, house_channel_id=None)
    monkeypatch.setattr(bot, "report_error", AsyncMock())

    interaction = await start(bot, server)

    assert replies(interaction) == [
        "♪ Wisp's House isn't set up, so he can't open your storage locker yet."
    ]
    assert await bot.cravings.today(GUILD_ID, USER_ID, NOW) is None
    assert (GUILD_ID, USER_ID) not in bot.room_games


# ---
# Wiring
# ---


async def test_the_craving_button_starts_a_round_like_the_command(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    interaction = make_interaction(bot, server)

    await CravingButton().callback(interaction)

    assert replies(interaction) == [STARTED]
    assert len(server.posts()) == 1


async def test_the_craving_button_survives_a_restart(
    bot: app.WispBot, server: FakeServer
) -> None:
    match = CravingButton.__discord_ui_compiled_template__.fullmatch(
        "wisp:play:craving"
    )
    assert match is not None

    restored = await CravingButton.from_custom_id(
        make_interaction(bot, server), MagicMock(spec=discord.ui.Button), match
    )

    assert isinstance(restored, CravingButton)
    assert restored.item.custom_id == "wisp:play:craving"


def test_the_guess_menu_id_names_the_member_and_day() -> None:
    menu = GuessMenu(USER_ID, date(2026, 11, 23))
    template = GuessMenu.__discord_ui_compiled_template__
    match = template.fullmatch(menu.item.custom_id)
    assert match is not None
    assert (match["user"], match["day"]) == (str(USER_ID), "2026-11-23")


async def test_the_craving_items_are_registered_at_startup(bot: app.WispBot) -> None:
    bot.add_dynamic_items = MagicMock()  # type: ignore[method-assign]

    await craving.setup(bot)

    bot.add_dynamic_items.assert_called_once_with(CravingButton, GuessMenu)


def test_craving_hangs_off_the_play_group() -> None:
    assert groups.play.get_command("craving") is craving.play_craving
    assert isinstance(craving.play_craving, app_commands.Command)
    assert craving.play_craving.description == "Guess the snack Wisp is craving."


def test_craving_is_a_loaded_extension() -> None:
    assert "cogs.craving" in app.EXTENSIONS
