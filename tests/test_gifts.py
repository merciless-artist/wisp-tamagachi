"""Tests for gifts: the catalog, the roll, the Vault select and the lunchbox.

Discord objects are fakes; the repositories are the real ones.
"""

import random
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import assets as art
from cogs import gifts, snacks
from cogs.assets import asset_image
from cogs.gifts import Gifts
from cogs.wisp_lunchbox import lunchbox_text
from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo
from db.database import Database
from db.drawings import DrawingRepo
from db.gifts import GiftAttempt, GiftRepo
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.magazines import MagazineRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from db.story import LifeStoryRepo
from tests.layout import (
    STYLE_EMOJIS,
    assert_is_a_menu,
    layout_selects,
    layout_text,
)
from tests.layout import section as menu_section
from tests.layout import vault_opened, vault_parts
from wisp import rules
from wisp.gifts import (
    GiftState,
    Outcome,
    decide,
    like_chance,
    named,
    tv_episode,
    tv_line,
    with_article,
)
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.rules import GIFT_BY_KEY, GIFT_COLLECTIONS, Stage
from wisp.text import (
    LAYOUT_TEXT_LIMIT,
    UNICODE_FRAME,
    USER_ERROR,
    Frame,
    frame_of,
    text_length,
)
from wisp.voice import DrawReason

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
USER_ID = 1
OTHER_USER_ID = 2
NEWCOMER_ID = 3
QUALIFYING_ROLE = 7
NO_PING = discord.AllowedMentions.none().to_dict()
PING_GIVER = {"parse": [], "users": [USER_ID]}
ASSETS = Path(__file__).resolve().parent.parent / "ASSETS"
KEEP = 0.0
PASS = 0.99
GIVE = "Give Wisp a gift"
PICK = "Pick a collection"
LONG_EMOJI = "<a:" + "e" * 23 + ":" + "1" * 19 + ">"
# Without the style's emojis uploaded, every menu is plain text.
FRAME = UNICODE_FRAME
GIFTS_HEADING = f"{FRAME.heading('Gifts', 4)} ・ 15 WC each"
GAMBLE = FRAME.note("ᵗʰᵉˢᵉ ᵃʳᵉ ᵃ ᵍᵃᵐᵇˡᵉ... ʰᵉ ᵐⁱᵍʰᵗ ⁿᵒᵗ ʷᵃⁿᵗ ⁱᵗ ᵗʰᵃᵗ ᵈᵃʸ")

# ---
# Fakes
# ---


class FixedRandom(random.Random):
    """A random source whose every roll is the same number."""

    def __init__(self, roll: float) -> None:
        super().__init__()
        self.roll = roll
        self.rolls = 0

    def random(self) -> float:
        self.rolls += 1
        return self.roll


