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
# The app emoji Wisp reacts with on a track post that fed him.
FED_REACTION: Final = "wisp_happy"
# Vault points for a member's first credited poke or mention of the UTC day, and
# for each counted Rhyme Duel.
CHAT_POINTS = 1
PLAY_POINTS = 1
# Each member's first CHAT_CREDITS_PER_DAY mentions of the UTC day fill Wellbeing
# by WELLBEING_PER_CHAT, and their first POKE_CREDITS_PER_DAY pokes by
# WELLBEING_PER_POKE.
WELLBEING_PER_CHAT = 5
WELLBEING_PER_POKE = 5
CHAT_CREDITS_PER_DAY = 3
POKE_CREDITS_PER_DAY = 3
# How long viibrmusic.com has to say which song a share link names.
VIIBR_RESOLVE_TIMEOUT = timedelta(seconds=5)

# ---
# Health
# ---

# His body, and the only meter that can kill him. Fed by tracks, and by
# HEALTH_PER_CLEANUP for each mess cleaned up.
HEALTH_MAX = 100.0
HEALTH_START = 50.0
# Every HEALTH_STRETCH of counted time with no track fed costs HEALTH_PENALTY,
# or OLD_FOGEY_HEALTH_PENALTY for an Old Fogey; Monster Pox and a cold make it
# bigger (see SICK_DRAIN_MULTIPLIER).
HEALTH_STRETCH = timedelta(hours=6)
HEALTH_PENALTY = 8.0
OLD_FOGEY_HEALTH_PENALTY = 6.0
HANGRY_BELOW = 30.0
FADING_BELOW = 10.0

# ---
# Wellbeing
# ---

# His heart, which never kills him. Filled by chats, pokes, counted Rhyme
# Duels, snacks and every gift bought; below LONELY_BELOW he is lonely, which
# only changes how he talks.
WELLBEING_MAX = 100.0
WELLBEING_START = 50.0
# Every WELLBEING_STRETCH of counted time with no credited chat, poke, duel,
# snack, gift or cleanup costs WELLBEING_PENALTY.
WELLBEING_STRETCH = timedelta(hours=6)
WELLBEING_PENALTY = 10.0
WELLBEING_PER_GIFT = 8
WELLBEING_PER_SNACK = 8
WELLBEING_PER_PLAY = 10
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
# and COLD_LATEST after hatching. Baby and Child each take at least
# STAGE_MIN_TIME (3 days), so a Teen cannot arrive before day 6: day 5 at the
# latest is always while he is still a Baby or Child.
COLD_EARLIEST = timedelta(days=1)
COLD_LATEST = timedelta(days=5)
# Credited time he stays sick.
SICK_FOR = timedelta(hours=48)
# While he has Monster Pox or a cold the Health penalty is SICK_DRAIN_MULTIPLIER
# times as big but never takes Health below SICK_FULL_FLOOR. While he has
# Monster Pox each member's daily meal cap has room for SICK_EXTRA_MEAL_CAP more
# meal points.
SICK_DRAIN_MULTIPLIER = 1.5
SICK_FULL_FLOOR = 1.0
SICK_EXTRA_MEAL_CAP = 15
# Each meal point fed while he has Monster Pox takes POX_HEALED_PER_MEAL_POINT off
# what is left of it, so the more he is fed the sooner he is better.
POX_HEALED_PER_MEAL_POINT = timedelta(minutes=15)
# The picture in ASSETS/moments his sick post and his card show, by stage.
SICK_PICTURES: Final[dict[Stage, str]] = {
    Stage.BABY: "sick_baby.png",
    Stage.CHILD: "sick_child.png",
    Stage.TEEN: "sick_teen.png",
}

# ---
# A cold ("sniffles" in the code, so it is never mistaken for Monster Pox)
# ---

# Counted time a cold lasts; meanwhile the Health penalty is
# SICK_DRAIN_MULTIPLIER times as big, as with Monster Pox.
SNIFFLES_FOR = timedelta(hours=48)

# ---
# Chores
# ---


class Chore(StrEnum):
    """The three chores members race to do in Wisp's House."""

    MESS = "mess"
    TANTRUM = "tantrum"
    NAP = "nap"


