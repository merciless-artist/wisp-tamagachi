"""Reading Wisp's layouts the way a member sees them, for the tests."""

from typing import Any

import discord

from wisp.text import CONTINUATION, WIDTHS, box_room, visual_width


def assert_fits_its_box(text: str) -> None:
    """The house style frame holds: nothing passes the box, the box lines have
    the same number of `═` and the two bars look as wide as each other."""
    lines = text.split("\n")
    top = next(index for index, line in enumerate(lines) if line.startswith("╔"))
    bottom = next(index for index, line in enumerate(lines) if line.startswith("╚"))
    width = lines[top].count("═")
    assert lines[top] == "╔" + "═" * width + "╗"
    assert lines[bottom] == "╚" + "═" * width + "╝"
    for line in lines[top + 1 : bottom]:
        assert visual_width(line) <= box_room(width), line
    title_bar, bottom_bar = lines[top - 1], lines[bottom + 1]
    gap = abs(visual_width(title_bar) - visual_width(bottom_bar))
    assert gap <= WIDTHS["staff"] / 2, (title_bar, bottom_bar)


def entries(lines: list[str]) -> list[str]:
    """`lines` with each wrapped line's rows joined back into one entry."""
    joined: list[str] = []
    for line in lines:
        if line.startswith(CONTINUATION) and joined:
            joined[-1] += "\n" + line
        else:
            joined.append(line)
    return joined


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
