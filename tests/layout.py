"""Reading a Components V2 layout the way a member sees it, for the tests."""

from typing import Any

import discord


def layout_text(view: discord.ui.LayoutView) -> str:
    """The layout's text displays joined in order, one line apart."""
    return "\n".join(
        child.content
        for child in view.walk_children()
        if isinstance(child, discord.ui.TextDisplay)
    )


def layout_selects(view: discord.ui.LayoutView) -> list[discord.ui.Select[Any]]:
    """The layout's selects in order."""
    return [
        child for child in view.walk_children() if isinstance(child, discord.ui.Select)
    ]


def layout_order(view: discord.ui.LayoutView) -> list[str]:
    """Each top-level piece: "text", or the placeholder of the select in a row."""
    order = []
    for child in view.children:
        if isinstance(child, discord.ui.TextDisplay):
            order.append("text")
        elif isinstance(child, discord.ui.ActionRow):
            (select,) = child.children
            assert isinstance(select, discord.ui.Select)
            order.append(select.placeholder or "")
    return order
