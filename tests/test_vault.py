"""Tests for the ViiBR Vault card: the leaderboard, version lines and its buttons.

Discord objects are fakes; the repositories are the real ones.
"""

import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs import groups, vault
from cogs.lunchbox import LunchboxButton, ShopButton
from cogs.vault import refresh_vault, render_leaderboard, version_line
from db.activity import ActivityRepo
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp.life import Life, Phase, new_egg
from wisp.links import Track, TrackKind
from wisp.rules import Stage

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
ERRORS_ID = 40
VAULT_ID = 61
VAULT_MESSAGE_ID = 778
FIRST_USER = 1
SECOND_USER = 2
LONG_ID = 10**17
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)
SEPARATOR = "・♪ ────────・──────── ♪・"
INTRO = (
    "Snacks and the leaderboard. " "Shop or open your lunchbox with the buttons below."
)

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, an errors channel and the Vault thread."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.errors = MagicMock(spec=discord.TextChannel)
        self.errors.send = AsyncMock()
        self.vault_edit: Any = AsyncMock()
        self.vault = MagicMock(spec=discord.Thread)
        self.vault.id = VAULT_ID
        self.vault.parent_id = FORUM_ID
        self.vault.archived = False
        self.vault.get_partial_message.return_value = MagicMock(
            spec=discord.PartialMessage, edit=self.vault_edit
        )
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        channels: dict[int, MagicMock] = {HOUSE_ID: self.house, ERRORS_ID: self.errors}
        self.guild.get_channel_or_thread.side_effect = channels.get

    async def fetch_channel(self, channel_id: int) -> MagicMock:
        if channel_id != VAULT_ID:
            raise discord.NotFound(MagicMock(status=404), "Unknown Channel")
        return self.vault


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
    monkeypatch.setattr(wisp_bot, "fetch_channel", server.fetch_channel)
    yield wisp_bot


async def configure(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID,
        house_channel_id=HOUSE_ID,
        studio_forum_id=FORUM_ID,
        error_channel_id=ERRORS_ID,
        vault_thread_id=VAULT_ID,
        vault_message_id=VAULT_MESSAGE_ID,
    )


def make_interaction(bot: app.WispBot, user_id: int = FIRST_USER) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def run(command: Any, *args: Any) -> None:
    await command.callback(*args)


def followups(interaction: MagicMock) -> list[str]:
    """Texts sent as ephemeral follow-ups that cannot ping anyone."""
    sent = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == (
            discord.AllowedMentions.none().to_dict()
        )
        sent.append(call.args[0])
    return sent


def make_life(
    version: int,
    phase: Phase,
    *,
    hatched_ago: timedelta | None = None,
    lived: timedelta | None = None,
    peak: Stage = Stage.BABY,
    hatched_by: int | None = None,
    from_coal: bool = False,
) -> Life:
    life = new_egg(version, NOW - timedelta(days=90))
    life.phase = phase
    life.peak_stage = peak
    life.stage = peak if phase is Phase.ALIVE else Stage.EGG
    life.hatched_by = hatched_by
    life.from_coal = from_coal
    life.care = 50.0
    if hatched_ago is not None:
        life.hatched_at = NOW - hatched_ago
        if lived is not None:
            life.ended_at = life.hatched_at + lived
    return life


async def lay(bot: app.WispBot) -> Life:
    life = make_life(1, Phase.ALIVE, hatched_ago=timedelta(hours=1))
    life.hatched_at = discord.utils.utcnow() - timedelta(hours=1)
    return await bot.lives.insert(GUILD_ID, life)


async def feed_points(
    bot: app.WispBot, life: Life, user_id: int, points: int, key: str
) -> None:
    assert life.id is not None
    track = Track(TrackKind.SUNO, key, f"https://suno.com/song/{key}")
    await bot.activity_log.record_feed(
        GUILD_ID, life.id, user_id, track, points, 1, NOW
    )
    await bot.players.add_points(GUILD_ID, user_id, points)


