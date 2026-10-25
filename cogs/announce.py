"""Announcements in Wisp's House and Mealtime, shared by the cogs that speak."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import discord
import pymysql

from cogs.assets import ASSETS_DIR, asset_image
from cogs.pictures import Picture, art_kwargs, life_image
from cogs.speech import ai_reply, poke_view
from cogs.studio import StudioError, studio_thread
from db.keepsakes import Keepsake, KeepsakeKind
from db.players import Player
from wisp.life import Event, EventKind, Life, Phase, egg_after, is_over, mood
from wisp.lines import FIELDS, Moment
from wisp.rules import LAST_EMBER_GIFTS, Stage
from wisp.voice import goodbye_prompt

if TYPE_CHECKING:
    from app import WispBot

_NO_PING: Final = discord.AllowedMentions.none()
_ENDINGS: Final = frozenset({EventKind.DIED, EventKind.EGG_COLD, EventKind.FAREWELL})
_NO_EGG: Final = "♪ No new egg for now. Staff can turn eggs back on with !wisp eggs on."
_BABY_STAGE: Final = "baby"
_GIVING: Final = "giving a keepsake"
_STAGE_KEEPSAKES: Final = {
    Stage.CHILD: KeepsakeKind.FIRST_SPARK,
    Stage.TEEN: KeepsakeKind.TEEN_SPARK,
    Stage.ADULT: KeepsakeKind.ADULT_SPARK,
    Stage.ROCKSTAR: KeepsakeKind.GUITAR_PICK,
}

# ---
# Images
# ---


def _image_for(event: Event) -> Path | None:
    """Return the first existing image for an event, or None for text only."""
    stages = ASSETS_DIR / "stages"
    events = ASSETS_DIR / "events"
    candidates: list[tuple[Path, str]] = []
    match event.kind:
        case EventKind.STAGE_UP | EventKind.GREW_OLD if event.stage is not None:
            candidates = [(stages, event.stage.value)]
        case EventKind.HATCHED:
            candidates = [(stages, _BABY_STAGE), (events, "hatched")]
        case (
            EventKind.HATCH_STARTED
            | EventKind.DIED
            | EventKind.EGG_COLD
            | EventKind.FAREWELL
        ):
            candidates = [(events, event.kind.value)]
    return next(
        (path for folder, name in candidates if (path := asset_image(folder, name))),
        None,
    )


def keepsake_image(kind: KeepsakeKind) -> Path | None:
    """Return a keepsake's picture when it exists, or None for text only."""
    return asset_image(ASSETS_DIR / "keepsakes", kind.value)


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
        self._opened = False

    async def open(self) -> None:
        """Find the House channel once, or report that it cannot be found."""
        if self._opened:
            return
        self._opened = True
        self._guild = self._bot.get_guild(self._guild_id)
        self._channel = await self._bot.house_channel(self._guild)
        if self._channel is not None:
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

        A failure is reported.
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
# Mealtime
# ---


async def say_in_mealtime(
    bot: "WispBot", guild: discord.Guild, text: str, context: str
) -> None:
    """Post in the Mealtime thread without pinging anyone.

    A failure is reported as `context`, in Mealtime, or in Wisp's House when
    Mealtime cannot be reached.
    """
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild.id, "mealtime_thread_id")
        await thread.send(text, allowed_mentions=_NO_PING)
    except (discord.DiscordException, StudioError) as error:
        await bot.report_error(guild, context, error, where=thread)


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
    A missing House channel is reported.
    """
    await post_in_house(
        bot, guild_id, prefix + _line(bot, moment, life, name=name), image, view
    )


async def post_in_house(
    bot: "WispBot",
    guild_id: int,
    text: str,
    image: Path | None = None,
    view: discord.ui.View | None = None,
) -> None:
    """Post text in Wisp's House, with an image or buttons when given.

    A missing House channel is reported.
    """
    house = _House(bot, guild_id)
    await house.open()
    await house.say(text, image, view)


async def post_events(bot: "WispBot", guild_id: int, events: list[Event]) -> None:
    """Announce life events in Wisp's House.

    Each event is spoken in Wisp's voice with the image for it when one exists.
    A death, a cold egg or a farewell is followed by the next life, unless the
    current life is not over, which means the ending is stale. Hatching, each
    stage up and growing old give a keepsake to the member who was there.
    A missing House channel is reported once; the next life still comes.
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
        if (kind := _milestone(event)) is not None:
            await _give_milestone(bot, guild_id, house, life, kind)
        if event.kind in _ENDINGS:
            await _next_life(bot, guild_id, house, discord.utils.utcnow(), ending=True)