CHORE_POINTS: Final[dict[Chore, int]] = {
    Chore.MESS: 2,
    Chore.TANTRUM: 2,
    Chore.NAP: 2,
}
# A fed track makes a mess due between MESS_DELAY_MIN and MESS_DELAY_MAX later,
# when none is open or pending and MESS_GAP has passed since the last one
# appeared. Left for MESS_LEFT_FOR it gives him a cold; a cleanup adds
# HEALTH_PER_CLEANUP.
MESS_DELAY_MIN = timedelta(minutes=30)
MESS_DELAY_MAX = timedelta(minutes=90)
MESS_GAP = timedelta(hours=6)
MESS_LEFT_FOR = timedelta(hours=6)
HEALTH_PER_CLEANUP = 5
# About once a day he throws a tantrum while awake. Myra may stretch the window
# while the server is small.
TANTRUM_WINDOW = timedelta(minutes=15)
TANTRUM_WELLBEING_PENALTY = 15.0
# He naps for NAP_FOR from each of NAP_LOCAL_HOURS on the NAP_TIMEZONE clock,
# which members read as NAP_TIMEZONE_NAME; the slots follow that clock through
# daylight saving, and everything else stays UTC. The lights must go off
# within LIGHTS_WINDOW, or he loses LIGHTS_WELLBEING_PENALTY Wellbeing and is
# cranky for CRANKY_FOR after the nap. A poke that wakes him makes him cranky
# for CRANKY_FOR too.
NAP_TIMEZONE: Final = "America/Los_Angeles"
NAP_TIMEZONE_NAME: Final = "Pacific"
NAP_LOCAL_HOURS: Final = (7, 13, 22)
NAP_FOR = timedelta(hours=1)
LIGHTS_WINDOW = timedelta(minutes=15)
LIGHTS_WELLBEING_PENALTY = 10.0
CRANKY_FOR = timedelta(hours=1)
# What the mess is at each stage, its button label and its picture in
# ASSETS/moments; a None picture posts the words and the button alone.
MESSES: Final[dict[Stage, tuple[str, str, str | None]]] = {
    Stage.BABY: ("poop", "Clean up", "poop.gif"),
    Stage.CHILD: ("poop", "Clean up", "poop.gif"),
    Stage.TEEN: ("a zit breakout", "Hand him face wash", "pimple.gif"),
    Stage.ADULT: (
        "takeout boxes and dirty dishes",
        "Take out the trash",
        "trash_adult.gif",
    ),
    Stage.ROCKSTAR: (
        "the green room he trashed after a show",
        "Clean the green room",
        "trash_rockstar.gif",
    ),
    Stage.OLD_FOGEY: ("dentures that need a soak", "Soak his teeth", "dentures.gif"),
}
# The pictures in ASSETS/moments for a cold, its medicine and a tantrum.
SNIFFLES_PICTURE: Final = "wispsick.gif"
MEDICINE_PICTURE: Final = "medicine.png"
SNEEZE_PICTURE: Final = "sneeze.gif"
# The pictures in ASSETS/moments one of which goes with his reply to a member
# talking to him or poking him while he is sick. Monster Pox wins over a cold.
POX_PICTURES: Final[dict[Stage, tuple[str, ...]]] = {
    stage: (
        *((SICK_PICTURES[stage],) if stage in SICK_PICTURES else ()),
        SNEEZE_PICTURE,
    )
    for stage in Stage
}
COLD_PICTURES: Final = (SNIFFLES_PICTURE, SNEEZE_PICTURE)
# Medicine in the Vault cures his cold for MEDICINE_COST and pays the buyer
# MEDICINE_POINTS.
MEDICINE_COST = 10
MEDICINE_POINTS = 3
MEDICINE_EMOJI: Final = "medicine"
TANTRUM_PICTURES: Final[dict[Stage, str]] = {
    Stage.BABY: "tantrum_baby.gif",
    Stage.CHILD: "grumpy.gif",
    Stage.TEEN: "cry_teen.gif",
    Stage.ADULT: "grumpy_adult.gif",
    Stage.ROCKSTAR: "grumpy_adult.gif",
    Stage.OLD_FOGEY: "grumpy_old_fogey.gif",
}

