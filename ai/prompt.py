"""The text sent to an AI provider."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Prompt:
    """A system instruction and the user message it frames."""

    system: str
    user: str
