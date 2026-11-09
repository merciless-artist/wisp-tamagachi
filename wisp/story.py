"""Wisp's life story: what has really happened to him, for when he talks.

Moments are saved as they happen. His hatching comes from the life itself, and
so does what a Wisp alive before the story was kept can still know: the stages
behind him and whether he has had Monster Pox.
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum, auto
from typing import Final

from wisp.gifts import with_article
from wisp.life import (
    Event,
    EventKind,
    Life,
    Phase,
    age_days,
    is_over,
    is_sick,
    sickness,
)
from wisp.rules import PAST_LIVES_REMEMBERED, Stage
from wisp.text import count

# ---
# Moments
# ---


class EntryKind(StrEnum):
    """The kinds of moment saved to his story."""

    GREW_UP = auto()
    POX_CAUGHT = auto()
    POX_OVER = auto()
    COLD_CAUGHT = auto()
    MEDICINE = auto()


@dataclass(frozen=True)
class Entry:
    """One moment of a life.

    `stage` is the stage he was in, or grew into for GREW_UP. `member_id` is
    who gave the medicine, or whose meal ended his Monster Pox; None for a
    moment nobody brought on.
    """

    kind: EntryKind
    stage: Stage
    member_id: int | None
    at: datetime


_FROM_EVENT: Final = {
    EventKind.SICK: EntryKind.POX_CAUGHT,
    EventKind.RECOVERED: EntryKind.POX_OVER,
    EventKind.STAGE_UP: EntryKind.GREW_UP,
    EventKind.GREW_OLD: EntryKind.GREW_UP,
}
_POX: Final = frozenset({EntryKind.POX_CAUGHT, EntryKind.POX_OVER})
_ILLNESS: Final = _POX | {EntryKind.COLD_CAUGHT}


def entries_from(events: Iterable[Event], now: datetime) -> list[Entry]:
    """The moments worth saving among `events`, all happening at `now`."""
    return [
        Entry(_FROM_EVENT[event.kind], event.stage, event.member_id, now)
        for event in events
        if event.kind in _FROM_EVENT and event.stage is not None
    ]


def member_ids(life: Life, entries: Iterable[Entry]) -> set[int]:
    """Everyone his story names: who hatched him and who helped him since."""
    named = {entry.member_id for entry in entries if entry.member_id is not None}
    return named if life.hatched_by is None else named | {life.hatched_by}


def past_lives(history: Iterable[Life]) -> list[Life]:
    """The newest real lives that hatched and are over, from newest-first `history`.

    Staff test lives are not remembered.
    """
    hatched = [
        life
        for life in history
        if is_over(life) and life.hatched_at and not life.is_test
    ]
    return hatched[:PAST_LIVES_REMEMBERED]


# ---
# Telling it
# ---

_HEADING: Final = (
    "**Your life so far.** All of this really happened to you. Bring it up when "
    "it fits and don't recite it. Never make up anything else about your past: "
    "if someone asks about something that isn't here, say you don't remember it."
)
_PAST_HEADING: Final = (
    "You're a fire sprite, and fire sprites remember their past lives. These are "
    "the Wisps you were before this one:"
)


def life_story(
    life: Life,
    entries: Sequence[Entry],
    past: Sequence[Life],
    names: Mapping[int, str],
    now: datetime,
) -> str:
    """What `life` has been through and the Wisps before him, for his prompt.

    `entries` are his saved moments, oldest first, and `names` what to call
    each member they name.
    """
    told = "\n".join(
        [
            _HEADING,
            *_hatching(life, names, now),
            *_stages_behind(life, entries),
            *(_entry_line(entry, names, now) for entry in entries),
            *_pox_before_the_story(life, entries),
            *_health_now(life, entries),
        ]
    )
    if not past:
        return told
    return f"{told}\n\n" + "\n".join([_PAST_HEADING, *map(_past_line, past)])


def how_long_ago(at: datetime, now: datetime) -> str:
    """How long ago `at` was, in UTC calendar days."""
    days = (now.date() - at.date()).days
    if days <= 0:
        return "today"
    return "yesterday" if days == 1 else f"{days} days ago"


def _hatching(life: Life, names: Mapping[int, str], now: datetime) -> list[str]:
    if life.hatched_at is None:
        return []
    line = f"- You hatched {how_long_ago(life.hatched_at, now)}."
    if life.hatched_by is not None and life.hatched_by in names:
        line += f" {names[life.hatched_by]} fed you the meal that hatched you."
    return [line]


def _stages_behind(life: Life, entries: Sequence[Entry]) -> list[str]:
    """The stages he has left behind; Rockstar is optional, so needs a record."""
    order = list(Stage)
    grew_into = {entry.stage for entry in entries if entry.kind is EntryKind.GREW_UP}
    behind = [
        stage.label
        for stage in order[order.index(Stage.BABY) : order.index(life.stage)]
        if stage is not Stage.ROCKSTAR or stage in grew_into
    ]
    if not behind:
        return []
    return [f"- Stages you've already lived through: {', '.join(behind)}."]


def _entry_line(entry: Entry, names: Mapping[int, str], now: datetime) -> str:
    when = how_long_ago(entry.at, now)
    stage = with_article(entry.stage.label)
    member = entry.member_id
    who = "Someone" if member is None else names.get(member, "Someone")
    told = {
        EntryKind.GREW_UP: f"{when}: you grew into {stage}",
        EntryKind.POX_CAUGHT: f"{when}, as {stage}: you caught Monster Pox",
        EntryKind.POX_OVER: (
            f"{when}, as {stage}: your Monster Pox ran its course and you got better"
            if member is None
            else f"{when}, as {stage}: you got over Monster Pox early because "
            f"people kept feeding you songs. {who} fed you the one that finished it"
        ),
        EntryKind.COLD_CAUGHT: f"{when}, as {stage}: you caught a cold",
        EntryKind.MEDICINE: (
            f"{when}, as {stage}: {who} gave you medicine and cured your cold"
        ),
    }[entry.kind]
    return f"- {told[0].upper()}{told[1:]}."


def _pox_before_the_story(life: Life, entries: Sequence[Entry]) -> list[str]:
    """What he knows of a Monster Pox that came before moments were saved."""
    on_record = any(entry.kind in _POX for entry in entries)
    if not life.had_cold or is_sick(life) or on_record:
        return []
    return [
        "- Earlier in this life you had Monster Pox and got over it. You don't "
        "remember exactly when."
    ]


def _health_now(life: Life, entries: Sequence[Entry]) -> list[str]:
    """Whether he has had Monster Pox and, when he isn't sick, that he isn't."""
    lines = [] if life.had_cold else ["- You have not had Monster Pox in this life."]
    if sickness(life) is not None:
        return lines
    been_sick = life.had_cold or any(entry.kind in _ILLNESS for entry in entries)
    better = " If anyone asks, you're all better." if been_sick else ""
    return [*lines, f"- You are not sick right now.{better}"]


def _past_line(life: Life) -> str:
    """One line on a Wisp who came before."""
    days = count(age_days(life, life.ended_at or life.last_tick_at), "day")
    stage = with_article(life.peak_stage.label)
    if life.phase is Phase.PASSED:
        return f"- Wisp v{life.version} grew into {stage} and passed on after {days}."
    return f"- Wisp v{life.version} faded away as {stage} after {days}."
