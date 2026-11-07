"""Tests for header pictures: every picture file is closed after its send."""

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from cogs import headers
from cogs.headers import FOOTER, gallery_files, send_headed

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
