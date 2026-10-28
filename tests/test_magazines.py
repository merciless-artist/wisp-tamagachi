"""Tests for the Rockstar magazines: the Vault's covers, buying them, the Snack Pack.

Discord objects are fakes; the repositories are the real ones.
"""

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import magazines, snacks
from cogs.magazines import cover_art
from db.activity import ActivityRepo
from db.badges import BadgeRepo
from db.database import Database
from db.gifts import GiftRepo
from db.keepsakes import KeepsakeKind, KeepsakeRepo
from db.lives import LifeRepo
from db.magazines import MagazineRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from tests.layout import (
    assert_fits_its_box,
    entries,
    layout_order,
    layout_selects,
    layout_text,
)
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import BADGES, GIFT_BY_KEY, MAGAZINES, SNACKS, Stage
from wisp.text import (
    BLANK,
    LAYOUT_TEXT_LIMIT,
    MESSAGE_LIMIT,
    SECTION_BREAK,
    text_length,
)

GUILD_ID = 100
HOUSE_ID = 20
USER_ID = 1
QUALIFYING_ROLE = 7
NO_PING = discord.AllowedMentions.none().to_dict()
GONE = "♪ The magazines are gone from the shelf."
POSTING_LIMIT = 1024 * 1024

# ---
# Fakes
# ---


@pytest.fixture
def guild() -> MagicMock:
    fake = MagicMock(spec=discord.Guild)
    fake.id = GUILD_ID
    fake.get_role.return_value = None
    return fake


@pytest.fixture
def bot(
    db: Database, guild: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.players = PlayerRepo(db)
    wisp_bot.activity_log = ActivityRepo(db)
    wisp_bot.keepsakes = KeepsakeRepo(db)
    wisp_bot.gifts = GiftRepo(db)
    wisp_bot.badges = BadgeRepo(db)
    wisp_bot.magazines = MagazineRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: guild)
    monkeypatch.setattr(wisp_bot, "report_error", AsyncMock())
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    await bot.players.activate(GUILD_ID, USER_ID, discord.utils.utcnow())


def member(roles: tuple[int, ...] = (QUALIFYING_ROLE,)) -> MagicMock:
    fake = MagicMock(spec=discord.Member)
    fake.id = USER_ID
    fake.display_name = "Member1"
    fake.roles = [MagicMock(spec=discord.Role, id=role_id) for role_id in roles]
    return fake


def make_interaction(
    bot: app.WispBot, guild: MagicMock, user: MagicMock | None = None
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = guild
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.Thread)
    interaction.user = user or member()
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


async def lay(
    bot: app.WispBot,
    stage: Stage = Stage.ROCKSTAR,
    version: int = 1,
    phase: Phase = Phase.ALIVE,
) -> Life:
    life = new_egg(version, discord.utils.utcnow() - timedelta(days=50))
    life.phase = phase
    life.full = 60.0
    if phase is not Phase.EGG:
        life.stage = life.peak_stage = stage
        life.hatched_at = life.stage_started_at = discord.utils.utcnow()
    return await bot.lives.insert(GUILD_ID, life)


async def open_vault(
    bot: app.WispBot, guild: MagicMock
) -> tuple[discord.ui.LayoutView, str, list[discord.ui.Select[Any]]]:
    interaction = make_interaction(bot, guild)
    command: Any = snacks.wisp_vault
    await command.callback(interaction)
    view = interaction.followup.send.await_args.kwargs["view"]
    return view, layout_text(view), layout_selects(view)


def magazine_select(
    selects: list[discord.ui.Select[Any]],
) -> discord.ui.Select[Any] | None:
    found = [select for select in selects if select.placeholder == "Get a magazine"]
    return found[0] if found else None


async def pick(
    select: discord.ui.Select[Any],
    bot: app.WispBot,
    guild: MagicMock,
    key: str,
    user: MagicMock | None = None,
) -> MagicMock:
    select._values = [key]
    interaction = make_interaction(bot, guild, user)
    await select.callback(interaction)
    return interaction


