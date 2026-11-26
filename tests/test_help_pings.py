"""Tests for help pings: the helper role, the board giving it, the backfill
when staff set it, and the button that turns it off and on.

Discord objects are fakes; the repositories are the real ones.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.ext import commands

import app
from cogs import help_pings, vault
from cogs.help_pings import (
    GET_LABEL,
    HELP_PINGS_ID,
    STOP_LABEL,
    HelpPingsButton,
    helperrole,
    helperrole_off,
)
from cogs.snacks import ShopButton, SnackPackButton
from db.activity import ActivityRepo
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo

GUILD_ID = 100
CHANNEL_ID = 30
HELPER_ROLE = 55
OTHER_ROLE = 56
MEMBER_ID = 1
HOLDER_ID = 2
OPTED_OUT_ID = 3
LEFT_ID = 4
NEWCOMER_ID = 5
NO_PING = discord.AllowedMentions.none().to_dict()

# ---
# Fakes
# ---


def make_role(role_id: int, default: bool = False) -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = role_id
    role.mention = f"<@&{role_id}>"
    role.is_default.return_value = default
    return role


def make_member(user_id: int, *role_ids: int) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = user_id
    member.roles = [make_role(role_id) for role_id in role_ids]
    member.add_roles = AsyncMock()
    member.remove_roles = AsyncMock()
    return member


class FakeServer:
    """A guild with the helper role and its members, fetched by id."""

    def __init__(self) -> None:
        self.role = make_role(HELPER_ROLE)
        self.members: dict[int, MagicMock] = {}
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_role.side_effect = {HELPER_ROLE: self.role}.get
        self.guild.get_channel_or_thread.return_value = None
        self.guild.fetch_member = AsyncMock(side_effect=self._fetch)
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.id = CHANNEL_ID
        self.channel.send = AsyncMock()

    def add(self, user_id: int, *role_ids: int) -> MagicMock:
        member = make_member(user_id, *role_ids)
        self.members[user_id] = member
        return member

    async def _fetch(self, user_id: int) -> MagicMock:
        if user_id not in self.members:
            raise discord.NotFound(MagicMock(status=404), "Unknown Member")
        return self.members[user_id]

    def sent(self) -> list[str]:
        """What was posted in the command's channel, none of it able to ping."""
        texts = []
        for call in self.channel.send.await_args_list:
            assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
            texts.append(str(call.args[0]))
        return texts


def forbidden() -> discord.Forbidden:
    return discord.Forbidden(MagicMock(status=403), "Missing Permissions")


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
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


async def set_role(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, helper_role_id=HELPER_ROLE)


async def invoke(command: Any, *args: Any) -> None:
    await command.callback(*args)


def make_ctx(bot: app.WispBot, server: FakeServer) -> MagicMock:
    ctx = MagicMock(spec=commands.Context)
    ctx.bot = bot
    ctx.guild = server.guild
    ctx.channel = server.channel
    return ctx


