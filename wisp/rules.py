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

# Starting values; staff can change them per guild with !wisp food.
MEAL_POINTS: dict[TrackKind, int] = {TrackKind.VIIBR: 5, TrackKind.SUNO: 1}
MEAL_POINTS_MAX = 50
DAILY_MEAL_CAP = 15
# Vault points for a member's first poke or mention of the UTC day, and for each
# counted Rhyme Duel.
CHAT_POINTS = 1
PLAY_POINTS = 1
# How long viibrmusic.com has to say which song a share link names.
VIIBR_RESOLVE_TIMEOUT = timedelta(seconds=5)

# ---
# Full
# ---

FULL_MAX = 100.0
FULL_DRAIN_PER_DAY = 15.0
OLD_FOGEY_FULL_DRAIN_PER_DAY = 10.0
HATCHED_FULL = 50.0
HANGRY_BELOW = 30.0
FADING_BELOW = 10.0

# ---
# Care
# ---

# Filled by counted Rhyme Duels and every gift bought; below LONELY_BELOW he
# is lonely, which only changes how he talks.
CARE_MAX = 100.0
CARE_START = 50.0
CARE_DRAIN_PER_DAY = 10.0
CARE_PER_PLAY = 10
CARE_PER_GIFT = 8
LONELY_BELOW = 30.0
# The pictures in ASSETS/moments his lonely post picks from, by stage.
LONELY_PICTURES: Final[dict[Stage, tuple[str, ...]]] = {
    Stage.BABY: ("cry_baby.gif", "grumpy_baby.png"),
    Stage.CHILD: ("grumpy.gif",),
    Stage.TEEN: ("cry_teen.gif",),
    Stage.ADULT: ("cry_teen.gif",),
    Stage.ROCKSTAR: ("cry_teen.gif",),
    Stage.OLD_FOGEY: ("cry_teen.gif",),
}

# ---
# Monster Pox, his childhood sickness (named "cold" in the code)
# ---

# Once per life he catches Monster Pox, due a random time between COLD_EARLIEST
# and COLD_LATEST after hatching. Adult needs 14 days, so it comes first.
COLD_EARLIEST = timedelta(days=1)
COLD_LATEST = timedelta(days=12)
# Credited time he stays sick.
SICK_FOR = timedelta(hours=48)
# While sick Full drains faster, never drops below SICK_FULL_FLOOR, and each
# member's daily meal cap has room for SICK_EXTRA_MEAL_CAP more meal points.
SICK_DRAIN_MULTIPLIER = 1.5
SICK_FULL_FLOOR = 1.0
SICK_EXTRA_MEAL_CAP = 15
# The picture in ASSETS/moments his sick post and his card show, by stage.
SICK_PICTURES: Final[dict[Stage, str]] = {
    Stage.BABY: "sick_baby.png",
    Stage.CHILD: "sick_child.png",
    Stage.TEEN: "sick_teen.png",
}

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

# The stages that have nap art, and so show it when he is woken or goes quiet.
NAP_STAGES: Final = frozenset({Stage.BABY, Stage.CHILD})

# ---
# Snacks
# ---