class FakeServer:
    """A guild with Wisp's House."""

    def __init__(self) -> None:
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock()
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def cog(bot: app.WispBot) -> Gifts:
    gifts_cog = Gifts(bot)
    gifts_cog.rng = FixedRandom(KEEP)
    return gifts_cog


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.story = LifeStoryRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.drawings = DrawingRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.magazines = MagazineRepo(db)
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture(autouse=True)
def drawing(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    made = AsyncMock()
    monkeypatch.setattr(snacks, "draw_for", made)
    return made


@pytest.fixture(autouse=True)
async def configured(
    bot: app.WispBot, cog: Gifts, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        bot, "get_cog", lambda name: cog if name == Gifts.__cog_name__ else None
    )
    monkeypatch.setattr(snacks, "maybe_meet", AsyncMock())
    await bot.settings.update(
        GUILD_ID, house_channel_id=HOUSE_ID, studio_forum_id=FORUM_ID
    )
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    for user_id in (USER_ID, OTHER_USER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())
        await bot.players.add_points(GUILD_ID, user_id, 100)


def make_interaction(
    bot: app.WispBot,
    user_id: int = USER_ID,
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.user = MagicMock(spec=discord.Member)
    interaction.user.id = user_id
    interaction.user.display_name = f"Member{user_id}"
    interaction.user.roles = [
        MagicMock(spec=discord.Role, id=role_id) for role_id in roles
    ]
    interaction.response = MagicMock()
    interaction.response.is_done.return_value = False

    async def answer(*_args: Any, **_kwargs: Any) -> None:
        interaction.response.is_done.return_value = True

    interaction.response.defer = AsyncMock(side_effect=answer)
    interaction.response.send_message = AsyncMock(side_effect=answer)
    interaction.edit_original_response = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def give_emojis(bot: app.WispBot, *names: str) -> None:
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(names, start=1)
    }


def emoji_text(name: str, index: int) -> str:
    return f"<:{name}:{index}>"


async def lay(
    bot: app.WispBot,
    phase: Phase = Phase.ALIVE,
    health: float = 50.0,
    version: int = 1,
    stage: Stage = Stage.BABY,
) -> Life:
    life = new_egg(version, discord.utils.utcnow() - timedelta(days=2))
    life.phase = phase
    life.health = health
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = stage
        life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


def gave(gift: str, earlier_gifts: int = 0) -> str:
    """The receipt line for a gift given after `earlier_gifts` others today."""
    now = rules.WELLBEING_START + (earlier_gifts + 1) * rules.WELLBEING_PER_GIFT
    return (
        f"♪ You gave Wisp {gift}. "
        f"Wellbeing +{rules.WELLBEING_PER_GIFT} (now {now:.0f})."
    )


def posted(user_id: int, gift: str, bond: int = 0, earlier_gifts: int = 0) -> str:
    """The head of a gift's post in the House."""
    now = rules.WELLBEING_START + (earlier_gifts + 1) * rules.WELLBEING_PER_GIFT
    kept = f" ・ bond +{bond}" if bond else ""
    return (
        f"♪ <@{user_id}> gave Wisp {gift} ・ "
        f"Wellbeing +{rules.WELLBEING_PER_GIFT} (now {now:.0f}){kept}"
    )


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


async def open_vault(
    bot: app.WispBot, user_id: int = USER_ID
) -> tuple[str, list[discord.ui.Select[Any]]]:
    interaction = make_interaction(bot, user_id)
    command: Any = snacks.wisp_vault
    await command.callback(interaction)
    return vault_opened(interaction.followup.send)


def placeholder_select(
    selects: list[discord.ui.Select[Any]], placeholder: str
) -> discord.ui.Select[Any]:
    (select,) = [select for select in selects if select.placeholder == placeholder]
    return select


def gift_select(selects: list[discord.ui.Select[Any]]) -> discord.ui.Select[Any]:
    return placeholder_select(selects, GIVE)


def collection_select(
    selects: list[discord.ui.Select[Any]],
) -> discord.ui.Select[Any]:
    return placeholder_select(selects, PICK)


def shown(interaction: MagicMock) -> tuple[str, list[discord.ui.Select[Any]]]:
    """The Vault as an interaction last showed it: its text and its selects."""
    call = interaction.edit_original_response.await_args
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert "content" not in call.kwargs
    view = call.kwargs["view"]
    return layout_text(view), layout_selects(view)


async def pick(
    bot: app.WispBot,
    collection_key: str,
    user_id: int = USER_ID,
    select: discord.ui.Select[Any] | None = None,
) -> MagicMock:
    """Pick a collection in the Vault, opened now unless a select is given."""
    if select is None:
        _, selects = await open_vault(bot, user_id)
        select = collection_select(selects)
    select._values = [collection_key]
    interaction = make_interaction(bot, user_id)
    await select.callback(interaction)
    return interaction


async def item_select(
    bot: app.WispBot, collection_key: str, user_id: int = USER_ID
) -> discord.ui.Select[Any]:
    """The gift select the Vault shows after picking a collection."""
    _, selects = shown(await pick(bot, collection_key, user_id))
    return gift_select(selects)


async def offered(bot: app.WispBot, user_id: int = USER_ID) -> list[str]:
    """Every gift the Vault offers now, collection by collection."""
    _, selects = await open_vault(bot, user_id)
    pickers = [select for select in selects if select.placeholder == PICK]
    keys: list[str] = []
    for picker in pickers:
        for option in picker.options:
            items = await item_select(bot, option.value, user_id)
            keys.extend(item.value for item in items.options)
    return keys


async def give(
    bot: app.WispBot,
    key: str,
    user_id: int = USER_ID,
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
    select: discord.ui.Select[Any] | None = None,
) -> MagicMock:
    """Give a gift through the Vault's two selects, picked now unless one is given."""
    if select is None:
        select = await item_select(bot, GIFT_BY_KEY[key].collection, user_id)
    select._values = [key]
    interaction = make_interaction(bot, user_id, roles)
    await select.callback(interaction)
    return interaction


def edited(interaction: MagicMock) -> str:
    text, _ = shown(interaction)
    return text


def lines_under(text: str, heading: str) -> list[str]:
    """The lines under a section heading, up to the next heading or the footer."""
    return menu_section(text.splitlines(), FRAME.heading(heading, 0))


def gift_lines(text: str) -> list[str]:
    """The Vault's lines under the Gifts heading, up to the footer."""
    lines = text.splitlines()
    start = lines.index(GIFTS_HEADING) + 1
    return lines[start : lines.index(FRAME.footer)]


def house_post(server: FakeServer) -> tuple[str, dict[str, Any]]:
    """The one House post about a gift, checked to ping only its giver."""
    server.house.send.assert_awaited_once()
    call = server.house.send.await_args
    assert call.kwargs["allowed_mentions"].to_dict() == PING_GIVER
    return cast(str, call.args[0]), call.kwargs


def say(bot: app.WispBot) -> MagicMock:
    bot.lines = MagicMock()
    bot.lines.pick.side_effect = lambda moment, *_args, **_fields: f"[{moment}]"
    return cast(MagicMock, bot.lines.pick)


async def balance(bot: app.WispBot, user_id: int = USER_ID) -> int:
    return (await bot.players.get(GUILD_ID, user_id)).balance


async def bond(bot: app.WispBot, user_id: int = USER_ID) -> int:
    return (await bot.players.get(GUILD_ID, user_id)).bond


async def kept_keys(bot: app.WispBot) -> list[str]:
    life = await current_life(bot)
    assert life.id is not None
    return [attempt.gift for attempt in await bot.gifts.kept(GUILD_ID, life.id)]


def collection(key: str) -> rules.GiftCollection:
    return next(group for group in GIFT_COLLECTIONS if group.key == key)


# ---
# The catalog
# ---


def test_there_are_four_collections_in_order() -> None:
    assert [
        (group.name, [gift.key for gift in group.gifts]) for group in GIFT_COLLECTIONS
    ] == [
        ("Alien Dolls", ["alien_blue", "alien_green", "alien_purple", "alien_yellow"]),
        ("Books", ["book_blue", "book_green", "book_orange", "book_red"]),
        (
            "Tamagotchis",
            ["tama_hawaikotchi", "tama_mimitchi", "tama_nano", "tama_welcotchi"],
        ),
        (
            "Tech",
            ["tetris_handheld", "tech_arcade", "tech_tv"],
        ),
    ]
    assert [len(group.gifts) for group in GIFT_COLLECTIONS] == [4, 4, 4, 3]
    assert all(len(key) <= 30 for key in GIFT_BY_KEY)
    assert len(GIFT_BY_KEY) == 15


@pytest.mark.parametrize(
    ("key", "title"),
    [
        ("alien_blue", "Blue Alien Doll"),
        ("book_red", "Red Book"),
        ("tama_hawaikotchi", "Hawaikotchi"),
        ("tama_mimitchi", "Mimitchi"),
        ("tama_nano", "Tamagotchi Nano"),
        ("tama_welcotchi", "Welcotchi"),
        ("tetris_handheld", "Tetris Handheld"),
        ("tech_arcade", "Arcade"),
        ("tech_tv", "TV Shows"),
    ],
)
def test_a_gift_reads_with_its_collection(key: str, title: str) -> None:
    assert GIFT_BY_KEY[key].title == title


@pytest.mark.parametrize("stage", [stage for stage in Stage if stage is not Stage.EGG])
def test_every_gift_has_its_emoji_name_and_art(stage: Stage) -> None:
    for group in GIFT_COLLECTIONS:
        for gift in group.gifts:
            look = f"{gift.key}_{stage.value}" if gift.grows else gift.key
            assert gift.collection == group.key
            assert gift.look(stage) == look
            assert gift.emoji_name(stage) == f"gift_{look}"
            assert len(gift.emoji_name(stage)) <= 32, look
            assert rules.GIFT_BY_LOOK[look] is gift
            assert asset_image(ASSETS / "gifts", look) is not None, look


def test_only_the_tv_grows_and_each_stage_has_one_show_episode() -> None:
    assert [gift.key for gift in GIFT_BY_KEY.values() if gift.grows] == ["tech_tv"]
    shown = [stage for show in rules.TV_SHOWS for stage in show.stages]
    assert sorted(shown) == sorted(set(Stage) - {Stage.EGG})
    assert len(shown) == len(set(shown))
    assert GIFT_BY_KEY["tech_tv"].look(Stage.OLD_FOGEY) == "tech_tv_old_fogey"
    for show in rules.TV_SHOWS:
        assert len(show.episodes) == len(show.stages)


LLAMA, ZEPHYRINE = rules.TV_SHOWS


@pytest.mark.parametrize(
    ("kept_at", "stage", "show", "number"),
    [
        (Stage.BABY, Stage.BABY, LLAMA, 1),
        (Stage.BABY, Stage.CHILD, LLAMA, 2),
        (Stage.BABY, Stage.TEEN, LLAMA, 3),
        (Stage.BABY, Stage.ADULT, ZEPHYRINE, 1),
        (Stage.BABY, Stage.OLD_FOGEY, ZEPHYRINE, 3),
        (Stage.CHILD, Stage.CHILD, LLAMA, 1),
        (Stage.CHILD, Stage.TEEN, LLAMA, 2),
        (Stage.CHILD, Stage.ADULT, ZEPHYRINE, 1),
        (Stage.TEEN, Stage.TEEN, LLAMA, 1),
        (Stage.TEEN, Stage.ADULT, ZEPHYRINE, 1),
        (Stage.TEEN, Stage.ROCKSTAR, ZEPHYRINE, 2),
        (Stage.ADULT, Stage.ADULT, ZEPHYRINE, 1),
        (Stage.ROCKSTAR, Stage.OLD_FOGEY, ZEPHYRINE, 2),
        (Stage.OLD_FOGEY, Stage.OLD_FOGEY, ZEPHYRINE, 1),
    ],
)
def test_the_tv_plays_its_shows_episodes_in_order_from_the_first(
    kept_at: Stage, stage: Stage, show: rules.TvShow, number: int
) -> None:
    episode = tv_episode(kept_at, stage)

    assert episode is not None
    assert (episode.show, episode.number) == (show, number)
    assert episode.link == show.episodes[number - 1]


@pytest.mark.parametrize(
    ("kept_at", "stage"),
    [(Stage.TEEN, Stage.CHILD), (Stage.BABY, Stage.EGG), (Stage.EGG, Stage.EGG)],
)
def test_no_episode_before_he_had_the_tv_or_as_an_egg(
    kept_at: Stage, stage: Stage
) -> None:
    assert tv_episode(kept_at, stage) is None


@pytest.mark.parametrize(
    ("kept_at", "number"), [(Stage.ADULT, 2), (Stage.TEEN, 2), (Stage.BABY, 2)]
)
def test_a_skipped_rockstar_skips_no_episode(kept_at: Stage, number: int) -> None:
    episode = tv_episode(kept_at, Stage.OLD_FOGEY, frozenset({Stage.ROCKSTAR}))

    assert episode is not None
    assert (episode.show, episode.number) == (ZEPHYRINE, number)


def test_a_skipped_stage_has_no_episode() -> None:
    assert tv_episode(Stage.ADULT, Stage.ROCKSTAR, frozenset({Stage.ROCKSTAR})) is None


def test_the_tv_line_names_the_show_and_episode_over_its_link() -> None:
    episode = tv_episode(Stage.CHILD, Stage.TEEN)
    assert episode is not None

    assert tv_line(episode) == (
        "♪ Now on Wisp's TV: Llama Brain, episode 2\n"
        "https://www.youtube.com/watch?v=rpJkTXWM-dI"
    )


def test_the_catalog_fits_discord_and_the_database() -> None:
    for group in GIFT_COLLECTIONS:
        assert len(group.gifts) <= 25, group.key
        assert len(group.name) <= 100, group.key
        for gift in group.gifts:
            assert len(gift.key) <= 30, gift.key
            assert len(gift.name) <= 100, gift.key
            assert len(gift.title) <= 100, gift.key


def test_gift_numbers_are_the_starting_values() -> None:
    assert rules.GIFT_COST == 15
    assert rules.GIFT_LIKE_CHANCE == pytest.approx(1 / 2)
    assert rules.GIFT_LIKE_RISE == pytest.approx(1 / 4)
    assert rules.BOND_PER_KEPT_GIFT == 5
    assert rules.COLLECTION_BOND_BONUS == 25


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Orange Book", "an Orange Book"),
        ("Blue Alien Doll", "a Blue Alien Doll"),
        ("Amethyst", "an Amethyst"),
        ("Ruby", "a Ruby"),
        ("Hawaikotchi", "a Hawaikotchi"),
        ("I Block", "an I Block"),
        ("L Block", "an L Block"),
        ("S Block", "an S Block"),
        ("T Block", "a T Block"),
        ("Z Block", "a Z Block"),
        ("Tech Toy", "a Tech Toy"),
        ("Arcade", "an Arcade"),
        ("TV", "a TV"),
    ],
)
def test_a_gift_gets_the_right_article(title: str, expected: str) -> None:
    assert with_article(title) == expected


