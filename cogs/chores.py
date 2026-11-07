"""Chore posts in Wisp's House and the first-press buttons that do them.

A mess, a tantrum and a nap each post once with one button. The first member
who can feed Wisp to press it does the chore and earns its points; the post
then says who did it and loses its button. A chore that runs out edits its
post instead.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

import discord

from cogs.announce import edit_in_house, say_in_house
from cogs.assets import moment_image, nap_image
from cogs.groups import require_guild
from cogs.players import (
    EXPECTED_FAILURES,
    Refusal,
    bot_of,
    chore_refusal_text,
    member_blocker,
    report_failure,
    require_unfrozen,
    say_privately,
)
from wisp.chores import (
    ChoreEvent,
    ChoreEventKind,
    do_chore,
    drop_chore,
    is_napping,
    is_open,
    message_id,
    set_message_id,
    wake,
)
from wisp.life import Life, Phase, mood
from wisp.lines import Moment
from wisp.rules import (
    CHORE_POINTS,
    MESSES,
    SNIFFLES_PICTURE,
    TANTRUM_PICTURES,
    Chore,
    Stage,
)
from wisp.text import meter_receipt, with_emoji
from wisp.voice import MINI_COIN_EMOJI

if TYPE_CHECKING:
    from app import WispBot

CHORE_ID: Final = r"wisp:chore:(?P<chore>mess|tantrum|nap):(?P<life_id>[0-9]+)"
_NO_PING: Final = discord.AllowedMentions.none()
_CONTEXT: Final = "the chore button"
_ALREADY_DONE: Final = "♪ Someone already took care of that."
_NO_POST: Final = "♪ That post can't be found, so nothing was done."
_OLD_POST: Final = "♪ That post is from a Wisp who is gone now."
_NOT_ALIVE: Final = "♪ Wisp isn't alive right now, so there is nothing to do."
_LABELS: Final = {Chore.TANTRUM: "Scold", Chore.NAP: "Lights off"}
_POSTED: Final = {
    ChoreEventKind.MESS: Chore.MESS,
    ChoreEventKind.TANTRUM: Chore.TANTRUM,
    ChoreEventKind.NAP: Chore.NAP,
}
_ENDED: Final = frozenset(
    {
        ChoreEventKind.MESS_LEFT,
        ChoreEventKind.TANTRUM_MISSED,
        ChoreEventKind.LIGHTS_MISSED,
    }
)
_YOU_DID: Final = {
    Chore.MESS: "cleaned up",
    Chore.TANTRUM: "scolded Wisp",
    Chore.NAP: "turned off the lights",
}
_DONE: Final = {
    Chore.MESS: ("cleaned up the mess", Moment.MESS_CLEANED),
    Chore.TANTRUM: ("scolded Wisp", Moment.SCOLDED),
    Chore.NAP: ("turned off the lights", Moment.LIGHTS_OFF),
}

# ---
# Buttons
# ---


def chore_label(chore: Chore, stage: Stage) -> str:
    """The words on a chore's button; a mess's grow up with him."""
    if chore is Chore.MESS:
        return MESSES[stage][1]
    return _LABELS[chore]


class ChoreButton(
    discord.ui.DynamicItem[discord.ui.Button["discord.ui.View"]],
    template=re.compile(CHORE_ID),
):
    """The one button on a chore post, which the first eligible member wins.

    The chore and the life are in its custom id, so the button keeps working
    after the bot restarts.
    """

    def __init__(self, chore: Chore, life_id: int, label: str) -> None:
        super().__init__(
            discord.ui.Button(
                label=label,
                style=discord.ButtonStyle.primary,
                custom_id=f"wisp:chore:{chore.value}:{life_id}",
            )
        )
        self.chore = chore
        self.life_id = life_id

    @classmethod
    async def from_custom_id(
        cls,
        interaction: discord.Interaction,
        item: discord.ui.Item[discord.ui.View],
        match: re.Match[str],
        /,
    ) -> "ChoreButton":
        """Rebuild the button from its custom id, keeping the pressed label."""
        label = item.label if isinstance(item, discord.ui.Button) else None
        return cls(
            Chore(match["chore"]), int(match["life_id"]), label or match["chore"]
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        """Do the chore for the presser, reporting a failure where it was pressed."""
        try:
            await _press(interaction, self.chore, self.life_id)
        except EXPECTED_FAILURES as error:
            await report_failure(interaction, _CONTEXT, error)


def chore_view(chore: Chore, life_id: int, stage: Stage) -> discord.ui.View:
    """A view with just the chore's button, for a life at `stage`."""
    view = discord.ui.View(timeout=None)
    view.add_item(ChoreButton(chore, life_id, chore_label(chore, stage)))
    return view


