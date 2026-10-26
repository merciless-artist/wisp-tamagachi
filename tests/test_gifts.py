"""Tests for gifts: the catalog, the roll, the Vault select and the lunchbox.

Discord objects are fakes; the repositories are the real ones.
"""

import random
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import gifts, snacks
from cogs.assets import asset_image
from cogs.gifts import Gifts
from cogs.wisp_lunchbox import lunchbox_text
from db.activity import ActivityRepo, InteractionKind
from db.badges import BadgeRepo
from db.database import Database
from db.gifts import GiftAttempt, GiftRepo
from db.lives import LifeRepo
from db.lunchbox import WispLunchboxRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp import rules
from wisp.gifts import GiftState, Outcome, decide, with_article
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import Moment
from wisp.rules import GIFT_BY_KEY, GIFT_COLLECTIONS, Stage
from wisp.text import USER_ERROR, text_length

GUILD_ID = 100
FORUM_ID = 10
HOUSE_ID = 20
USER_ID = 1
OTHER_USER_ID = 2
NEWCOMER_ID = 3
QUALIFYING_ROLE = 7
SEPARATOR = "・♪ ────────・──────── ♪・"
NO_PING = discord.AllowedMentions.none().to_dict()
ASSETS = Path(__file__).resolve().parent.parent / "ASSETS"
KEEP = 0.0
PASS = 0.99
GIVE = "Give Wisp a gift"
PICK = "Pick a collection"
LONG_EMOJI = "<a:" + "e" * 23 + ":" + "1" * 19 + ">"

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
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.wisp_lunchbox = WispLunchboxRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


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
    bot: app.WispBot, phase: Phase = Phase.ALIVE, full: float = 50.0, version: int = 1
) -> Life:
    life = new_egg(version, discord.utils.utcnow() - timedelta(days=2))
    life.phase = phase
    life.full = full
    if phase is Phase.ALIVE:
        life.stage = life.peak_stage = Stage.BABY
        life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


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
    call = interaction.followup.send.await_args
    return call.args[0], list(call.kwargs["view"].children)


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
    return call.kwargs["content"], list(call.kwargs["view"].children)


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
    call = interaction.edit_original_response.await_args
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    return cast(str, call.kwargs["content"])


def house_post(server: FakeServer) -> tuple[str, dict[str, Any]]:
    server.house.send.assert_awaited_once()
    call = server.house.send.await_args
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
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


def test_there_are_seven_collections_in_order() -> None:
    assert [
        (group.name, [gift.key for gift in group.gifts]) for group in GIFT_COLLECTIONS
    ] == [
        (
            "Lunchbox Liners",
            ["liner_bird", "liner_butterfly", "liner_kitties", "liner_poppies"],
        ),
        ("Alien Dolls", ["alien_blue", "alien_green", "alien_purple", "alien_yellow"]),
        ("Books", ["book_blue", "book_green", "book_orange", "book_red"]),
        (
            "Affirmation Cards",
            [
                "card_futureisbright",
                "card_goodvibes",
                "card_keepcalm",
                "card_seeyou",
            ],
        ),
        (
            "Tamagotchis",
            ["tama_hawaikotchi", "tama_mimitchi", "tama_nano", "tama_welcotchi"],
        ),
        (
            "Tetris",
            [
                "tetris_handheld",
                "tetris_i",
                "tetris_l",
                "tetris_t",
                "tetris_s",
                "tetris_z",
            ],
        ),
        ("Jewels", ["jewel_amethyst", "jewel_crystal", "jewel_rainbow", "jewel_ruby"]),
    ]
    assert [len(group.gifts) for group in GIFT_COLLECTIONS] == [4, 4, 4, 4, 4, 6, 4]
    assert all(len(key) <= 30 for key in GIFT_BY_KEY)
    assert len(GIFT_BY_KEY) == 30


