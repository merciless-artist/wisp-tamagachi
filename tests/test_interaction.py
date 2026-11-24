"""Tests for the Interaction post: Myra's lines, each with its button.

Discord objects are fakes; the settings repository is the real one.
"""

from collections.abc import Iterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import interaction
from cogs.conversation import PokeButton
from cogs.interaction import (
    Interaction,
    interaction_layout,
    interaction_lines,
    show_interaction,
)
from cogs.rhyme_duel import PlayButton
from cogs.snacks import FeedButton, ShopButton, SnackPackButton
from cogs.studio import STUDIO_ENSURED, StudioError
from cogs.wisp_lunchbox import LunchboxButton
from db.database import Database
from db.settings import SettingsRepo

GUILD_ID = 100
INTERACTION_ID = 70
SHOP_ID = 60
CARD_ID = 9001
VAULT_LINK = f"https://discord.com/channels/{GUILD_ID}/{SHOP_ID}"
NO_PING = discord.AllowedMentions.none().to_dict()
LINES = [
    "Feed Wisp a treat other than a music track!",
    "Poke Wisp to earn engagement points and Wisp Coins!",
    "Visit the ViiBR Vault to buy presents and vanity roles!",
    "Check your Snack Pack items here or check your personal storage locker",
    "Play games with Wisp!",
    "Check out Wisp's Lunchbox with his favorite songs, toys and more!",
]

# ---
# Fakes
# ---


class FakePost:
    """The Interaction post, which keeps its card and what was sent to it."""

    def __init__(self) -> None:
        self.thread = MagicMock(spec=discord.Thread)
        self.thread.id = INTERACTION_ID
        self.thread.send = AsyncMock(side_effect=self._send)
        self.thread.get_partial_message.side_effect = self._partial
        self.cards: set[int] = set()
        self.edits: list[dict[str, Any]] = []
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID

    async def _send(self, **kwargs: Any) -> MagicMock:
        card_id = CARD_ID + len(self.cards)
        self.cards.add(card_id)
        return MagicMock(spec=discord.Message, id=card_id)

    def _partial(self, message_id: int) -> MagicMock:
        async def edit(**kwargs: Any) -> None:
            if message_id not in self.cards:
                raise discord.NotFound(MagicMock(status=404), "Unknown Message")
            self.edits.append({"id": message_id, **kwargs})

        partial = MagicMock(spec=discord.PartialMessage)
        partial.edit = AsyncMock(side_effect=edit)
        return partial


@pytest.fixture
def post(monkeypatch: pytest.MonkeyPatch) -> FakePost:
    fake = FakePost()

    async def thread(_bot: app.WispBot, _guild_id: int, attr: str) -> MagicMock:
        assert attr == "interaction_thread_id"
        return fake.thread

    monkeypatch.setattr(interaction, "studio_thread", thread)
    return fake


@pytest.fixture
def bot(
    db: Database, post: FakePost, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.report_error = AsyncMock()  # type: ignore[method-assign]
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: post.guild)
    yield wisp_bot


async def set_up(bot: app.WispBot, **values: Any) -> None:
    await bot.settings.update(GUILD_ID, interaction_thread_id=INTERACTION_ID, **values)


def card_parts(view: discord.ui.LayoutView) -> list[tuple[str, discord.ui.Item[Any]]]:
    """The card's text displays, each paired with the one button on the row after it."""
    children = list(view.children)
    parts = []
    for text, row in zip(children[::2], children[1::2], strict=True):
        assert isinstance(text, discord.ui.TextDisplay)
        assert isinstance(row, discord.ui.ActionRow)
        (button,) = row.children
        parts.append((text.content, button))
    return parts


def label(button: discord.ui.Item[Any]) -> str | None:
    shown = button.item if isinstance(button, discord.ui.DynamicItem) else button
    assert isinstance(shown, discord.ui.Button)
    return shown.label


# ---
# The card
# ---


async def test_each_line_is_followed_by_its_persistent_button() -> None:
    parts = card_parts(interaction_layout(None))

    assert [text for text, _ in parts] == LINES
    assert [
        (type(button), label(button), button.item.custom_id)
        for _, button in parts
        if isinstance(button, discord.ui.DynamicItem)
    ] == [
        (FeedButton, "Feed WiSP", "wisp:feed"),
        (PokeButton, "Poke", "wisp:poke"),
        (ShopButton, "ViiBR Vault", "wisp:vault"),
        (SnackPackButton, "Snack Pack", "wisp:snackpack"),
        (PlayButton, "Games", "wisp:play"),
        (LunchboxButton, "Lunchbox", "wisp:lunchbox"),
    ]
    assert interaction_layout(None).timeout is None