@pytest.mark.parametrize(
    ("key", "expected"),
    [("book_red", "a Red Book"), ("tech_arcade", "an Arcade"), ("tech_tv", "TV Shows")],
)
def test_a_plural_gift_is_named_with_no_article(key: str, expected: str) -> None:
    assert named(GIFT_BY_KEY[key]) == expected
    assert GIFT_BY_KEY[key].plural is (key == "tech_tv")


# ---
# The roll and the stock
# ---


def test_the_roll_keeps_under_the_like_chance() -> None:
    state = GiftState(frozenset(), frozenset(), kept_today=False, stage=Stage.BABY)

    assert decide(state, FixedRandom(rules.GIFT_LIKE_CHANCE - 0.01)) is Outcome.KEPT
    assert decide(state, FixedRandom(rules.GIFT_LIKE_CHANCE)) is Outcome.PASSED


@pytest.mark.parametrize(
    ("passed_today", "chance"),
    [((), 1 / 2), (("aliens",), 3 / 4), (("aliens", "books"), 1.0)],
)
def test_each_gift_he_passes_on_makes_him_more_open(
    passed_today: tuple[str, ...], chance: float
) -> None:
    state = GiftState(
        frozenset(), frozenset(passed_today), kept_today=False, stage=Stage.BABY
    )

    assert like_chance(state) == pytest.approx(chance)
    assert decide(state, FixedRandom(chance - 0.01)) is Outcome.KEPT


def test_the_third_gift_of_a_day_is_always_kept() -> None:
    state = GiftState(
        frozenset(), frozenset({"aliens", "books"}), kept_today=False, stage=Stage.BABY
    )

    assert decide(state, FixedRandom(PASS)) is Outcome.KEPT
    assert like_chance(
        GiftState(
            frozenset(), frozenset({"aliens", "books", "tech"}), False, Stage.BABY
        )
    ) == pytest.approx(1.0)


def test_after_a_kept_gift_he_is_full_without_rolling() -> None:
    rng = FixedRandom(KEEP)

    outcome = decide(
        GiftState(frozenset(), frozenset(), kept_today=True, stage=Stage.BABY), rng
    )

    assert outcome is Outcome.FULL
    assert rng.rolls == 0


def test_the_state_knows_stock_open_collections_and_completion() -> None:
    aliens = collection("aliens")
    kept = frozenset(gift.key for gift in aliens.gifts[:3])
    state = GiftState(kept, frozenset({"books"}), kept_today=False, stage=Stage.BABY)

    assert not state.in_stock(aliens.gifts[0])
    assert state.can_give(aliens.gifts[3])
    assert state.completes(aliens.gifts[3])
    assert not state.can_give(collection("books").gifts[0])
    assert state.offered_from(aliens) == [aliens.gifts[3]]
    assert state.offered_from(collection("books")) == []
    assert state.offered_from(collection("tech")) == list(collection("tech").gifts)


# ---
# Storage
# ---