@pytest.mark.parametrize(
    ("key", "title"),
    [
        ("alien_blue", "Blue Alien Doll"),
        ("liner_bird", "Bird Lunchbox Liner"),
        ("book_red", "Red Book"),
        ("card_keepcalm", "Keep Calm Affirmation Card"),
        ("card_futureisbright", "Future Is Bright Affirmation Card"),
        ("tama_hawaikotchi", "Hawaikotchi"),
        ("tama_mimitchi", "Mimitchi"),
        ("tama_nano", "Tamagotchi Nano"),
        ("tama_welcotchi", "Welcotchi"),
        ("tetris_handheld", "Tetris Handheld"),
        ("tetris_i", "I Block"),
        ("tetris_l", "L Block"),
        ("tetris_t", "T Block"),
        ("tetris_s", "S Block"),
        ("tetris_z", "Z Block"),
        ("jewel_amethyst", "Amethyst"),
        ("jewel_crystal", "Crystal"),
        ("jewel_rainbow", "Rainbow Jewel"),
        ("jewel_ruby", "Ruby"),
    ],
)
def test_a_gift_reads_with_its_collection(key: str, title: str) -> None:
    assert GIFT_BY_KEY[key].title == title


def test_every_gift_has_its_emoji_name_and_art() -> None:
    for group in GIFT_COLLECTIONS:
        for gift in group.gifts:
            assert gift.collection == group.key
            assert gift.emoji_name == f"gift_{gift.key}"
            assert asset_image(ASSETS / "gifts", gift.key) is not None, gift.key


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
    assert rules.GIFT_LIKE_CHANCE == pytest.approx(1 / 3)
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
        ("Tetris Toy", "a Tetris Toy"),
    ],
)
def test_a_gift_gets_the_right_article(title: str, expected: str) -> None:
    assert with_article(title) == expected


# ---
# The roll and the stock
# ---


def test_the_roll_keeps_under_the_like_chance() -> None:
    state = GiftState(frozenset(), frozenset(), kept_today=False)

    assert decide(state, FixedRandom(rules.GIFT_LIKE_CHANCE - 0.01)) is Outcome.KEPT
    assert decide(state, FixedRandom(rules.GIFT_LIKE_CHANCE)) is Outcome.PASSED


def test_after_a_kept_gift_he_is_full_without_rolling() -> None:
    rng = FixedRandom(KEEP)

    outcome = decide(GiftState(frozenset(), frozenset(), kept_today=True), rng)

    assert outcome is Outcome.FULL
    assert rng.rolls == 0


def test_the_state_knows_stock_open_collections_and_completion() -> None:
    aliens = collection("aliens")
    kept = frozenset(gift.key for gift in aliens.gifts[:3])
    state = GiftState(kept, frozenset({"books"}), kept_today=False)

    assert not state.in_stock(aliens.gifts[0])
    assert state.can_give(aliens.gifts[3])
    assert state.completes(aliens.gifts[3])
    assert not state.can_give(collection("books").gifts[0])
    assert state.offered_from(aliens) == [aliens.gifts[3]]
    assert state.offered_from(collection("books")) == []
    assert state.offered_from(collection("tetris")) == list(collection("tetris").gifts)


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
    await repo.record(GUILD_ID, 2, USER_ID, "liner_bird", True, now)

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
    monkeypatch.setattr(gifts, "ASSETS_DIR", tmp_path)
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
    assert text == "♪ Member1 gave Wisp a Blue Alien Doll\n[gift_kept]"
    assert "file" not in kwargs
    pick.assert_called_once_with(
        Moment.GIFT_KEPT, Mood.HAPPY, name="Member1", gift="Blue Alien Doll"
    )
    reply = edited(interaction)
    assert reply.startswith("♪ Wisp kept your Blue Alien Doll")
    assert f"{100 - rules.GIFT_COST} points" in reply
    assert "alien_blue" not in await offered(bot)