@dataclass(frozen=True)
class Snack:
    """A snack in the Snack Box."""

    key: str
    name: str
    cost: int
    full: int
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
    Snack("cheese", "Cheese", 6, 8, 2),
    Snack("pickles", "Pickles", 6, 8, 2),
    Snack("glitterwave", "Glitter Wave", 8, 12, 3),
    Snack("viibrwave", "ViiBR Wave", 10, 15, 3),
)
SNACK_BY_KEY: dict[str, Snack] = {snack.key: snack for snack in SNACKS}
PAID_SNACKS: tuple[Snack, ...] = tuple(snack for snack in SNACKS if snack.cost > 0)

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
    it, such as "Blue Alien Doll" or "I Block".
    """

    key: str
    name: str
    collection: str
    title: str

    @property
    def emoji_name(self) -> str:
        """Name of the app emoji that shows this gift."""
        return f"gift_{self.key}"


@dataclass(frozen=True)
class GiftCollection:
    """A set of gifts; `item` names one of them, such as "Alien Doll"."""

    key: str
    name: str
    item: str
    gifts: tuple[Gift, ...]


def _collection(
    key: str,
    name: str,
    item: str,
    gifts: tuple[tuple[str, str], ...],
    *,
    named_by_item: bool = True,
) -> GiftCollection:
    """A collection whose gifts are titled "<name> <item>", such as "Red Book".

    With `named_by_item` off, each gift's name is already its whole title,
    such as "Mimitchi".
    """
    return GiftCollection(
        key,
        name,
        item,
        tuple(
            Gift(
                gift_key,
                gift_name,
                key,
                f"{gift_name} {item}" if named_by_item else gift_name,
            )
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
    _collection(
        "tamagotchis",
        "Tamagotchis",
        "Tamagotchi",
        (
            ("tama_hawaikotchi", "Hawaikotchi"),
            ("tama_mimitchi", "Mimitchi"),
            ("tama_nano", "Tamagotchi Nano"),
            ("tama_welcotchi", "Welcotchi"),
        ),
        named_by_item=False,
    ),
    _collection(
        "tetris",
        "Tetris",
        "Tetris Toy",
        (
            ("tetris_handheld", "Tetris Handheld"),
            ("tetris_i", "I Block"),
            ("tetris_l", "L Block"),
            ("tetris_t", "T Block"),
            ("tetris_s", "S Block"),
            ("tetris_z", "Z Block"),
        ),
        named_by_item=False,
    ),
    _collection(
        "jewels",
        "Jewels",
        "Jewel",
        (
            ("jewel_amethyst", "Amethyst"),
            ("jewel_crystal", "Crystal"),
            ("jewel_rainbow", "Rainbow Jewel"),
            ("jewel_ruby", "Ruby"),
        ),
        named_by_item=False,
    ),
)
GIFT_BY_KEY: dict[str, Gift] = {
    gift.key: gift for collection in GIFT_COLLECTIONS for gift in collection.gifts
}
COLLECTION_BY_KEY: dict[str, GiftCollection] = {
    collection.key: collection for collection in GIFT_COLLECTIONS
}

# ---
# Badges
# ---


@dataclass(frozen=True)
class Badge:
    """A vanity role sold in the ViiBR Vault, worn for one Wisp's life.

    Its bond is outside the daily casual bond cap. `phrase` follows the
    buyer's name when Wisp's House announces it. `needs_tier` names the bond
    tier a member must be at to buy it, or None when anyone who can feed may.
    """

    key: str
    name: str
    cost: int
    bond: int
    phrase: str
    needs_tier: str | None = None

    @property
    def emoji_name(self) -> str:
        """Name of the app emoji that shows this badge."""
        return f"badge_{self.key}"


BADGES: tuple[Badge, ...] = (
    Badge("pickle_diplomat", "Pickle Diplomat", 25, 5, "is now a Pickle Diplomat"),
    Badge("flame_keeper", "Flame Keeper", 100, 15, "is now a Flame Keeper"),
    Badge("team_viibr", "Team ViiBR", 250, 25, "joined Team ViiBR"),
    Badge(
        "bandmate",
        "Bandmate",
        250,
        25,
        "is now one of Wisp's Bandmates",
        needs_tier=BOND_TIERS[-1][0],
    ),
)
BADGE_BY_KEY: dict[str, Badge] = {badge.key: badge for badge in BADGES}
RETIRED_BADGE_NAMES: dict[str, str] = {
    "egg_warmer": "Egg Warmer",
    "viibr_roadie": "ViiBR Roadie",
}


def badge_name(key: str) -> str:
    """A badge's name; for a badge no longer sold, its old name.

    Members keep retired badges they bought. A key with no known name reads
    as its words, so "old_badge" reads "Old Badge".
    """
    badge = BADGE_BY_KEY.get(key)
    if badge is not None:
        return badge.name
    return RETIRED_BADGE_NAMES.get(key) or key.replace("_", " ").title()


# ---
# Magazines
# ---


@dataclass(frozen=True)
class Magazine:
    """A magazine cover sold in the ViiBR Vault while Wisp is a Rockstar.

    A member can buy each one once per Wisp life and keeps it for good. Its
    picture is `{key}_cover.jpg` in the assets' mags folder.
    """

    key: str
    name: str


MAGAZINE_COST = 100
MAGAZINES: tuple[Magazine, ...] = (
    Magazine("viibrations", "VIIBRATIONS cover"),
    Magazine("musicnscience", "Music & Science cover"),
)
MAGAZINE_BY_KEY: dict[str, Magazine] = {
    magazine.key: magazine for magazine in MAGAZINES
}


# ---
# AI voice
# ---

AI_TIMEOUT = timedelta(seconds=8)
AI_PROVIDER_COOLDOWN = timedelta(minutes=5)
AI_MAX_OUTPUT_TOKENS = 1024
AI_MAX_CHARS = 600

# ---
# Talking
# ---

TALK_COOLDOWN = timedelta(seconds=15)
EGG_LINE_CHARS = 120
CHIME_IN_CHANCE = 0.04
CHIME_IN_GAP = timedelta(minutes=90)
CONTEXT_LINES = 12
CONTEXT_LINE_CHARS = 300
NOTES_KEPT = 8
NOTE_MAX_CHARS = 200

# ---
# Poking
# ---

# A House quiet this long, or a poke in these UTC hours (3 AM up to 7 AM),
# likely wakes him.
POKE_SLEEP_AFTER = timedelta(hours=2)
POKE_SLEEP_HOURS = range(3, 7)
# This many pokes from anyone within the window, this one included, likely
# annoy him. So does being hangry.
POKE_SPAM_WINDOW = timedelta(minutes=2)
POKE_SPAM_POKES = 3
# How likely each kind of poke reaction is, as weights. Waking up and being
# annoyed only get POKE_MOOD_WEIGHT while their reason holds, else none.
POKE_TICKLED_WEIGHT = 6
POKE_STARTLED_WEIGHT = 2
POKE_CURIOUS_WEIGHT = 2
POKE_MOOD_WEIGHT = 12
