"""Private menus: the selects of the Vault and the snack menu.

A menu lives only in the memory of the bot that sent it. It never times out
(`Lasting`), and every menu select's custom id carries this run's token.
After a restart the old menu's selects still show; `ClosedMenu` catches a
press on one and tells the member to open the menu again. A press on a menu this run
sent goes to the menu itself: discord.py offers every press to the dynamic
items as well as to the live view, so `ClosedMenu` turns away this run's
token and each press is answered once.
"""

import re
import secrets
from typing import Any, Final

import discord

RUN: Final = secrets.token_hex(4)
CLOSED: Final = (
    "♪ This menu closed when Wisp restarted. Open it again from the Status post."
)


class Lasting:
    """Makes a menu view never time out, whatever a send sets.

    discord.py gives a private follow-up's view 15 minutes when it has none;
    this timeout stays None, so the menu lasts until the bot restarts.
    """

    @property
    def timeout(self) -> float | None:
        """Always None: the menu never times out."""
        return None

    @timeout.setter
    def timeout(self, value: float | None) -> None:
        """Ignore the timeout a send would set."""


def menu_id(slot: str, run: str = RUN) -> str:
    """The custom id of `run`'s `slot` select, such as "snacks"."""
    return f"wisp:menu:{run}:{slot}"


class ClosedMenu(
    discord.ui.DynamicItem[discord.ui.Select[Any]],
    template=re.compile(r"wisp:menu:(?P<run>[0-9a-f]{8}):(?P<slot>[a-z]+)"),
):
    """A select of a menu sent before Wisp last restarted.

    It answers the press privately, so the member is never shown "This
    interaction failed". A select of a menu sent since the restart is left to
    that menu.
    """

    def __init__(self, slot: str, run: str) -> None:
        super().__init__(discord.ui.Select(custom_id=menu_id(slot, run)))
        self.run = run

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[Any],
        match: re.Match[str],
        /,
    ) -> "ClosedMenu":
        """Rebuild the select a press reached."""
        return cls(match["slot"], match["run"])

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """Only a menu from an earlier run is closed; this run's menus answer."""
        return self.run != RUN

    async def callback(self, interaction: discord.Interaction) -> None:
        """Tell the member the menu closed and where to open it again."""
        await interaction.response.send_message(CLOSED, ephemeral=True)