async def test_a_kept_gift_brings_its_art_when_it_exists(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gifts").mkdir()
    (tmp_path / "gifts" / "book_orange.png").write_bytes(b"PNG")
    monkeypatch.setattr(gifts, "ASSETS_DIR", tmp_path)
    await lay(bot)
    say(bot)

    await give(bot, "book_orange")

    text, kwargs = house_post(server)
    assert text.startswith("♪ Member1 gave Wisp an Orange Book\n")
    attached = kwargs["file"]
    assert isinstance(attached, discord.File)
    assert attached.filename == "book_orange.png"


async def test_a_passed_gift_stays_in_stock_and_still_costs(
    bot: app.WispBot, server: FakeServer, cog: Gifts
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(PASS)
    say(bot)

    interaction = await give(bot, "card_keepcalm")

    assert await balance(bot) == 100 - rules.GIFT_COST
    assert await bond(bot) == 0
    assert (await current_life(bot)).growth == 0
    assert await kept_keys(bot) == []
    text, kwargs = house_post(server)
    assert text == (
        "♪ Member1 gave Wisp a Keep Calm Affirmation Card\n[gift_passed]\n"
        "♪ It's back in the ViiBR Vault."
    )
    assert "file" not in kwargs
    assert edited(interaction).startswith(
        "♪ Wisp passed on your Keep Calm Affirmation Card"
    )
    now = discord.utils.utcnow()
    assert await bot.activity_log.people_since(GUILD_ID, now - timedelta(hours=1))


async def test_a_collection_is_given_from_once_a_day(
    bot: app.WispBot, server: FakeServer, cog: Gifts
) -> None:
    await lay(bot)
    cog.rng = FixedRandom(PASS)
    before = await item_select(bot, "aliens", OTHER_USER_ID)
    await give(bot, "alien_blue")

    text, _ = await open_vault(bot, OTHER_USER_ID)
    assert not any(key.startswith("alien_") for key in await offered(bot))
    assert "𝄃 Alien Dolls: back tomorrow" in text

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
    text = server.house.send.await_args.args[0]
    assert text == (
        "♪ Member2 gave Wisp a Red Book\n[gift_full]\n♪ It's back in the ViiBR Vault."
    )
    assert "already kept a gift today" in edited(interaction)
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
    assert text == ("♪ Member1 gave Wisp a Red Book\n[gift_kept]\n[collection_done]")
    pick.assert_any_call(
        Moment.COLLECTION_DONE, Mood.HAPPY, name="Member1", collection="Books"
    )
    assert "Books" in edited(interaction)
    vault_text, _ = await open_vault(bot)
    assert "𝄃 Books: all kept this life" in vault_text


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
    assert "[not_enough_points]" in edited(interaction)
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

    assert "Active Lounger" in edited(interaction)
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize("phase", [Phase.EGG, Phase.HATCHING, Phase.DEAD])
async def test_wisp_must_be_alive_for_gifts(
    bot: app.WispBot, server: FakeServer, phase: Phase
) -> None:
    await lay(bot)
    select = await item_select(bot, "aliens")
    await lay(bot, phase=phase, full=0.0, version=2)

    interaction = await give(bot, "alien_blue", select=select)

    assert "isn't hatched" in edited(interaction)
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


async def test_a_hangry_wisp_reacts_hangry(bot: app.WispBot) -> None:
    await lay(bot, full=5.0)
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


# ---
# The Vault
# ---


async def test_the_vault_lists_gifts_under_the_snack_box(bot: app.WispBot) -> None:
    await lay(bot)
    give_emojis(bot, "wisp_coin", "gift_alien_blue", "gift_alien_green")

    text, selects = await open_vault(bot)

    lines = text.splitlines()
    snacks_at = lines.index("𝄃 **Snacks**")
    badges_at = lines.index("𝄃 **Badges**")
    gifts_at = lines.index("𝄃 **Gifts**・15 points each・he might not like it")
    assert snacks_at < badges_at < gifts_at
    assert lines[gifts_at + 1 :] == [
        "𝄃 Lunchbox Liners: Bird Butterfly Kitties Poppies",
        f"𝄃 Alien Dolls: {emoji_text('gift_alien_blue', 2)} "
        f"{emoji_text('gift_alien_green', 3)} Purple Yellow",
        "𝄃 Books: Blue Green Orange Red",
        "𝄃 Affirmation Cards: Future Is Bright Good Vibes Keep Calm See You",
        "𝄃 Tamagotchis: Hawaikotchi Mimitchi Tamagotchi Nano Welcotchi",
        "𝄃 Tetris: Tetris Handheld I Block L Block T Block S Block Z Block",
        "𝄃 Jewels: Amethyst Crystal Rainbow Jewel Ruby",
        "╚══════════════════╝",
        "𝄃𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂",
    ]
    assert text_length(text) < 2000
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
    aliens = collections.options[1]
    assert str(aliens.emoji) == emoji_text("gift_alien_blue", 2)


async def test_picking_a_collection_shows_its_gifts_with_the_price(
    bot: app.WispBot,
) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "tetris_i", True, yesterday)
    give_emojis(bot, "gift_tetris_l")

    interaction = await pick(bot, "tetris")

    text, selects = shown(interaction)
    assert text.startswith("♪ You have")
    assert [select.placeholder for select in selects] == ["Buy a snack", PICK, GIVE]
    items = gift_select(selects)
    assert [(option.label, option.value) for option in items.options] == [
        ("Tetris Handheld", "tetris_handheld"),
        ("L Block", "tetris_l"),
        ("T Block", "tetris_t"),
        ("S Block", "tetris_s"),
        ("Z Block", "tetris_z"),
    ]
    assert {option.description for option in items.options} == {"15 points"}
    assert str(items.options[1].emoji) == emoji_text("gift_tetris_l", 1)
    tetris = collection_select(selects).options[5]
    assert tetris.description == "5 left"
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
    await give(bot, "jewel_ruby")

    interaction = await pick(
        bot, "jewels", OTHER_USER_ID, select=collection_select(before)
    )

    text, selects = shown(interaction)
    assert text.startswith(
        "♪ Someone already gave Wisp a Jewel today. Back tomorrow.\n"
    )
    assert GIVE not in [select.placeholder for select in selects]
    assert "jewels" not in [
        option.value for option in collection_select(selects).options
    ]
    assert await balance(bot, OTHER_USER_ID) == 100
    assert server.house.send.await_count == 1


async def test_a_collection_kept_in_full_is_refused(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    _, before = await open_vault(bot)
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for gift in collection("jewels").gifts:
        await bot.gifts.record(GUILD_ID, life.id, USER_ID, gift.key, True, yesterday)

    interaction = await pick(bot, "jewels", select=collection_select(before))

    text, selects = shown(interaction)
    assert text.startswith("♪ Wisp already kept every gift in Jewels this life.\n")
    assert GIVE not in [select.placeholder for select in selects]


async def test_picking_a_collection_once_he_is_gone_says_gifts_wait(
    bot: app.WispBot,
) -> None:
    await lay(bot)
    _, before = await open_vault(bot)
    await lay(bot, phase=Phase.DEAD, full=0.0, version=2)

    interaction = await pick(bot, "aliens", select=collection_select(before))

    text, selects = shown(interaction)
    assert text.startswith("♪ Wisp isn't hatched yet.")
    assert [select.placeholder for select in selects] == ["Buy a snack"]


async def test_the_vault_shows_stock_and_the_days_buys(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    yesterday = now - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "alien_blue", True, yesterday)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "book_red", False, now)

    text, _ = await open_vault(bot)

    assert "𝄃 Alien Dolls: Green Purple Yellow" in text
    assert "𝄃 Books: back tomorrow" in text
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
    heading = next(i for i, line in enumerate(lines) if line.startswith("𝄃 **Gifts**"))
    assert lines[heading + 1] == (
        "𝄃 Wisp already picked his treasure today. "
        "Anything you give him goes back to the Vault."
    )
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
    assert text.count("back tomorrow") == len(GIFT_COLLECTIONS)


@pytest.mark.parametrize("phase", [None, Phase.EGG, Phase.DEAD])
async def test_before_he_hatches_the_vault_says_gifts_wait(
    bot: app.WispBot, phase: Phase | None
) -> None:
    if phase is not None:
        await lay(bot, phase=phase, full=0.0)

    text, selects = await open_vault(bot)

    assert "𝄃 He takes gifts once he has hatched" in text
    assert [select.placeholder for select in selects] == ["Buy a snack"]


# ---
# Wisp's lunchbox
# ---


async def test_the_lunchbox_shows_this_lifes_collections(bot: app.WispBot) -> None:
    old = await lay(bot)
    assert old.id is not None
    long_ago = discord.utils.utcnow() - timedelta(days=9)
    await bot.gifts.record(GUILD_ID, old.id, USER_ID, "card_seeyou", True, long_ago)
    life = await lay(bot, version=2)
    assert life.id is not None
    give_emojis(bot, "gift_alien_blue")
    for days, (key, user_id) in enumerate(
        [
            ("alien_blue", USER_ID),
            ("book_blue", OTHER_USER_ID),
            ("alien_green", OTHER_USER_ID),
            ("book_green", USER_ID),
            ("book_orange", USER_ID),
            ("book_red", OTHER_USER_ID),
        ]
    ):
        at = discord.utils.utcnow() - timedelta(days=8 - days)
        await bot.gifts.record(GUILD_ID, life.id, user_id, key, True, at)
    await bot.gifts.record(
        GUILD_ID, life.id, USER_ID, "liner_bird", False, discord.utils.utcnow()
    )

    text = await lunchbox_text(bot, GUILD_ID)

    section = text.split(SEPARATOR + "\n")[-1]
    assert section.splitlines() == [
        "Collections",
        f"・Alien Dolls 2/4 ・ {emoji_text('gift_alien_blue', 1)} Blue "
        f"(from <@{USER_ID}>) ・ Green (from <@{OTHER_USER_ID}>)",
        f"・Books 4/4 complete ・ finished by <@{OTHER_USER_ID}>",
    ]


async def test_an_empty_collection_section_says_nothing_yet(
    bot: app.WispBot,
) -> None:
    await lay(bot)

    text = await lunchbox_text(bot, GUILD_ID)

    assert text.endswith("Collections\n・Nothing yet")


async def test_the_lunchbox_still_fits_with_long_songs_and_collections(
    bot: app.WispBot, db: Database
) -> None:
    life = await lay(bot)
    assert life.id is not None
    at = discord.utils.utcnow() - timedelta(days=1)
    for group in GIFT_COLLECTIONS:
        for gift in group.gifts[:3]:
            await bot.gifts.record(GUILD_ID, life.id, 10**17, gift.key, True, at)
    day = at.date()
    for offset in range(rules.FAVORITE_SONGS_SHOWN):
        await db.execute(
            f"INSERT INTO {db.t('favorites')} "
            "(guild_id, day, user_id, track_key, url, picked_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                GUILD_ID,
                day - timedelta(days=offset),
                10**17,
                f"viibr:{offset}",
                "https://viibrmusic.com/songs/" + "x" * 200,
                datetime(2026, 10, 1),
            ),
        )

    text = await lunchbox_text(bot, GUILD_ID)

    assert len(text) <= 2000
    assert text.splitlines()[-1].startswith("・Jewels 3/4")


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


