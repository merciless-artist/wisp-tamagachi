"""Tests for header pictures: every picture file is closed after its send."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs import headers
from cogs.headers import gallery_files, layout_text, send_framed

HEADER = "title.png"
OTHER = "other.png"


@pytest.fixture(autouse=True)
def pictures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in (HEADER, OTHER):
        (tmp_path / name).write_bytes(b"PNG")
    monkeypatch.setattr(headers, "ASSETS_DIR", tmp_path)
    return tmp_path


def is_closed(file: discord.File) -> bool:
    return bool(file.fp.closed)


def posted(components: list[Any]) -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.components = components
    return message


def text_display(content: str) -> discord.TextDisplay:
    return discord.TextDisplay({"type": 10, "content": content})


def test_layout_text_reads_a_posted_layouts_text_displays_in_order() -> None:
    message = posted([MagicMock(), text_display("one"), text_display("two")])

    assert layout_text(message) == "one\ntwo"


def test_a_message_from_before_v3_reads_as_no_text() -> None:
    assert layout_text(posted([])) == ""


def test_gallery_files_are_closed_when_the_block_ends() -> None:
    with gallery_files(HEADER, OTHER) as files:
        assert [file.filename for file in files] == [HEADER, OTHER]
        assert not any(is_closed(file) for file in files)

    assert all(is_closed(file) for file in files)


def test_gallery_files_are_closed_when_the_send_fails() -> None:
    with pytest.raises(OSError), gallery_files(HEADER, OTHER) as files:
        raise OSError("the send failed")

    assert all(is_closed(file) for file in files)


def test_gallery_files_leave_out_a_missing_picture(pictures: Path) -> None:
    (pictures / OTHER).unlink()

    with gallery_files(HEADER, OTHER) as files:
        assert [file.filename for file in files] == [HEADER]


# ---
# Framed menus (house style v3)
# ---


async def test_send_framed_sends_one_layout_of_the_header_and_the_text() -> None:
    send = AsyncMock()

    await send_framed(send, HEADER, "the text", allowed_mentions=None)

    call = send.await_args
    assert call is not None and call.args == ()
    (picture,) = call.kwargs["files"]
    assert picture.filename == HEADER and is_closed(picture)
    assert call.kwargs["allowed_mentions"] is None
    view = call.kwargs["view"]
    assert isinstance(view, discord.ui.LayoutView)
    gallery, text = view.children
    assert isinstance(gallery, discord.ui.MediaGallery)
    assert gallery.items[0].media.url == f"attachment://{HEADER}"
    assert isinstance(text, discord.ui.TextDisplay) and text.content == "the text"
    assert view.timeout is None


async def test_send_framed_puts_each_row_of_buttons_under_the_text() -> None:
    send = AsyncMock()
    first: list[discord.ui.Button[Any]] = [
        discord.ui.Button(label="a"),
        discord.ui.Button(label="b"),
    ]
    second: list[discord.ui.Button[Any]] = [discord.ui.Button(label="c")]

    sent = await send_framed(send, HEADER, "the text", [first, second])

    assert sent is send.return_value
    call = send.await_args
    assert call is not None
    _, text, *rows = call.kwargs["view"].children
    assert isinstance(text, discord.ui.TextDisplay)
    assert all(isinstance(row, discord.ui.ActionRow) for row in rows)
    assert [[button.label for button in row.children] for row in rows] == [
        ["a", "b"],
        ["c"],
    ]


async def test_send_framed_closes_the_picture_when_the_send_fails() -> None:
    send = AsyncMock(side_effect=discord.HTTPException(MagicMock(status=500), "boom"))

    with pytest.raises(discord.HTTPException):
        await send_framed(send, HEADER, "the text")

    call = send.await_args
    assert call is not None
    assert all(is_closed(picture) for picture in call.kwargs["files"])


async def test_send_framed_leaves_out_a_missing_header(pictures: Path) -> None:
    (pictures / HEADER).unlink()
    send = AsyncMock()

    await send_framed(send, HEADER, "the text")

    call = send.await_args
    assert call is not None and call.kwargs["files"] == []
    (text,) = call.kwargs["view"].children
    assert isinstance(text, discord.ui.TextDisplay)