async def test_with_a_vault_post_the_vault_button_jumps_to_it() -> None:
    text, vault = card_parts(interaction_layout(VAULT_LINK))[2]

    assert text == LINES[2]
    assert isinstance(vault, discord.ui.Button)
    assert (vault.label, vault.url, vault.style) == (
        "ViiBR Vault",
        VAULT_LINK,
        discord.ButtonStyle.link,
    )


async def test_the_lines_match_the_card() -> None:
    lines = interaction_lines(VAULT_LINK)
    parts = card_parts(interaction_layout(VAULT_LINK))

    assert [(text, label(button)) for text, button in lines] == [
        (text, label(button)) for text, button in parts
    ]


# ---
# Drawing the post
# ---


async def test_a_post_without_a_card_gets_one_with_the_vault_link(
    bot: app.WispBot, post: FakePost
) -> None:
    await set_up(bot, shop_thread_id=SHOP_ID)

    await show_interaction(bot, GUILD_ID)

    post.thread.send.assert_awaited_once()
    kwargs = post.thread.send.await_args.kwargs
    assert kwargs["allowed_mentions"].to_dict() == NO_PING
    _, vault = card_parts(kwargs["view"])[2]
    assert isinstance(vault, discord.ui.Button)
    assert vault.url == VAULT_LINK
    assert (await bot.settings.get(GUILD_ID)).interaction_message_id == CARD_ID


async def test_the_card_is_edited_in_place_when_drawn_again(
    bot: app.WispBot, post: FakePost
) -> None:
    await set_up(bot)
    await show_interaction(bot, GUILD_ID)
    await bot.settings.update(GUILD_ID, shop_thread_id=SHOP_ID)

    await show_interaction(bot, GUILD_ID)

    post.thread.send.assert_awaited_once()
    (edit,) = post.edits
    assert edit["id"] == CARD_ID
    assert edit["allowed_mentions"].to_dict() == NO_PING
    _, vault = card_parts(edit["view"])[2]
    assert isinstance(vault, discord.ui.Button)
    assert vault.url == VAULT_LINK


async def test_a_card_that_is_gone_is_posted_again(
    bot: app.WispBot, post: FakePost
) -> None:
    await set_up(bot, interaction_message_id=1234)

    await show_interaction(bot, GUILD_ID)

    post.thread.send.assert_awaited_once()
    assert post.edits == []
    assert (await bot.settings.get(GUILD_ID)).interaction_message_id == CARD_ID


async def test_a_guild_without_the_post_is_left_alone(
    bot: app.WispBot, post: FakePost
) -> None:
    await show_interaction(bot, GUILD_ID)

    post.thread.send.assert_not_awaited()
    bot.report_error.assert_not_awaited()  # type: ignore[attr-defined]


async def test_a_failed_post_is_reported_not_raised(
    bot: app.WispBot, post: FakePost
) -> None:
    await set_up(bot)
    refused = discord.Forbidden(MagicMock(status=403), "Missing Permissions")
    post.thread.send.side_effect = refused

    await show_interaction(bot, GUILD_ID)

    bot.report_error.assert_awaited_once_with(  # type: ignore[attr-defined]
        post.guild, "drawing the Interaction post", refused, where=post.thread
    )
    assert (await bot.settings.get(GUILD_ID)).interaction_message_id is None


async def test_an_unreachable_studio_is_reported_in_the_house(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await set_up(bot)
    missing = StudioError("The Studio forum is not set. Run !wisp setup first.")

    async def thread(_bot: app.WispBot, _guild_id: int, _attr: str) -> MagicMock:
        raise missing

    monkeypatch.setattr(interaction, "studio_thread", thread)

    await show_interaction(bot, GUILD_ID)

    bot.report_error.assert_awaited_once_with(  # type: ignore[attr-defined]
        bot.get_guild(GUILD_ID), "drawing the Interaction post", missing, where=None
    )


async def test_ensuring_the_studio_draws_the_post(
    bot: app.WispBot, post: FakePost
) -> None:
    await set_up(bot)
    cog = Interaction(bot)
    listener = getattr(cog, f"on_{STUDIO_ENSURED}")

    await listener(GUILD_ID)

    post.thread.send.assert_awaited_once()