async def test_the_sixth_tetris_piece_completes_its_collection(
    bot: app.WispBot,
    server: FakeServer,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "gifts").mkdir()
    (tmp_path / "gifts" / "tetris_z.gif").write_bytes(b"GIF")
    monkeypatch.setattr(gifts, "ASSETS_DIR", tmp_path)
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for gift in collection("tetris").gifts[:5]:
        await bot.gifts.record(
            GUILD_ID, life.id, OTHER_USER_ID, gift.key, True, yesterday
        )
    say(bot)

    interaction = await give(bot, "tetris_z")

    bonus = rules.BOND_PER_KEPT_GIFT + rules.COLLECTION_BOND_BONUS
    assert await bond(bot) == bonus
    assert edited(interaction).startswith(
        f"♪ Wisp kept your Z Block ・ bond +{bonus} ・ Tetris complete"
    )
    text, kwargs = house_post(server)
    assert text == "♪ Member1 gave Wisp a Z Block\n[gift_kept]\n[collection_done]"
    assert kwargs["file"].filename == "tetris_z.gif"
    vault_text, _ = await open_vault(bot)
    assert "𝄃 Tetris: all kept this life" in vault_text
    lunchbox = await lunchbox_text(bot, GUILD_ID)
    assert f"・Tetris 6/6 complete ・ finished by <@{USER_ID}>" in lunchbox


