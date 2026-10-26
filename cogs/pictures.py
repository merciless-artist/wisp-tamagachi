"""Wisp's own picture and attaching it to a message that keeps showing him.

The status card and the House's Poke Wisp panel both show Wisp as he is now
and share the fallback for a picture Discord refuses.
"""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord

from cogs.assets import ASSETS_DIR
from wisp.life import Life, Phase, is_sick
from wisp.rules import SICK_PICTURES, Stage

if TYPE_CHECKING:
    from app import WispBot


def life_image(life: Life) -> Path | None:
    """Return the existing picture of Wisp as he is now, or None.

    An egg, hatching or not, is the egg picture; an egg from coal is the coal
    egg's own picture when it exists. A living Wisp is his stage's picture,
    or while he is sick his stage's sick picture when there is one. A life
    that is over has none.
    """
    stages = ASSETS_DIR / "stages"
    candidates: list[Path] = []
    match life.phase:
        case Phase.EGG | Phase.HATCHING:
            if life.from_coal:
                candidates.append(stages / "coal_egg.png")
            candidates.append(stages / "egg.png")
        case Phase.ALIVE:
            if is_sick(life) and (sick := sick_image(life.stage)) is not None:
                return sick
            candidates.append(stages / f"{life.stage.value}.png")
    return next((path for path in candidates if path.is_file()), None)


def sick_image(stage: Stage) -> Path | None:
    """The stage's sick picture when it exists, or None."""
    name = SICK_PICTURES.get(stage)
    if name is None:
        return None
    path = ASSETS_DIR / "moments" / name
    return path if path.is_file() else None


def art_kwargs(field: str, art: discord.File | None) -> dict[str, Any]:
    """The keyword that attaches `art`: "attachments" for an edit, "file" to send."""
    if art is None:
        return {}
    return {field: [art] if field == "attachments" else art}


class Picture:
    """Attaches a display's picture, falling back to no picture when refused."""

    def __init__(
        self,
        bot: "WispBot",
        guild_id: int,
        where: discord.abc.Messageable | None,
        message_attr: str,
        label: str,
    ) -> None:
        self._bot = bot
        self._guild_id = guild_id
        self._where = where
        self._key = (guild_id, f"{message_attr} picture")
        self._label = label

    async def attach(
        self,
        image: Path | None,
        send: Callable[[discord.File | None], Awaitable[discord.Message]],
    ) -> tuple[discord.Message, str | None]:
        """Send with `image` attached; return the message and the picture's name.

        The name is None when no picture was attached.

        A refused picture is sent again without it, then reported in `where`
        once per streak. A missing message (NotFound) is raised for the caller.
        """
        if image is None:
            return await send(None), None
        try:
            message = await send(discord.File(image))
        except discord.NotFound:
            raise
        except discord.HTTPException as error:
            message = await send(None)
            if self._key not in self._bot.failing_displays:
                self._bot.failing_displays.add(self._key)
                await self._bot.report_error(
                    self._bot.get_guild(self._guild_id),
                    f"attaching the {self._label} picture",
                    error,
                    where=self._where,
                )
            return message, None
        self._bot.failing_displays.discard(self._key)
        return message, image.name
