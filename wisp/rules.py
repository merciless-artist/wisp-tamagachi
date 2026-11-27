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
# Each member's daily limits: DAILY_MEAL_CAP meal points from tracks and,
# separately, DAILY_SNACK_CAP from snacks, so a snack never stops a track.
DAILY_MEAL_CAP = 15
DAILY_SNACK_CAP = 15
# A track's Health follows how many members fed him a track in the last
# ACTIVE_FEEDER_WINDOW, so a small group keeps him going with the same effort
# as a big one: he holds steady when TRACK_SHARE of them each feed one
# viibrmusic.com track a day. One viibrmusic.com track (its MEAL_POINTS) gives
# between TRACK_HEALTH_MIN and TRACK_HEALTH_MAX Health, and every other track
# the same per meal point. Points and coins never shift.
ACTIVE_FEEDER_WINDOW = timedelta(days=7)
TRACK_SHARE = 0.5
TRACK_HEALTH_MIN = 2.0
TRACK_HEALTH_MAX = 20.0
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
# His lonely post shows his stage's crying gif (ASSETS/wispmoods/gifs); a stage
# with none on disk shows its picture in ASSETS/moments here instead.
LONELY_PICTURES: Final[dict[Stage, str]] = {Stage.CHILD: "grumpy.gif"}

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
# Monster Pox each member's daily track limit has room for SICK_EXTRA_MEAL_CAP
# more meal points; the snack limit stays as it is.
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
# About once a day he throws a tantrum while awake. The window is four hours
# while there are few beta testers (it was 15 minutes, then an hour).
TANTRUM_WINDOW = timedelta(hours=4)
TANTRUM_WELLBEING_PENALTY = 15.0
# He naps for NAP_FOR from each of NAP_LOCAL_HOURS on the NAP_TIMEZONE clock;
# the slots follow that clock through daylight saving, and everything else
# stays UTC. Members see nap times in their own time zone. The lights must go off
# within LIGHTS_WINDOW, or he loses LIGHTS_WELLBEING_PENALTY Wellbeing and is
# cranky for CRANKY_FOR after the nap. LIGHTS_WINDOW must stay under NAP_FOR;
# it is most of the nap while the server is small (it was 15 minutes, then 55
# with one-hour naps). A poke during a nap wakes him, cranky for CRANKY_FOR,
# for WOKEN_FOR; the nap keeps counting down, and he dozes off again for what
# is left of it.
NAP_TIMEZONE: Final = "America/Los_Angeles"
NAP_LOCAL_HOURS: Final = (7, 13, 22)
NAP_FOR = timedelta(hours=4, minutes=30)
LIGHTS_WINDOW = timedelta(hours=4)
LIGHTS_WELLBEING_PENALTY = 10.0
CRANKY_FOR = timedelta(hours=1)
WOKEN_FOR = timedelta(minutes=30)
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
# The pictures in ASSETS/moments for a cold and its medicine.
SNIFFLES_PICTURE: Final = "wispsick.gif"
MEDICINE_PICTURE: Final = "medicine.png"
SNEEZE_PICTURE: Final = "sneeze.gif"
# More Monster Pox pictures in ASSETS/moments for his replies only, by stage.
POX_TALK_PICTURES: Final[dict[Stage, str]] = {
    Stage.CHILD: "childpox.png",
    Stage.TEEN: "teenpox.png",
}
# The pictures in ASSETS/moments one of which goes with his reply to a member
# talking to him or poking him while he is sick. Monster Pox wins over a cold.
POX_PICTURES: Final[dict[Stage, tuple[str, ...]]] = {
    stage: (
        *((SICK_PICTURES[stage],) if stage in SICK_PICTURES else ()),
        *((POX_TALK_PICTURES[stage],) if stage in POX_TALK_PICTURES else ()),
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
# His tantrum post shows his stage's angry gif (ASSETS/wispmoods/gifs); with
# that file missing it shows its picture in ASSETS/moments here instead.
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

# The picture in ASSETS/moments Wisp posts with a member's first offense.
FIRST_OFFENSE_PICTURE: Final = "banned.gif"
# Ban lengths by offence count; None is permanent.
BAN_LADDER: tuple[timedelta | None, ...] = (
    timedelta(days=1),
    timedelta(days=7),
    None,
)

# ---
# Rhyme Duel
# ---

RHYME_TURN = timedelta(seconds=15)
RHYME_PERFECT_POINTS = 2
RHYME_SLANT_POINTS = 1
RHYME_OPENER_RHYMES = 8
# Spanish and French openers also need this many letters, and are never among
# the first RHYME_OPENER_SKIP_TOP (most frequent) words of their list, so a
# function word like "la" or "que" never opens a duel.
RHYME_OPENER_MIN_LETTERS = 4
RHYME_OPENER_SKIP_TOP = 150
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
# Wisp's Craving
# ---

# Each member's own daily snack guess, apart from their Rhyme Duel plays. A
# round ends as a loss after CRAVING_GUESSES wrong guesses, or after
# CRAVING_TIMEOUT with no guess, counted from the last one. One round a day
# is kept by the cravings table's key, so there is no count to tune.
CRAVING_GUESSES = 3
CRAVING_TIMEOUT = timedelta(minutes=5)

# ---
# Moody phrases
# ---

# When Wisp is hangry, lonely or feels anything (sick, spoiled, cranky) at one
# of MOODY_STAGES, each AI answer has MOODY_PHRASE_CHANCE of working one of
# staff's song lines for his stage into it, at most once per MOODY_PHRASE_GAP
# per server. A stage plays once it has MOODY_OPTIONS different songs; the
# menu under the line offers that many (the rounds table holds three). The
# first member to name the song within MOODY_ROUND_FOR wins
# MOODY_PHRASE_REWARD wisp coins.
MOODY_STAGES: Final = (
    Stage.CHILD,
    Stage.TEEN,
    Stage.ADULT,
    Stage.ROCKSTAR,
    Stage.OLD_FOGEY,
)
MOODY_PHRASE_CHANCE = 0.25
MOODY_PHRASE_GAP = timedelta(minutes=30)
MOODY_ROUND_FOR = timedelta(hours=2)
MOODY_OPTIONS = 3
MOODY_PHRASE_REWARD = 3
# The longest phrase, artist and song staff can add, and the years allowed.
MOODY_PHRASE_MAX = 300
MOODY_CREDIT_MAX = 100
MOODY_YEAR_MIN = 1000
MOODY_YEAR_MAX = 2100

# ---
# Rooms
# ---

# Each member's private thread off his House. Discord caps a thread name at
# ROOM_NAME_MAX characters, and only allows 60, 1440, 4320 or 10080 minutes
# here and for STUDIO_THREAD_ARCHIVE_MINUTES.
ROOM_ARCHIVE_MINUTES: Final = 10080
ROOM_NAME_MAX: Final = 100

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
# Snacks
# ---


@dataclass(frozen=True)
class Snack:
    """A snack in the Snack Box.

    `article` goes before its name in a sentence, such as "a Jelly Wave" or
    "some Cheese".
    """

    key: str
    name: str
    cost: int
    meal: int
    growth: int
    article: str = "a"

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
    Snack("cloudwave", "Cloud Wave", 6, 5, 1),
    Snack("jellywave", "Jelly Wave", 6, 5, 1),
    Snack("juicewave", "Juice Wave", 6, 5, 1),
    Snack("spicywave", "Spicy Wave", 5, 8, 2),
    Snack("cheese", "Cheese", 6, 8, 2, article="some"),
    Snack("pickles", "Pickles", 6, 8, 2, article="some"),
    Snack("glitterwave", "Glitter Wave", 6, 12, 3),
    Snack("viibrwave", "ViiBR Wave", 10, 15, 3),
)
SNACK_BY_KEY: dict[str, Snack] = {snack.key: snack for snack in SNACKS}
PAID_SNACKS: tuple[Snack, ...] = tuple(snack for snack in SNACKS if snack.cost > 0)

# ---
# Wisp's lunchbox
# ---

FAVORITE_SONGS_SHOWN = 3
# The longest song title he keeps; `favorites.title` holds this many characters.
SONG_TITLE_LIMIT = 200

# ---
# Gifts
# ---

GIFT_COST = 15
# Wisp coins for opening /wisp board the first time.
STARTER_COINS = 30
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
    it, such as "Blue Alien Doll" or "Arcade". A gift that `grows` looks
    different at each of Wisp's stages, like his TV. A `plural` title takes
    no "a" in messages, as "gave Wisp TV Shows".
    """

    key: str
    name: str
    collection: str
    title: str
    grows: bool = False
    plural: bool = False

    def look(self, stage: Stage) -> str:
        """The name of its emoji and picture while Wisp is at `stage`.

        A gift that grows is named for the stage too, as "tech_tv_teen".
        """
        return f"{self.key}_{stage.value}" if self.grows else self.key

    def emoji_name(self, stage: Stage) -> str:
        """Name of the app emoji that shows this gift while Wisp is at `stage`."""
        return f"gift_{self.look(stage)}"


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
    growing: frozenset[str] = frozenset(),
    plural: frozenset[str] = frozenset(),
) -> GiftCollection:
    """A collection whose gifts are titled "<name> <item>", such as "Red Book".

    With `named_by_item` off, each gift's name is already its whole title,
    such as "Mimitchi". The gifts keyed in `growing` look different at each
    of Wisp's stages; those keyed in `plural` have plural titles.
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
                gift_key in growing,
                gift_key in plural,
            )
            for gift_key, gift_name in gifts
        ),
    )


