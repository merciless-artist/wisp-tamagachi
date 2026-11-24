"""Reading Wisp's layouts the way a member sees them, for the tests."""

from typing import Any

import discord

from wisp.text import (
    FOOTER_BAR,
    FOOTER_MIC,
    SECTION_ICONS,
    TITLE_BAR,
    UNICODE_FRAME,
    Frame,
)

# Every app emoji WiSP's Favorites style is made of, each once.
STYLE_EMOJIS = tuple(
    dict.fromkeys((*TITLE_BAR, *FOOTER_BAR, FOOTER_MIC, *SECTION_ICONS))
)
# The v3 frame's emojis, which no menu draws any more.
_OLD_FRAME = ("header_edge", "rest_bar", "header2", "header3", ":clef:")


def assert_is_a_menu(text: str, frame: Frame, title: str | None = None) -> None:
    """WiSP's Favorites style holds: the text opens with the title line of
    `title` when given, closes with the footer line, has no empty line and
    none of the v3 frame's edge and bar emojis."""
    lines = text.split("\n")
    if title is not None:
        assert lines[0] == frame.title(title)
    assert lines[-1] == frame.footer
    for line in lines:
        assert line, text
        assert not any(old in line for old in _OLD_FRAME), line


def section(lines: list[str], heading: str, frame: Frame = UNICODE_FRAME) -> list[str]:
    """The lines under the `heading` line, up to the next heading or the footer."""
    start = lines.index(heading) + 1
    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith("## ") or lines[index] == frame.footer
        ),
        len(lines),
    )
    return lines[start:end]


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


def vault_parts(send: Any) -> list[discord.ui.LayoutView]:
    """The three parts of the Vault `send`, a mocked follow-up send, sent last."""
    calls = send.await_args_list[-3:]
    assert len(calls) == 3
    return [call.kwargs["view"] for call in calls]


def vault_opened(send: Any) -> tuple[str, list[discord.ui.Select[Any]]]:
    """The Vault `send` sent last: every part's text, one line apart, and every
    select in order."""
    parts = vault_parts(send)
    text = "\n".join(layout_text(part) for part in parts)
    return text, [select for part in parts for select in layout_selects(part)]


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
