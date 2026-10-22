"""Every tunable number in Wisp's game, in one place."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum, auto

from wisp.links import TrackKind


class Stage(StrEnum):
    """Wisp's life stages, in order."""

    EGG = auto()
    BABY = auto()
    CHILD = auto()
    TEEN = auto()
    ADULT = auto()
    ROCKSTAR = auto()


# ---
# Meals and points
# ---

MEAL_POINTS: dict[TrackKind, int] = {TrackKind.VIIBR: 5, TrackKind.SUNO: 1}
DAILY_MEAL_CAP = 15

# ---
# Care
# ---

CARE_MAX = 100.0
CARE_DRAIN_PER_DAY = 15.0
HATCHED_CARE = 50.0
HANGRY_BELOW = 30.0
FADING_BELOW = 10.0

# ---
# Egg
# ---

EGG_FOOD_NEEDED = 30
EGG_WARMTH = timedelta(hours=48)
HATCHING_TIME = timedelta(hours=5)

# ---
# Growth
# ---

HAPPY_FULL_AT_PEOPLE = 5

# Per stage: (minimum age in days, growth points, distinct caretakers).
STAGE_RULES: dict[Stage, tuple[int, int, int]] = {
    Stage.CHILD: (3, 20, 3),
    Stage.TEEN: (7, 60, 5),
    Stage.ADULT: (14, 150, 8),
}

ROCKSTAR_HAPPY_FOR = timedelta(days=7)
ROCKSTAR_HAPPINESS = 80

GROWTH_PER_PLAY = 2
GROWTH_PER_BOND_MOMENT = 5

# ---
# Bond
# ---

BOND_PER_VIIBR_TRACK = 10
BOND_PER_SNACK = 1
BOND_PER_PLAY = 3
DAILY_CASUAL_BOND_CAP = 7
MEET_AFTER_DAYS = 3

# Per tier: (name, bond needed), lowest first.
BOND_TIERS: tuple[tuple[str, int], ...] = (
    ("New face", 0),
    ("Familiar", 50),
    ("Friend", 150),
    ("Bandmate", 400),
)

# ---
# Names and discipline
# ---

NAME_MAX = 24

# Ban lengths by offence count; None is permanent.
BAN_LADDER: tuple[timedelta | None, ...] = (
    timedelta(days=1),
    timedelta(days=7),
    None,
)

# ---
# Timing
# ---

MAX_CREDITED_GAP = timedelta(minutes=15)
TICK_EVERY = timedelta(minutes=5)
COMPLIMENT_COOLDOWN = timedelta(minutes=10)
HAPPINESS_WINDOW = timedelta(hours=24)
QUIET_AFTER = timedelta(hours=9)

# ---
# Snacks
# ---


@dataclass(frozen=True)
class Snack:
    """A snack on the lunchbox menu."""

    key: str
    name: str
    cost: int
    care: int
    growth: int

    @property
    def emoji_name(self) -> str:
        """Name of the app emoji that shows this snack."""
        return f"snack_{self.key}"

    @property
    def gif_name(self) -> str:
        """File name of the GIF of Wisp eating this snack."""
        return f"eat_{self.key}.gif"


FANCY_SNACK_COST = 8

SNACKS: tuple[Snack, ...] = (
    Snack("sinewave", "Sine Wave", 0, 2, 1),
    Snack("cloudwave", "Cloud Wave", 3, 5, 1),
    Snack("jellywave", "Jelly Wave", 3, 5, 1),
    Snack("juicewave", "Juice Wave", 3, 5, 1),
    Snack("spicywave", "Spicy Wave", 5, 8, 2),
    Snack("glitterwave", "Glitter Wave", 8, 12, 3),
    Snack("viibrwave", "ViiBR Wave", 10, 15, 3),
    Snack("cheese", "Cheese", 6, 8, 2),
    Snack("pickles", "Pickles", 6, 8, 2),
)