async def buy(bot: app.WispBot, guild: MagicMock, key: str) -> MagicMock:
    """Open the Vault and get a magazine from its select."""
    _, _, selects = await open_vault(bot, guild)
    select = magazine_select(selects)
    assert select is not None
    return await pick(select, bot, guild, key)


def shown(interaction: MagicMock) -> str:
    """The Vault's text as the interaction last showed it."""
    call = interaction.edit_original_response.await_args
    assert call.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert "content" not in call.kwargs
    return layout_text(call.kwargs["view"])


def section(text: str, heading: str) -> list[str]:
    """The entries under a `#` heading, up to the next break, each wrapped
    entry's rows joined."""
    lines = text.splitlines()
    start = lines.index(f"║𝄡𝄚𝄂𝄆 **{heading}**") + 1
    end = next(
        index
        for index in range(start, len(lines))
        if lines[index] in (SECTION_BREAK, BLANK) or lines[index].startswith("╚")
    )
    return entries(lines[start:end])


def sent_files(interaction: MagicMock) -> list[discord.File]:
    return [
        call.kwargs["file"]
        for call in interaction.followup.send.await_args_list
        if "file" in call.kwargs
    ]


def give_emojis(bot: app.WispBot, *names: str) -> None:
    bot.emojis_by_name = {
        name: cast(discord.Emoji, discord.PartialEmoji(name=name, id=index))
        for index, name in enumerate(names, start=1)
    }


async def rich(bot: app.WispBot, points: int = 1000) -> None:
    await bot.players.add_points(GUILD_ID, USER_ID, points)


async def balance(bot: app.WispBot) -> int:
    return (await bot.players.get(GUILD_ID, USER_ID)).balance


# ---
# The Vault
# ---


@pytest.mark.parametrize(
    ("stage", "phase"),
    [
        (Stage.EGG, Phase.EGG),
        (Stage.TEEN, Phase.ALIVE),
        (Stage.ADULT, Phase.ALIVE),
        (Stage.OLD_FOGEY, Phase.ALIVE),
        (Stage.ROCKSTAR, Phase.DEAD),
    ],
)
async def test_the_vault_has_no_magazines_unless_wisp_lives_as_a_rockstar(
    bot: app.WispBot, guild: MagicMock, stage: Stage, phase: Phase
) -> None:
    await lay(bot, stage, phase=phase)

    _, text, selects = await open_vault(bot, guild)

    assert "**Magazines**" not in text
    assert magazine_select(selects) is None


async def test_a_vault_with_no_wisp_has_no_magazines(
    bot: app.WispBot, guild: MagicMock
) -> None:
    _, text, selects = await open_vault(bot, guild)

    assert "**Magazines**" not in text
    assert magazine_select(selects) is None


async def test_a_rockstar_vault_sells_both_covers_with_a_select_under_them(
    bot: app.WispBot, guild: MagicMock
) -> None:
    give_emojis(bot, "wisp_coin_mini")
    await lay(bot)

    view, text, selects = await open_vault(bot, guild)

    assert section(text, "Magazines") == [
        "║𝄡 VIIBRATIONS cover・<:wisp_coin_mini:1> 100 WC",
        "║𝄡 Music & Science cover\n║ ・<:wisp_coin_mini:1> 100 WC",
    ]
    lines = text.splitlines()
    assert lines.index("║𝄡𝄚𝄂𝄆 **Badges**") < lines.index("║𝄡𝄚𝄂𝄆 **Magazines**")
    assert lines.index("║𝄡𝄚𝄂𝄆 **Magazines**") < lines.index(
        next(line for line in lines if line.startswith("║𝄡𝄚𝄂𝄆 **Gifts**"))
    )
    assert layout_order(view) == [
        "text",
        "Buy a snack",
        "text",
        "text",
        "Get a magazine",
        "text",
        "Pick a collection",
        "text",
    ]
    select = magazine_select(selects)
    assert select is not None
    assert [
        (option.label, option.value, option.description) for option in select.options
    ] == [
        ("VIIBRATIONS cover", "viibrations", "100 WC"),
        ("Music & Science cover", "musicnscience", "100 WC"),
    ]


