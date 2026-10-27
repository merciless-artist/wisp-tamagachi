"""Tests for badges: their roles, buying them in the Vault, wearing and losing them.

Discord objects are fakes; the repositories are the real ones.
"""

import re
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import discord
import pymysql
import pytest

import app
from cogs import badges, snacks
from cogs.badges import ensure_badge_roles, sweep_badges
from db.activity import ActivityRepo
from db.badges import BadgeRepo
from db.database import Database
from db.gifts import GiftRepo
from db.keepsakes import KeepsakeKind, KeepsakeRepo
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from tests.layout import layout_order, layout_selects, layout_text
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import BADGE_BY_KEY, BADGES, BOND_TIERS, GIFT_BY_KEY, SNACKS, Stage
from wisp.text import (
    BOX_BOTTOM,
    LAYOUT_TEXT_LIMIT,
    MESSAGE_LIMIT,
    SECTION_BREAK,
    text_length,
)

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
SETUP_CHANNEL_ID = 30
USER_ID = 1
OTHER_USER_ID = 2
LEFT_USER_ID = 3
QUALIFYING_ROLE = 7
NO_PING = discord.AllowedMentions.none().to_dict()
CANNOT_FEED = (
    "♪ Only members at Active Lounger or higher who have opened /wisp board "
    "can feed Wisp."
)
BANDMATE_BOND = BOND_TIERS[-1][1]
EMOJI = "[🀀-🿿☀-♩♫-➿️]"

# ---
# Fakes
# ---


def http_error(status: int, text: str) -> discord.HTTPException:
    return discord.HTTPException(MagicMock(status=status), text)


def forbidden() -> discord.Forbidden:
    return discord.Forbidden(MagicMock(status=403), "Missing Permissions")


class FakeServer:
    """A guild with Wisp's House, roles Wisp can make and members he can fetch."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.id = HOUSE_ID
        self.house.send = AsyncMock()
        self.setup_channel = MagicMock(spec=discord.TextChannel)
        self.setup_channel.id = SETUP_CHANNEL_ID
        self.setup_channel.send = AsyncMock()
        self.roles: dict[int, MagicMock] = {}
        self.created: list[dict[str, Any]] = []
        self.members: dict[int, MagicMock] = {}
        self._next_role_id = 500
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.features = ["ROLE_ICONS"]
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get
        self.guild.get_role.side_effect = self.roles.get
        self.guild.create_role = AsyncMock(side_effect=self._create_role)
        self.guild.fetch_member = AsyncMock(side_effect=self._fetch_member)

    def _create_role(self, **fields: Any) -> MagicMock:
        self._next_role_id += 1
        self.created.append(fields)
        return self.add_role(
            self._next_role_id, fields["name"], fields.get("display_icon")
        )

    def add_role(self, role_id: int, name: str, icon: bytes | None = None) -> MagicMock:
        role = MagicMock(spec=discord.Role)
        role.id = role_id
        role.name = name
        role.display_icon = icon
        role.edit = AsyncMock()
        role.delete = AsyncMock()
        self.roles[role_id] = role
        return role

    def member(
        self, user_id: int, name: str, roles: tuple[int, ...] = (QUALIFYING_ROLE,)
    ) -> MagicMock:
        member = MagicMock(spec=discord.Member)
        member.id = user_id
        member.display_name = name
        member.roles = [MagicMock(spec=discord.Role, id=role_id) for role_id in roles]
        member.add_roles = AsyncMock()
        member.remove_roles = AsyncMock()
        self.members[user_id] = member
        return member

    def _fetch_member(self, user_id: int) -> MagicMock:
        if user_id not in self.members:
            raise discord.NotFound(MagicMock(status=404), "Unknown Member")
        return self.members[user_id]


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
    wisp_bot.keepsakes = KeepsakeRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture(autouse=True)
def art(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty badge art folder, so no real art is read."""
    folder = tmp_path / "badges"
    folder.mkdir()
    monkeypatch.setattr(badges, "BADGE_ART", folder)
    return folder


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot, server: FakeServer) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    for user_id in (USER_ID, OTHER_USER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())
    server.member(USER_ID, "Member1")
    server.member(OTHER_USER_ID, "Member2")


@pytest.fixture(autouse=True)
def no_meeting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snacks, "maybe_meet", AsyncMock())


def give_emojis(bot: app.WispBot, *names: str) -> None:
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(names, start=1)
    }


