"""`!wisp testlife`: staff play one whole Wisp life on the real Wisp, step by step.

Every step runs the code the tick, the track drop, the Vault or a button
runs, so each post, picture, button and meter change is the real one. Time
passing is the stored clock moved, then one real tick. While a run is on,
the scheduled tick leaves its server alone, and a button step waits with no
time limit until the member who started the run presses it.
"""

import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Annotated, Final, TypeVar

import discord
from discord.ext import commands

from cogs.announce import begin_again, post_events, post_in_house
from cogs.chores import post_chores
from cogs.drawings import DrawResult, draw_for
from cogs.feeding import credit_feed
from cogs.life_loop import LifeLoop
from cogs.lifetest_runs import LifeTestRun
from cogs.players import FROZEN_REASON, blocker_reason, is_frozen, member_blocker
from cogs.snacks import announce_medicine
from cogs.staff import StaffContext, guild_of, reply
from db.settings import Settings
from wisp.chores import (
    ChoreEvent,
    is_open,
    message_id,
    open_mess,
    open_tantrum,
    start_nap,
)
from wisp.life import (
    Life,
    Phase,
    cure_sniffles,
    cut_short,
    has_sniffles,
    is_over,
    is_sick,
    jump_to,
    own_time,
    ready_to_pass_on,
)
from wisp.links import Track, TrackKind
from wisp.rules import (
    DRAWINGS_PER_DAY,
    EGG_FOOD_NEEDED,
    HATCHING_TIME,
    HEALTH_PENALTY,
    HEALTH_STRETCH,
    LONELY_BELOW,
    TEST_STEP_PAUSE,
    TICK_EVERY,
    WELLBEING_STRETCH,
    Chore,
    Stage,
)
from wisp.text import count
from wisp.voice import DrawReason

if TYPE_CHECKING:
    from app import WispBot

T = TypeVar("T")

_ALREADY_RUNNING: Final = "♪ A test life is already running."
_CANNOT: Final = "♪ You can't run a test life: {reason}"
_CONFIRM: Final = (
    "♪ This ends the current Wisp (v{version}). "
    "Type !wisp testlife confirm to go on."
)
_NOTHING_TO_CONFIRM: Final = "♪ Nothing to confirm. Type !wisp testlife first."
_NOT_RUNNING: Final = "♪ No test life is running."
_STOPPING: Final = "♪ Stopping the test life."
_NO_WORKER: Final = (
    "Wisp made no drawing: the picture worker address (CF_IMAGE_WORKER_URL) "
    "is not set."
)
_ONE_TICK: Final = TICK_EVERY.total_seconds()
_PHASES: Final = {
    Phase.EGG: "an egg",
    Phase.HATCHING: "hatching",
    Phase.ALIVE: "alive",
    Phase.DEAD: "dead",
    Phase.COLD: "a cold egg",
    Phase.PASSED: "passed on",
}


class Mode(StrEnum):
    """Which test life to play: a whole one, or one that starves."""

    FULL = auto()
    STARVE = auto()


class Word(StrEnum):
    """What staff may type after `!wisp testlife`."""

    STARVE = auto()
    CONFIRM = auto()
    STOP = auto()


_USAGE: Final = f"[{' | '.join(Word)}]"


def _word(argument: str) -> Word:
    """Read a word after `!wisp testlife` in any case."""
    try:
        return Word(argument.lower())
    except ValueError as error:
        raise commands.BadArgument(f"Not a testlife word: {argument}") from error


class StepFailed(Exception):
    """What a test life step expected to happen and did not, worded for staff."""


class _Stopped(Exception):
    """Staff stopped the run while a step waited for a button."""


def summary(passed: int, failed: list[int]) -> str:
    """The line that ends a test life, naming the steps that failed."""
    text = f"♪ Test life done: {count(passed, 'step')} passed, {len(failed)} failed"
    if not failed:
        return f"{text}."
    which = "step" if len(failed) == 1 else "steps"
    return f"{text} ({which} {', '.join(str(number) for number in failed)})."