async def test_the_fullest_rockstar_vault_stays_within_the_layout_text_limit(
    bot: app.WispBot, guild: MagicMock
) -> None:
    await lay(bot)
    for index, badge in enumerate(BADGES, start=1):
        await bot.badges.set_role(GUILD_ID, badge.key, 500 + index)
    guild.get_role.side_effect = lambda role_id: MagicMock(
        spec=discord.Role, id=role_id
    )
    names = [
        "wisp_coin",
        "wisp_coin_mini",
        "viibr_logo",
        *(badge.emoji_name for badge in BADGES),
        *(snack.emoji_name for snack in SNACKS),
        *(gift.emoji_name for gift in GIFT_BY_KEY.values()),
    ]
    bot.emojis_by_name = {
        name: cast(
            discord.Emoji,
            discord.PartialEmoji(name=name, id=2**64 - 1 - index, animated=True),
        )
        for index, name in enumerate(names)
    }
    await rich(bot, points=10**9)

    view, text, selects = await open_vault(bot, guild)

    assert text_length(text) <= LAYOUT_TEXT_LIMIT
    assert_fits_its_box(text)
    assert "Get a badge" in layout_order(view)
    assert magazine_select(selects) is not None
    for gift in GIFT_BY_KEY.values():
        assert f"<a:{gift.emoji_name}:" in text, gift.key


# ---
# Buying
# ---


async def test_buying_a_cover_spends_records_and_sends_the_picture_privately(
    bot: app.WispBot, guild: MagicMock
) -> None:
    life = await lay(bot)
    await rich(bot, points=150)

    interaction = await buy(bot, guild, "viibrations")

    assert await balance(bot) == 50
    assert life.id is not None
    assert await bot.magazines.owned(GUILD_ID, USER_ID, life.id) == {"viibrations"}
    text = shown(interaction)
    assert text.splitlines()[0] == "♪ You got the VIIBRATIONS cover."
    assert section(text, "Magazines") == [
        "║𝄡 VIIBRATIONS cover・100 WC\n║ ・owned",
        "║𝄡 Music & Science cover・100 WC",
    ]
    (call,) = interaction.followup.send.await_args_list
    assert call.kwargs["ephemeral"] is True
    (picture,) = sent_files(interaction)
    assert picture.filename == "viibrations_cover.jpg"
    picture.close()
    select = magazine_select(
        layout_selects(interaction.edit_original_response.await_args.kwargs["view"])
    )
    assert select is not None
    assert [option.value for option in select.options] == ["musicnscience"]


async def test_owning_both_covers_leaves_the_section_without_a_select(
    bot: app.WispBot, guild: MagicMock
) -> None:
    await lay(bot)
    await rich(bot)
    for magazine in MAGAZINES:
        for picture in sent_files(await buy(bot, guild, magazine.key)):
            picture.close()

    view, text, selects = await open_vault(bot, guild)

    assert all(line.endswith("・owned") for line in section(text, "Magazines"))
    assert magazine_select(selects) is None
    assert "Get a magazine" not in layout_order(view)
    assert await balance(bot) == 800


async def test_a_member_short_of_points_is_refused(
    bot: app.WispBot, guild: MagicMock
) -> None:
    life = await lay(bot)
    await rich(bot, points=99)

    interaction = await buy(bot, guild, "viibrations")

    note = shown(interaction).splitlines()[0]
    assert note in {
        line.format(name="Member1")
        for line in LINES[(Moment.NOT_ENOUGH_POINTS, Mood.HAPPY)]
    }
    assert await balance(bot) == 99
    assert life.id is not None
    assert await bot.magazines.owned(GUILD_ID, USER_ID, life.id) == set()
    assert sent_files(interaction) == []


