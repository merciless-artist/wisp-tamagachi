"""Moody phrases: the rules of the name-that-song Easter egg, without Discord.

Staff add song lines for each stage from Child on. When Wisp is in a bad way
he now and then works one into an AI answer as his own outburst, and members
pick the song it came from out of a menu under it.
"""

import random
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from wisp.chores import is_open
from wisp.life import Life, Mood, mood
from wisp.rules import (
    MOODY_CREDIT_MAX,
    MOODY_OPTIONS,
    MOODY_PHRASE_MAX,
    MOODY_STAGES,
    MOODY_YEAR_MAX,
    MOODY_YEAR_MIN,
    Chore,
)
from wisp.text import clip, text_length
from wisp.voice import feelings_of

# Discord's limit on a menu option's label.
OPTION_LABEL_MAX = 100
# The longest Discord ID, so a winner's line always fits under the reply.
_LONGEST_ID = 2**64 - 1
_PUNCTUATION = re.compile(r"[^\w\s]")
_BAD_MOODS = frozenset({Mood.HANGRY, Mood.LONELY})

# ---
# Phrases
# ---


@dataclass(frozen=True)
class Phrase:
    """One song line staff added for a stage, with the song it comes from."""

    id: int
    stage: str
    text: str
    artist: str
    song: str
    year: int

    @property
    def song_key(self) -> tuple[str, str, int]:
        """What makes two phrases the same song."""
        return (self.artist, self.song, self.year)


def credit(phrase: Phrase) -> str:
    """The song a phrase is from, as "Artist, Song (Year)"."""
    return f"{phrase.artist}, {phrase.song} ({phrase.year})"


def option_label(phrase: Phrase) -> str:
    """The phrase's song as a menu option, cut to Discord's label limit."""
    return clip(credit(phrase), OPTION_LABEL_MAX)


def problem(text: str, artist: str, song: str, year: int) -> str | None:
    """Why staff can't add this phrase, or None when it can be added.

    The texts are checked as given; strip them first.
    """
    for name, value, limit in (
        ("phrase", text, MOODY_PHRASE_MAX),
        ("artist", artist, MOODY_CREDIT_MAX),
        ("song", song, MOODY_CREDIT_MAX),
    ):
        if not value:
            return f"♪ The {name} can't be empty."
        if text_length(value) > limit:
            return f"♪ The {name} can be at most {limit} characters."
    if not _plain(text):
        return "♪ The phrase needs at least one word."
    if not MOODY_YEAR_MIN <= year <= MOODY_YEAR_MAX:
        return f"♪ The year must be from {MOODY_YEAR_MIN} to {MOODY_YEAR_MAX}."
    return None


def songs_short(phrases: Sequence[Phrase]) -> int:
    """How many more different songs the stage needs before Wisp uses it."""
    return max(0, MOODY_OPTIONS - len({phrase.song_key for phrase in phrases}))


# ---
# Starting a round
# ---


def is_moody(life: Life, now: datetime) -> bool:
    """Whether Wisp is in a bad way at a stage that plays the game.

    He is when hangry or lonely, when he feels anything at all (Monster Pox,
    a cold, spoiled or cranky) and while a tantrum or a mess of his waits.
    """
    if life.stage not in MOODY_STAGES:
        return False
    return (
        mood(life) in _BAD_MOODS
        or bool(feelings_of(life, now))
        or is_open(life, Chore.TANTRUM)
        or is_open(life, Chore.MESS)
    )


def pick_phrase(
    phrases: Sequence[Phrase], last_id: int | None, rng: random.Random
) -> Phrase | None:
    """A phrase for the next round, or None when the stage has too few songs.

    The phrase used last time is skipped while there is another.
    """
    if songs_short(phrases):
        return None
    fresh = [phrase for phrase in phrases if phrase.id != last_id]
    return rng.choice(fresh or list(phrases))


def options_for(
    answer: Phrase, phrases: Sequence[Phrase], rng: random.Random
) -> list[Phrase]:
    """The menu's phrases: `answer` and others of different songs, shuffled.

    Each other song is offered once, through one of its phrases.

    Raises:
        ValueError: The stage has too few other songs.
    """
    by_song: dict[tuple[str, str, int], list[Phrase]] = {}
    for phrase in phrases:
        if phrase.song_key != answer.song_key:
            by_song.setdefault(phrase.song_key, []).append(phrase)
    if len(by_song) < MOODY_OPTIONS - 1:
        raise ValueError("Too few other songs for a moody phrase menu")
    songs = sorted(by_song)
    others = [rng.choice(by_song[key]) for key in rng.sample(songs, MOODY_OPTIONS - 1)]
    options = [answer, *others]
    rng.shuffle(options)
    return options


# ---
# The reply
# ---


def _plain(text: str) -> str:
    return " ".join(_PUNCTUATION.sub("", text).lower().split())


def has_phrase(reply: str, phrase: str) -> bool:
    """Whether `reply` says `phrase`, ignoring case, punctuation and spacing."""
    return _plain(phrase) in _plain(reply)


def won_line(user_id: int, phrase: Phrase) -> str:
    """The line added under the reply once a member names the song."""
    return f"♪ <@{user_id}> named it: {credit(phrase)}"


def with_phrase(reply: str, phrase: Phrase, limit: int) -> str:
    """The reply carrying the phrase, with room left for its `won_line`.

    A reply that does not say the phrase gets it as its last line. When the
    whole would pass `limit`, the AI's words are cut, never the phrase; a
    reply that still says it once cut gets no second copy.
    """
    room = limit - text_length(won_line(_LONGEST_ID, phrase)) - 1
    kept = clip(reply, room)
    if has_phrase(kept, phrase.text):
        return kept
    words = clip(reply, room - text_length(phrase.text) - 1).rstrip()
    return f"{words}\n{phrase.text}" if words else phrase.text