# ---
# Commands
# ---


class LifeTest(commands.Cog):
    """`!wisp testlife`, and its words starve, confirm and stop.

    Each step that needs time to pass runs one tick of `life_loop`. `rng`
    picks when a jumped Baby or Child gets Monster Pox and when a fed track's
    mess is due. What each server was asked to confirm is kept in memory, so
    a restart forgets it.
    """

    def __init__(self, bot: "WispBot", life_loop: LifeLoop) -> None:
        self.bot = bot
        self.life_loop = life_loop
        self.rng = random.Random()
        self._asked: dict[int, Mode] = {}

    async def cog_unload(self) -> None:
        """Stop every run, so none is left waiting on a button."""
        for run in self.bot.test_runs.values():
            run.stop()

    @commands.command(name="testlife", usage=_USAGE, ignore_extra=False)
    async def testlife(
        self, ctx: StaffContext, word: Annotated[Word | None, _word] = None
    ) -> None:
        """Play a test life on the real Wisp, or confirm or stop one.

        On its own it plays the whole life; `starve` plays one that starves.
        """
        match word:
            case None:
                await self._ask(ctx, Mode.FULL)
            case Word.STARVE:
                await self._ask(ctx, Mode.STARVE)
            case Word.CONFIRM:
                await self._confirm(ctx)
            case Word.STOP:
                await self._stop(ctx)

    async def _confirm(self, ctx: StaffContext) -> None:
        """Play the test life this server was asked to confirm.

        The ask is kept until a run really starts, so a refused confirm can
        be typed again.
        """
        mode = self._asked.get(guild_of(ctx).id)
        if mode is None:
            await reply(ctx, _NOTHING_TO_CONFIRM)
            return
        await self._start(ctx, mode)

    async def _stop(self, ctx: StaffContext) -> None:
        """End the running test life after its step, or at once if it waits."""
        run = self.bot.test_runs.get(guild_of(ctx).id)
        if run is None:
            await reply(ctx, _NOT_RUNNING)
            return
        run.stop()
        await reply(ctx, _STOPPING)

    async def _ask(self, ctx: StaffContext, mode: Mode) -> None:
        """Play `mode`, or first ask to confirm when it would end a living Wisp.

        An egg, an ended life or no life at all needs no confirm. A run that
        could not go is refused first, so nothing is asked for it.
        """
        guild_id = guild_of(ctx).id
        refusal = await self._refusal(ctx)
        if refusal is not None:
            await reply(ctx, refusal)
            return
        life = await self.bot.lives.current(guild_id)
        if life is not None and life.phase is Phase.ALIVE:
            self._asked[guild_id] = mode
            await reply(ctx, _CONFIRM.format(version=life.version))
            return
        await self._start(ctx, mode)

    async def _start(self, ctx: StaffContext, mode: Mode) -> None:
        """Play `mode` for the member who typed the command, one run per server.

        The run is in `bot.test_runs` from the moment it is let start until it
        ends, however it ends. Starting uses up the server's ask to confirm.
        """
        guild_id = guild_of(ctx).id
        refusal = await self._refusal(ctx)
        if refusal is not None:
            await reply(ctx, refusal)
            return
        self._asked.pop(guild_id, None)
        member = ctx.author
        run = LifeTestRun(guild_id, member.id, member.display_name)
        self.bot.test_runs[guild_id] = run
        try:
            life = _TestLife(
                self.bot, self.life_loop, run, member, ctx.message.id, self.rng
            )
            await life.play(mode)
        finally:
            del self.bot.test_runs[guild_id]

    async def _refusal(self, ctx: StaffContext) -> str | None:
        """Why no test life may start for the member typing now, or None.

        Checked before anything is asked or changed. The runner must be able
        to feed Wisp, since the button steps wait for their presses, and the
        server needs the House and Status post the steps' ticks post to. The
        running check comes last, after every wait, so two runs started at
        once cannot both pass it.
        """
        guild_id = guild_of(ctx).id
        blocker = await member_blocker(
            self.bot, guild_id, ctx.author, discord.utils.utcnow()
        )
        if blocker is not None:
            reason = await blocker_reason(self.bot, guild_id, blocker)
            return _CANNOT.format(reason=reason)
        settings = await self.bot.settings.get(guild_id)
        missing = _not_set_up(settings)
        if missing is not None:
            return _CANNOT.format(reason=missing)
        if settings.frozen:
            return f"♪ {FROZEN_REASON}"
        if guild_id in self.bot.test_runs:
            return _ALREADY_RUNNING
        return None