async def test_a_second_purchase_in_the_same_life_is_refused(
    bot: app.WispBot, guild: MagicMock
) -> None:
    await lay(bot)
    await rich(bot, points=300)
    _, _, selects = await open_vault(bot, guild)
    select = magazine_select(selects)
    assert select is not None

    first = await pick(select, bot, guild, "viibrations")
    second = await pick(select, bot, guild, "viibrations")

    for picture in sent_files(first):
        picture.close()
    assert shown(second).splitlines()[0] == (
        "♪ You already have the VIIBRATIONS cover for Wisp v1."
    )
    assert sent_files(second) == []
    assert await balance(bot) == 200


@pytest.mark.parametrize(
    ("stage", "phase"),
    [(Stage.OLD_FOGEY, Phase.ALIVE), (Stage.ROCKSTAR, Phase.DEAD)],
)
async def test_a_select_left_open_after_the_rockstar_days_refuses_cleanly(
    bot: app.WispBot, guild: MagicMock, stage: Stage, phase: Phase
) -> None:
    life = await lay(bot)
    await rich(bot, points=150)
    _, _, selects = await open_vault(bot, guild)
    select = magazine_select(selects)
    assert select is not None
    life.stage = stage
    life.phase = phase
    await bot.lives.save(GUILD_ID, life)

    interaction = await pick(select, bot, guild, "musicnscience")

    text = shown(interaction)
    assert text.splitlines()[0] == GONE
    assert "**Magazines**" not in text
    assert await balance(bot) == 150
    assert sent_files(interaction) == []
    assert life.id is not None
    assert await bot.magazines.owned(GUILD_ID, USER_ID, life.id) == set()


async def test_a_banned_member_is_refused(bot: app.WispBot, guild: MagicMock) -> None:
    await lay(bot)
    await rich(bot)
    _, _, selects = await open_vault(bot, guild)
    select = magazine_select(selects)
    assert select is not None
    await bot.players.set_offense(
        GUILD_ID, USER_ID, 1, discord.utils.utcnow() + timedelta(days=1), False
    )

    interaction = await pick(select, bot, guild, "viibrations")

    assert shown(interaction).splitlines()[0] == (
        "♪ Wisp is not taking snacks or gifts from you right now."
    )
    assert await balance(bot) == 1000


async def test_a_member_who_cannot_feed_is_refused(
    bot: app.WispBot, guild: MagicMock
) -> None:
    await lay(bot)
    await rich(bot)
    _, _, selects = await open_vault(bot, guild)
    select = magazine_select(selects)
    assert select is not None

    interaction = await pick(select, bot, guild, "viibrations", member(roles=()))

    assert shown(interaction).splitlines()[0].startswith("♪ Only members at ")
    assert await balance(bot) == 1000


async def test_the_next_rockstar_life_sells_the_covers_again(
    bot: app.WispBot, guild: MagicMock
) -> None:
    first = await lay(bot)
    await rich(bot)
    for picture in sent_files(await buy(bot, guild, "viibrations")):
        picture.close()
    first.phase = Phase.DEAD
    first.ended_at = discord.utils.utcnow()
    await bot.lives.save(GUILD_ID, first)
    await lay(bot, version=2)

    interaction = await buy(bot, guild, "viibrations")

    assert shown(interaction).splitlines()[0] == "♪ You got the VIIBRATIONS cover."
    for picture in sent_files(interaction):
        picture.close()
    assert await balance(bot) == 800