# ---
# Egg
# ---

EGG_FOOD_NEEDED = 20
COAL_EGG_FOOD = EGG_FOOD_NEEDED // 2
EGG_WARMTH = timedelta(hours=48)
HATCHING_TIME = timedelta(hours=5)

# ---
# Growth
# ---


@dataclass(frozen=True)
class StageRule:
    """What growing into a stage takes.

    He needs `growth` points and caretakers this stage numbering `share` of
    the people he saw in the last PEOPLE_WINDOW (rounded up, at least one),
    after at least STAGE_MIN_TIME in the stage before. On day `by_day` he
    grows into it no matter what.
    """

    growth: int
    share: float
    by_day: int


STAGE_RULES: dict[Stage, StageRule] = {
    Stage.CHILD: StageRule(growth=20, share=0.25, by_day=7),
    Stage.TEEN: StageRule(growth=60, share=0.5, by_day=13),
    Stage.ADULT: StageRule(growth=150, share=0.75, by_day=20),
}
STAGE_MIN_TIME = timedelta(days=3)
PEOPLE_WINDOW = timedelta(days=7)

OLD_FOGEY_AT_DAY = 24
FAREWELL_AT_DAY = 30
LAST_EMBER_GIFTS = 3

# An Adult whose Wellbeing stays at ROCKSTAR_WELLBEING or more for
# ROCKSTAR_WELLBEING_FOR of counted time becomes a Rockstar.
ROCKSTAR_WELLBEING = 80
ROCKSTAR_WELLBEING_FOR = timedelta(days=4)

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
# How many feeding roles a refusal and the rules post name before "or N more".
FEEDING_ROLES_SHOWN = 2
# The longest reason staff can give with !wisp punish.
PUNISH_REASON_MAX = 500

# Ban lengths by offence count; None is permanent.
BAN_LADDER: tuple[timedelta | None, ...] = (
    timedelta(days=1),
    timedelta(days=7),
    None,
)

# ---
# Rhyme Duel
# ---

# Discord only allows 60, 1440, 4320 or 10080 minutes, here and for
# STUDIO_THREAD_ARCHIVE_MINUTES.
RHYME_THREAD_ARCHIVE_MINUTES: Final = 60
RHYME_TURN = timedelta(seconds=15)
RHYME_PERFECT_POINTS = 2
RHYME_SLANT_POINTS = 1
RHYME_OPENER_RHYMES = 8
MAX_WORD_LENGTH = 30

# Wisp's first turns in a duel, by stage, on which he always finds a rhyme
# when one is left.
RHYME_SURE_TURNS: dict[Stage, int] = {
    Stage.BABY: 1,
    Stage.CHILD: 3,
    Stage.TEEN: 4,
    Stage.ADULT: 5,
    Stage.ROCKSTAR: 6,
    Stage.OLD_FOGEY: 4,
}
# Chance that Wisp finds a rhyme on his first turn after the sure ones, by
# stage. It drops by RHYME_TIRING on each turn after that.
RHYME_SKILL: dict[Stage, float] = {
    Stage.BABY: 0.5,
    Stage.CHILD: 0.65,
    Stage.TEEN: 0.8,
    Stage.ADULT: 0.9,
    Stage.ROCKSTAR: 0.97,
    Stage.OLD_FOGEY: 0.9,
}
RHYME_TIRING = 0.1

# ---
# Studio
# ---

# How long a Studio thread waits with no activity before Discord archives it.
STUDIO_THREAD_ARCHIVE_MINUTES: Final = 10080

# ---
# The Leaderboard card
# ---

LEADERBOARD_SIZE = 10
RHYME_LEADERBOARD_SIZE = 5

# ---
# Timing
# ---

MAX_CREDITED_GAP = timedelta(minutes=15)
TICK_EVERY = timedelta(minutes=5)
QUIET_AFTER = timedelta(hours=9)
# A staff test life holds this long after each step that waits for no button,
# so its posts can be read.
TEST_STEP_PAUSE = timedelta(seconds=8)

