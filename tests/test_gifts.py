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
from cogs.gifts import Gifts
from cogs.wisp_lunchbox import lunchbox_text
from db.activity import ActivityRepo, InteractionKind
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
    bot: app.WispBot, phase: Phase = Phase.ALIVE, care: float = 50.0, version: int = 1
) -> Life:
    life = new_egg(version, discord.utils.utcnow() - timedelta(days=2))
    life.phase = phase
    life.care = care
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


def gift_select(selects: list[discord.ui.Select[Any]]) -> discord.ui.Select[Any]:
    (select,) = [select for select in selects if select.placeholder == GIVE]
    return select


async def give(
    bot: app.WispBot,
    key: str,
    user_id: int = USER_ID,
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
    select: discord.ui.Select[Any] | None = None,
) -> MagicMock:
    """Give a gift through the Vault's gift select, opened now unless one is given."""
    if select is None:
        _, selects = await open_vault(bot, user_id)
        select = gift_select(selects)
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


def test_there_are_four_collections_of_four() -> None:
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
    ]


@pytest.mark.parametrize(
    ("key", "title"),
    [
        ("alien_blue", "Blue Alien Doll"),
        ("liner_bird", "Bird Lunchbox Liner"),
        ("book_red", "Red Book"),
        ("card_keepcalm", "Keep Calm Affirmation Card"),
        ("card_futureisbright", "Future Is Bright Affirmation Card"),
    ],
)
def test_a_gift_reads_with_its_collection(key: str, title: str) -> None:
    assert GIFT_BY_KEY[key].title == title


def test_every_gift_has_its_emoji_name_and_art() -> None:
    for group in GIFT_COLLECTIONS:
        for gift in group.gifts:
            assert gift.collection == group.key
            assert gift.emoji_name == f"gift_{gift.key}"
            assert (ASSETS / "gifts" / f"{gift.key}.png").is_file(), gift.key


def test_gift_numbers_are_the_starting_values() -> None:
    assert rules.GIFT_COST == 15
    assert rules.GIFT_LIKE_CHANCE == pytest.approx(1 / 3)
    assert rules.BOND_PER_KEPT_GIFT == 5
    assert rules.COLLECTION_BOND_BONUS == 25


@pytest.mark.parametrize(
    ("title", "expected"),
    [("Orange Book", "an Orange Book"), ("Blue Alien Doll", "a Blue Alien Doll")],
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
    assert state.offered() == [
        *collection("liners").gifts,
        aliens.gifts[3],
        *collection("cards").gifts,
    ]


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
    _, selects = await open_vault(bot)
    options = [option.value for option in gift_select(selects).options]
    assert "alien_blue" not in options


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
    _, before = await open_vault(bot, OTHER_USER_ID)
    await give(bot, "alien_blue")

    text, selects = await open_vault(bot, OTHER_USER_ID)
    options = [option.value for option in gift_select(selects).options]
    assert not any(option.startswith("alien_") for option in options)
    assert "・Alien Dolls: back tomorrow" in text

    stale = await give(bot, "alien_green", OTHER_USER_ID, select=gift_select(before))

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
    assert "・Books: all kept this life" in vault_text


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

    text, selects = await open_vault(bot)

    options = [option.value for option in gift_select(selects).options]
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
    _, selects = await open_vault(bot)
    await bot.players.set_offense(GUILD_ID, USER_ID, 3, None, True)

    interaction = await give(bot, "alien_blue", select=gift_select(selects))

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
    _, selects = await open_vault(bot)
    await lay(bot, phase=phase, care=0.0, version=2)

    interaction = await give(bot, "alien_blue", select=gift_select(selects))

    assert "isn't hatched" in edited(interaction)
    assert await balance(bot) == 100
    server.house.send.assert_not_awaited()


async def test_a_hangry_wisp_reacts_hangry(bot: app.WispBot) -> None:
    await lay(bot, care=5.0)
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

    sections = text.split(SEPARATOR + "\n")
    snack_box, gift_lines = sections[1].split("\n\n")
    assert snack_box.startswith("Snack Box")
    assert gift_lines.splitlines() == [
        f"Gifts ・ {emoji_text('wisp_coin', 1)} 15 points each ・ he might not like it",
        "・Lunchbox Liners: Bird Butterfly Kitties Poppies",
        f"・Alien Dolls: {emoji_text('gift_alien_blue', 2)} "
        f"{emoji_text('gift_alien_green', 3)} Purple Yellow",
        "・Books: Blue Green Orange Red",
        "・Affirmation Cards: Future Is Bright Good Vibes Keep Calm See You",
    ]
    assert len(text) < 2000
    snack_select, gift_choices = selects
    assert snack_select.placeholder == "Buy a snack"
    assert gift_choices.placeholder == GIVE
    assert [option.value for option in gift_choices.options] == [
        gift.key for group in GIFT_COLLECTIONS for gift in group.gifts
    ]
    blue = gift_choices.options[4]
    assert blue.label == "Blue Alien Doll"
    assert str(blue.emoji) == emoji_text("gift_alien_blue", 2)


async def test_the_vault_shows_stock_and_the_days_buys(bot: app.WispBot) -> None:
    life = await lay(bot)
    assert life.id is not None
    now = discord.utils.utcnow()
    yesterday = now - timedelta(days=1)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "alien_blue", True, yesterday)
    await bot.gifts.record(GUILD_ID, life.id, USER_ID, "book_red", False, now)

    text, selects = await open_vault(bot)

    assert "・Alien Dolls: Green Purple Yellow" in text
    assert "・Books: back tomorrow" in text
    options = [option.value for option in gift_select(selects).options]
    assert "alien_blue" not in options
    assert not any(option.startswith("book_") for option in options)
    assert "alien_green" in options


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
        await lay(bot, phase=phase, care=0.0)

    text, selects = await open_vault(bot)

    assert "・He takes gifts once he has hatched" in text
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
    assert text.splitlines()[-1].startswith("・Affirmation Cards 3/4")


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