async def lay(bot: app.WispBot, version: int = 1, phase: Phase = Phase.ALIVE) -> Life:
    life = new_egg(version, discord.utils.utcnow() - timedelta(days=1))
    life.phase = phase
    life.full = 60.0
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.TEEN
        life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


async def end(bot: app.WispBot, life: Life) -> None:
    life.phase = Phase.DEAD
    life.ended_at = discord.utils.utcnow()
    await bot.lives.save(GUILD_ID, life)


async def set_up_roles(bot: app.WispBot, server: FakeServer) -> list[str]:
    return await ensure_badge_roles(bot, server.guild, server.setup_channel)


def make_interaction(
    bot: app.WispBot, server: FakeServer, user_id: int = USER_ID
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.channel.send = AsyncMock()
    interaction.user = server.members[user_id]
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False

    async def answer(*_args: Any, **_kwargs: Any) -> None:
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=answer)
    interaction.response.send_message = AsyncMock(side_effect=answer)
    interaction.edit_original_response = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def open_vault(
    bot: app.WispBot, server: FakeServer, user_id: int = USER_ID
) -> tuple[str, list[discord.ui.Select[Any]]]:
    interaction = make_interaction(bot, server, user_id)
    command: Any = snacks.wisp_vault
    await command.callback(interaction)
    view = interaction.followup.send.await_args.kwargs["view"]
    return layout_text(view), layout_selects(view)


def badge_select(
    selects: list[discord.ui.Select[Any]],
) -> discord.ui.Select[Any] | None:
    found = [select for select in selects if select.placeholder == "Get a badge"]
    return found[0] if found else None


async def buy(
    bot: app.WispBot, server: FakeServer, key: str, user_id: int = USER_ID
) -> MagicMock:
    """Open the Vault and get a badge from its select."""
    _, selects = await open_vault(bot, server, user_id)
    select = badge_select(selects)
    assert select is not None
    select._values = [key]
    interaction = make_interaction(bot, server, user_id)
    await select.callback(interaction)
    return interaction


def shown_note(interaction: MagicMock) -> str:
    """The first line of the Vault as the interaction last showed it."""
    call = interaction.edit_original_response.await_args
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert "content" not in call.kwargs
    return layout_text(call.kwargs["view"]).splitlines()[0]


def vault_section(text: str, heading: str) -> list[str]:
    """The Vault's lines under a `#` heading, up to the next break."""
    lines = text.splitlines()
    start = lines.index(f"║𝄡𝄚𝄂𝄆 **{heading}**") + 1
    end = next(
        index
        for index in range(start, len(lines))
        if lines[index] in (SECTION_BREAK, BOX_BOTTOM)
    )
    return lines[start:end]


def house_posts(server: FakeServer) -> list[str]:
    posts = server.house.send.await_args_list
    assert all(post.kwargs["allowed_mentions"].to_dict() == NO_PING for post in posts)
    return [str(post.args[0]) for post in posts]


async def role_of(bot: app.WispBot, server: FakeServer, key: str) -> MagicMock:
    return server.roles[(await bot.badges.role_ids(GUILD_ID))[key]]


async def rich(bot: app.WispBot, user_id: int = USER_ID, points: int = 1000) -> None:
    await bot.players.add_points(GUILD_ID, user_id, points)


# ---
# Roles in the server
# ---


async def test_setup_creates_every_badge_role_and_remembers_it(
    bot: app.WispBot, server: FakeServer
) -> None:
    lines = await set_up_roles(bot, server)

    assert [fields["name"] for fields in server.created] == [
        badge.name for badge in BADGES
    ]
    assert all("display_icon" not in fields for fields in server.created)
    assert all(fields["reason"] for fields in server.created)
    stored = await bot.badges.role_ids(GUILD_ID)
    assert set(stored) == {badge.key for badge in BADGES}
    assert {server.roles[role_id].name for role_id in stored.values()} == {
        badge.name for badge in BADGES
    }
    assert lines == [f"・Badge roles created: {', '.join(b.name for b in BADGES)}"]


async def test_setup_gives_new_roles_their_icons_when_the_art_exists(
    bot: app.WispBot, server: FakeServer, art: Path
) -> None:
    (art / "team_viibr.png").write_bytes(b"team-viibr-png")

    await set_up_roles(bot, server)

    icons = {fields["name"]: fields.get("display_icon") for fields in server.created}
    assert icons["Team ViiBR"] == b"team-viibr-png"
    assert all(icon is None for name, icon in icons.items() if name != "Team ViiBR")


