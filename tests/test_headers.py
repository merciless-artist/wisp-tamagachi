"""Tests for header pictures: every picture file is closed after its send."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs import headers
from cogs.headers import FOOTER, frame_of, gallery_files, send_framed, send_headed
from wisp.text import FRAME_EMOJIS, UNICODE_FRAME, emoji_frame

HEADER = "title.png"


@pytest.fixture(autouse=True)
def pictures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in (HEADER, FOOTER):
        (tmp_path / name).write_bytes(b"PNG")
    monkeypatch.setattr(headers, "ASSETS_DIR", tmp_path)
    return tmp_path


def sent_files(send: AsyncMock) -> list[discord.File]:
    files: list[discord.File] = []
    for call in send.await_args_list:
        files.extend([call.kwargs["file"]] if "file" in call.kwargs else [])
    return files


def is_closed(file: discord.File) -> bool:
    return bool(file.fp.closed)


async def test_send_headed_closes_both_pictures_after_sending() -> None:
    send = AsyncMock()

    await send_headed(send, HEADER, "the text", allowed_mentions=None)

    header, footer = sent_files(send)
    assert (header.filename, footer.filename) == (HEADER, FOOTER)
    assert send.await_args_list[1].args == ("the text",)
    assert is_closed(header) and is_closed(footer)


@pytest.mark.parametrize("failing", [0, 1])
async def test_send_headed_closes_both_pictures_when_a_send_fails(
    monkeypatch: pytest.MonkeyPatch, failing: int
) -> None:
    opened: list[discord.File] = []
    real_file = discord.File

    def opening(*args: Any, **kwargs: Any) -> discord.File:
        file = real_file(*args, **kwargs)
        opened.append(file)
        return file

    monkeypatch.setattr(discord, "File", opening)
    send = AsyncMock(
        side_effect=[
            (
                discord.HTTPException(MagicMock(status=500), "boom")
                if call == failing
                else None
            )
            for call in range(2)
        ]
    )

    with pytest.raises(discord.HTTPException):
        await send_headed(send, HEADER, "the text")

    assert len(opened) == 2
    assert all(is_closed(file) for file in opened)


async def test_send_headed_leaves_out_a_missing_picture(pictures: Path) -> None:
    (pictures / HEADER).unlink()
    send = AsyncMock()

    await send_headed(send, HEADER, "the text")

    (footer,) = sent_files(send)
    assert footer.filename == FOOTER
    assert send.await_count == 1


def test_gallery_files_are_closed_when_the_block_ends() -> None:
    with gallery_files(HEADER, FOOTER) as files:
        assert [file.filename for file in files] == [HEADER, FOOTER]
        assert not any(is_closed(file) for file in files)

    assert all(is_closed(file) for file in files)


def test_gallery_files_are_closed_when_the_send_fails() -> None:
    with pytest.raises(OSError), gallery_files(HEADER, FOOTER) as files:
        raise OSError("the send failed")

    assert all(is_closed(file) for file in files)


def test_gallery_files_leave_out_a_missing_picture(pictures: Path) -> None:
    (pictures / FOOTER).unlink()

    with gallery_files(HEADER, FOOTER) as files:
        assert [file.filename for file in files] == [HEADER]


# ---
# The emoji frame (house style v3)
# ---


def emoji_bot(*uploaded: str) -> MagicMock:
    """A bot whose `emoji` gives `<:name:1>` for the uploaded names, else ""."""
    bot = MagicMock()
    bot.emoji.side_effect = lambda name: f"<:{name}:1>" if name in uploaded else ""
    return bot


def test_the_frame_is_myras_emojis_when_all_are_uploaded() -> None:
    frame = frame_of(emoji_bot(*FRAME_EMOJIS))

    assert frame == emoji_frame(*(f"<:{name}:1>" for name in FRAME_EMOJIS))


@pytest.mark.parametrize("missing", FRAME_EMOJIS)
def test_one_missing_frame_emoji_falls_back_to_the_unicode_frame(missing: str) -> None:
    uploaded = [name for name in FRAME_EMOJIS if name != missing]

    assert frame_of(emoji_bot(*uploaded)) is UNICODE_FRAME


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