# ---
# Milestone keepsakes
# ---


def _milestone(event: Event) -> KeepsakeKind | None:
    """The keepsake a big moment gives, or None for any other event."""
    match event.kind:
        case EventKind.HATCH_STARTED:
            return KeepsakeKind.EGGSHELL
        case EventKind.GREW_OLD:
            return KeepsakeKind.TIME_PIECE
        case EventKind.STAGE_UP if event.stage is not None:
            return _STAGE_KEEPSAKES.get(event.stage)
    return None


async def _give_milestone(
    bot: "WispBot", guild_id: int, house: _House, life: Life, kind: KeepsakeKind
) -> None:
    """Give a big moment's keepsake to the member who was there, and say so.

    The Eggshell goes to the member whose feed filled the egg; every other one
    to the member who last interacted with this life. Nobody gets it when
    there is no such member, when they are banned or when they already have it.
    A database or network failure is reported in Wisp's House and never stops
    the events after it.
    """
    if life.id is None:
        return
    try:
        user_id = (
            life.hatched_by
            if kind is KeepsakeKind.EGGSHELL
            else await bot.activity_log.latest_interactor(guild_id, life.id)
        )
        if user_id is None:
            return
        now = discord.utils.utcnow()
        player = await bot.players.get(guild_id, user_id)
        if player.is_banned(now):
            return
        keepsake = Keepsake(kind, life.version, now)
        if not await bot.keepsakes.give(guild_id, user_id, kind, life.version, now):
            return
        name = display_name(bot.get_guild(guild_id), player)
    except (pymysql.err.Error, OSError) as error:
        await bot.report_error(bot.get_guild(guild_id), _GIVING, error)
        return
    won = _line(bot, Moment.KEEPSAKE_WON, life, name=name)
    await house.say(f"♪ {name} gets {keepsake.title}\n{won}", keepsake_image(kind))


# ---
# The next life
# ---


@dataclass(frozen=True)
class _Embers:
    """A full life's Last Ember and the members it was newly given to."""

    life: Life
    ember: Keepsake
    receivers: tuple[Player, ...]


async def next_life(bot: "WispBot", guild_id: int, now: datetime) -> None:
    """Follow an ended life, or no life at all, with the next egg.

    After a full life its top sharers who are not banned get its Last Ember and
    the egg is a coal egg; after any other ending, or none, it is a fresh egg.
    A failure while announcing one member's ember is reported in Wisp's House
    and the rest still come.
    Nothing happens while the current life goes on, so calling this twice is
    safe. Wisp's House hears who got an ember, each with a goodbye from his AI
    voice, then the new egg. While staff have new eggs turned off, the embers
    are still given but no egg is laid.
    Takes `bot.guild_lock`, so it must be called outside it. The goodbyes are
    written after the lock is released, since AI calls take seconds.
    """
    await _next_life(bot, guild_id, _House(bot, guild_id), now, ending=False)


async def _next_life(
    bot: "WispBot", guild_id: int, house: _House, now: datetime, *, ending: bool
) -> None:
    """Give any Last Embers and lay the next egg, when eggs are on.

    With eggs off and `ending` set, which is only when the ending itself is
    announced, the House is told once that no egg is coming.
    """
    async with bot.guild_lock(guild_id):
        ended = await bot.lives.current(guild_id)
        if ended is not None and not is_over(ended):
            return
        embers = await _give_last_embers(bot, guild_id, ended, now)
        egg = None
        if (await bot.settings.get(guild_id)).lay_eggs:
            version = await bot.lives.next_version(guild_id)
            egg = await bot.lives.insert(guild_id, egg_after(ended, version, now))
    if egg is None and not ending and (embers is None or not embers.receivers):
        return
    await house.open()
    if embers is not None:
        guild = bot.get_guild(guild_id)
        for player in embers.receivers:
            name = display_name(guild, player)
            try:
                notes = await bot.notes.recent(guild_id, player.user_id)
            except (pymysql.err.Error, OSError) as error:
                await bot.report_error(guild, _GIVING, error)
                continue
            heading = f"♪ {name} gets {embers.ember.title}"
            goodbye = await _goodbye(bot, guild, embers.life, name, notes)
            await house.say(
                f"{heading}\n{goodbye}", keepsake_image(KeepsakeKind.LAST_EMBER)
            )
    if egg is None:
        if ending:
            await house.say(_NO_EGG)
        return
    moment = Moment.COAL_EGG if egg.from_coal else Moment.NEW_EGG
    await house.say(_line(bot, moment, egg), life_image(egg), poke_view())


