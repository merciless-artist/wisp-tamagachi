"""Tests for the staff discipline commands.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import random
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

import app
from cogs import discipline, groups
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import Stage

GUILD_ID = 100
HOUSE_ID = 20
TRACKS_ID = 30
COMMAND_CHANNEL_ID = 40
STAFF_ID = 9
MEMBER_ID = 1
REASON = "posted a fake track link"
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House and the channel staff run commands in."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.here = MagicMock(spec=discord.TextChannel)
        self.here.id = COMMAND_CHANNEL_ID
        self.here.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.channels: dict[int, MagicMock] = {
            HOUSE_ID: self.house,
            COMMAND_CHANNEL_ID: self.here,
        }
        self.guild.get_channel_or_thread.side_effect = self.channels.get


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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, tracks_channel_id=TRACKS_ID
    )


@pytest.fixture(autouse=True)
def shame_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An ASSETS folder with no shame images, so tests never touch the real one."""
    monkeypatch.setattr(discipline, "ASSETS_DIR", tmp_path)
    return tmp_path / "shame"


def make_member(
    user_id: int = MEMBER_ID, display_name: str = "Member1", *, bot: bool = False
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.bot = bot
    member.display_name = display_name
    member.mention = f"<@{user_id}>"
    return member


def make_interaction(bot: app.WispBot, *, staff: bool = True) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = bot.get_guild(GUILD_ID)
    interaction.guild_id = GUILD_ID
    interaction.channel = interaction.guild.get_channel_or_thread(COMMAND_CHANNEL_ID)
    interaction.permissions = discord.Permissions(manage_guild=staff)
    interaction.user = make_member(STAFF_ID, "Staffer")
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False

    async def answer(*_args: Any, **_kwargs: Any) -> None:
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=answer)
    interaction.response.send_message = AsyncMock(side_effect=answer)
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def run(command: Any, *args: Any) -> None:
    await command.callback(*args)


def replies(interaction: MagicMock) -> list[str]:
    """Texts sent back to the staff member, all private and unable to ping."""
    sent = []
    calls = [
        *interaction.response.send_message.await_args_list,
        *interaction.followup.send.await_args_list,
    ]
    for call in calls:
        assert call.kwargs["ephemeral"] is True
        assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
        sent.append(call.args[0])
    return sent


async def lay(bot: app.WispBot) -> Life:
    life = new_egg(1, discord.utils.utcnow() - timedelta(days=1))
    life.phase = Phase.ALIVE
    life.stage = life.peak_stage = Stage.BABY
    life.care = 50.0
    life.hatched_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


async def punish(
    bot: app.WispBot, member: MagicMock | None = None, reason: str = REASON
) -> MagicMock:
    interaction = make_interaction(bot)
    await run(discipline.punish, interaction, member or make_member(), reason)
    return interaction


def banned_lines(name: str) -> set[str]:
    return {
        template.format(name=name)
        for mood in Mood
        for template in LINES[(Moment.BANNED, mood)]
    }


def house_text(server: FakeServer) -> str:
    server.house.send.assert_awaited_once()
    return str(server.house.send.await_args.args[0])


def staff_log(server: FakeServer) -> str:
    """The log line posted in the channel the command was run in."""
    server.here.send.assert_awaited_once()
    return str(server.here.send.await_args.args[0])


# ---
# Punish
# ---


async def test_ladder_one_day_week_forever(bot: app.WispBot) -> None:
    await lay(bot)
    for offense, length in enumerate([timedelta(days=1), timedelta(days=7), None], 1):
        before = discord.utils.utcnow()
        await punish(bot)
        after = discord.utils.utcnow()
        player = await bot.players.get(GUILD_ID, MEMBER_ID)
        assert player.offenses == offense
        if length is None:
            assert player.banned_forever is True
        else:
            assert player.banned_forever is False
            assert player.banned_until is not None
            assert (
                before + length - timedelta(seconds=1)
                <= player.banned_until
                <= after + length
            )
        assert player.is_banned(discord.utils.utcnow())