async def test_five_of_six_tetris_pieces_is_not_complete(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    yesterday = discord.utils.utcnow() - timedelta(days=1)
    for gift in collection("tetris").gifts[:5]:
        await bot.gifts.record(GUILD_ID, life.id, USER_ID, gift.key, True, yesterday)

    lunchbox = await lunchbox_text(bot, GUILD_ID)

    (line,) = [line for line in lunchbox.splitlines() if "Tetris" in line]
    assert line.startswith("・Tetris 5/6 ・ ")
    assert "complete" not in line


def long_emojis(bot: app.WispBot, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every emoji shows as 47 characters of text."""
    assert len(LONG_EMOJI) == 47
    monkeypatch.setattr(bot, "emoji", lambda _name: LONG_EMOJI)


async def test_the_vault_fits_with_long_emojis_and_everything_in_stock(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = await lay(bot)
    assert life.id is not None
    await bot.gifts.record(
        GUILD_ID, life.id, USER_ID, "book_red", True, discord.utils.utcnow()
    )
    long_emojis(bot, monkeypatch)

    text, _ = await open_vault(bot)

    assert text_length(text) <= 2000
    assert "𝄃 **Gifts**・" in text
    for group in GIFT_COLLECTIONS:
        assert f"𝄃 {group.name}: " in text
    assert "treasure today" in text
    liners = next(line for line in text.splitlines() if line.startswith("𝄃 Lunchbox"))
    assert LONG_EMOJI in liners


async def test_the_vault_fits_under_a_note_after_a_gift(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    await lay(bot)
    long_emojis(bot, monkeypatch)
    say(bot)

    interaction = await give(bot, "card_futureisbright")

    text = edited(interaction)
    assert text.startswith("♪ Wisp kept your Future Is Bright Affirmation Card")
    assert text_length(text) <= 2000
    for group in GIFT_COLLECTIONS:
        assert f"𝄃 {group.name}: " in text


async def test_the_lunchbox_fits_with_every_collection_nearly_full(
    bot: app.WispBot, db: Database, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = await lay(bot)
    assert life.id is not None
    at = discord.utils.utcnow() - timedelta(days=1)
    for group in GIFT_COLLECTIONS:
        for gift in group.gifts[:-1]:
            await bot.gifts.record(GUILD_ID, life.id, 10**18, gift.key, True, at)
    for offset in range(rules.FAVORITE_SONGS_SHOWN):
        await db.execute(
            f"INSERT INTO {db.t('favorites')} "
            "(guild_id, day, user_id, track_key, url, picked_at) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (
                GUILD_ID,
                at.date() - timedelta(days=offset),
                10**18,
                f"viibr:{offset}",
                "https://viibrmusic.com/songs/" + "x" * 36,
                datetime(2026, 10, 1),
            ),
        )
    long_emojis(bot, monkeypatch)

    text = await lunchbox_text(bot, GUILD_ID)

    assert len(text) <= 2000
    section = text.split(SEPARATOR + "\n")[-1].splitlines()
    assert [line.split(" ・ ")[0] for line in section[1:]] == [
        f"・{group.name} {len(group.gifts) - 1}/{len(group.gifts)}"
        for group in GIFT_COLLECTIONS
    ]


async def test_the_lunchbox_fits_with_every_collection_complete(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    life = await lay(bot)
    assert life.id is not None
    at = discord.utils.utcnow() - timedelta(days=1)
    for group in GIFT_COLLECTIONS:
        for gift in group.gifts:
            await bot.gifts.record(GUILD_ID, life.id, 10**18, gift.key, True, at)
    long_emojis(bot, monkeypatch)

    text = await lunchbox_text(bot, GUILD_ID)

    assert len(text) <= 2000
    section = text.split(SEPARATOR + "\n")[-1].splitlines()
    assert section[1:] == [
        f"・{group.name} {len(group.gifts)}/{len(group.gifts)} complete "
        f"・ finished by <@{10**18}>"
        for group in GIFT_COLLECTIONS
    ]


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
        for gift in collection("jewels").gifts:
            await bot.gifts.record(
                GUILD_ID, life.id, USER_ID, gift.key, True, yesterday
            )
    select = collection_select(selects)
    select._values = ["jewels"]
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