def make_interaction(
    bot: app.WispBot, server: FakeServer, member: MagicMock
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = server.guild
    interaction.guild_id = GUILD_ID
    interaction.channel = server.channel
    interaction.user = member
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = True
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def private_texts(interaction: MagicMock) -> list[str]:
    texts = []
    for call in interaction.followup.send.await_args_list:
        assert call.kwargs["ephemeral"] is True
        if call.args:
            texts.append(str(call.args[0]))
    return texts


# ---
# Opening the board
# ---


async def open_board(
    bot: app.WispBot, server: FakeServer, member: MagicMock
) -> list[discord.ui.Item[Any]]:
    """Run /wisp board for `member` and return the board's buttons."""
    interaction = make_interaction(bot, server, member)
    await invoke(vault.wisp_board, interaction)
    board_call = interaction.followup.send.await_args_list[-1]
    *_, row = board_call.kwargs["view"].children
    assert isinstance(row, discord.ui.ActionRow)
    return list(row.children)


def help_button(buttons: list[discord.ui.Item[Any]]) -> HelpPingsButton:
    *_, last = buttons
    assert isinstance(last, HelpPingsButton)
    return last


async def test_opening_the_board_gives_the_helper_role_right_away(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    member = server.add(MEMBER_ID)

    buttons = await open_board(bot, server, member)

    member.add_roles.assert_awaited_once_with(server.role, reason="Opened /wisp board")
    shop, snack_pack, toggle = buttons
    assert isinstance(shop, ShopButton)
    assert isinstance(snack_pack, SnackPackButton)
    assert isinstance(toggle, HelpPingsButton)
    assert (toggle.item.label, toggle.item.custom_id) == (STOP_LABEL, HELP_PINGS_ID)


async def test_without_a_helper_role_the_board_gives_nothing_and_has_no_toggle(
    bot: app.WispBot, server: FakeServer
) -> None:
    member = server.add(MEMBER_ID)

    buttons = await open_board(bot, server, member)

    member.add_roles.assert_not_awaited()
    assert [type(button) for button in buttons] == [ShopButton, SnackPackButton]


async def test_a_member_who_holds_the_role_is_not_given_it_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    member = server.add(MEMBER_ID, HELPER_ROLE)

    buttons = await open_board(bot, server, member)

    member.add_roles.assert_not_awaited()
    assert help_button(buttons).item.label == STOP_LABEL


async def test_a_member_who_turned_help_pings_off_is_not_given_the_role_again(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    await bot.players.set_help_pings_off(GUILD_ID, MEMBER_ID, True)
    member = server.add(MEMBER_ID)

    for _ in range(2):
        buttons = await open_board(bot, server, member)
        assert help_button(buttons).item.label == GET_LABEL

    member.add_roles.assert_not_awaited()


@pytest.mark.parametrize(
    "error",
    [forbidden(), discord.HTTPException(MagicMock(status=500), "boom")],
    ids=["forbidden", "http"],
)
async def test_a_role_that_cannot_be_given_never_breaks_the_board(
    bot: app.WispBot,
    server: FakeServer,
    caplog: pytest.LogCaptureFixture,
    error: discord.HTTPException,
) -> None:
    await set_role(bot)
    member = server.add(MEMBER_ID)
    member.add_roles.side_effect = error

    buttons = await open_board(bot, server, member)

    assert help_button(buttons).item.label == GET_LABEL
    assert "Could not give 1 the helper role" in caplog.text
    assert not any("helper role" in text for text in server.sent())


# ---
# Staff setting the role
# ---


async def run_helperrole(bot: app.WispBot, server: FakeServer, role: MagicMock) -> str:
    """Run !wisp helperrole and return its answer, the last post."""
    await invoke(helperrole, make_ctx(bot, server), role)
    return server.sent()[-1]


async def test_helperrole_saves_the_role_and_gives_it_to_board_openers(
    bot: app.WispBot, server: FakeServer
) -> None:
    for user_id in (MEMBER_ID, HOLDER_ID, OPTED_OUT_ID, LEFT_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())
    await bot.players.set_help_pings_off(GUILD_ID, OPTED_OUT_ID, True)
    member = server.add(MEMBER_ID, OTHER_ROLE)
    holder = server.add(HOLDER_ID, HELPER_ROLE)
    opted_out = server.add(OPTED_OUT_ID)
    newcomer = server.add(NEWCOMER_ID)

    answer = await run_helperrole(bot, server, server.role)

    assert (await bot.settings.get(GUILD_ID)).helper_role_id == HELPER_ROLE
    member.add_roles.assert_awaited_once_with(server.role, reason="Opened /wisp board")
    for skipped in (holder, opted_out, newcomer):
        skipped.add_roles.assert_not_awaited()
    assert answer == (
        f"♪ <@&{HELPER_ROLE}> is Wisp's helper role now. His mess, tantrum and "
        "lights off posts in his House ping it.\n"
        "・Given to 1 of the members who opened /wisp board"
    )


async def test_a_forbidden_backfill_is_reported_once_and_stops(
    bot: app.WispBot, server: FakeServer
) -> None:
    for user_id in (MEMBER_ID, HOLDER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())
        server.add(user_id).add_roles.side_effect = forbidden()

    await invoke(helperrole, make_ctx(bot, server), server.role)

    report, answer = server.sent()
    assert report.startswith("Error in giving the helper role: Forbidden:")
    server.members[HOLDER_ID].add_roles.assert_not_awaited()
    assert answer.splitlines()[1:] == [
        "・Given to 0 of the members who opened /wisp board",
        "・Some members didn't get it; the error is above. Wisp needs Manage "
        f"Roles, and his own role above <@&{HELPER_ROLE}>.",
    ]
    assert (await bot.settings.get(GUILD_ID)).helper_role_id == HELPER_ROLE


async def test_another_discord_failure_is_reported_and_the_rest_still_get_it(
    bot: app.WispBot, server: FakeServer
) -> None:
    for user_id in (MEMBER_ID, HOLDER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())
    failing = server.add(MEMBER_ID)
    failing.add_roles.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    fine = server.add(HOLDER_ID)

    await invoke(helperrole, make_ctx(bot, server), server.role)

    report, answer = server.sent()
    assert report.startswith("Error in giving the helper role: HTTPException:")
    fine.add_roles.assert_awaited_once()
    assert "・Given to 1 of the members who opened /wisp board" in answer


@pytest.mark.parametrize(
    ("mention_everyone", "warned"),
    [(False, True), (True, False)],
    ids=["warned", "mention-everyone"],
)
async def test_helperrole_warns_when_wisp_cannot_ping_the_role(
    bot: app.WispBot, server: FakeServer, mention_everyone: bool, warned: bool
) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=CHANNEL_ID)
    server.guild.get_channel.side_effect = {CHANNEL_ID: server.channel}.get
    server.channel.permissions_for.return_value = discord.Permissions(
        mention_everyone=mention_everyone
    )
    server.role.mentionable = False

    answer = await run_helperrole(bot, server, server.role)

    server.channel.permissions_for.assert_called_once_with(server.guild.me)
    warning = (
        f"・Wisp can't ping <@&{HELPER_ROLE}> yet. Turn on 'Allow anyone to "
        "@mention this role' for it, or give Wisp Mention Everyone in his House."
    )
    assert (warning in answer.splitlines()) is warned


async def test_helperrole_without_a_house_checks_the_server_permissions(
    bot: app.WispBot, server: FakeServer
) -> None:
    server.guild.me.guild_permissions = discord.Permissions.none()
    server.role.mentionable = False

    answer = await run_helperrole(bot, server, server.role)

    assert answer.splitlines()[-1].startswith(f"・Wisp can't ping <@&{HELPER_ROLE}>")


async def test_helperrole_refuses_everyone(
    bot: app.WispBot, server: FakeServer
) -> None:
    answer = await run_helperrole(bot, server, make_role(GUILD_ID, default=True))

    assert answer == (
        "♪ Everyone has that role, so pinging it would ping the whole server. "
        "Pick another role."
    )
    assert (await bot.settings.get(GUILD_ID)).helper_role_id is None


async def test_helperrole_off_clears_the_role(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)

    await invoke(helperrole_off, make_ctx(bot, server))

    assert (await bot.settings.get(GUILD_ID)).helper_role_id is None
    assert server.sent() == [
        "♪ Wisp has no helper role now, so his House posts ping nobody."
    ]


def test_helperrole_off_is_its_subcommand() -> None:
    assert helperrole.get_command("off") is helperrole_off
    assert helperrole.get_command("OFF") is helperrole_off
    assert helperrole.usage == "@role | off"


# ---
# The help pings button
# ---


class Toggle:
    """The help pings button on a board, and what pressing it did."""

    def __init__(self, holds: bool) -> None:
        self.button = HelpPingsButton(holds)
        self.board = discord.ui.LayoutView(timeout=None)
        self.board.add_item(discord.ui.ActionRow(self.button))
        self.answers: list[str] = []
        self.redrawn: discord.ui.LayoutView | None = None

    async def press(
        self, bot: app.WispBot, server: FakeServer, member: MagicMock
    ) -> None:
        interaction = make_interaction(bot, server, member)
        interaction.edit_original_response = AsyncMock()
        await self.button.callback(interaction)
        interaction.response.defer.assert_awaited_once_with()
        self.answers = private_texts(interaction)
        if interaction.edit_original_response.await_args is not None:
            edited = interaction.edit_original_response.await_args.kwargs
            assert edited["allowed_mentions"].to_dict() == NO_PING
            self.redrawn = edited["view"]

    def label(self) -> str | None:
        """The label of the help pings button on the redrawn board."""
        assert self.redrawn is self.board
        (row,) = self.redrawn.children
        assert isinstance(row, discord.ui.ActionRow)
        (button,) = row.children
        assert isinstance(button, HelpPingsButton)
        return button.item.label


async def test_stop_help_pings_takes_the_role_and_remembers_it(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    member = server.add(MEMBER_ID, HELPER_ROLE)
    toggle = Toggle(holds=True)

    await toggle.press(bot, server, member)

    member.remove_roles.assert_awaited_once_with(
        server.role, reason="Turned help pings off"
    )
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).help_pings_off is True
    assert toggle.label() == GET_LABEL
    assert toggle.answers == [
        "♪ Help pings are off, and Wisp won't give them back on his own. "
        "Press Get help pings to turn them on again."
    ]


async def test_get_help_pings_gives_the_role_and_forgets_the_opt_out(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    await bot.players.set_help_pings_off(GUILD_ID, MEMBER_ID, True)
    member = server.add(MEMBER_ID)
    toggle = Toggle(holds=False)

    await toggle.press(bot, server, member)

    member.add_roles.assert_awaited_once_with(
        server.role, reason="Turned help pings on"
    )
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).help_pings_off is False
    assert toggle.label() == STOP_LABEL
    (answer,) = toggle.answers
    assert answer.startswith("♪ Help pings are on")


async def test_a_stale_label_still_goes_by_the_role_held(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    member = server.add(MEMBER_ID)
    toggle = Toggle(holds=True)

    await toggle.press(bot, server, member)

    member.add_roles.assert_awaited_once()
    assert toggle.label() == STOP_LABEL


async def test_the_toggle_without_a_helper_role_changes_nothing(
    bot: app.WispBot, server: FakeServer
) -> None:
    member = server.add(MEMBER_ID, HELPER_ROLE)
    toggle = Toggle(holds=True)

    await toggle.press(bot, server, member)

    assert toggle.answers == [
        "♪ There are no help pings right now: staff haven't set a role."
    ]
    assert toggle.redrawn is None
    member.remove_roles.assert_not_awaited()
    member.add_roles.assert_not_awaited()


async def test_a_toggle_that_fails_is_reported_and_records_nothing(
    bot: app.WispBot, server: FakeServer
) -> None:
    await set_role(bot)
    member = server.add(MEMBER_ID, HELPER_ROLE)
    member.remove_roles.side_effect = forbidden()
    toggle = Toggle(holds=True)

    await toggle.press(bot, server, member)

    (report,) = server.sent()
    assert report.startswith("Error in the help pings button: Forbidden:")
    assert (await bot.players.get(GUILD_ID, MEMBER_ID)).help_pings_off is False
    assert toggle.redrawn is None


# ---
# Registration
# ---


async def test_the_command_and_the_button_survive_a_restart(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_dynamic_items = MagicMock()
    monkeypatch.setattr(bot, "add_dynamic_items", add_dynamic_items)

    await help_pings.setup(bot)

    add_dynamic_items.assert_called_once_with(HelpPingsButton)
    assert bot.get_command("helperrole") is helperrole
    assert bot.get_command("helperrole off") is helperrole_off
    assert "cogs.help_pings" in app.EXTENSIONS


async def test_the_button_is_rebuilt_from_its_fixed_custom_id() -> None:
    item = discord.ui.Button[discord.ui.View](label=GET_LABEL, custom_id=HELP_PINGS_ID)
    match = HelpPingsButton.__discord_ui_compiled_template__.fullmatch(HELP_PINGS_ID)
    assert match is not None

    rebuilt = await HelpPingsButton.from_custom_id(MagicMock(), item, match)

    assert rebuilt.item.custom_id == HELP_PINGS_ID
    assert rebuilt.item.style is discord.ButtonStyle.secondary
