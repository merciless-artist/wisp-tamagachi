"""Tests for private menus: they never time out, and close cleanly on a restart.

The menus go through a real discord.py ViewStore, so a press is dispatched
the way discord.py dispatches it; the interactions and messages are fakes.
"""

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord.components import ActionRow as RowComponent
from discord.ui.view import BaseView, ViewStore
from discord.webhook import async_ as async_webhook

from cogs.menus import CLOSED, RUN, ClosedMenu, menu_id
from cogs.snacks import Menu, ShopButton, SnackSelect, VaultLayout, _VaultPiece
from wisp.rules import SNACKS

MESSAGE_ID = 1234
SELECT_TYPE = discord.ComponentType.string_select.value
EARLIER_RUN = "00000000" if RUN != "00000000" else "ffffffff"

# ---
# Fakes
# ---


def snack_menu(chosen: list[str]) -> Menu:
    """The snack menu, noting each snack its select hands on."""

    async def on_choice(_interaction: discord.Interaction, snack: Any) -> None:
        chosen.append(snack.key)

    options = [
        discord.SelectOption(label=snack.name, value=snack.key) for snack in SNACKS
    ]
    return Menu(
        "the snack menu", SnackSelect(options, "Pick a snack", on_choice, "feed")
    )


def pressed(custom_id: str, value: str) -> MagicMock:
    """A press on the select `custom_id` of message MESSAGE_ID, choosing `value`."""
    row = RowComponent(
        {
            "type": 1,
            "components": [
                {
                    "type": SELECT_TYPE,
                    "custom_id": custom_id,
                    "options": [{"label": value, "value": value}],
                }
            ],
        }
    )
    interaction = MagicMock(spec=discord.Interaction)
    interaction.message = MagicMock(spec=discord.Message)
    interaction.message.id = MESSAGE_ID
    interaction.message.interaction_metadata = None
    interaction.message.flags = discord.MessageFlags()
    interaction.message.components = [row]
    interaction.data = {
        "custom_id": custom_id,
        "component_type": SELECT_TYPE,
        "values": [value],
    }
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    return interaction


async def dispatch(store: ViewStore, interaction: MagicMock) -> None:
    """Hand a press to the store as discord.py does, and let every task finish."""
    store.dispatch_view(SELECT_TYPE, interaction.data["custom_id"], interaction)
    for _ in range(5):
        await asyncio.sleep(0)


def store_with_closed_menus() -> ViewStore:
    store = ViewStore(MagicMock())
    store.add_dynamic_items(ClosedMenu)
    return store


# ---
# Menu ids
# ---


async def test_a_menu_select_carries_this_runs_token() -> None:
    menu = snack_menu([])
    (select,) = menu.children
    assert isinstance(select, discord.ui.Select)
    assert select.custom_id == menu_id("feed") == f"wisp:menu:{RUN}:feed"
    match = ClosedMenu.__discord_ui_compiled_template__.fullmatch(select.custom_id)
    assert match is not None
    assert (match["run"], match["slot"]) == (RUN, "feed")


def sent_message() -> dict[str, Any]:
    """What Discord answers an ephemeral follow-up with: the message it made."""
    return {
        "id": str(MESSAGE_ID),
        "channel_id": "1",
        "type": 0,
        "content": "",
        "attachments": [],
        "embeds": [],
        "mentions": [],
        "mention_roles": [],
        "pinned": False,
        "mention_everyone": False,
        "tts": False,
        "timestamp": "2026-11-06T00:00:00+00:00",
        "edited_timestamp": None,
        "flags": 64,
        "components": [],
        "author": {"id": "2", "username": "wisp", "discriminator": "0", "avatar": None},
    }


async def send_privately(view: BaseView, store: ViewStore) -> None:
    """Send `view` as an ephemeral follow-up through discord.py's real Webhook.send.

    Only the HTTP call is faked; the view goes into the real `store`.
    """
    adapter = MagicMock()
    adapter.execute_webhook = AsyncMock(return_value=sent_message())
    async_webhook.async_context.set(adapter)
    state = MagicMock()
    state.store_view.side_effect = lambda view, message_id: store.add_view(
        view, message_id
    )
    hook = discord.Webhook(
        {"id": 9, "type": 3, "token": "t", "application_id": 9},
        session=MagicMock(),
        state=state,
    )
    await hook.send(view=view, ephemeral=True, wait=True)


def vault_menu() -> VaultLayout:
    options = [
        discord.SelectOption(label=snack.name, value=snack.key) for snack in SNACKS
    ]
    select = SnackSelect(options, "Buy a snack", AsyncMock(), "snacks")
    return VaultLayout([_VaultPiece(["the Vault"], [select])])


@pytest.mark.parametrize("make", [lambda: snack_menu([]), vault_menu])
async def test_a_menu_sent_privately_never_times_out(
    make: Callable[[], BaseView],
) -> None:
    store = ViewStore(MagicMock())
    menu = make()

    await send_privately(menu, store)

    assert menu.timeout is None
    assert menu._BaseView__timeout_task is None  # type: ignore[attr-defined]
    assert not menu.is_finished()
    assert store._views[MESSAGE_ID]


async def test_a_menus_timeout_cannot_be_set() -> None:
    menu = snack_menu([])
    menu.timeout = 900.0
    assert menu.timeout is None


# ---
# Pressing a menu
# ---


async def test_a_press_on_a_live_menu_is_answered_by_the_menu_alone() -> None:
    chosen: list[str] = []
    store = store_with_closed_menus()
    store.add_view(snack_menu(chosen), MESSAGE_ID)
    interaction = pressed(menu_id("feed"), "cheese")

    await dispatch(store, interaction)

    assert chosen == ["cheese"]
    interaction.response.send_message.assert_not_awaited()


async def test_a_press_on_a_menu_from_before_a_restart_says_it_closed() -> None:
    chosen: list[str] = []
    store = store_with_closed_menus()
    store.add_view(snack_menu(chosen), MESSAGE_ID)
    interaction = pressed(menu_id("feed", EARLIER_RUN), "cheese")

    await dispatch(store, interaction)

    assert chosen == []
    interaction.response.send_message.assert_awaited_once_with(CLOSED, ephemeral=True)


async def test_the_closed_menu_turns_away_this_runs_menus_only() -> None:
    interaction = MagicMock(spec=discord.Interaction)
    assert not await ClosedMenu("feed", RUN).interaction_check(interaction)
    assert await ClosedMenu("feed", EARLIER_RUN).interaction_check(interaction)


def test_the_closed_menu_line() -> None:
    assert CLOSED == (
        "♪ This menu closed when Wisp restarted. Open it again from the Status post."
    )


# ---
# Persistent buttons in a menu
# ---


async def test_a_snack_pack_view_leaving_the_store_keeps_the_shop_button() -> None:
    """A view filed under its own message id never unregisters a dynamic item.

    Filed under the key a direct answer shares with the persistent views, its
    removal would unregister the Shop the Vault button for everyone.
    """
    store = ViewStore(MagicMock())
    other = discord.ui.View(timeout=None)
    other.add_item(discord.ui.Button(label="Other", custom_id="other"))
    store.add_view(other)
    pack = discord.ui.View(timeout=None)
    pack.add_item(ShopButton())
    store.add_view(pack, MESSAGE_ID)

    store.remove_view(pack)

    template = ShopButton.__discord_ui_compiled_template__
    assert store._dynamic_items[template] is ShopButton