def _not_set_up(settings: Settings) -> str | None:
    """What setup a test life lacks, and how to set it, or None when it has all."""
    missing = [
        name
        for name, channel_id in (
            ("Wisp's House", settings.house_channel_id),
            ("the Status post", settings.status_thread_id),
        )
        if channel_id is None
    ]
    if not missing:
        return None
    verb = "is" if len(missing) == 1 else "are"
    return f"{' and '.join(missing)} {verb} not set. Run !wisp setup first."


# ---
# Playing a life
# ---


@dataclass(frozen=True)
class _Step:
    """One step of a test life: what its House line says happens, and doing it.

    A step that `waits` for a button is not followed by a pause.
    """

    what: str
    run: Callable[[], Awaitable[None]]
    waits: bool = False


class _TestLife:
    """One test life being played: its steps, its runner and the run's state.

    The runner is credited like any member: the feed, the keepsakes and the
    drawing are really theirs. Life changes happen under the guild lock;
    posts, ticks and button waits outside it.
    """

    def __init__(
        self,
        bot: "WispBot",
        life_loop: LifeLoop,
        run: LifeTestRun,
        member: discord.User | discord.Member,
        message_id: int,
        rng: random.Random,
    ) -> None:
        self._bot = bot
        self._loop = life_loop
        self._run = run
        self._member = member
        self._message_id = message_id
        self._rng = rng
        self._guild_id = run.guild_id
        self._ended_id: int | None = None

    async def play(self, mode: Mode) -> None:
        """Play every step of `mode` in order, then post how it went.

        Each step is announced first. A failing step is reported and the run
        goes on. A stop, or Wisp frozen before a step, ends the run there.

        The catch around each step is the test run's top-level error reporter:
        a tester's job is to report whatever breaks and keep going, so any
        error is caught there. A stop is caught first, and a cancel passes
        through.
        """
        steps = self._steps(mode)
        passed = 0
        failed: list[int] = []
        for number, step in enumerate(steps, start=1):
            if self._run.stopping:
                break
            if await is_frozen(self._bot, self._guild_id):
                await self._say(f"♪ {FROZEN_REASON}")
                break
            await self._say(f"♪ Test life, step {number} of {len(steps)}: {step.what}.")
            try:
                await step.run()
            except _Stopped:
                break
            except Exception as error:
                failed.append(number)
                await self._bot.report_error(
                    self._bot.get_guild(self._guild_id),
                    f"test life step {number}",
                    error,
                )
            else:
                passed += 1
            if not step.waits and number < len(steps):
                await self._run.pause(TEST_STEP_PAUSE)
        await self._say(summary(passed, failed))

    def _steps(self, mode: Mode) -> list[_Step]:
        name = self._run.runner_name
        begin = f"Waiting for {name} to press Begin again"
        start = [
            _Step("a new egg is laid", self._lay_egg),
            _Step(
                "he is fed until he hatches into a Baby "
                "(the daily meal limit is lifted for the test)",
                self._hatch,
            ),
        ]
        if mode is Mode.STARVE:
            return [
                *start,
                _Step("nobody feeds him, so his Health runs out", self._starve),
                _Step(begin, self._begin_again, waits=True),
            ]
        return [
            *start,
            _Step("he catches Monster Pox, then gets better", self._pox),
            _Step(
                f"he makes a mess. Waiting for {name} to press its button",
                lambda: self._chore(Chore.MESS, open_mess),
                waits=True,
            ),
            _Step("a second mess is left too long, so he catches a cold", self._cold),
            _Step("medicine cures his cold (free for the test)", self._medicine),
            _Step(
                f"he throws a tantrum. Waiting for {name} to press Scold",
                lambda: self._chore(Chore.TANTRUM, open_tantrum),
                waits=True,
            ),
            _Step(
                f"he takes a nap. Waiting for {name} to press Lights off",
                lambda: self._chore(Chore.NAP, start_nap),
                waits=True,
            ),
            _Step(
                "one stretch passes with nobody caring for him, so his meters drop",
                self._meters_drop,
            ),
            _Step("his Wellbeing drops below the lonely line", self._lonely),
            _Step(
                "he grows into a Child (First Spark)",
                lambda: self._grow(Stage.CHILD),
            ),
            _Step("he grows into a Teen (Teen Spark)", lambda: self._grow(Stage.TEEN)),
            _Step(
                "he grows into an Adult (Adult Spark)",
                lambda: self._grow(Stage.ADULT),
            ),
            _Step(f"he makes a drawing for {name}", self._drawing),
            _Step(
                "he becomes a Rockstar "
                "(Guitar Pick, and the magazines go on the shelf)",
                lambda: self._grow(Stage.ROCKSTAR),
            ),
            _Step(
                "he grows into an Old Fogey (Time Piece)",
                lambda: self._grow(Stage.OLD_FOGEY),
            ),
            _Step(f"his farewell (Last Ember). {begin}", self._farewell, waits=True),
        ]

    # ---
    # The steps
    # ---

    async def _lay_egg(self) -> None:
        """End the current life if it goes on, then lay an egg by Begin again."""
        now = discord.utils.utcnow()
        async with self._bot.guild_lock(self._guild_id):
            life = await self._bot.lives.current(self._guild_id)
            if life is not None and not is_over(life):
                cut_short(life, now)
                await self._bot.lives.save(self._guild_id, life)
        if await begin_again(self._bot, self._guild_id, now) is None:
            raise StepFailed("no egg was laid: a Wisp who goes on came first.")
        await self._loop.tick_guild(self._guild_id, now)

    async def _hatch(self) -> None:
        """Feed the egg full as a track from the runner, then let it hatch.

        The feed is the track drop's own, for exactly what the egg still
        needs, past the runner's daily meal limit.
        """
        now = discord.utils.utcnow()
        async with self._bot.guild_lock(self._guild_id):
            egg = await self._living(Phase.EGG)
            track = Track(
                TrackKind.VIIBR, f"testlife:{egg.id}", f"test life v{egg.version}"
            )
            events = await credit_feed(
                self._bot,
                self._guild_id,
                egg,
                self._run.runner_id,
                track,
                EGG_FOOD_NEEDED - egg.egg_food,
                self._message_id,
                now,
                self._rng,
            )
        await post_events(self._bot, self._guild_id, events)
        await self._run.pause(TEST_STEP_PAUSE)
        life = await self._pass_time(Phase.HATCHING, _hatching_ends)
        if life.phase is not Phase.ALIVE:
            raise StepFailed("Wisp did not hatch.")

    async def _pox(self) -> None:
        life = await self._pass_time(Phase.ALIVE, _pox_due)
        if not is_sick(life):
            raise StepFailed("Wisp did not catch Monster Pox.")
        await self._run.pause(TEST_STEP_PAUSE)
        life = await self._pass_time(Phase.ALIVE, _pox_ends)
        if is_sick(life):
            raise StepFailed("Wisp did not get over Monster Pox.")

    async def _chore(self, chore: Chore, opener: Callable[[Life], ChoreEvent]) -> None:
        """Post a chore with its button and wait until the runner does it."""
        await self._post_chore(chore, opener)
        await self._wait_until(
            lambda life: life is not None and not is_open(life, chore)
        )

    async def _cold(self) -> None:
        """Post a second mess, then leave it until it runs out and he catches a cold."""
        await self._post_chore(Chore.MESS, open_mess)
        await self._run.pause(TEST_STEP_PAUSE)
        life = await self._pass_time(Phase.ALIVE, _mess_runs_out)
        if not has_sniffles(life):
            raise StepFailed("Wisp did not catch a cold from the mess.")

    async def _medicine(self) -> None:
        """Cure his cold the Vault's way, from the runner, at no cost."""

        def cure(life: Life) -> None:
            if not cure_sniffles(life):
                raise StepFailed("Wisp has no cold to cure.")

        life, _ = await self._change(Phase.ALIVE, cure)
        player = await self._bot.players.get(self._guild_id, self._run.runner_id)
        name = player.name or self._member.display_name
        await announce_medicine(self._bot, self._guild_id, life, name)

    async def _meters_drop(self) -> None:
        before = await self._current()
        life = await self._pass_time(Phase.ALIVE, _stretches_fill)
        if life.health >= before.health or life.wellbeing >= before.wellbeing:
            raise StepFailed("Wisp's meters did not drop.")

    async def _lonely(self) -> None:
        life = await self._pass_time(Phase.ALIVE, _lonely_due)
        if not life.lonely_warned:
            raise StepFailed("Wisp did not get lonely.")

    async def _grow(self, stage: Stage) -> None:
        """Put him straight into `stage`, announced like a real one, then tick."""
        now = discord.utils.utcnow()
        _, event = await self._change(
            Phase.ALIVE, lambda life: jump_to(life, stage, now, self._rng)
        )
        await post_events(self._bot, self._guild_id, [] if event is None else [event])
        await self._loop.tick_guild(self._guild_id, now)
        if (await self._current()).stage is not stage:
            raise StepFailed(f"Wisp did not grow into his {stage.label} stage.")

    async def _drawing(self) -> None:
        if not self._bot.images.configured:
            raise StepFailed(_NO_WORKER)
        name = self._run.runner_name
        result = await draw_for(
            self._bot,
            self._guild_id,
            self._member,
            DrawReason.LIKE,
            discord.utils.utcnow(),
        )
        if result is DrawResult.FAILED:
            raise StepFailed("Wisp made no drawing; why is posted above.")
        if result is DrawResult.SKIPPED:
            raise StepFailed(
                f"Wisp made no drawing: {name} can't feed him or already had one "
                f"today, or the server had its {DRAWINGS_PER_DAY} for today."
            )

    async def _farewell(self) -> None:
        """Make his next tick his farewell, run it, then wait for Begin again."""
        now = discord.utils.utcnow()
        life, _ = await self._change(
            Phase.ALIVE, lambda life: ready_to_pass_on(life, now, self._rng)
        )
        await self._loop.tick_guild(self._guild_id, now)
        await self._ended(life, "Wisp did not say his farewell.")
        await self._begin_again()

    async def _starve(self) -> None:
        life = await self._current()
        await self._pass_time(Phase.ALIVE, _health_runs_out)
        await self._ended(life, "Wisp did not starve.")

    async def _begin_again(self) -> None:
        """Wait until the runner's Begin again lays the egg after the ended life."""
        ended = self._ended_id
        if ended is None:
            raise StepFailed(
                "no life of this run has ended, so there is no Begin again."
            )
        await self._wait_until(lambda life: life is not None and life.id != ended)

    # ---
    # Helpers
    # ---

    async def _say(self, text: str) -> None:
        await post_in_house(self._bot, self._guild_id, text)

    async def _ended(self, life: Life, failure: str) -> None:
        """Note that `life` has ended, or raise `failure` when it goes on.

        A life the runner already replaced with Begin again has ended too.
        """
        current = await self._current()
        if current.id == life.id and not is_over(current):
            raise StepFailed(failure)
        self._ended_id = life.id

    async def _current(self) -> Life:
        life = await self._bot.lives.current(self._guild_id)
        if life is None:
            raise StepFailed("there is no Wisp.")
        return life

    async def _living(self, phase: Phase) -> Life:
        """The current life, which must be in `phase`. Call under the guild lock."""
        life = await self._current()
        if life.phase is not phase:
            raise StepFailed(
                f"this step needs Wisp to be {_PHASES[phase]}, "
                f"and he is {_PHASES[life.phase]}."
            )
        return life

    async def _change(
        self, phase: Phase, change: Callable[[Life], T]
    ) -> tuple[Life, T]:
        """Change the current life, which must be in `phase`, and save it.

        Returns the life and what `change` returned.
        """
        async with self._bot.guild_lock(self._guild_id):
            life = await self._living(phase)
            result = change(life)
            await self._bot.lives.save(self._guild_id, life)
        return life, result

    async def _pass_time(
        self, phase: Phase, change: Callable[[Life, datetime], None]
    ) -> Life:
        """Make something come due within one tick, then run one real tick.

        `change` sets what comes due at `now`. His last tick is put one tick
        back, so the tick counts one tick's worth of time for everything, as
        a real one would. Returns the life as the tick left it.
        """
        now = discord.utils.utcnow()

        def due(life: Life) -> None:
            change(life, now)
            life.last_tick_at = now - TICK_EVERY

        await self._change(phase, due)
        await self._loop.tick_guild(self._guild_id, now)
        return await self._current()

    async def _post_chore(
        self, chore: Chore, opener: Callable[[Life], ChoreEvent]
    ) -> None:
        """Open a chore and post it with its button; one already posted is kept.

        Raises:
            StepFailed: The post could not be made, so the chore was dropped.
        """

        def open_chore(life: Life) -> list[ChoreEvent]:
            if is_open(life, chore) and message_id(life, chore) is not None:
                return []
            return [opener(life)]

        life, events = await self._change(Phase.ALIVE, open_chore)
        await post_chores(self._bot, self._guild_id, life, events)
        posted = await self._current()
        if not is_open(posted, chore) or message_id(posted, chore) is None:
            raise StepFailed(f"the {chore} post could not be made.")

    async def _wait_until(self, done: Callable[[Life | None], bool]) -> None:
        """Wait with no time limit until the runner's presses make `done` true.

        Raises:
            _Stopped: Staff stopped the run first.
        """
        while not done(await self._bot.lives.current(self._guild_id)):
            if self._run.stopping:
                raise _Stopped
            await self._run.wait()


