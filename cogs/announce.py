"""Announcements in Wisp's House, shared by the feeding listener and the life loop."""

from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord

from cogs.assets import ASSETS_DIR
from cogs.studio import StudioError, studio_thread
from wisp.life import Event, EventKind, Life, is_over, mood, new_egg
from wisp.lines import FIELDS, Moment

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_ENDINGS: Final = frozenset({EventKind.DIED, EventKind.EGG_COLD})
_BABY_STAGE: Final = "baby"

# ---
# Images
# ---


def _image_for(event: Event) -> Path | None:
    """Return the first existing image for an event, or None for text only."""
    stages = ASSETS_DIR / "stages"
    events = ASSETS_DIR / "events"
    candidates: list[Path] = []
    match event.kind:
        case EventKind.STAGE_UP if event.stage is not None:
            candidates = [stages / f"{event.stage.value}.png"]
        case EventKind.HATCHED:
            candidates = [stages / f"{_BABY_STAGE}.png", events / "hatched.png"]
        case EventKind.DIED | EventKind.EGG_COLD:
            candidates = [events / f"{event.kind.value}.png"]
    return next((path for path in candidates if path.is_file()), None)


# ---
# Wisp's House
# ---


class _House:
    """Wisp's House channel, resolved once so a missing one is reported once."""

    def __init__(self, bot: "WispBot", guild_id: int) -> None:
        self._bot = bot
        self._guild_id = guild_id
        self._guild: discord.Guild | None = None
        self._channel: discord.abc.Messageable | None = None

    async def open(self) -> None:
        """Find the House channel, or report to staff that it cannot be found."""
        self._guild = self._bot.get_guild(self._guild_id)
        settings = await self._bot.settings.get(self._guild_id)
        found = (
            self._guild.get_channel_or_thread(settings.house_channel_id)
            if self._guild is not None and settings.house_channel_id is not None
            else None
        )
        if isinstance(found, discord.abc.Messageable):
            self._channel = found
            return
        await self._bot.report_error(
            self._guild,
            "posting to Wisp's House",
            LookupError("the House channel is not set or cannot be seen"),
        )

    async def say(
        self,
        text: str,
        image: Path | None = None,
        view: discord.ui.View | None = None,
    ) -> None:
        """Post a line, with an image or buttons when given.

        A failure is reported to staff.
        """
        if self._channel is None:
            return
        extras: dict[str, Any] = {}
        if image is not None:
            extras["file"] = discord.File(image)
        if view is not None:
            extras["view"] = view
        try:
            await self._channel.send(text, allowed_mentions=_NO_PING, **extras)
        except discord.DiscordException as error:
            await self._bot.report_error(self._guild, "posting to Wisp's House", error)


# ---
# Events
# ---


def _fields(
    moment: Moment, version: int, event: Event | None, name: str | None
) -> dict[str, str]:
    available = {"version": str(version)}
    if event is not None and event.stage is not None:
        available["stage"] = event.stage.value
    if name is not None:
        available["name"] = name
    return {field: available[field] for field in FIELDS[moment]}


def _line(
    bot: "WispBot",
    moment: Moment,
    life: Life,
    event: Event | None = None,
    name: str | None = None,
) -> str:
    return bot.lines.pick(
        moment, mood(life), **_fields(moment, life.version, event, name)
    )


async def say_in_house(
    bot: "WispBot",
    guild_id: int,
    moment: Moment,
    life: Life,
    *,
    name: str | None = None,
    prefix: str = "",
    image: Path | None = None,
    view: discord.ui.View | None = None,
) -> None:
    """Say one line for a moment in Wisp's House, in the mood of `life`.

    `name` fills the line's name when the moment has one, `prefix` goes in front
    of the line, `image` attaches a file and `view` adds buttons.
    A missing House channel is reported to staff.
    """
    house = _House(bot, guild_id)
    await house.open()
    await house.say(prefix + _line(bot, moment, life, name=name), image, view)


async def _lay_next_egg(bot: "WispBot", guild_id: int, house: _House) -> None:
    """Insert the next egg once the current life is over, then announce it."""
    async with bot.guild_lock(guild_id):
        ended = await bot.lives.current(guild_id)
        if ended is None or not is_over(ended):
            return
        egg = await bot.lives.insert(
            guild_id,
            new_egg(await bot.lives.next_version(guild_id), discord.utils.utcnow()),
        )
    await house.say(_line(bot, Moment.NEW_EGG, egg))


async def post_events(bot: "WispBot", guild_id: int, events: list[Event]) -> None:
    """Announce life events in Wisp's House.

    Each event is spoken in Wisp's voice with the image for it when one exists.
    A death or a cold egg is followed by the next egg being laid and announced,
    unless the current life is not over, which means the ending is stale.
    A missing House channel is reported to staff once; the eggs are still laid.
    """
    if not events:
        return
    life = await bot.lives.current(guild_id)
    if life is None:
        return
    house = _House(bot, guild_id)
    await house.open()
    for event in events:
        if event.kind in _ENDINGS and not is_over(life):
            continue
        moment = Moment(event.kind.value)
        await house.say(_line(bot, moment, life, event), _image_for(event))
        if event.kind in _ENDINGS:
            await _lay_next_egg(bot, guild_id, house)


# ---
# Pinned messages
# ---


async def show_in_thread(
    bot: "WispBot",
    guild_id: int,
    thread_attr: str,
    message_attr: str,
    content: str,
    label: str,
    view: discord.ui.View | None = None,
) -> None:
    """Keep one pinned message in a Studio thread showing `content`.

    Args:
        bot: The running bot.
        guild_id: The guild whose Studio to use.
        thread_attr: The Settings field of the thread, such as "status_thread_id".
        message_attr: The Settings field of the message, such as
            "status_message_id".
        content: The message text.
        label: What the message is, for error reports ("status card").
        view: Buttons to show on the message, or None to leave it as it is.

    The stored message is edited. If it is gone, a new one is posted, pinned and
    stored. A failure is reported to staff once per streak of failures and never
    raised, so one broken display cannot stop the rest of a tick.
    """
    key = (guild_id, message_attr)
    try:
        await _show(bot, guild_id, thread_attr, message_attr, content, label, view)
    except (discord.DiscordException, StudioError) as error:
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                bot.get_guild(guild_id), f"updating the {label}", error
            )
    else:
        bot.failing_displays.discard(key)


async def _show(
    bot: "WispBot",
    guild_id: int,
    thread_attr: str,
    message_attr: str,
    content: str,
    label: str,
    view: discord.ui.View | None,
) -> None:
    extras: dict[str, Any] = {} if view is None else {"view": view}
    thread = await studio_thread(bot, guild_id, thread_attr)
    message_id: int | None = getattr(await bot.settings.get(guild_id), message_attr)
    if message_id is not None:
        try:
            await thread.get_partial_message(message_id).edit(
                content=content, allowed_mentions=_NO_PING, **extras
            )
            return
        except discord.NotFound:
            pass
    posted = await thread.send(content, allowed_mentions=_NO_PING, **extras)
    await bot.settings.update(guild_id, **{message_attr: posted.id})
    try:
        await posted.pin()
    except discord.HTTPException as error:
        await bot.report_error(bot.get_guild(guild_id), f"pinning the {label}", error)