# ---
# Posting chores
# ---


def _picture(chore: Chore, stage: Stage) -> Path | None:
    """The picture a chore's post shows at `stage`, or None for words only."""
    match chore:
        case Chore.MESS:
            name = MESSES[stage][2]
            return None if name is None else moment_image(name)
        case Chore.TANTRUM:
            return moment_image(TANTRUM_PICTURES[stage])
        case Chore.NAP:
            return nap_image(stage)


def _mess_named(stage: Stage) -> str:
    """The first line of a mess post: what the mess is at `stage`."""
    return f"♪ Wisp's mess: {MESSES[stage][0]}.\n"


async def post_chores(
    bot: "WispBot", guild_id: int, life: Life, events: list[ChoreEvent]
) -> None:
    """Show what his chores did in Wisp's House, pinging nobody.

    A new mess, tantrum or nap is posted with its picture and button, and the
    post is remembered on the life; a mess post first names the mess of his
    stage. A chore whose post failed is dropped, so it never waits where
    nobody can press it. A mess left too long, a missed tantrum and missed
    lights edit their own post with his line and take its button away.
    Catching a cold is posted with his sick picture.
    """
    if life.id is None:
        return
    for event in events:
        moment = Moment(event.kind.value)
        if event.kind in _POSTED:
            chore = _POSTED[event.kind]
            posted = await say_in_house(
                bot,
                guild_id,
                moment,
                life,
                prefix=_mess_named(life.stage) if chore is Chore.MESS else "",
                image=_picture(chore, life.stage),
                view=chore_view(chore, life.id, life.stage),
            )
            if posted is None:
                await _drop(bot, guild_id, life.id, chore)
            else:
                await _remember(bot, guild_id, life.id, chore, posted)
        elif event.kind in _ENDED and event.message_id is not None:
            line = bot.lines.pick(moment, mood(life))
            await edit_in_house(bot, guild_id, event.message_id, line)
        elif event.kind is ChoreEventKind.SNIFFLES:
            await say_in_house(
                bot, guild_id, moment, life, image=moment_image(SNIFFLES_PICTURE)
            )


async def _remember(
    bot: "WispBot",
    guild_id: int,
    life_id: int,
    chore: Chore,
    posted: discord.Message,
) -> None:
    """Store the post that shows `chore`, while that life still has it open.

    A first presser may have stored it already. A post nobody can win any
    more (the life changed, the chore closed or a newer post is already
    stored) keeps its words and loses its button.
    """
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        if life is not None and life.id == life_id:
            if message_id(life, chore) == posted.id:
                return
            if is_open(life, chore) and message_id(life, chore) is None:
                set_message_id(life, chore, posted.id)
                await bot.lives.save(guild_id, life)
                return
    await edit_in_house(bot, guild_id, posted.id, posted.content)


async def _drop(bot: "WispBot", guild_id: int, life_id: int, chore: Chore) -> None:
    """Drop `chore` from the life whose post of it failed, if still unposted."""
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        if life is not None and life.id == life_id and drop_chore(life, chore):
            await bot.lives.save(guild_id, life)


# ---
# Waking him
# ---