# ---
# What comes due
# ---


def _hatching_ends(life: Life, _now: datetime) -> None:
    life.phase_seconds = HATCHING_TIME.total_seconds() - _ONE_TICK


def _pox_due(life: Life, now: datetime) -> None:
    if life.had_cold:
        raise StepFailed("Wisp has had Monster Pox already.")
    life.cold_due_at = own_time(life, now)


def _pox_ends(life: Life, _now: datetime) -> None:
    life.cold_left = _ONE_TICK


def _mess_runs_out(life: Life, _now: datetime) -> None:
    life.mess_left = _ONE_TICK


def _stretches_fill(life: Life, _now: datetime) -> None:
    life.health_stretch = HEALTH_STRETCH.total_seconds() - _ONE_TICK
    life.wellbeing_stretch = WELLBEING_STRETCH.total_seconds() - _ONE_TICK


def _lonely_due(life: Life, _now: datetime) -> None:
    """Put Wellbeing on the lonely line, with a drop one tick away."""
    life.wellbeing = LONELY_BELOW
    life.lonely_warned = False
    life.wellbeing_stretch = WELLBEING_STRETCH.total_seconds() - _ONE_TICK


def _health_runs_out(life: Life, _now: datetime) -> None:
    """Leave him one Health drop from empty, with the drop one tick away."""
    life.health = min(life.health, HEALTH_PENALTY)
    life.health_stretch = HEALTH_STRETCH.total_seconds() - _ONE_TICK


async def setup(bot: "WispBot") -> None:
    """Load `!wisp testlife`, which ticks through the loaded life loop.

    Raises:
        LookupError: The life loop is not loaded.
    """
    life_loop = bot.get_cog(LifeLoop.__cog_name__)
    if not isinstance(life_loop, LifeLoop):
        raise LookupError("the life loop must be loaded before the life tester")
    await bot.add_cog(LifeTest(bot, life_loop))
