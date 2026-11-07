"""A staff test life in progress, shared by the run and the buttons it waits on.

The run lives in `bot.test_runs`, keyed by guild. While a guild has one, the
scheduled tick leaves that guild alone and only its runner may press the
chore and Begin again buttons there, or type `!wisp begin`.
"""

import asyncio
import contextlib
from dataclasses import dataclass, field
from datetime import timedelta


@dataclass(eq=False)
class LifeTestRun:
    """One server's test life: who runs it and whether it should stop.

    `runner_id` is the staff member who started it, matched by Discord ID;
    `runner_name` is only for showing. A press by the runner, or a stop,
    wakes a step that is waiting.
    """

    guild_id: int
    runner_id: int
    runner_name: str
    stopping: bool = False
    _woken: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    @property
    def refusal(self) -> str:
        """What anyone else pressing one of the run's buttons is told."""
        return f"♪ This button is for {self.runner_name}'s test run."

    @property
    def begin_refusal(self) -> str:
        """What anyone else typing `!wisp begin` during the run is told."""
        return f"♪ A test life is running, so only {self.runner_name} can begin again."

    def is_runner(self, user_id: int) -> bool:
        """Whether `user_id` started this run."""
        return user_id == self.runner_id

    def wake(self) -> None:
        """Tell a waiting step that the runner pressed a button."""
        self._woken.set()

    def stop(self) -> None:
        """End the run after the current step, or at once while it waits."""
        self.stopping = True
        self._woken.set()

    async def wait(self) -> None:
        """Wait, with no time limit, until the runner presses a button or a stop."""
        await self._woken.wait()
        self._woken.clear()

    async def pause(self, length: timedelta) -> None:
        """Hold for `length` so a step's posts can be read; a stop cuts it short."""
        with contextlib.suppress(TimeoutError):
            async with asyncio.timeout(length.total_seconds()):
                while not self.stopping:
                    await self.wait()