async def test_a_picture_that_cannot_be_sent_is_reported_and_the_purchase_stands(
    bot: app.WispBot,
    guild: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(magazines, "MAGAZINE_ART", tmp_path)
    life = await lay(bot)
    await rich(bot, points=100)

    interaction = await buy(bot, guild, "musicnscience")

    assert shown(interaction).splitlines()[0] == "♪ You got the Music & Science cover."
    report = cast(AsyncMock, bot.report_error).await_args
    assert report is not None
    assert report.args[1] == (
        "sending the Music & Science cover picture (the purchase went through)"
    )
    assert isinstance(report.args[2], FileNotFoundError)
    assert await balance(bot) == 0
    assert life.id is not None
    assert await bot.magazines.owned(GUILD_ID, USER_ID, life.id) == {"musicnscience"}


def test_each_cover_has_a_picture_small_enough_to_post() -> None:
    for magazine in MAGAZINES:
        path = cover_art(magazine)
        assert path.is_file(), path
        assert path.stat().st_size < POSTING_LIMIT, path


# ---
# The Snack Pack
# ---


async def snack_pack(bot: app.WispBot, guild: MagicMock) -> str:
    interaction = make_interaction(bot, guild)
    command: Any = snacks.wisp_snackpack
    await command.callback(interaction)
    return str(interaction.followup.send.await_args.args[0])


async def test_the_snack_pack_keeps_every_cover_from_every_life_newest_first(
    bot: app.WispBot, guild: MagicMock
) -> None:
    at = discord.utils.utcnow()
    await bot.magazines.record(GUILD_ID, USER_ID, "viibrations", 1, 1, at)
    await bot.magazines.record(
        GUILD_ID, USER_ID, "musicnscience", 3, 3, at - timedelta(minutes=1)
    )
    await bot.magazines.record(GUILD_ID, USER_ID, "viibrations", 3, 3, at)

    text = await snack_pack(bot, guild)

    assert section(text, "Magazines") == [
        "║𝄡 Wisp v3's VIIBRATIONS cover",
        "║𝄡 Wisp v3's Music & Science cover",
        "║𝄡 Wisp v1's VIIBRATIONS cover",
    ]
    lines = text.splitlines()
    assert lines.index("║𝄡𝄚𝄂𝄆 **Badges**") < lines.index("║𝄡𝄚𝄂𝄆 **Magazines**")
    assert lines[-2].startswith("╚")


async def test_a_snack_pack_without_magazines_has_no_magazines_section(
    bot: app.WispBot, guild: MagicMock
) -> None:
    text = await snack_pack(bot, guild)

    assert "**Magazines**" not in text


async def test_the_fullest_snack_pack_with_magazines_still_fits_one_message(
    bot: app.WispBot, guild: MagicMock
) -> None:
    give_emojis(
        bot,
        "wisp_coin",
        *(badge.emoji_name for badge in BADGES),
        *(f"keepsake_{kind.value}" for kind in KeepsakeKind),
    )
    await bot.players.set_name(GUILD_ID, USER_ID, "W" * 24)
    at = discord.utils.utcnow()
    for version in range(1, 30):
        for kind in KeepsakeKind:
            await bot.keepsakes.give(GUILD_ID, USER_ID, kind, 1000 + version, at)
        for badge in BADGES:
            await bot.badges.record(
                GUILD_ID, USER_ID, badge.key, version, 1000 + version, at
            )
        for magazine in MAGAZINES:
            await bot.magazines.record(
                GUILD_ID, USER_ID, magazine.key, version, 1000 + version, at
            )

    text = await snack_pack(bot, guild)

    assert text_length(text) <= MESSAGE_LIMIT
    assert_fits_its_box(text)
    assert text.splitlines()[-2].startswith("╚")
    for heading in ("Keepsakes", "Badges", "Magazines"):
        lines = section(text, heading)
        assert len(lines) > 2, heading
        assert lines[-1].startswith("║𝄡 and ") and lines[-1].endswith(" more")
    assert section(text, "Magazines")[0] == ("║𝄡 Wisp v1029's Music & Science\n║ cover")