async def wake_by_poke(
    bot: "WispBot", guild_id: int, user_id: int, now: datetime
) -> Life | None:
    """Wake him if he is napping, cranky and with no Wellbeing penalty.

    When the lights were still on, the nap post says who woke him and loses
    its button once the guild lock is released. Returns the woken life, or
    None when he was not asleep.
    """
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        if life is None or not is_napping(life):
            return None
        lights_were_on = wake(life, now)
        await bot.lives.save(guild_id, life)
    if lights_were_on and life.nap_message_id is not None:
        await edit_in_house(
            bot,
            guild_id,
            life.nap_message_id,
            f"♪ <@{user_id}> woke Wisp up before the lights went off.",
        )
    return life


# ---
# Pressing a chore button
# ---


async def _press(interaction: discord.Interaction, chore: Chore, life_id: int) -> None:
    """Do the chore for the first eligible presser and pay them its points.

    A member who cannot earn, or who comes too late, is told why privately and
    nothing changes. The winner is told what it did privately; their post says
    who did it and loses its button, edited after the guild lock is released.
    """
    await interaction.response.defer()
    bot = bot_of(interaction)
    guild_id = require_guild(interaction)
    user = interaction.user
    player = await bot.players.get(guild_id, user.id)
    blocker = await member_blocker(bot, guild_id, user, discord.utils.utcnow())
    if blocker is not None:
        refusal = await chore_refusal_text(bot, guild_id, blocker)
        await say_privately(interaction, refusal)
        return
    post = interaction.message
    if post is None:
        await say_privately(interaction, _NO_POST)
        return
    try:
        life, health_before = await _take(bot, guild_id, chore, life_id, post, user.id)
    except Refusal as refusal:
        await say_privately(interaction, str(refusal))
        return
    done, moment = _DONE[chore]
    line = bot.lines.pick(moment, mood(life), name=player.name or user.display_name)
    await post.edit(
        content=(
            f"{post.content}\n♪ <@{user.id}> {done} ・ +{CHORE_POINTS[chore]} WC\n"
            f"{line}"
        ),
        view=None,
        allowed_mentions=_NO_PING,
    )
    coins = with_emoji(bot.emoji(MINI_COIN_EMOJI), f"+{CHORE_POINTS[chore]} WC")
    receipt = f"♪ You {_YOU_DID[chore]}. {coins}."
    if chore is Chore.MESS:
        health = meter_receipt("Health", health_before, life.health)
        receipt = f"{receipt} {health}."
    await say_privately(interaction, receipt)


async def _take(
    bot: "WispBot",
    guild_id: int,
    chore: Chore,
    life_id: int,
    post: discord.Message,
    user_id: int,
) -> tuple[Life, float]:
    """Do the chore for `user_id` if `post` still shows it open on the current life.

    Returns the life it was done for and his Health before the chore.

    A press that comes before the post's id is stored stores it: the button
    is on the post, so the post is taken to be this chore's. A chore does not
    remember when it opened, so an older post of the same kind whose button
    a failed edit left in place could claim the new chore in that moment; the
    chore is then done and paid as usual, and the new post loses its button.

    Raises:
        Refusal: Wisp is frozen, someone already did it, the post is an older
            one, the life has moved on or he is no longer alive.
    """
    await require_unfrozen(bot, guild_id)
    async with bot.guild_lock(guild_id):
        life = await bot.lives.current(guild_id)
        if life is None or life.id != life_id:
            raise Refusal(_OLD_POST)
        if life.phase is not Phase.ALIVE:
            raise Refusal(_NOT_ALIVE)
        if is_open(life, chore) and message_id(life, chore) is None:
            set_message_id(life, chore, post.id)
        if not is_open(life, chore) or message_id(life, chore) != post.id:
            raise Refusal(_ALREADY_DONE)
        health_before = life.health
        do_chore(life, chore)
        await bot.lives.save(guild_id, life)
        await bot.players.add_points(guild_id, user_id, CHORE_POINTS[chore])
    return life, health_before


async def setup(bot: "WispBot") -> None:
    """Register the chore button so it still works after a restart."""
    bot.add_dynamic_items(ChoreButton)