async def _give_last_embers(
    bot: "WispBot", guild_id: int, ended: Life | None, now: datetime
) -> _Embers | None:
    """Give a full life's Last Ember to its top sharers who are not banned."""
    if ended is None or ended.phase is not Phase.PASSED or ended.id is None:
        return None
    ember = Keepsake(KeepsakeKind.LAST_EMBER, ended.version, now)
    receivers: list[Player] = []
    top = await bot.activity_log.top_this_life(guild_id, ended.id, LAST_EMBER_GIFTS)
    for user_id, _points in top:
        player = await bot.players.get(guild_id, user_id)
        if player.is_banned(now):
            continue
        if await bot.keepsakes.give(
            guild_id, user_id, ember.kind, ember.version, ember.given_at
        ):
            receivers.append(player)
    return _Embers(ended, ember, tuple(receivers))


def display_name(guild: discord.Guild | None, player: Player) -> str:
    """The name Wisp calls a member, else their server name, else a mention."""
    if player.name is not None:
        return player.name
    member = guild.get_member(player.user_id) if guild is not None else None
    return member.display_name if member is not None else f"<@{player.user_id}>"


async def _goodbye(
    bot: "WispBot",
    guild: discord.Guild | None,
    life: Life,
    name: str,
    notes: list[str],
) -> str:
    """Wisp's goodbye to one member he gives his Last Ember to.

    It is in his AI voice, with what he remembers about them, or his canned
    line when the AI has no answer.
    """
    reply = await ai_reply(bot, guild, goodbye_prompt(life.version, name, notes))
    if reply is None:
        return _line(bot, Moment.LAST_EMBER, life, name=name)
    return reply.text


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
    image: Path | None = None,
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
        image: The picture the message shows, or None to leave its picture as
            it is.

    The stored message is edited. If it is gone, a new one is posted, pinned and
    stored. The picture is uploaded only when it is not the one this process
    last attached to that message, so an unchanged picture is not sent every
    tick; after a restart it is attached once more. When Discord refuses the
    picture, the message is updated without it and the refusal is posted on
    its own, once per streak.

    A failure is posted in the thread, or in Wisp's House when the thread
    cannot be reached, once per streak of failures. It is never raised,
    so one broken display cannot stop the rest of a tick.
    """
    key = (guild_id, message_attr)
    thread: discord.Thread | None = None
    try:
        thread = await studio_thread(bot, guild_id, thread_attr)
        await _show(bot, guild_id, thread, message_attr, content, label, view, image)
    except (discord.DiscordException, StudioError) as error:
        if key not in bot.failing_displays:
            bot.failing_displays.add(key)
            await bot.report_error(
                bot.get_guild(guild_id), f"updating the {label}", error, where=thread
            )
    else:
        bot.failing_displays.discard(key)


async def _show(
    bot: "WispBot",
    guild_id: int,
    thread: discord.Thread,
    message_attr: str,
    content: str,
    label: str,
    view: discord.ui.View | None,
    image: Path | None,
) -> None:
    key = (guild_id, message_attr)
    picture = Picture(bot, guild_id, thread, message_attr, label)
    extras: dict[str, Any] = {} if view is None else {"view": view}
    message_id: int | None = getattr(await bot.settings.get(guild_id), message_attr)
    if message_id is not None:
        message = thread.get_partial_message(message_id)
        shown = image is not None and bot.shown_images.get(key) == (
            message_id,
            image.name,
        )
        try:
            _, attached = await picture.attach(
                None if shown else image,
                lambda art: message.edit(
                    content=content,
                    allowed_mentions=_NO_PING,
                    **extras,
                    **art_kwargs("attachments", art),
                ),
            )
        except discord.NotFound:
            pass
        else:
            if attached is not None:
                bot.shown_images[key] = (message_id, attached)
            return
    posted, attached = await picture.attach(
        image,
        lambda art: thread.send(
            content,
            allowed_mentions=_NO_PING,
            **extras,
            **art_kwargs("file", art),
        ),
    )
    if attached is not None:
        bot.shown_images[key] = (posted.id, attached)
    await bot.settings.update(guild_id, **{message_attr: posted.id})
    try:
        await posted.pin()
    except discord.HTTPException as error:
        await bot.report_error(
            bot.get_guild(guild_id), f"pinning the {label}", error, where=thread
        )