async def test_a_second_setup_leaves_the_roles_alone(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_up_roles(bot, server)
    server.created.clear()

    lines = await set_up_roles(bot, server)

    assert server.created == []
    assert lines == ["・Badge roles: all 4 ready"]


async def test_a_later_setup_adds_icons_that_now_exist(
    bot: app.WispBot, server: FakeServer, art: Path
) -> None:
    await set_up_roles(bot, server)
    (art / "pickle_diplomat.png").write_bytes(b"pickle-png")

    lines = await set_up_roles(bot, server)

    egg = await role_of(bot, server, "pickle_diplomat")
    egg.edit.assert_awaited_once()
    assert egg.edit.await_args.kwargs["display_icon"] == b"pickle-png"
    (await role_of(bot, server, "team_viibr")).edit.assert_not_awaited()
    assert "・Badge icons added: Pickle Diplomat" in lines


async def test_a_deleted_badge_role_is_recreated(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_up_roles(bot, server)
    old = await role_of(bot, server, "flame_keeper")
    del server.roles[old.id]
    server.created.clear()

    lines = await set_up_roles(bot, server)

    assert [fields["name"] for fields in server.created] == ["Flame Keeper"]
    assert (await role_of(bot, server, "flame_keeper")).id != old.id
    assert "・Badge roles recreated: Flame Keeper" in lines


async def test_setup_renames_a_role_whose_name_is_not_its_badges(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.badges.set_role(GUILD_ID, "team_viibr", 9)
    old = server.add_role(9, "Team Wisp", b"icon")

    lines = await set_up_roles(bot, server)

    old.edit.assert_awaited_once()
    assert old.edit.await_args.kwargs["name"] == "Team ViiBR"
    assert (await bot.badges.role_ids(GUILD_ID))["team_viibr"] == 9
    assert "Team ViiBR" not in [fields["name"] for fields in server.created]
    assert "・Badge roles renamed: Team ViiBR" in lines
    server.setup_channel.send.assert_not_awaited()


async def test_setup_deletes_the_roles_of_badges_no_longer_sold(
    bot: app.WispBot, server: FakeServer
) -> None:
    await bot.badges.set_role(GUILD_ID, "egg_warmer", 8)
    await bot.badges.set_role(GUILD_ID, "viibr_roadie", 9)
    egg = server.add_role(8, "Egg Warmer")
    unrelated = server.add_role(10, "Viibr Roadie")

    lines = await set_up_roles(bot, server)

    egg.delete.assert_awaited_once()
    unrelated.delete.assert_not_awaited()
    assert set(await bot.badges.role_ids(GUILD_ID)) == set(BADGE_BY_KEY)
    assert "・Badge roles no longer sold, deleted: Egg Warmer, ViiBR Roadie" in lines
    server.setup_channel.send.assert_not_awaited()


async def test_a_retired_role_that_cannot_be_deleted_is_reported_and_kept(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_up_roles(bot, server)
    await bot.badges.set_role(GUILD_ID, "egg_warmer", 8)
    egg = server.add_role(8, "Egg Warmer")
    egg.delete.side_effect = forbidden()

    lines = await set_up_roles(bot, server)

    (report,) = [call.args[0] for call in server.setup_channel.send.await_args_list]
    assert report.startswith(
        "Error in deleting the Egg Warmer badge role, no longer sold: Forbidden"
    )
    assert (await bot.badges.role_ids(GUILD_ID))["egg_warmer"] == 8
    assert lines == ["・Badge roles: all 4 ready"]


async def test_the_sweep_takes_back_a_badge_no_longer_sold(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await bot.badges.set_role(GUILD_ID, "egg_warmer", 8)
    egg = server.add_role(8, "Egg Warmer")
    assert life.id is not None
    await bot.badges.record(
        GUILD_ID, USER_ID, "egg_warmer", life.id, 1, discord.utils.utcnow()
    )
    await end(bot, life)

    await sweep_badges(bot, GUILD_ID, discord.utils.utcnow())

    server.members[USER_ID].remove_roles.assert_awaited_once_with(
        egg, reason="Wisp v1's life ended"
    )
    assert await bot.badges.pending(GUILD_ID) == []


async def test_roles_are_found_by_id_not_by_name(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.add_role(9, "Team ViiBR")

    await set_up_roles(bot, server)

    assert (await bot.badges.role_ids(GUILD_ID))["team_viibr"] != 9


async def test_a_server_without_role_icons_gets_plain_roles_and_one_note(
    bot: app.WispBot, server: FakeServer, art: Path
) -> None:
    server.guild.features = []
    for badge in BADGES:
        (art / f"{badge.key}.png").write_bytes(b"png")

    lines = await set_up_roles(bot, server)

    assert len(server.created) == len(BADGES)
    assert all("display_icon" not in fields for fields in server.created)
    notes = [line for line in lines if "icons" in line]
    assert notes == [
        "・Role icons are not available on this server (it needs more boosts), "
        "so the badges have no icons."
    ]


async def test_an_icon_discord_refuses_means_a_plain_role_and_one_note(
    bot: app.WispBot, server: FakeServer, art: Path
) -> None:
    for badge in BADGES:
        (art / f"{badge.key}.png").write_bytes(b"png")
    plain = server._create_role

    def refuse_icons(**fields: Any) -> MagicMock:
        if "display_icon" in fields:
            raise http_error(400, "Invalid Form Body")
        return plain(**fields)

    server.guild.create_role.side_effect = refuse_icons

    lines = await set_up_roles(bot, server)

    assert set(await bot.badges.role_ids(GUILD_ID)) == set(BADGE_BY_KEY)
    assert sum("not available" in line for line in lines) == 1
    server.setup_channel.send.assert_not_awaited()


async def test_missing_manage_roles_is_reported_where_setup_ran(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.guild.create_role.side_effect = forbidden()

    await set_up_roles(bot, server)

    (report,) = [call.args[0] for call in server.setup_channel.send.await_args_list]
    assert report.startswith(
        "Error in creating the Pickle Diplomat badge role: Forbidden"
    )
    server.guild.create_role.assert_awaited_once()
    assert await bot.badges.role_ids(GUILD_ID) == {}


async def test_a_role_that_cannot_be_remembered_is_deleted_and_reported(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = AsyncMock(side_effect=pymysql.err.OperationalError(2003, "down"))
    monkeypatch.setattr(bot.badges, "set_role", broken)

    lines = await set_up_roles(bot, server)

    (made,) = server.roles.values()
    made.delete.assert_awaited_once()
    (report,) = [call.args[0] for call in server.setup_channel.send.await_args_list]
    assert report.startswith(
        "Error in remembering the Pickle Diplomat badge role: OperationalError"
    )
    assert not any("created" in line for line in lines)


# ---
# The Vault
# ---


async def test_the_vault_lists_every_badge_with_its_price(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    give_emojis(bot, "badge_team_viibr")

    text, selects = await open_vault(bot, server)

    assert vault_section(text, "Badges") == [
        "║𝄡 pickle diplomat  │・25 WC",
        "║𝄡 flame keeper       │・100 WC",
        "║𝄡 team viibr              │<:badge_team_viibr:1>・250 WC",
        "║𝄡 bandmate              │・250 WC・Bandmates only",
    ]
    select = badge_select(selects)
    assert select is not None
    assert [option.value for option in select.options] == [
        badge.key for badge in BADGES if badge.needs_tier is None
    ]
    assert not re.search(EMOJI, text)


async def test_a_bandmate_can_get_the_bandmate_badge(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await bot.players.add_bond(GUILD_ID, USER_ID, BANDMATE_BOND)

    text, selects = await open_vault(bot, server)

    assert "Bandmates only" not in text
    select = badge_select(selects)
    assert select is not None
    assert "bandmate" in [option.value for option in select.options]


async def test_owned_badges_are_marked_and_left_out_of_the_select(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await buy(bot, server, "pickle_diplomat")

    text, selects = await open_vault(bot, server)

    assert "║𝄡 pickle diplomat  │・25 WC・owned" in text.splitlines()
    select = badge_select(selects)
    assert select is not None
    assert "pickle_diplomat" not in [option.value for option in select.options]
    assert len(select.options) <= 25


async def test_badges_without_a_role_cannot_be_bought_yet(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    text, selects = await open_vault(bot, server)

    assert "║𝄡 team viibr              │・250 WC・coming soon" in text.splitlines()
    assert badge_select(selects) is None


async def test_the_badge_lines_show_the_mini_coin_and_badge_emojis(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    give_emojis(bot, "wisp_coin_mini", "badge_pickle_diplomat")

    text, _ = await open_vault(bot, server)

    assert vault_section(text, "Badges")[0] == (
        "║𝄡 pickle diplomat  │<:badge_pickle_diplomat:2>・<:wisp_coin_mini:1> 25 WC"
    )


async def test_the_badge_select_sits_under_the_badges(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    interaction = make_interaction(bot, server)
    command: Any = snacks.wisp_vault

    await command.callback(interaction)

    view = interaction.followup.send.await_args.kwargs["view"]
    assert layout_order(view) == [
        "text",
        "Buy a snack",
        "text",
        "Get a badge",
        "text",
        "Pick a collection",
        "text",
    ]


async def test_the_fullest_vault_stays_within_the_layout_text_limit(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    names = [
        "wisp_coin",
        "wisp_coin_mini",
        "viibr_logo",
        *(badge.emoji_name for badge in BADGES),
        *(snack.emoji_name for snack in SNACKS),
        *(gift.emoji_name for gift in GIFT_BY_KEY.values()),
    ]
    bot.emojis_by_name = {
        name: cast(
            discord.Emoji,
            discord.PartialEmoji(name=name, id=2**64 - 1 - index, animated=True),
        )
        for index, name in enumerate(names)
    }
    await rich(bot, points=10**9)

    text, selects = await open_vault(bot, server)

    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    assert all(len(select.options) <= 25 for select in selects)
    assert len(selects) <= 4
    for gift in GIFT_BY_KEY.values():
        assert f"<a:{gift.emoji_name}:" in text, gift.key


# ---
# Buying
# ---


async def test_buying_spends_gives_bond_and_the_role(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot, points=300)

    interaction = await buy(bot, server, "team_viibr")

    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.lifetime_points, player.bond) == (50, 300, 25)
    role = await role_of(bot, server, "team_viibr")
    server.members[USER_ID].add_roles.assert_awaited_once_with(
        role, reason="Bought in the ViiBR Vault"
    )
    assert life.id is not None
    assert await bot.badges.owned(GUILD_ID, USER_ID, life.id) == {"team_viibr"}
    assert shown_note(interaction) == "♪ You got the Team ViiBR badge ・ bond +25"
    (post,) = house_posts(server)
    heading, line = post.split("\n")
    assert heading == "♪ Member1 joined Team ViiBR"
    options = {
        text.format(name="Member1") for text in LINES[(Moment.BADGE_BOUGHT, Mood.HAPPY)]
    }
    assert line in options


@pytest.mark.parametrize(
    ("key", "heading"),
    [
        ("pickle_diplomat", "♪ Aria is now a Pickle Diplomat"),
        ("flame_keeper", "♪ Aria is now a Flame Keeper"),
        ("team_viibr", "♪ Aria joined Team ViiBR"),
        ("bandmate", "♪ Aria is now one of Wisp's Bandmates"),
    ],
)
async def test_the_house_announces_each_badge_in_its_own_words(
    bot: app.WispBot, server: FakeServer, key: str, heading: str
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await bot.players.add_bond(GUILD_ID, USER_ID, BANDMATE_BOND)
    await bot.players.set_name(GUILD_ID, USER_ID, "Aria")

    await buy(bot, server, key)

    (post,) = house_posts(server)
    assert post.split("\n")[0] == heading


async def test_badge_bond_skips_the_daily_casual_cap(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)

    for key in ("pickle_diplomat", "flame_keeper", "team_viibr"):
        await buy(bot, server, key)

    assert (await bot.players.get(GUILD_ID, USER_ID)).bond == 5 + 15 + 25


async def test_a_second_purchase_in_the_same_life_is_refused(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot, points=100)
    _, selects = await open_vault(bot, server)
    select = badge_select(selects)
    assert select is not None

    for _ in range(2):
        select._values = ["pickle_diplomat"]
        interaction = make_interaction(bot, server)
        await select.callback(interaction)

    assert shown_note(interaction) == (
        "♪ You already have the Pickle Diplomat badge for Wisp v1."
    )
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.bond) == (75, 5)
    server.members[USER_ID].add_roles.assert_awaited_once()


@pytest.mark.parametrize(
    ("bond", "refused"), [(BANDMATE_BOND - 1, True), (BANDMATE_BOND, False)]
)
async def test_the_bandmate_badge_needs_the_bandmate_tier(
    bot: app.WispBot, server: FakeServer, bond: int, refused: bool
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await bot.players.add_bond(GUILD_ID, USER_ID, BANDMATE_BOND)
    _, selects = await open_vault(bot, server)
    select = badge_select(selects)
    assert select is not None
    await bot.players.add_bond(GUILD_ID, USER_ID, bond - BANDMATE_BOND)
    select._values = ["bandmate"]
    interaction = make_interaction(bot, server)

    await select.callback(interaction)

    note = shown_note(interaction)
    if refused:
        assert note == "♪ The Bandmate badge is only for Bandmates."
        server.members[USER_ID].add_roles.assert_not_awaited()
        assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 1000
    else:
        assert note == "♪ You got the Bandmate badge ・ bond +25"


async def test_a_member_short_on_points_is_refused(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot, points=24)

    interaction = await buy(bot, server, "pickle_diplomat")

    note = shown_note(interaction)
    assert note in {
        text.format(name="Member1")
        for text in LINES[(Moment.NOT_ENOUGH_POINTS, Mood.HAPPY)]
    }
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.bond) == (24, 0)
    server.members[USER_ID].add_roles.assert_not_awaited()
    assert house_posts(server) == []


async def test_a_banned_member_is_refused(bot: app.WispBot, server: FakeServer) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    _, selects = await open_vault(bot, server)
    select = badge_select(selects)
    assert select is not None
    await bot.players.set_offense(
        GUILD_ID, USER_ID, 1, discord.utils.utcnow() + timedelta(days=1), False
    )
    select._values = ["pickle_diplomat"]
    interaction = make_interaction(bot, server)

    await select.callback(interaction)

    assert shown_note(interaction) == (
        "♪ Wisp is not taking snacks or gifts from you right now."
    )
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 1000
    server.members[USER_ID].add_roles.assert_not_awaited()


async def test_a_member_who_cannot_feed_is_refused(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    server.member(USER_ID, "Member1", roles=())

    interaction = await buy(bot, server, "pickle_diplomat")

    assert shown_note(interaction) == CANNOT_FEED
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 1000
    server.members[USER_ID].add_roles.assert_not_awaited()


async def test_a_role_that_cannot_be_given_refunds_everything(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot, points=300)
    server.members[USER_ID].add_roles.side_effect = forbidden()

    interaction = await buy(bot, server, "team_viibr")

    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.lifetime_points, player.bond) == (300, 300, 0)
    assert life.id is not None
    assert await bot.badges.owned(GUILD_ID, USER_ID, life.id) == set()
    assert shown_note(interaction) == (
        "♪ Your Team ViiBR badge didn't go through. Your WC are back."
    )
    (report,) = [call.args[0] for call in interaction.channel.send.await_args_list]
    assert report.startswith("Error in giving the Team ViiBR badge role: Forbidden")
    assert house_posts(server) == []


@pytest.mark.parametrize(
    "error",
    [aiohttp.ClientConnectionError("reset"), OSError("network down"), TimeoutError()],
)
async def test_a_network_failure_giving_the_role_refunds_everything(
    bot: app.WispBot, server: FakeServer, error: BaseException
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot, points=300)
    server.members[USER_ID].add_roles.side_effect = error

    interaction = await buy(bot, server, "team_viibr")

    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.bond) == (300, 0)
    assert life.id is not None
    assert await bot.badges.owned(GUILD_ID, USER_ID, life.id) == set()
    assert shown_note(interaction) == (
        "♪ Your Team ViiBR badge didn't go through. Your WC are back."
    )
    (report,) = [call.args[0] for call in interaction.channel.send.await_args_list]
    assert report.startswith(
        f"Error in giving the Team ViiBR badge role: {type(error).__name__}"
    )


async def test_a_purchase_already_recorded_is_refunded(
    bot: app.WispBot, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot, points=100)
    await buy(bot, server, "pickle_diplomat")
    monkeypatch.setattr(bot.badges, "owned", AsyncMock(return_value=set()))

    interaction = await buy(bot, server, "pickle_diplomat")

    assert shown_note(interaction) == (
        "♪ You already have the Pickle Diplomat badge for Wisp v1."
    )
    player = await bot.players.get(GUILD_ID, USER_ID)
    assert (player.balance, player.bond) == (75, 5)
    server.members[USER_ID].add_roles.assert_awaited_once()


async def test_badges_wait_for_a_wisp(bot: app.WispBot, server: FakeServer) -> None:
    await set_up_roles(bot, server)
    await rich(bot)
    life = await lay(bot)
    _, selects = await open_vault(bot, server)
    select = badge_select(selects)
    assert select is not None
    await end(bot, life)
    select._values = ["pickle_diplomat"]
    interaction = make_interaction(bot, server)

    await select.callback(interaction)

    assert shown_note(interaction) == "♪ There's no Wisp to wear a badge for right now."
    assert (await bot.players.get(GUILD_ID, USER_ID)).balance == 1000


async def test_an_egg_can_have_badges_bought_for_it(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot, phase=Phase.EGG)
    await set_up_roles(bot, server)
    await rich(bot)

    interaction = await buy(bot, server, "pickle_diplomat")

    assert shown_note(interaction) == "♪ You got the Pickle Diplomat badge ・ bond +5"


# ---
# When a life ends
# ---


async def sweep(bot: app.WispBot) -> None:
    await sweep_badges(bot, GUILD_ID, discord.utils.utcnow())


async def test_the_sweep_takes_an_ended_lifes_badges_back_once(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    for user_id in (USER_ID, OTHER_USER_ID):
        await rich(bot, user_id)
    await buy(bot, server, "pickle_diplomat")
    await buy(bot, server, "team_viibr")
    await buy(bot, server, "flame_keeper", OTHER_USER_ID)
    server.member(LEFT_USER_ID, "Gone")
    await bot.players.activate(GUILD_ID, LEFT_USER_ID, discord.utils.utcnow())
    await rich(bot, LEFT_USER_ID)
    await buy(bot, server, "flame_keeper", LEFT_USER_ID)
    del server.members[LEFT_USER_ID]
    await end(bot, life)
    server.house.send.reset_mock()

    await sweep(bot)
    await sweep(bot)

    first = server.members[USER_ID].remove_roles
    first.assert_awaited_once()
    assert set(first.await_args.args) == {
        await role_of(bot, server, "pickle_diplomat"),
        await role_of(bot, server, "team_viibr"),
    }
    assert first.await_args.kwargs["reason"] == "Wisp v1's life ended"
    second = server.members[OTHER_USER_ID].remove_roles
    second.assert_awaited_once()
    assert set(second.await_args.args) == {await role_of(bot, server, "flame_keeper")}
    assert server.guild.fetch_member.await_count == 3
    assert await bot.badges.pending(GUILD_ID) == []
    assert house_posts(server) == []


async def test_the_sweep_leaves_a_living_wisps_badges_alone(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await buy(bot, server, "pickle_diplomat")

    await sweep(bot)

    server.members[USER_ID].remove_roles.assert_not_awaited()
    server.guild.fetch_member.assert_not_awaited()


async def test_a_deleted_role_still_marks_the_purchase(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await buy(bot, server, "pickle_diplomat")
    del server.roles[(await role_of(bot, server, "pickle_diplomat")).id]
    await end(bot, life)

    await sweep(bot)

    server.members[USER_ID].remove_roles.assert_not_awaited()
    assert await bot.badges.pending(GUILD_ID) == []


async def test_a_failed_removal_is_retried_and_reported_once_per_streak(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    for user_id in (USER_ID, OTHER_USER_ID):
        await rich(bot, user_id)
        await buy(bot, server, "pickle_diplomat", user_id)
    await end(bot, life)
    failing = server.members[USER_ID].remove_roles
    failing.side_effect = http_error(500, "Internal Server Error")
    server.house.send.reset_mock()

    await sweep(bot)
    await sweep(bot)

    (report,) = house_posts(server)
    assert report.startswith("Error in taking back badge roles: HTTPException")
    assert failing.await_count == 2
    server.members[OTHER_USER_ID].remove_roles.assert_awaited_once()
    assert [item.user_id for item in await bot.badges.pending(GUILD_ID)] == [USER_ID]

    failing.side_effect = None
    await sweep(bot)
    assert await bot.badges.pending(GUILD_ID) == []
    assert failing.await_count == 3

    other = await lay(bot, version=2)
    await rich(bot)
    await buy(bot, server, "team_viibr")
    await end(bot, other)
    failing.side_effect = forbidden()
    server.house.send.reset_mock()
    await sweep(bot)
    assert len(house_posts(server)) == 1


async def test_a_forbidden_removal_stops_the_sweep_for_that_tick(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    for user_id in (USER_ID, OTHER_USER_ID):
        await rich(bot, user_id)
        await buy(bot, server, "pickle_diplomat", user_id)
    await end(bot, life)
    first = server.members[USER_ID].remove_roles
    first.side_effect = forbidden()
    server.house.send.reset_mock()

    await sweep(bot)
    await sweep(bot)

    (report,) = house_posts(server)
    assert report.startswith("Error in taking back badge roles: Forbidden")
    assert first.await_count == 2
    server.members[OTHER_USER_ID].remove_roles.assert_not_awaited()
    assert len(await bot.badges.pending(GUILD_ID)) == 2


async def test_a_badge_bought_again_in_the_next_life_is_never_taken_off(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await buy(bot, server, "pickle_diplomat")
    await end(bot, life)
    await lay(bot, version=2)

    await buy(bot, server, "pickle_diplomat")
    await sweep(bot)

    server.members[USER_ID].remove_roles.assert_not_awaited()
    assert await bot.badges.pending(GUILD_ID) == []


async def test_a_purchase_landing_mid_sweep_gets_its_role_back(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await buy(bot, server, "pickle_diplomat")
    await buy(bot, server, "team_viibr")
    await end(bot, life)
    new_life = await lay(bot, version=2)
    new_id = new_life.id
    assert new_id is not None
    member = server.members[USER_ID]
    member.add_roles.reset_mock()

    async def bought_meanwhile(*_roles: Any, **_fields: Any) -> None:
        await bot.badges.record(
            GUILD_ID, USER_ID, "pickle_diplomat", new_id, 2, discord.utils.utcnow()
        )

    member.remove_roles.side_effect = bought_meanwhile

    await sweep(bot)

    member.remove_roles.assert_awaited_once()
    member.add_roles.assert_awaited_once_with(
        await role_of(bot, server, "pickle_diplomat"), reason="Bought again for Wisp v2"
    )
    assert await bot.badges.pending(GUILD_ID) == []


async def test_the_next_life_sells_the_badges_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    await set_up_roles(bot, server)
    await rich(bot)
    await buy(bot, server, "pickle_diplomat")
    await end(bot, life)
    await lay(bot, version=2)

    text, selects = await open_vault(bot, server)

    assert "owned" not in text
    select = badge_select(selects)
    assert select is not None
    assert "pickle_diplomat" in [option.value for option in select.options]
    interaction = await buy(bot, server, "pickle_diplomat")
    assert shown_note(interaction) == "♪ You got the Pickle Diplomat badge ・ bond +5"


# ---
# The Snack Pack
# ---


async def snack_pack(bot: app.WispBot, server: FakeServer) -> str:
    interaction = make_interaction(bot, server)
    command: Any = snacks.wisp_snackpack
    await command.callback(interaction)
    return str(interaction.followup.send.await_args.args[0])


async def test_the_snack_pack_lists_every_badge_ever_bought_retired_too(
    bot: app.WispBot, server: FakeServer
) -> None:
    give_emojis(bot, "badge_team_viibr")
    at = discord.utils.utcnow()
    await bot.badges.record(GUILD_ID, USER_ID, "egg_warmer", 1, 1, at)
    await bot.badges.record(GUILD_ID, USER_ID, "team_viibr", 2, 2, at)
    await bot.badges.record(GUILD_ID, USER_ID, "viibr_roadie", 3, 3, at)

    text = await snack_pack(bot, server)

    assert vault_section(text, "Badges") == [
        "║𝄡 Wisp v3's ViiBR Roadie",
        "║𝄡 Wisp v2's <:badge_team_viibr:1>",
        "║𝄡 Wisp v1's Egg Warmer",
    ]


async def test_a_snack_pack_without_badges_says_so(
    bot: app.WispBot, server: FakeServer
) -> None:
    text = await snack_pack(bot, server)

    assert vault_section(text, "Badges") == ["║𝄡 none yet"]
    assert text.splitlines()[-2] == BOX_BOTTOM


async def test_the_fullest_snack_pack_still_fits_one_message(
    bot: app.WispBot, server: FakeServer
) -> None:
    give_emojis(
        bot,
        "wisp_coin",
        *(badge.emoji_name for badge in BADGES),
        *(f"keepsake_{kind.value}" for kind in KeepsakeKind),
    )
    await bot.players.set_name(GUILD_ID, USER_ID, "W" * 24)
    at = discord.utils.utcnow()
    for version in range(1, 30):
        for kind in KeepsakeKind:
            await bot.keepsakes.give(GUILD_ID, USER_ID, kind, 1000 + version, at)
        for badge in BADGES:
            await bot.badges.record(
                GUILD_ID, USER_ID, badge.key, version, 1000 + version, at
            )

    text = await snack_pack(bot, server)

    assert text_length(text) <= MESSAGE_LIMIT
    keepsakes = vault_section(text, "Keepsakes")
    badge_lines = vault_section(text, "Badges")
    assert text.splitlines()[-2] == BOX_BOTTOM
    assert keepsakes[-1].startswith("║𝄡 and ") and keepsakes[-1].endswith(" more")
    assert badge_lines[-1].startswith("║𝄡 and ") and badge_lines[-1].endswith(" more")
    assert len(keepsakes) > 2 and len(badge_lines) > 2
    assert badge_lines[0] == "║𝄡 Wisp v1029's <:badge_bandmate:5>"