# The stages that have nap art, and so show it when he is woken or goes quiet.
NAP_STAGES: Final = frozenset({Stage.BABY, Stage.CHILD})

# ---
# The ViiBR Vault
# ---

# The Vault's box width: wide enough for the widest badge row, from its name
# and padding to its price.
VAULT_WIDTH: Final = 24

# ---
# Snacks
# ---


@dataclass(frozen=True)
class Snack:
    """A snack in the Snack Box."""

    key: str
    name: str
    cost: int
    meal: int
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
GIFT_LIKE_CHANCE = 1 / 2
# Added for each gift he passed on today, so the third gift of a day is kept.
GIFT_LIKE_RISE = 1 / 4
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
AI_PROVIDER_COOLDOWN = timedelta(minutes=1)
AI_MAX_OUTPUT_TOKENS = 1024
AI_MAX_CHARS = 600

# ---
# Pictures
# ---

VISION_MAX_BYTES = 8 * 1024 * 1024
VISION_MAX_CHARS = 300
VISION_EMBED_WAIT = timedelta(seconds=2)
VISION_TYPES = frozenset({"image/png", "image/jpeg", "image/webp", "image/gif"})

# ---
# Drawings
# ---

# The Cloudflare worker answers in 5 to 15 seconds; a picture over
# IMAGE_MAX_BYTES is more than Discord takes in an upload.
IMAGE_TIMEOUT = timedelta(seconds=60)
IMAGE_MAX_BYTES = 8 * 1024 * 1024
IMAGE_PROMPT_MAX_CHARS = 500
# What he gives a member for a gift he loves, a new bond tier, the day's most
# tracks and "I like you": at most this many per member and per server each
# UTC day. "I like you" picks from the members who fed, chatted or played in
# the last DRAWING_LIKE_WINDOW.
DRAWINGS_PER_MEMBER_PER_DAY = 1
DRAWINGS_PER_DAY = 6
DRAWING_LIKE_WINDOW = timedelta(hours=24)
DRAWING_FILE_NAME = "wisp_drawing.jpg"

# ---
# Talking
# ---

TALK_COOLDOWN = timedelta(seconds=4)
BOARD_NOTICE_LIFETIME = timedelta(seconds=8)
EGG_LINE_CHARS = 120
CHIME_IN_CHANCE = 0.04
CHIME_IN_GAP = timedelta(minutes=90)
CONTEXT_LINES = 12
CONTEXT_LINE_CHARS = 300
NOTES_KEPT = 8
NOTE_MAX_CHARS = 200
LIFE_STORY_ENTRIES = 20
PAST_LIVES_REMEMBERED = 5

# ---
# Long memory
# ---

MEMORY_MEMBER_RECALLED = 3
MEMORY_HOUSE_RECALLED = 2
MEMORY_CANDIDATES = 25
MEMORY_MIN_SIMILARITY = 0.70
MEMORY_HALF_LIFE = timedelta(days=30)
MEMORY_FADE_FLOOR = 0.5
MEMORY_RECENT_SKIP = timedelta(minutes=30)
MEMORY_EMBED_SIZE = 768
MEMORY_EMBED_TIMEOUT = timedelta(seconds=5)

# ---
# Poking
# ---

# A House quiet this long likely wakes him when poked.
POKE_SLEEP_AFTER = timedelta(hours=2)
# A member's pokes in a row: each within POKE_STREAK_GAP of their last one.
# From POKE_MAD_AT in a row he is always mad at them, from POKE_FED_UP_AT fed
# up. Pokes from other members never add to someone's streak.
POKE_STREAK_GAP = timedelta(minutes=10)
POKE_MAD_AT = 3
POKE_FED_UP_AT = 5
# How likely each other kind of poke reaction is, as weights. Waking up only
# gets POKE_MOOD_WEIGHT while the House is sleepy, and being annoyed only while
# he is hangry, else none.
POKE_TICKLED_WEIGHT = 6
POKE_STARTLED_WEIGHT = 2
POKE_CURIOUS_WEIGHT = 2
POKE_MOOD_WEIGHT = 12