async def test_attempts_are_kept_per_life_and_per_day(db: Database) -> None:
    repo = GiftRepo(db)
    now = discord.utils.utcnow()
    yesterday = now - timedelta(days=1)
    await repo.record(GUILD_ID, 1, USER_ID, "alien_blue", True, yesterday)
    await repo.record(GUILD_ID, 1, OTHER_USER_ID, "book_red", False, now)
    await repo.record(GUILD_ID, 1, USER_ID, "book_blue", True, now)
    await repo.record(GUILD_ID, 2, USER_ID, "tama_nano", True, now)

    kept = await repo.kept(GUILD_ID, 1)
    today = await repo.today(GUILD_ID, 1, now)

    assert [(attempt.gift, attempt.user_id) for attempt in kept] == [
        ("alien_blue", USER_ID),
        ("book_blue", USER_ID),
    ]
    assert [(attempt.gift, attempt.kept) for attempt in today] == [
        ("book_red", False),
        ("book_blue", True),
    ]
    assert isinstance(kept[0], GiftAttempt)


# ---
# Giving a gift
# ---


async def test_a_kept_gift_leaves_the_vault_and_gives_bond_and_growth(
    bot: app.WispBot,
    server: FakeServer,
    db: Database,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(art, "ASSETS_DIR", tmp_path)
    await lay(bot)
    pick = say(bot)

    interaction = await give(bot, "alien_blue")

    assert await balance(bot) == 100 - rules.GIFT_COST
    assert await bond(bot) == rules.BOND_PER_KEPT_GIFT
    assert (await current_life(bot)).growth == rules.GROWTH_PER_BOND_MOMENT
    assert await kept_keys(bot) == ["alien_blue"]
    rows = await db.fetchall(
        f"SELECT kind, bond, meal_points FROM {db.t('interactions')}"
    )
    assert rows == [
        {"kind": "gift", "bond": rules.BOND_PER_KEPT_GIFT, "meal_points": 0}
    ]
    text, kwargs = house_post(server)
    bond_gained = rules.BOND_PER_KEPT_GIFT
    head = posted(USER_ID, "a Blue Alien Doll", bond_gained)
    assert text == f"{head}\n[gift_kept]"
    assert "file" not in kwargs
    pick.assert_called_once_with(
        Moment.GIFT_KEPT, Mood.HAPPY, name="Member1", gift="Blue Alien Doll"
    )
    reply = edited(interaction)
    assert reply.startswith(
        f"{gave('a Blue Alien Doll')}\n♪ Wisp kept your Blue Alien Doll"
    )
    assert FRAME.note(f"wisp coins: {100 - rules.GIFT_COST}") in reply.splitlines()
    assert "alien_blue" not in await offered(bot)


async def test_a_kept_gift_brings_its_art_when_it_exists(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gifts").mkdir()
    (tmp_path / "gifts" / "book_orange.png").write_bytes(b"PNG")
    monkeypatch.setattr(art, "ASSETS_DIR", tmp_path)
    await lay(bot)
    say(bot)

    await give(bot, "book_orange")

    text, kwargs = house_post(server)
    head = posted(USER_ID, "an Orange Book", rules.BOND_PER_KEPT_GIFT)
    assert text.startswith(f"{head}\n")
    attached = kwargs["file"]
    assert isinstance(attached, discord.File)
    assert attached.filename == "book_orange.png"


async def test_a_passed_gift_stays_in_stock_and_still_costs(
    bot: app.WispBot, server: FakeServer, cog: Gifts
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(PASS)
    say(bot)

    interaction = await give(bot, "tama_mimitchi")

    assert await balance(bot) == 100 - rules.GIFT_COST
    assert await bond(bot) == 0
    assert (await current_life(bot)).growth == 0
    assert await kept_keys(bot) == []
    text, kwargs = house_post(server)
    head = posted(USER_ID, "a Mimitchi")
    assert text == f"{head}\n[gift_passed]\n♪ It's back in the ViiBR Vault."
    assert "file" not in kwargs
    assert edited(interaction).startswith(
        f"{gave('a Mimitchi')}\n"
        "♪ Wisp passed on your Mimitchi. It's back in the Vault."
    )
    now = discord.utils.utcnow()
    assert await bot.activity_log.people_since(GUILD_ID, now - timedelta(hours=1))


@pytest.mark.parametrize(
    ("roll", "moment"), [(KEEP, Moment.GIFT_ASLEEP), (PASS, Moment.GIFT_PASSED)]
)
async def test_a_gift_kept_while_he_naps_gets_a_sleepy_line(
    bot: app.WispBot, server: FakeServer, cog: Gifts, roll: float, moment: Moment
) -> None:
    """A passed-on gift keeps its own line, which says it went back."""
    life = await lay(bot)
    life.nap_left = 1800.0
    await bot.lives.save(GUILD_ID, life)
    cog.rng = FixedRandom(roll)
    pick = say(bot)

    await give(bot, "alien_blue")

    text, _kwargs = house_post(server)
    head, said = text.split("\n")[:2]
    assert head.startswith(f"♪ <@{USER_ID}> gave Wisp a Blue Alien Doll ・ Wellbeing")
    assert said == f"[{moment}]"
    pick.assert_called_once_with(
        moment, Mood.HAPPY, name="Member1", gift="Blue Alien Doll"
    )


@pytest.mark.parametrize("roll", [KEEP, PASS])
async def test_every_gift_bought_adds_eight_wellbeing_and_ends_its_stretch(
    bot: app.WispBot, cog: Gifts, roll: float
) -> None:
    life = await lay(bot)
    life.wellbeing_stretch = 5400.0
    await bot.lives.save(GUILD_ID, life)
    cog.rng = FixedRandom(roll)
    say(bot)

    await give(bot, "alien_blue")
    after = await current_life(bot)
    assert after.wellbeing == rules.WELLBEING_START + rules.WELLBEING_PER_GIFT == 58.0
    assert after.wellbeing_stretch == 0.0

    cog.rng = FixedRandom(KEEP)
    await give(bot, "book_red", OTHER_USER_ID)
    await give(bot, "tama_mimitchi", OTHER_USER_ID)

    kept_today = roll == KEEP
    assert await kept_keys(bot) == (["alien_blue"] if kept_today else ["book_red"])
    expected = rules.WELLBEING_START + 3 * rules.WELLBEING_PER_GIFT
    assert (await current_life(bot)).wellbeing == expected


async def test_a_refused_gift_adds_no_care(bot: app.WispBot) -> None:
    await lay(bot)
    await bot.players.spend(GUILD_ID, USER_ID, 100 - rules.GIFT_COST + 1)
    say(bot)

    await give(bot, "alien_blue")

    assert (await current_life(bot)).wellbeing == rules.WELLBEING_START


async def test_a_collection_is_given_from_once_a_day(
    bot: app.WispBot, server: FakeServer, cog: Gifts
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(PASS)
    before = await item_select(bot, "aliens", OTHER_USER_ID)
    await give(bot, "alien_blue")

    text, _ = await open_vault(bot, OTHER_USER_ID)
    assert not any(key.startswith("alien_") for key in await offered(bot))
    assert FRAME.item("Alien Dolls: back tomorrow") in text

    stale = await give(bot, "alien_green", OTHER_USER_ID, select=before)

    assert await balance(bot, OTHER_USER_ID) == 100
    assert "Alien Doll" in edited(stale) and "tomorrow" in edited(stale)
    assert server.house.send.await_count == 1


async def test_after_one_kept_gift_he_is_full_for_the_day(
    bot: app.WispBot, server: FakeServer, cog: Gifts
) -> None:
    await lay(bot)
    say(bot)
    await give(bot, "alien_blue")

    interaction = await give(bot, "book_red", OTHER_USER_ID)

    assert await balance(bot, OTHER_USER_ID) == 100 - rules.GIFT_COST
    assert await bond(bot, OTHER_USER_ID) == 0
    assert await kept_keys(bot) == ["alien_blue"]
    call = server.house.send.await_args
    head = posted(OTHER_USER_ID, "a Red Book", earlier_gifts=1)
    assert call.args[0] == f"{head}\n[gift_full]\n♪ It's back in the ViiBR Vault."
    assert call.kwargs["allowed_mentions"].to_dict() == {
        "parse": [],
        "users": [OTHER_USER_ID],
    }
    assert edited(interaction).startswith(
        f"{gave('a Red Book', 1)}\n♪ Wisp already kept a gift today. "
        "Your Red Book is back in the Vault."
    )
    assert cast(FixedRandom, cog.rng).rolls == 1


async def test_he_keeps_another_gift_the_next_day(bot: app.WispBot, cog: Gifts) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "alien_blue", True, yesterday)

    await give(bot, "alien_green")

    assert await kept_keys(bot) == ["alien_blue", "alien_green"]


async def test_the_fourth_item_completes_the_collection_with_a_bonus(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for key in ("book_blue", "book_green", "book_orange"):
        await bot.gifts.record(GUILD_ID, life.id, OTHER_USER_ID, key, True, yesterday)
    pick = say(bot)

    interaction = await give(bot, "book_red")

    assert await bond(bot) == rules.BOND_PER_KEPT_GIFT + rules.COLLECTION_BOND_BONUS
    text, _ = house_post(server)
    gained = rules.BOND_PER_KEPT_GIFT + rules.COLLECTION_BOND_BONUS
    head = posted(USER_ID, "a Red Book", gained)
    assert text == f"{head}\n[gift_kept]\n[collection_done]"
    pick.assert_any_call(
        Moment.COLLECTION_DONE, Mood.HAPPY, name="Member1", collection="Books"
    )
    assert "Books" in edited(interaction)
    vault_text, _ = await open_vault(bot)
    assert FRAME.item("Books: all kept this life") in vault_text


async def test_a_new_life_restocks_the_vault(bot: app.WispBot) -> None:
    old = await lay(bot)
    assert old.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for gift in collection("aliens").gifts:
        await bot.gifts.record(GUILD_ID, old.id, USER_ID, gift.key, True, yesterday)
    await bot.gifts.record(
        GUILD_ID, old.id, USER_ID, "book_red", False, discord.utils.utcnow()
    )
    await lay(bot, version=2)

    text, _ = await open_vault(bot)

    options = await offered(bot)
    assert options == [gift.key for group in GIFT_COLLECTIONS for gift in group.gifts]
    assert "back tomorrow" not in text
    assert "all kept" not in text


async def test_short_points_are_refused_and_nothing_is_recorded(
    bot: app.WispBot, server: FakeServer, db: Database
) -> None:
    await lay(bot)
    await bot.players.spend(GUILD_ID, USER_ID, 100 - rules.GIFT_COST + 1)
    say(bot)

    interaction = await give(bot, "alien_blue")

    assert await balance(bot) == rules.GIFT_COST - 1
    assert (
        f"[not_enough_points]\n♪ That costs {rules.GIFT_COST} WC "
        f"and you have {rules.GIFT_COST - 1}."
    ) in edited(interaction)
    assert await db.fetchall(f"SELECT id FROM {db.t('gift_attempts')}") == []
    assert await db.fetchall(f"SELECT id FROM {db.t('interactions')}") == []
    server.house.send.assert_not_awaited()


async def test_a_ban_after_opening_the_vault_refuses_the_gift(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    select = await item_select(bot, "aliens")
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await give(bot, "alien_blue", select=select)

    assert "not taking snacks or gifts" in edited(interaction)
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


async def test_members_who_cannot_feed_cannot_give(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)

    interaction = await give(bot, "alien_blue", roles=())

    assert edited(interaction).startswith(
        "♪ Wisp can't take that from you: you don't have a role that can feed "
        f"Wisp: <@&{QUALIFYING_ROLE}>."
    )
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize(
    ("phase", "reason"),
    [
        (Phase.EGG, "♪ Wisp isn't hatched yet. Gifts have to wait until he is."),
        (Phase.HATCHING, "♪ Wisp isn't hatched yet. Gifts have to wait until he is."),
        (Phase.DEAD, "♪ Wisp isn't alive right now, so gifts have to wait."),
    ],
)
async def test_wisp_must_be_alive_for_gifts(
    bot: app.WispBot, server: FakeServer, phase: Phase, reason: str
) -> None:
    await lay(bot)
    select = await item_select(bot, "aliens")
    await lay(bot, phase=phase, health=0.0, version=2)

    interaction = await give(bot, "alien_blue", select=select)

    assert edited(interaction).startswith(reason)
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


async def test_a_gift_while_frozen_says_he_is_frozen(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    select = await item_select(bot, "aliens")
    await bot.settings.update(GUILD_ID, frozen=True)

    interaction = await give(bot, "alien_blue", select=select)

    assert edited(interaction).startswith(
        "♪ Wisp is frozen right now, so nothing can change until staff unfreeze him."
    )
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


async def test_a_hangry_wisp_reacts_hangry(bot: app.WispBot) -> None:
    await lay(bot, health=5.0)
    pick = say(bot)

    await give(bot, "alien_blue")

    pick.assert_called_once_with(
        Moment.GIFT_KEPT, Mood.HANGRY, name="Member1", gift="Blue Alien Doll"
    )


async def test_the_chosen_name_is_used(bot: app.WispBot) -> None:
    await lay(bot)
    await bot.players.set_name(GUILD_ID, USER_ID, "Zed")
    pick = say(bot)

    await give(bot, "alien_blue")

    assert pick.call_args.kwargs["name"] == "Zed"


async def test_giving_lets_wisp_meet_the_member(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    meeting = AsyncMock()
    monkeypatch.setattr(snacks, "maybe_meet", meeting)

    await give(bot, "alien_blue")

    meeting.assert_awaited_once_with(bot, GUILD_ID, USER_ID, display_name="Member1")


async def test_a_kept_gift_has_wisp_draw_the_giver_a_picture(
    bot: app.WispBot, drawing: AsyncMock
) -> None:
    await lay(bot)

    interaction = await give(bot, "alien_blue")

    drawing.assert_awaited_once()
    args = drawing.await_args.args
    assert args[:4] == (bot, GUILD_ID, interaction.user, DrawReason.GIFT)


async def test_a_gift_he_passes_on_draws_nothing(
    bot: app.WispBot, cog: Gifts, drawing: AsyncMock
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(PASS)

    await give(bot, "alien_blue")

    drawing.assert_not_awaited()


async def test_a_gift_from_a_member_who_cannot_feed_him_draws_nothing(
    bot: app.WispBot, drawing: AsyncMock
) -> None:
    await lay(bot)

    await give(bot, "alien_blue", roles=())

    drawing.assert_not_awaited()


# ---
# The Vault
# ---


async def test_the_vault_lists_gifts_under_the_snack_box(bot: app.WispBot) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_coin", "gift_alien_blue", "gift_alien_green")

    text, selects = await open_vault(bot)

    lines = text.splitlines()
    snacks_at = lines.index(FRAME.heading("Snacks", 0))
    badges_at = lines.index(FRAME.heading("Badges", 0))
    gifts_at = lines.index(GIFTS_HEADING)
    assert snacks_at < badges_at < gifts_at
    alien_emojis = (
        f"{emoji_text('gift_alien_blue', 2)} ・ {emoji_text('gift_alien_green', 3)}"
    )
    stock = {
        "Alien Dolls": f"{alien_emojis} ・ Purple ・ Yellow",
        "Books": "Blue ・ Green ・ Orange ・ Red",
        "Tamagotchis": "Hawaikotchi ・ Mimitchi ・ Tamagotchi Nano ・ Welcotchi",
        "Tech": "Tetris Handheld ・ Arcade ・ TV Shows",
    }
    assert lines[gifts_at + 1 :] == [
        GAMBLE,
        *(FRAME.item(f"{name}: {gifts}") for name, gifts in stock.items()),
        FRAME.footer,
    ]
    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    assert_is_a_menu(text, FRAME)
    snack_select, collections = selects
    assert snack_select.placeholder == "Buy a snack"
    assert collections.placeholder == PICK
    assert [
        (option.label, option.value, option.description)
        for option in collections.options
    ] == [
        (group.name, group.key, f"{len(group.gifts)} left")
        for group in GIFT_COLLECTIONS
    ]
    (aliens,) = [o for o in collections.options if o.value == "aliens"]
    assert str(aliens.emoji) == emoji_text("gift_alien_blue", 2)


async def gift_command(bot: app.WispBot, user_id: int = USER_ID) -> MagicMock:
    interaction = make_interaction(bot, user_id)
    command: Any = snacks.wisp_gift
    await command.callback(interaction)
    return interaction


async def test_wisp_gift_shows_only_the_gifts_privately(bot: app.WispBot) -> None:
    await lay(bot)

    interaction = await gift_command(bot)

    interaction.response.defer.assert_awaited_once_with(ephemeral=True, thinking=True)
    call = interaction.followup.send.await_args
    interaction.followup.send.assert_awaited_once()
    assert call.kwargs["ephemeral"] is True
    assert call.kwargs["wait"] is True
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    view = call.kwargs["view"]
    text = layout_text(view)
    assert text.splitlines()[:2] == [GIFTS_HEADING, GAMBLE]
    assert text.endswith(FRAME.footer)
    assert FRAME.heading("Snacks", 0) not in text
    assert FRAME.heading("Badges", 0) not in text
    assert [select.placeholder for select in layout_selects(view)] == [PICK]


async def test_a_gift_given_through_wisp_gift_goes_through(
    bot: app.WispBot, server: FakeServer
) -> None:
    await lay(bot)
    view = (await gift_command(bot)).followup.send.await_args.kwargs["view"]

    picked = await pick(bot, "aliens", select=collection_select(layout_selects(view)))
    _, selects = shown(picked)
    await give(bot, "alien_blue", select=gift_select(selects))

    assert await balance(bot) == 100 - rules.GIFT_COST
    life = await current_life(bot)
    assert life.id is not None
    given = await bot.gifts.today(GUILD_ID, life.id, discord.utils.utcnow())
    assert [attempt.gift for attempt in given] == ["alien_blue"]
    server.house.send.assert_awaited()


async def test_a_banned_member_is_turned_away_from_wisp_gift(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await gift_command(bot)

    interaction.followup.send.assert_awaited_once()
    call = interaction.followup.send.await_args
    assert call.args == ("♪ Wisp is not taking snacks or gifts from you right now.",)
    assert "view" not in call.kwargs


async def test_picking_a_collection_shows_its_gifts_with_the_price(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    await bot.gifts.record(
        GUILD_ID, life.id, USER_ID, "tetris_handheld", True, yesterday
    )
    give_emojis(bot, "gift_tech_arcade")

    interaction = await pick(bot, "tech")

    text, selects = shown(interaction)
    assert text.startswith(f"{GIFTS_HEADING}\n")
    assert FRAME.heading("Badges", 0) not in text
    assert [select.placeholder for select in selects] == [PICK, GIVE]
    items = gift_select(selects)
    assert [(option.label, option.value) for option in items.options] == [
        ("Arcade", "tech_arcade"),
        ("TV Shows", "tech_tv"),
    ]
    assert {option.description for option in items.options} == {"15 WC"}
    assert str(items.options[0].emoji) == emoji_text("gift_tech_arcade", 1)
    (tech,) = [o for o in collection_select(selects).options if o.value == "tech"]
    assert tech.description == "2 left"
    assert await balance(bot) == 100


async def test_no_vault_select_ever_has_more_than_25_options(
    bot: app.WispBot,
) -> None:
    await lay(bot)

    _, selects = await open_vault(bot)

    picker = collection_select(selects)
    assert len(picker.options) == len(GIFT_COLLECTIONS) <= 25
    for option in picker.options:
        items = await item_select(bot, option.value)
        assert len(items.options) <= 25
    assert all(len(select.options) <= 25 for select in selects)


async def test_a_collection_closed_after_opening_the_vault_is_refused(
    bot: app.WispBot, server: FakeServer, cog: Gifts
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(PASS)
    _, before = await open_vault(bot, OTHER_USER_ID)
    await give(bot, "tama_mimitchi")

    interaction = await pick(
        bot, "tamagotchis", OTHER_USER_ID, select=collection_select(before)
    )

    text, selects = shown(interaction)
    assert text.startswith(
        "♪ Someone already gave Wisp a Tamagotchi today. Back tomorrow.\n"
    )
    assert GIVE not in [select.placeholder for select in selects]
    assert "tamagotchis" not in [
        option.value for option in collection_select(selects).options
    ]
    assert await balance(bot, OTHER_USER_ID) == 100
    assert server.house.send.await_count == 1


async def test_a_collection_kept_in_full_is_refused(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    _, before = await open_vault(bot)
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for gift in collection("tamagotchis").gifts:
        await bot.gifts.record(GUILD_ID, life.id, USER_ID, gift.key, True, yesterday)

    interaction = await pick(bot, "tamagotchis", select=collection_select(before))

    text, selects = shown(interaction)
    assert text.startswith("♪ Wisp already kept every gift in Tamagotchis this life.\n")
    assert GIVE not in [select.placeholder for select in selects]


async def test_picking_a_collection_once_he_is_gone_says_gifts_wait(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    _, before = await open_vault(bot)
    await lay(bot, phase=Phase.DEAD, health=0.0, version=2)

    interaction = await pick(bot, "aliens", select=collection_select(before))

    text, selects = shown(interaction)
    assert text.startswith("♪ Wisp isn't alive right now, so gifts have to wait.")
    assert selects == []


async def test_the_vault_shows_stock_and_the_days_buys(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    yesterday = now - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "alien_blue", True, yesterday)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "book_red", False, now)

    text, _ = await open_vault(bot)

    assert FRAME.item("Alien Dolls: Green ・ Purple ・ Yellow") in text.splitlines()
    assert FRAME.item("Books: back tomorrow") in text
    options = await offered(bot)
    assert "alien_blue" not in options
    assert not any(option.startswith("book_") for option in options)
    assert "alien_green" in options


async def test_the_vault_warns_when_he_already_kept_a_gift_today(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "alien_blue", True, now)

    text, _ = await open_vault(bot)

    lines = text.splitlines()
    heading = lines.index(GIFTS_HEADING)
    kept_today = FRAME.note(
        "Wisp already picked his treasure today. "
        "Anything you give him goes back to the Vault."
    )
    warned = [GAMBLE, kept_today]
    assert lines[heading + 1 : heading + 1 + len(warned)] == warned
    assert "book_red" in await offered(bot)


async def test_no_warning_before_he_keeps_a_gift_today(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "alien_blue", False, now)
    yesterday = now - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "book_red", True, yesterday)

    text, _ = await open_vault(bot)

    assert "treasure" not in text


async def test_with_nothing_to_give_there_is_no_gift_select(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    for group in GIFT_COLLECTIONS:
        await bot.gifts.record(
            GUILD_ID, life.id, USER_ID, group.gifts[0].key, False, now
        )

    text, selects = await open_vault(bot)

    assert [select.placeholder for select in selects] == ["Buy a snack"]
    for group in GIFT_COLLECTIONS:
        assert FRAME.item(f"{group.name}: back tomorrow") in text


@pytest.mark.parametrize("phase", [None, Phase.EGG, Phase.DEAD])
async def test_before_he_hatches_the_vault_says_gifts_wait(
    bot: app.WispBot, phase: Phase | None
) -> None:
    if phase is not None:
        await lay(bot, phase=phase, health=0.0)

    text, selects = await open_vault(bot)

    assert gift_lines(text) == [
        GAMBLE,
        FRAME.item("He takes gifts once he has hatched"),
    ]
    assert [select.placeholder for select in selects] == ["Buy a snack"]


# ---
# Wisp's lunchbox
# ---


def favorite_gifts(text: str) -> str:
    """The lunchbox's FAVORITE GIFTS line, just above the footer."""
    return text.splitlines()[-2]


# ---
# The cog
# ---


def test_the_gifts_cog_has_an_injectable_rng(bot: app.WispBot) -> None:
    assert isinstance(Gifts(bot).rng, random.Random)


async def test_the_gifts_cog_is_loaded(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_cog: Any = AsyncMock()
    monkeypatch.setattr(bot, "add_cog", add_cog)

    await gifts.setup(bot)

    assert "cogs.gifts" in app.EXTENSIONS
    (added,) = add_cog.await_args.args
    assert isinstance(added, Gifts)


def test_the_bot_has_the_gift_repo() -> None:
    assert isinstance(app.WispBot().gifts, GiftRepo)


def test_a_gift_is_its_own_kind_of_interaction() -> None:
    assert InteractionKind.GIFT.value == "gift"


# ---
# Bigger collections and the worst case
# ---


async def test_the_last_tech_toy_completes_tech(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gifts").mkdir()
    (tmp_path / "gifts" / "tech_arcade.gif").write_bytes(b"GIF")
    monkeypatch.setattr(art, "ASSETS_DIR", tmp_path)
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for key in ("tetris_handheld", "tech_tv"):
        await bot.gifts.record(GUILD_ID, life.id, OTHER_USER_ID, key, True, yesterday)
    say(bot)

    interaction = await give(bot, "tech_arcade")

    bonus = rules.BOND_PER_KEPT_GIFT + rules.COLLECTION_BOND_BONUS
    assert await bond(bot) == bonus
    assert edited(interaction).startswith(
        f"{gave('an Arcade')}\n"
        f"♪ Wisp kept your Arcade ・ bond +{bonus} ・ Tech complete"
    )
    text, kwargs = house_post(server)
    head = posted(USER_ID, "an Arcade", bonus)
    assert text == f"{head}\n[gift_kept]\n[collection_done]"
    assert kwargs["file"].filename == "tech_arcade.gif"
    vault_text, _ = await open_vault(bot)
    assert FRAME.item("Tech: all kept this life") in vault_text
    lunchbox = await lunchbox_text(bot, GUILD_ID)
    assert favorite_gifts(lunchbox) == "### ・" + "・".join(
        GIFT_BY_KEY[key].name for key in ("tetris_handheld", "tech_tv", "tech_arcade")
    )


@pytest.mark.parametrize(
    ("stage", "show", "link"),
    [
        (Stage.BABY, "Llama Brain", "https://www.youtube.com/watch?v=U1jUICPWMYU"),
        (Stage.TEEN, "Llama Brain", "https://www.youtube.com/watch?v=U1jUICPWMYU"),
        (
            Stage.OLD_FOGEY,
            "Zephyrine Show",
            "https://www.youtube.com/watch?v=51X9Rdz2PWk",
        ),
    ],
)
async def test_a_kept_tv_shows_his_stages_tv_and_its_shows_first_episode(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: Stage,
    show: str,
    link: str,
) -> None:
    (tmp_path / "gifts").mkdir()
    (tmp_path / "gifts" / f"tech_tv_{stage.value}.png").write_bytes(b"PNG")
    monkeypatch.setattr(art, "ASSETS_DIR", tmp_path)
    await lay(bot, stage=stage)
    say(bot)

    await give(bot, "tech_tv")

    text, kwargs = house_post(server)
    assert text == (
        f"{posted(USER_ID, 'TV Shows', rules.BOND_PER_KEPT_GIFT)}\n[gift_kept]\n"
        f"♪ Now on Wisp's TV: {show}, episode 1\n{link}"
    )
    assert kwargs["file"].filename == f"tech_tv_{stage.value}.png"
    life = await current_life(bot)
    assert life.id is not None
    (kept,) = await bot.gifts.kept(GUILD_ID, life.id)
    assert kept.stage is stage


async def test_a_tv_he_passes_on_shows_no_tv_and_no_episode(
    bot: app.WispBot, cog: Gifts, server: FakeServer
) -> None:
    await lay(bot, stage=Stage.ROCKSTAR)
    cog.rng = FixedRandom(PASS)
    say(bot)

    await give(bot, "tech_tv")

    text, kwargs = house_post(server)
    assert text == (
        f"{posted(USER_ID, 'TV Shows')}\n[gift_passed]\n"
        "♪ It's back in the ViiBR Vault."
    )
    assert "youtube" not in text
    assert "file" not in kwargs


async def test_the_vault_and_lunchbox_show_the_tv_for_his_stage(
    bot: app.WispBot,
) -> None:
    life = await lay(bot, stage=Stage.ROCKSTAR)
    assert life.id is not None
    give_emojis(bot, "gift_tech_tv_baby", "gift_tech_tv_rockstar")

    text, _ = await open_vault(bot)

    rockstar_tv = emoji_text("gift_tech_tv_rockstar", 2)
    tech = FRAME.item(f"Tech: Tetris Handheld ・ Arcade ・ {rockstar_tv}")
    assert tech in text.splitlines()
    assert "gift_tech_tv_baby" not in text
    items = gift_select(shown(await pick(bot, "tech"))[1])
    assert str(items.options[2].emoji) == emoji_text("gift_tech_tv_rockstar", 2)
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "tech_tv", True, yesterday)
    lunchbox = await lunchbox_text(bot, GUILD_ID)
    assert favorite_gifts(lunchbox) == f"### ・{bot.emoji('gift_tech_tv_rockstar')}"
    assert "gift_tech_tv_baby" not in lunchbox


async def test_retired_tech_toys_kept_before_are_left_out(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for key in ("tetris_handheld", "tetris_i", "tetris_z", "tech_game_controller"):
        await bot.gifts.record(GUILD_ID, life.id, USER_ID, key, True, yesterday)

    lunchbox = await lunchbox_text(bot, GUILD_ID)
    vault_text, _ = await open_vault(bot)

    assert favorite_gifts(lunchbox) == "### ・" + GIFT_BY_KEY["tetris_handheld"].name
    assert "Game Controller" not in lunchbox
    assert FRAME.item("Tech: Arcade ・ TV Shows") in vault_text.splitlines()


async def test_retired_collections_kept_before_are_left_out(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for key in ("alien_blue", "card_keepcalm", "jewel_ruby", "liner_bird"):
        await bot.gifts.record(GUILD_ID, life.id, USER_ID, key, True, yesterday)

    lunchbox = await lunchbox_text(bot, GUILD_ID)
    vault_text, _ = await open_vault(bot)

    assert favorite_gifts(lunchbox) == "### ・" + GIFT_BY_KEY["alien_blue"].name
    for gone in ("Affirmation", "Keep Calm", "Jewel", "Ruby", "Liner"):
        assert gone not in lunchbox
        assert gone not in vault_text


def long_emojis(bot: app.WispBot, monkeypatch: pytest.MonkeyPatch) -> Frame:
    """Every emoji shows as 47 characters of text, but the style's own.

    The style's emojis have fixed names, so they show as their names with the
    longest id, animated; the frame they make is returned.
    """
    assert len(LONG_EMOJI) == 47

    def emoji(name: str) -> str:
        return f"<a:{name}:{'9' * 19}>" if name in STYLE_EMOJIS else LONG_EMOJI

    monkeypatch.setattr(bot, "emoji", emoji)
    return frame_of(emoji)


async def test_the_vault_fits_with_long_emojis_and_everything_in_stock(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.gifts.record(
        GUILD_ID, life.id, USER_ID, "book_red", True, discord.utils.utcnow()
    )
    frame = long_emojis(bot, monkeypatch)
    interaction = make_interaction(bot, USER_ID)
    command: Any = snacks.wisp_vault

    await command.callback(interaction)

    text, _ = vault_opened(interaction.followup.send)
    for part in vault_parts(interaction.followup.send):
        assert text_length(layout_text(part)) <= LAYOUT_TEXT_LIMIT
    assert_is_a_menu(text, frame, "ViiBR Vault")
    assert f"{frame.heading('Gifts', 4)} ・ {LONG_EMOJI} 15 WC each" in text
    picked = GIFT_BY_KEY["book_red"].collection
    for group in GIFT_COLLECTIONS:
        if group.key == picked:
            assert frame.item(f"{group.name}: back tomorrow") in text
        else:
            assert frame.item(f"{group.name}: {LONG_EMOJI}") in text
    gifts_part = layout_text(vault_parts(interaction.followup.send)[2])
    shown_gifts = sum(len(g.gifts) for g in GIFT_COLLECTIONS if g.key != picked)
    assert gifts_part.count(LONG_EMOJI) == shown_gifts + 1
    assert "Wisp already picked his" in text
    assert frame.item(f"Alien Dolls: {LONG_EMOJI} ・ {LONG_EMOJI}") in text


async def test_the_vault_fits_under_a_note_after_a_gift(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    frame = long_emojis(bot, monkeypatch)
    say(bot)

    interaction = await give(bot, "tama_welcotchi")

    text = edited(interaction)
    assert text.startswith(f"{gave('a Welcotchi')}\n" "♪ Wisp kept your Welcotchi")
    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    picked = GIFT_BY_KEY["tama_welcotchi"].collection
    for group in GIFT_COLLECTIONS:
        if group.key == picked:
            assert frame.item(f"{group.name}: back tomorrow") in text
        else:
            assert frame.item(f"{group.name}: {LONG_EMOJI}") in text
    assert text.splitlines()[-1] == frame.footer


@pytest.mark.parametrize(
    ("kept_in_full", "context"),
    [
        (False, "showing a gift collection"),
        (True, "showing a closed gift collection"),
    ],
)
async def test_a_collection_pick_that_cannot_be_shown_tells_the_member(
    bot: app.WispBot, kept_in_full: bool, context: str
) -> None:
    life = await lay(bot)
    assert life.id is not None
    _, selects = await open_vault(bot)
    if kept_in_full:
        yesterday = discord.utils.utcnow() - timedelta(days=1)
        for gift in collection("tamagotchis").gifts:
            await bot.gifts.record(
                GUILD_ID, life.id, USER_ID, gift.key, True, yesterday
            )
    select = collection_select(selects)
    select._values = ["tamagotchis"]
    interaction = make_interaction(bot)
    interaction.guild.id = GUILD_ID
    interaction.channel.send = AsyncMock()
    interaction.edit_original_response.side_effect = discord.HTTPException(
        MagicMock(status=500), "Server Error"
    )

    await select.callback(interaction)

    (report,) = interaction.channel.send.await_args.args
    assert report.startswith(f"Error in {context}: HTTPException")
    interaction.followup.send.assert_awaited_once_with(USER_ERROR, ephemeral=True)
