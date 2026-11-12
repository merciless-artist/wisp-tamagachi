"""Reading Wisp's layouts the way a member sees them, for the tests."""

from typing import Any

import discord

from wisp.text import UNICODE_FRAME, Frame, visual_width


def assert_fits_its_frame(text: str, frame: Frame) -> None:
    """Myra's v3 frame holds: every line is a section break or opens with the
    frame's edge, the box closes with the frame's bottom line, and nothing
    looks wider than it."""
    lines = text.split("\n")
    assert lines[-1] == frame.bottom
    for line in lines[:-1]:
        assert line == frame.section_break or line.startswith(frame.blank), line
        assert visual_width(line) <= frame.room, line


def rows(frame: Frame, *lines: str) -> list[str]:
    """`lines` as a menu shows them: each wrapped to fit `frame`."""
    return "\n".join(frame.wrapped(lines)).split("\n")


def entries(lines: list[str], frame: Frame = UNICODE_FRAME) -> list[str]:
    """`lines` with each wrapped line's rows joined back into one entry."""
    joined: list[str] = []
    for line in lines:
        if line.startswith(frame.continuation) and joined:
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


def vault_parts(send: Any) -> list[discord.ui.LayoutView]:
    """The two parts of the Vault `send`, a mocked follow-up send, sent last."""
    calls = send.await_args_list[-2:]
    assert len(calls) == 2
    return [call.kwargs["view"] for call in calls]


def vault_opened(send: Any) -> tuple[str, list[discord.ui.Select[Any]]]:
    """The Vault `send` sent last: both parts' text, one line apart, and every
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