async def test_simultaneous_punishes_are_two_distinct_offenses(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await asyncio.gather(punish(bot), punish(bot))
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert player.offenses == 2
    logs = sorted(str(call.args[0]) for call in server.here.send.await_args_list)
    assert ["offense 1, 1 day" in logs[0], "offense 2, 7 days" in logs[1]] == [True] * 2


async def test_offenses_past_the_ladder_stay_permanent(bot: app.WispBot) -> None:
    await lay(bot)
    for _ in range(5):
        await punish(bot)
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert (player.offenses, player.banned_forever) == (5, True)


async def test_a_lighter_ban_does_not_replace_a_longer_offense_history(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    await bot.players.set_offense(GUILD_ID, MEMBER_ID, 1, None, False)
    await punish(bot)
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert player.offenses == 2
    assert player.banned_until is not None
    assert player.banned_until - discord.utils.utcnow() > timedelta(days=6)


async def test_punish_announces_in_the_house_without_the_reason(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await punish(bot, make_member(display_name="Cheater"))
    text = house_text(server)
    assert text in banned_lines("Cheater")
    assert REASON not in text
    assert server.house.send.await_args.kwargs["allowed_mentions"].to_dict() == NO_PING


async def test_punish_uses_the_chosen_name_in_the_house(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.players.set_name(GUILD_ID, MEMBER_ID, "Nova")
    await punish(bot, make_member(display_name="Cheater"))
    assert house_text(server) in banned_lines("Nova")


async def test_the_log_line_is_posted_in_the_channel_the_command_was_run_in(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    interaction = await punish(bot, make_member(display_name="Cheater"))
    assert staff_log(server) == (
        f"♪ <@{STAFF_ID}> punished <@{MEMBER_ID}> (offense 1, 1 day): {REASON}"
    )
    assert REASON not in house_text(server)
    assert server.here.send.await_args.kwargs["allowed_mentions"].to_dict() == NO_PING
    (reply,) = replies(interaction)
    assert reply == "♪ <@1> is banned from Wisp (offense 1, 1 day)."


async def test_the_staff_log_names_the_permanent_ban(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await bot.players.set_offense(GUILD_ID, MEMBER_ID, 2, None, False)
    await punish(bot)
    assert staff_log(server) == (
        f"♪ <@{STAFF_ID}> punished <@{MEMBER_ID}> (offense 3, permanent): {REASON}"
    )


async def test_punish_tells_the_staff_member_the_outcome(bot: app.WispBot) -> None:
    await lay(bot)
    interaction = await punish(bot, make_member(display_name="Cheater"))
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    (reply,) = replies(interaction)
    assert reply == "♪ <@1> is banned from Wisp (offense 1, 1 day)."


async def test_shame_image_optional(
    bot: app.WispBot, server: FakeServer, shame_folder: Path
) -> None:
    await lay(bot)
    await punish(bot)
    assert "file" not in server.house.send.await_args.kwargs

    server.house.send.reset_mock()
    shame_folder.mkdir(parents=True)
    await punish(bot)
    assert "file" not in server.house.send.await_args.kwargs


async def test_a_random_shame_image_is_attached(
    bot: app.WispBot,
    server: FakeServer,
    shame_folder: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await lay(bot)
    shame_folder.mkdir(parents=True)
    for name in ("a.png", "b.gif", "c.jpg", "d.webp", "notes.txt"):
        (shame_folder / name).write_bytes(b"x")
    seen: list[list[Path]] = []

    def pick_last(choices: list[Path]) -> Path:
        seen.append(choices)
        return choices[-1]

    monkeypatch.setattr(random, "choice", pick_last)
    await punish(bot)
    assert [path.name for path in seen[0]] == ["a.png", "b.gif", "c.jpg", "d.webp"]
    sent = server.house.send.await_args.kwargs["file"]
    assert sent.filename == "d.webp"


async def test_punish_without_a_life_still_bans_and_logs(
    bot: app.WispBot, server: FakeServer
) -> None:
    interaction = await punish(bot)
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert player.is_banned(discord.utils.utcnow())
    server.house.send.assert_not_awaited()
    assert REASON in staff_log(server)
    (reply,) = replies(interaction)
    assert "no life" in reply


async def test_a_failed_log_line_is_reported_where_it_failed_and_noted(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    server.here.send.side_effect = [
        discord.HTTPException(MagicMock(status=500), "boom"),
        None,
    ]
    interaction = await punish(bot)
    (reply,) = replies(interaction)
    assert reply.endswith("\n・The log line could not be posted here.")
    assert "not recorded" not in reply
    assert "Error in logging the punishment" in str(server.here.send.await_args.args[0])
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).offenses == 1


async def test_a_log_line_with_nowhere_to_go_is_noted(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    interaction = make_interaction(bot)
    interaction.channel = MagicMock(spec=discord.CategoryChannel)
    await run(discipline.punish, interaction, make_member(), REASON)
    (reply,) = replies(interaction)
    assert reply.endswith("\n・The log line could not be posted here.")
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).offenses == 1


@pytest.mark.parametrize(
    ("spec", "channel_id", "parent_id"),
    [
        (discord.TextChannel, TRACKS_ID, None),
        (discord.Thread, 41, TRACKS_ID),
        (discord.PartialMessageable, 42, None),
    ],
    ids=["the track drop", "a thread in the track drop", "a partial channel"],
)
async def test_punish_in_the_track_drop_logs_in_the_house_instead(
    bot: app.WispBot,
    server: FakeServer,
    spec: type,
    channel_id: int,
    parent_id: int | None,
) -> None:
    await lay(bot)
    where = MagicMock(spec=spec)
    where.id = channel_id
    if parent_id is not None:
        where.parent_id = parent_id
    where.send = AsyncMock()
    interaction = make_interaction(bot)
    interaction.channel = where

    await run(discipline.punish, interaction, make_member(), REASON)

    where.send.assert_not_awaited()
    log_line = f"♪ <@{STAFF_ID}> punished <@{MEMBER_ID}> (offense 1, 1 day): {REASON}"
    logged = [
        call for call in server.house.send.await_args_list if call.args == (log_line,)
    ]
    assert len(logged) == 1
    assert logged[0].kwargs["allowed_mentions"].to_dict() == NO_PING
    (reply,) = replies(interaction)
    assert reply == "♪ <@1> is banned from Wisp (offense 1, 1 day)."


def test_the_reason_is_described_as_public() -> None:
    reason = discipline.punish.get_parameter("reason")
    assert reason is not None
    assert "only staff" not in reason.description
    assert "posted in this channel" in reason.description


# ---
# Unban
# ---


async def test_unban_keeps_offense_count(bot: app.WispBot) -> None:
    await lay(bot)
    await punish(bot)
    await punish(bot)
    interaction = make_interaction(bot)
    await run(discipline.unban, interaction, make_member())
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert player.offenses == 2
    assert (player.banned_until, player.banned_forever) == (None, False)
    assert not player.is_banned(discord.utils.utcnow())
    (reply,) = replies(interaction)
    assert reply == "♪ <@1> can play with Wisp again. Their offense count stays at 2."


async def test_unban_lifts_a_permanent_ban(bot: app.WispBot) -> None:
    await bot.players.set_offense(GUILD_ID, MEMBER_ID, 3, None, True)
    await run(discipline.unban, make_interaction(bot), make_member())
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert (player.offenses, player.banned_forever) == (3, False)


async def test_unban_of_someone_not_banned_changes_nothing(bot: app.WispBot) -> None:
    await bot.players.set_offense(
        GUILD_ID, MEMBER_ID, 1, discord.utils.utcnow() - timedelta(days=2), False
    )
    interaction = make_interaction(bot)
    await run(discipline.unban, interaction, make_member())
    (reply,) = replies(interaction)
    assert reply == "♪ <@1> is not banned."
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).banned_until is not None


# ---
# Strip points
# ---


async def test_strip_never_negative(bot: app.WispBot) -> None:
    await bot.players.add_points(GUILD_ID, MEMBER_ID, 10)
    await bot.players.spend(GUILD_ID, MEMBER_ID, 8)
    interaction = make_interaction(bot)
    await run(discipline.strip, interaction, make_member(), 5)
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert (player.lifetime_points, player.balance) == (5, 0)
    await run(discipline.strip, make_interaction(bot), make_member(), 500)
    player = await bot.players.get(GUILD_ID, MEMBER_ID)
    assert (player.lifetime_points, player.balance) == (0, 0)
    (reply,) = replies(interaction)
    assert reply == "♪ Took 5 points from <@1>."


async def test_strip_one_point_is_singular(bot: app.WispBot) -> None:
    interaction = make_interaction(bot)
    await run(discipline.strip, interaction, make_member(), 1)
    (reply,) = replies(interaction)
    assert reply == "♪ Took 1 point from <@1>."


def test_strip_needs_at_least_one_point() -> None:
    points = discipline.strip.parameters[1]
    assert (points.name, points.min_value) == ("points", 1)


# ---
# Reset name
# ---


async def test_resetname_clears_name(bot: app.WispBot) -> None:
    await bot.players.set_name(GUILD_ID, MEMBER_ID, "Nova")
    interaction = make_interaction(bot)
    await run(discipline.resetname, interaction, make_member())
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).name is None
    (reply,) = replies(interaction)
    assert reply == "♪ Wisp forgot <@1>'s name. They can choose a new one."


@pytest.mark.parametrize(
    ("command_name", "extra", "storage"),
    [
        ("unban", (), "get"),
        ("strip", (5,), "strip_points"),
        ("resetname", (), "set_name"),
    ],
)
async def test_corrections_defer_before_touching_storage(
    bot: app.WispBot,
    monkeypatch: pytest.MonkeyPatch,
    command_name: str,
    extra: tuple[Any, ...],
    storage: str,
) -> None:
    order: list[str] = []
    interaction = make_interaction(bot)
    original_defer = interaction.response.defer.side_effect

    async def defer(*args: Any, **kwargs: Any) -> None:
        order.append("defer")
        await original_defer(*args, **kwargs)

    interaction.response.defer.side_effect = defer
    original = getattr(bot.players, storage)

    async def spy(*args: Any) -> Any:
        order.append("storage")
        return await original(*args)

    monkeypatch.setattr(bot.players, storage, spy)
    await run(getattr(discipline, command_name), interaction, make_member(), *extra)
    assert order[:2] == ["defer", "storage"]
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)
    interaction.response.send_message.assert_not_awaited()
    assert len(replies(interaction)) == 1


# ---
# Refusals and staff checks
# ---


@pytest.mark.parametrize(
    "command_name, extra",
    [("punish", (REASON,)), ("unban", ()), ("strip", (5,)), ("resetname", ())],
)
async def test_bots_are_refused(
    bot: app.WispBot, server: FakeServer, command_name: str, extra: tuple[Any, ...]
) -> None:
    await lay(bot)
    interaction = make_interaction(bot)
    command = getattr(discipline, command_name)
    await run(command, interaction, make_member(7, bot=True), *extra)
    (reply,) = replies(interaction)
    assert reply == "♪ <@7> is a bot, and bots do not play with Wisp."
    assert (await bot.players.get(GUILD_ID, 7)).offenses == 0
    server.house.send.assert_not_awaited()
    server.here.send.assert_not_awaited()


def test_every_discipline_leaf_is_staff_only() -> None:
    leaves = {
        command.name: command
        for command in groups.wispadmin.walk_commands()
        if isinstance(command, app_commands.Command)
    }
    for name in ("punish", "unban", "strip", "resetname"):
        command = leaves[name]
        assert command.parent is groups.wispadmin
        assert command.checks, name
        for check in command.checks:
            assert check(make_interaction(MagicMock(), staff=True))
            with pytest.raises(app_commands.MissingPermissions):
                check(make_interaction(MagicMock(), staff=False))


def test_the_extension_is_registered() -> None:
    assert "cogs.discipline" in app.EXTENSIONS
