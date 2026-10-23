"""Every tunable number in Wisp's game, in one place."""

from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum, auto
from typing import Final

from wisp.links import TrackKind


class Stage(StrEnum):
    """Wisp's life stages, in order."""

    EGG = auto()
    BABY = auto()
    CHILD = auto()
    TEEN = auto()
    ADULT = auto()
    ROCKSTAR = auto()
    OLD_FOGEY = auto()

    @property
    def label(self) -> str:
        """The stage's name as it is shown to members."""
        return self.value.replace("_", " ").title()


# ---
# Meals and points
# ---

# Starting values; staff can change them per guild with /wispadmin food.
MEAL_POINTS: dict[TrackKind, int] = {TrackKind.VIIBR: 5, TrackKind.SUNO: 1}
MEAL_POINTS_MAX = 50
DAILY_MEAL_CAP = 15

# ---
# Care
# ---

CARE_MAX = 100.0
CARE_DRAIN_PER_DAY = 15.0
OLD_FOGEY_CARE_DRAIN_PER_DAY = 10.0
HATCHED_CARE = 50.0
HANGRY_BELOW = 30.0
FADING_BELOW = 10.0

# ---
# Egg
# ---

EGG_FOOD_NEEDED = 30
COAL_EGG_FOOD = EGG_FOOD_NEEDED // 2
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

OLD_FOGEY_AT_DAY = 45
FAREWELL_AT_DAY = 60
LAST_EMBER_GIFTS = 3

ROCKSTAR_HAPPY_FOR = timedelta(days=7)
ROCKSTAR_HAPPINESS = 80

GROWTH_PER_PLAY = 2
PLAYS_PER_DAY = 5
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
# Rhyme Duel
# ---

# Discord only allows 60, 1440, 4320 or 10080 minutes.
RHYME_THREAD_ARCHIVE_MINUTES: Final = 60
RHYME_TURN = timedelta(seconds=15)
RHYME_PERFECT_POINTS = 2
RHYME_SLANT_POINTS = 1
RHYME_OPENER_RHYMES = 8
MAX_WORD_LENGTH = 30

# Chance that Wisp finds a rhyme on his turn, by stage.
RHYME_SKILL: dict[Stage, float] = {
    Stage.BABY: 0.5,
    Stage.CHILD: 0.65,
    Stage.TEEN: 0.8,
    Stage.ADULT: 0.9,
    Stage.ROCKSTAR: 0.97,
    Stage.OLD_FOGEY: 0.9,
}

# ---
# The Vault card
# ---

LEADERBOARD_SIZE = 10
RHYME_LEADERBOARD_SIZE = 5

# ---
# Timing
# ---

MAX_CREDITED_GAP = timedelta(minutes=15)
TICK_EVERY = timedelta(minutes=5)
HAPPINESS_WINDOW = timedelta(hours=24)
QUIET_AFTER = timedelta(hours=9)

# ---
# Snacks
# ---


@dataclass(frozen=True)
class Snack:
    """A snack in the Snack Box."""

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
SNACK_BY_KEY: dict[str, Snack] = {snack.key: snack for snack in SNACKS}

# ---
# Wisp's lunchbox
# ---

FAVORITE_SONGS_SHOWN = 10

# ---
# Gifts
# ---

GIFT_COST = 15
GIFT_LIKE_CHANCE = 1 / 3
# Outside the daily casual bond cap.
BOND_PER_KEPT_GIFT = 5
COLLECTION_BOND_BONUS = 25


@dataclass(frozen=True)
class Gift:
    """A gift members can give Wisp from the Vault.

    `collection` is the key of its collection and `title` is how messages name
    it, such as "Blue Alien Doll".
    """

    key: str
    name: str
    collection: str
    title: str

    @property
    def emoji_name(self) -> str:
        """Name of the app emoji that shows this gift."""
        return f"gift_{self.key}"

    @property
    def image_name(self) -> str:
        """File name of this gift's picture in ASSETS/gifts."""
        return f"{self.key}.png"


@dataclass(frozen=True)
class GiftCollection:
    """A set of gifts; `item` names one of them, such as "Alien Doll"."""

    key: str
    name: str
    item: str
    gifts: tuple[Gift, ...]


def _collection(
    key: str, name: str, item: str, gifts: tuple[tuple[str, str], ...]
) -> GiftCollection:
    return GiftCollection(
        key,
        name,
        item,
        tuple(
            Gift(gift_key, gift_name, key, f"{gift_name} {item}")
            for gift_key, gift_name in gifts
        ),
    )


GIFT_COLLECTIONS: tuple[GiftCollection, ...] = (
    _collection(
        "liners",
        "Lunchbox Liners",
        "Lunchbox Liner",
        (
            ("liner_bird", "Bird"),
            ("liner_butterfly", "Butterfly"),
            ("liner_kitties", "Kitties"),
            ("liner_poppies", "Poppies"),
        ),
    ),
    _collection(
        "aliens",
        "Alien Dolls",
        "Alien Doll",
        (
            ("alien_blue", "Blue"),
            ("alien_green", "Green"),
            ("alien_purple", "Purple"),
            ("alien_yellow", "Yellow"),
        ),
    ),
    _collection(
        "books",
        "Books",
        "Book",
        (
            ("book_blue", "Blue"),
            ("book_green", "Green"),
            ("book_orange", "Orange"),
            ("book_red", "Red"),
        ),
    ),
    _collection(
        "cards",
        "Affirmation Cards",
        "Affirmation Card",
        (
            ("card_futureisbright", "Future Is Bright"),
            ("card_goodvibes", "Good Vibes"),
            ("card_keepcalm", "Keep Calm"),
            ("card_seeyou", "See You"),
        ),
    ),
)
GIFT_BY_KEY: dict[str, Gift] = {
    gift.key: gift for collection in GIFT_COLLECTIONS for gift in collection.gifts
}

# ---
# AI voice
# ---

AI_TIMEOUT = timedelta(seconds=12)
AI_PROVIDER_COOLDOWN = timedelta(minutes=5)
AI_MAX_OUTPUT_TOKENS = 1024
AI_MAX_CHARS = 600

# ---
# Talking
# ---

LINES_REMEMBERED = 5

TALK_COOLDOWN = timedelta(seconds=15)
CHIME_IN_CHANCE = 0.04
CHIME_IN_GAP = timedelta(minutes=90)
CONTEXT_LINES = 12
CONTEXT_LINE_CHARS = 300
NOTES_KEPT = 8
NOTE_MAX_CHARS = 200