GIFT_COLLECTIONS: tuple[GiftCollection, ...] = (
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
        "tech",
        "Tech",
        "Tech Toy",
        (
            ("tetris_handheld", "Tetris Handheld"),
            ("tech_arcade", "Arcade"),
            ("tech_tv", "TV Shows"),
        ),
        named_by_item=False,
        growing=frozenset({"tech_tv"}),
        plural=frozenset({"tech_tv"}),
    ),
)
GIFT_BY_KEY: dict[str, Gift] = {
    gift.key: gift for collection in GIFT_COLLECTIONS for gift in collection.gifts
}
# Every name a gift's emoji and picture go by, at any stage.
GIFT_BY_LOOK: dict[str, Gift] = {
    gift.look(stage): gift for gift in GIFT_BY_KEY.values() for stage in Stage
}
# The episode on Wisp's TV at each stage, posted in his House when he keeps it.
TV_EPISODES: dict[Stage, str] = {
    Stage.BABY: "https://www.youtube.com/watch?v=U1jUICPWMYU",
    Stage.CHILD: "https://www.youtube.com/watch?v=rpJkTXWM-dI",
    Stage.TEEN: "https://www.youtube.com/shorts/XByD0w9P9lk",
    Stage.ADULT: "https://www.youtube.com/watch?v=51X9Rdz2PWk",
    Stage.ROCKSTAR: "https://www.youtube.com/watch?v=CtvxQ09LqUY",
    Stage.OLD_FOGEY: "https://www.youtube.com/watch?v=7cv91dwBUo4",
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
    Badge("team_viibr", "Team ViiBR", 175, 25, "joined Team ViiBR"),
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
# The worker's FLUX.2 klein model draws him from his stage's picture. His AI
# writes a scene of at most DRAWING_SCENE_MAX_CHARS; a line saying he is the
# character in that picture and the style are added, up to
# IMAGE_PROMPT_MAX_CHARS in all.
IMAGE_PROMPT_MAX_CHARS = 1000
DRAWING_SCENE_MAX_CHARS = 400
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
# The chance his answer to a mention or a poke shows the mood gif of what he
# feels (angry, annoyed, crying) or of a laugh in his words, when he is not sick.
MOOD_TALK_PICTURE_CHANCE = 0.35
# The chance his answer to a mention or a poke shows a sick picture while he is
# sick; otherwise that answer has no picture at all.
SICK_TALK_PICTURE_CHANCE = 0.35
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
# gets POKE_MOOD_WEIGHT while the House is sleepy. Being annoyed gets
# POKE_MOOD_WEIGHT while he is hangry, plus POKE_LONELY_WEIGHT while he is
# lonely, POKE_CRANKY_WEIGHT while cranky and POKE_SPOILED_WEIGHT while
# spoiled, else none.
POKE_TICKLED_WEIGHT = 6
POKE_STARTLED_WEIGHT = 2
POKE_CURIOUS_WEIGHT = 2
POKE_MOOD_WEIGHT = 12
POKE_LONELY_WEIGHT = 8
POKE_CRANKY_WEIGHT = 10
POKE_SPOILED_WEIGHT = 8