# ---
# Activation and the board command
# ---


async def test_board_activates_once(bot: app.WispBot) -> None:
    await lay(bot)

    first = make_interaction(bot)
    await run(vault.wisp_board, first)
    activated = (await bot.players.get(GUILD_ID, FIRST_USER)).activated_at
    assert activated is not None
    first.response.defer.assert_awaited_once_with(ephemeral=True)
    radar, board = followups(first)
    assert "radar" in radar
    assert board.startswith("♪ The ViiBR Vault")

    second = make_interaction(bot)
    await run(vault.wisp_board, second)
    (board_only,) = followups(second)
    assert board_only.startswith("♪ The ViiBR Vault")
    assert (await bot.players.get(GUILD_ID, FIRST_USER)).activated_at == activated


async def test_board_puts_the_buttons_on_the_leaderboard_only(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    interaction = make_interaction(bot)

    await run(vault.wisp_board, interaction)

    radar_call, board_call = interaction.followup.send.await_args_list
    assert "view" not in radar_call.kwargs
    view = board_call.kwargs["view"]
    shop, lunchbox = view.children
    assert isinstance(shop, ShopButton)
    assert isinstance(lunchbox, LunchboxButton)


async def test_board_works_before_any_life_exists(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)

    await run(vault.wisp_board, interaction)

    assert "Nobody" in followups(interaction)[-1]


# ---
# Version lines
# ---


@pytest.mark.parametrize(
    ("life", "expected"),
    [
        pytest.param(make_life(1, Phase.EGG), "v1 ・ still an egg", id="egg"),
        pytest.param(
            make_life(1, Phase.EGG, from_coal=True),
            "v1 ・ still an egg ・ from coal",
            id="coal-egg",
        ),
        pytest.param(make_life(1, Phase.HATCHING), "v1 ・ hatching now", id="hatching"),
        pytest.param(
            make_life(
                1, Phase.ALIVE, hatched_ago=timedelta(days=12, hours=1), peak=Stage.TEEN
            ),
            "v1 ・ going strong ・ 12 days ・ Teen",
            id="alive",
        ),
        pytest.param(
            make_life(
                1, Phase.ALIVE, hatched_ago=timedelta(days=1), peak=Stage.OLD_FOGEY
            ),
            "v1 ・ going strong ・ 1 day ・ Old Fogey",
            id="alive-old-fogey",
        ),
        pytest.param(
            make_life(
                1,
                Phase.PASSED,
                hatched_ago=timedelta(days=60),
                lived=timedelta(days=45, hours=2),
                peak=Stage.OLD_FOGEY,
                hatched_by=SECOND_USER,
            ),
            "v1 ・ lived a full life ・ 45 days ・ peak Old Fogey"
            f" ・ hatched by <@{SECOND_USER}>",
            id="passed",
        ),
        pytest.param(
            make_life(
                1,
                Phase.PASSED,
                hatched_ago=timedelta(days=60),
                lived=timedelta(days=45),
                peak=Stage.OLD_FOGEY,
            ),
            "v1 ・ lived a full life ・ 45 days ・ peak Old Fogey",
            id="passed-no-hatcher",
        ),
        pytest.param(
            make_life(
                1,
                Phase.DEAD,
                hatched_ago=timedelta(days=40),
                lived=timedelta(days=18, hours=3),
                peak=Stage.ROCKSTAR,
                hatched_by=SECOND_USER,
            ),
            "v1 ・ went out after 18 days ・ peak Rockstar"
            f" ・ hatched by <@{SECOND_USER}>",
            id="dead",
        ),
        pytest.param(
            make_life(
                1,
                Phase.DEAD,
                hatched_ago=timedelta(days=5),
                lived=timedelta(days=1),
                peak=Stage.BABY,
            ),
            "v1 ・ went out after 1 day ・ peak Baby",
            id="dead-no-hatcher",
        ),
        pytest.param(make_life(1, Phase.COLD), "v1 ・ never hatched", id="cold"),
    ],
)
def test_version_lines(life: Life, expected: str) -> None:
    assert version_line(life, NOW) == expected


async def test_leaderboard_lists_versions_newest_first(bot: app.WispBot) -> None:
    await bot.lives.insert(
        GUILD_ID,
        make_life(
            1,
            Phase.DEAD,
            hatched_ago=timedelta(days=40),
            lived=timedelta(days=18, hours=3),
            peak=Stage.TEEN,
            hatched_by=SECOND_USER,
        ),
    )
    await bot.lives.insert(GUILD_ID, make_life(2, Phase.COLD))
    await bot.lives.insert(
        GUILD_ID,
        make_life(3, Phase.ALIVE, hatched_ago=timedelta(days=12, hours=1)),
    )

    text = await render_leaderboard(bot, GUILD_ID, NOW)

    assert text.split("\n")[-3:] == [
        "v3 ・ going strong ・ 12 days ・ Baby",
        "v2 ・ never hatched",
        f"v1 ・ went out after 18 days ・ peak Teen ・ hatched by <@{SECOND_USER}>",
    ]


# ---
# Leaderboard
# ---


async def test_leaderboard_heading_is_the_vault(bot: app.WispBot) -> None:
    text = await render_leaderboard(bot, GUILD_ID, NOW)

    assert text.splitlines()[:3] == ["♪ The ViiBR Vault", INTRO, SEPARATOR]


async def test_leaderboard_ranks_this_life_and_all_time(bot: app.WispBot) -> None:
    life = await bot.lives.insert(
        GUILD_ID, make_life(2, Phase.ALIVE, hatched_ago=timedelta(days=1))
    )
    await feed_points(bot, life, FIRST_USER, 1, "aaaa")
    await feed_points(bot, life, SECOND_USER, 5, "bbbb")
    await bot.players.add_points(GUILD_ID, FIRST_USER, 200)
    await bot.players.add_bond(GUILD_ID, FIRST_USER, 150)

    text = await render_leaderboard(bot, GUILD_ID, NOW)

    this_life, all_time, _rhymes, _versions = text.split(SEPARATOR + "\n")[1:]
    assert this_life.splitlines() == [
        "This life",
        f"・1. <@{SECOND_USER}> ・ 5 points",
        f"・2. <@{FIRST_USER}> ・ 1 point",
    ]
    assert all_time.splitlines() == [
        "All time",
        f"・1. <@{FIRST_USER}> ・ 201 points ・ Friend",
        f"・2. <@{SECOND_USER}> ・ 5 points ・ New face",
    ]


async def test_leaderboard_shows_top_rhyme_scores(bot: app.WispBot) -> None:
    await lay(bot)
    for offset, best in enumerate([4, 12, 7, 9, 2, 15]):
        await bot.players.record_rhyme_score(GUILD_ID, 10 + offset, best)
    await bot.players.record_rhyme_score(GUILD_ID, FIRST_USER, 1)

    text = await render_leaderboard(bot, GUILD_ID, NOW)

    _this_life, _all_time, rhymes, versions = text.split(SEPARATOR + "\n")[1:]
    assert rhymes.splitlines() == [
        "Rhyme Duel",
        "・1. <@15> ・ 15 points",
        "・2. <@11> ・ 12 points",
        "・3. <@13> ・ 9 points",
        "・4. <@12> ・ 7 points",
        "・5. <@10> ・ 4 points",
    ]
    assert versions.startswith("Versions\nv1 ・ going strong")


async def test_leaderboard_is_empty_but_tidy_for_a_new_server(
    bot: app.WispBot,
) -> None:
    text = await render_leaderboard(bot, GUILD_ID, NOW)

    assert text == "\n".join(
        [
            "♪ The ViiBR Vault",
            INTRO,
            SEPARATOR,
            "This life",
            "・Nobody has fed him yet",
            SEPARATOR,
            "All time",
            "・Nobody has points yet",
            SEPARATOR,
            "Rhyme Duel",
            "・Nobody has dueled him yet",
            SEPARATOR,
            "Versions",
            "・None yet",
        ]
    )


async def test_leaderboard_uses_bot_style(bot: app.WispBot) -> None:
    life = await lay(bot)
    await feed_points(bot, life, FIRST_USER, 3, "cccc")

    text = await render_leaderboard(bot, GUILD_ID, NOW)

    assert "・" in text
    assert "♪" in text
    assert SEPARATOR in text
    assert not re.search("[🀀-🿿☀-♩♫-➿️]", text)


async def test_leaderboard_fits_one_message(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = await bot.lives.insert(
        GUILD_ID, make_life(61, Phase.ALIVE, hatched_ago=timedelta(days=3))
    )
    for offset in range(10):
        member = LONG_ID + offset
        await feed_points(bot, life, member, 100 + offset, f"track{offset}")
        await bot.players.add_bond(GUILD_ID, member, 400)
        await bot.players.record_rhyme_score(GUILD_ID, member, 1000 + offset)
    history = [life] + [
        make_life(
            version,
            Phase.DEAD,
            hatched_ago=timedelta(days=90),
            lived=timedelta(days=18),
            peak=Stage.ROCKSTAR,
            hatched_by=LONG_ID,
        )
        for version in range(60, 0, -1)
    ]
    monkeypatch.setattr(bot.lives, "history", AsyncMock(return_value=history))

    text = await render_leaderboard(bot, GUILD_ID, NOW)

    assert len(text) <= 2000
    lines = text.splitlines()
    assert sum(line.startswith("・") and ". <@" in line for line in lines) == 25
    version_lines = [line for line in lines if re.match(r"v\d+ ・", line)]
    assert 0 < len(version_lines) < len(history)
    assert version_lines[0].startswith("v61 ・ going strong")
    assert version_lines[1].startswith("v60 ・")
    expected = [f"v{n} ・" for n in range(61, 61 - len(version_lines), -1)]
    assert [line[: len(prefix)] for line, prefix in zip(version_lines, expected)] == (
        expected
    )
    assert all(line.endswith(f"hatched by <@{LONG_ID}>") for line in version_lines[1:])


# ---
# The card
# ---


async def test_refresh_vault_edits_the_pinned_message(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)

    await refresh_vault(bot, GUILD_ID)

    server.vault.get_partial_message.assert_called_once_with(VAULT_MESSAGE_ID)
    kwargs = server.vault_edit.await_args.kwargs
    assert kwargs["content"].startswith("♪ The ViiBR Vault")
    assert "v1 ・ going strong" in kwargs["content"]
    assert kwargs["allowed_mentions"].to_dict() == (
        discord.AllowedMentions.none().to_dict()
    )
    server.errors.send.assert_not_awaited()


async def test_refresh_vault_puts_shop_and_lunchbox_buttons_on_the_card(
    bot: app.WispBot, server: FakeServer
) -> None:
    await configure(bot)
    await lay(bot)

    await refresh_vault(bot, GUILD_ID)

    view = server.vault_edit.await_args.kwargs["view"]
    assert view.timeout is None
    shop, lunchbox = view.children
    assert isinstance(shop, ShopButton)
    assert isinstance(lunchbox, LunchboxButton)


def test_board_command_hangs_off_the_wisp_group() -> None:
    assert groups.wisp.get_command("board") is vault.wisp_board
    assert isinstance(vault.wisp_board, app_commands.Command)


def test_vault_loads_right_after_the_lunchbox() -> None:
    assert app.EXTENSIONS.index("cogs.vault") == (
        app.EXTENSIONS.index("cogs.lunchbox") + 1
    )
