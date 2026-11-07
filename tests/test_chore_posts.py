"""Tests for chore posts in Wisp's House and their first-press buttons.

Discord objects are fakes; the repositories are the real ones.
"""

import asyncio
import random
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

import app
from cogs import chores as chore_posts
from cogs.chores import ChoreButton, chore_view, post_chores
from db.database import Database
from db.lives import LifeRepo
from db.players import PlayerRepo
from db.settings import SettingsRepo
from wisp.chores import (
    ChoreEvent,
    ChoreEventKind,
    is_open,
    latest_nap_start,
    message_id,
    open_mess,
    open_tantrum,
    start_nap,
    tick_chores,
    wake,
)
from wisp.life import Life, Mood, Phase, new_egg
from wisp.lines import LINES, Moment
from wisp.rules import (
    CHORE_POINTS,
    HEALTH_PER_CLEANUP,
    MESS_LEFT_FOR,
    SICK_FOR,
    TANTRUM_PICTURES,
    Chore,
    Stage,
)

GUILD_ID = 100
HOUSE_ID = 20
USER_ID = 1
OTHER_USER_ID = 2
OUTSIDER_ID = 3
QUALIFYING_ROLE = 7
FIRST_POST_ID = 9000
POST_TEXT = "a chore post"
NO_PING = discord.AllowedMentions.none().to_dict()
ALREADY_DONE = "♪ Someone already took care of that."
NO_ROLE = (
    "♪ You can't take care of Wisp: you don't have a role that can feed Wisp: "
    f"<@&{QUALIFYING_ROLE}>."
)
NOT_OPENED = "♪ You can't take care of Wisp: you haven't opened /wisp board yet."
BANNED = "♪ You can't take care of Wisp: you are banned from feeding Wisp right now."
FROZEN = "♪ Wisp is frozen right now, so nothing can change until staff unfreeze him."
NO_POST = "♪ That post can't be found, so nothing was done."
OLD_POST = "♪ That post is from a Wisp who is gone now."
NOT_ALIVE = "♪ Wisp isn't alive right now, so there is nothing to do."
LATER = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)
COLD_WORDS = (
    "cold",
    "sniff",
    "sneez",
    "achoo",
    "stuffy",
    "nose",
    "clogged",
    "sick",
    "medicine",
)

# ---
# Fakes
# ---


class FakeServer:
    """A guild with Wisp's House, whose posts get ids from FIRST_POST_ID up."""

    def __init__(self) -> None:
        self.posts: dict[int, MagicMock] = {}
        self.house = MagicMock(spec=discord.TextChannel)
        self.house.send = AsyncMock(side_effect=self._send)
        self.house.fetch_message = AsyncMock(side_effect=self._fetch)
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = GUILD_ID
        self.guild.get_channel_or_thread.side_effect = {HOUSE_ID: self.house}.get

    async def _send(self, text: str, **_kwargs: Any) -> MagicMock:
        post = make_post(FIRST_POST_ID + len(self.posts), text)
        self.posts[post.id] = post
        return post

    async def _fetch(self, message_id: int) -> MagicMock:
        if message_id not in self.posts:
            raise discord.NotFound(MagicMock(status=404), "Unknown Message")
        return self.posts[message_id]


def make_post(message_id: int, text: str = POST_TEXT) -> MagicMock:
    post = MagicMock(spec=discord.Message)
    post.id = message_id
    post.content = text
    post.edit = AsyncMock()
    return post


@pytest.fixture
def server() -> FakeServer:
    return FakeServer()


@pytest.fixture
def bot(
    db: Database, server: FakeServer, monkeypatch: pytest.MonkeyPatch
) -> Iterator[app.WispBot]:
    wisp_bot = app.WispBot()
    wisp_bot.settings = SettingsRepo(db)
    wisp_bot.lives = LifeRepo(db)
    wisp_bot.players = PlayerRepo(db)
    monkeypatch.setattr(wisp_bot, "get_guild", lambda _id: server.guild)
    yield wisp_bot


@pytest.fixture(autouse=True)
async def configured(bot: app.WispBot) -> None:
    await bot.settings.update(GUILD_ID, house_channel_id=HOUSE_ID)
    await bot.settings.add_role(GUILD_ID, QUALIFYING_ROLE)
    for user_id in (USER_ID, OTHER_USER_ID):
        await bot.players.activate(GUILD_ID, user_id, discord.utils.utcnow())


def make_interaction(
    bot: app.WispBot,
    post: MagicMock,
    user_id: int = USER_ID,
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
) -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.client = bot
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild_id = GUILD_ID
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.message = post
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
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def lay(bot: app.WispBot, stage: Stage = Stage.BABY) -> Life:
    now = discord.utils.utcnow()
    life = new_egg(1, now - timedelta(days=1))
    life.phase = Phase.ALIVE
    life.health = 50.0
    life.stage = life.peak_stage = stage
    life.hatched_at = life.stage_started_at = now
    return await bot.lives.insert(GUILD_ID, life)


async def open_chore(
    bot: app.WispBot, chore: Chore, posted_id: int = FIRST_POST_ID
) -> Life:
    """A Baby with `chore` open, shown by the House post `posted_id`."""
    life = await lay(bot)
    match chore:
        case Chore.MESS:
            open_mess(life)
            life.mess_message_id = posted_id
        case Chore.TANTRUM:
            open_tantrum(life)
            life.tantrum_message_id = posted_id
        case Chore.NAP:
            start_nap(life)
            life.nap_message_id = posted_id
    await bot.lives.save(GUILD_ID, life)
    return life


async def press(
    bot: app.WispBot,
    chore: Chore,
    life_id: int,
    post: MagicMock,
    user_id: int = USER_ID,
    roles: tuple[int, ...] = (QUALIFYING_ROLE,),
) -> MagicMock:
    interaction = make_interaction(bot, post, user_id, roles)
    await ChoreButton(chore, life_id, "Press").callback(interaction)
    return interaction


def private_replies(interaction: MagicMock) -> list[str]:
    replies = []
    for sent in interaction.followup.send.await_args_list:
        assert sent.kwargs["ephemeral"] is True
        replies.append(str(sent.args[0]))
    return replies


async def current_life(bot: app.WispBot) -> Life:
    life = await bot.lives.current(GUILD_ID)
    assert life is not None
    return life


async def points(bot: app.WispBot, user_id: int) -> int:
    return (await bot.players.get(GUILD_ID, user_id)).lifetime_points


def only_button(view: discord.ui.View) -> discord.ui.Button[discord.ui.View]:
    (child,) = view.children
    assert isinstance(child, ChoreButton)
    return child.item


def filename(kwargs: dict[str, Any]) -> str | None:
    if "file" not in kwargs:
        return None
    file: discord.File = kwargs["file"]
    file.close()
    return file.filename


def lines(moment: Moment, **fields: str) -> set[str]:
    return {line.format(**fields) for line in LINES[(moment, Mood.HAPPY)]}


def house_reports(server: FakeServer) -> list[str]:
    texts = [str(call.args[0]) for call in server.house.send.await_args_list]
    return [text for text in texts if text.startswith("Error in ")]


# ---
# Posting chores
# ---


async def test_a_mess_posts_poop_gif_and_a_clean_up_button_without_pings(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    open_mess(life)
    await bot.lives.save(GUILD_ID, life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.MESS)])

    (sent,) = server.house.send.await_args_list
    head, line = sent.args[0].split("\n")
    assert head == "♪ Wisp's mess: poop."
    assert line in lines(Moment.MESS)
    assert filename(sent.kwargs) == "poop.gif"
    assert sent.kwargs["allowed_mentions"].to_dict() == NO_PING
    button = only_button(sent.kwargs["view"])
    assert (button.label, button.custom_id) == (
        "Clean up",
        f"wisp:chore:mess:{life.id}",
    )
    assert sent.kwargs["view"].timeout is None
    assert (await current_life(bot)).mess_message_id == FIRST_POST_ID


async def test_a_teen_mess_is_a_zit_breakout_with_a_face_wash_button(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot, Stage.TEEN)
    open_mess(life)
    await bot.lives.save(GUILD_ID, life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.MESS)])

    (sent,) = server.house.send.await_args_list
    assert filename(sent.kwargs) == "pimple.gif"
    button = only_button(sent.kwargs["view"])
    assert (button.label, button.custom_id) == (
        "Hand him face wash",
        f"wisp:chore:mess:{life.id}",
    )


@pytest.mark.parametrize(
    ("stage", "head"),
    [
        (Stage.BABY, "♪ Wisp's mess: poop."),
        (Stage.TEEN, "♪ Wisp's mess: a zit breakout."),
        (Stage.OLD_FOGEY, "♪ Wisp's mess: dentures that need a soak."),
    ],
)
async def test_a_mess_post_names_the_mess_of_his_stage(
    bot: app.WispBot, server: FakeServer, stage: Stage, head: str
) -> None:
    life = await lay(bot, stage)
    open_mess(life)
    await bot.lives.save(GUILD_ID, life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.MESS)])

    (sent,) = server.house.send.await_args_list
    assert sent.args[0].split("\n")[0] == head


@pytest.mark.parametrize("picture", ["missing.gif", None])
async def test_a_mess_without_its_picture_is_words_and_the_button(
    bot: app.WispBot,
    server: FakeServer,
    monkeypatch: pytest.MonkeyPatch,
    picture: str | None,
) -> None:
    monkeypatch.setitem(chore_posts.MESSES, Stage.ADULT, ("a mess", "Tidy", picture))
    life = await lay(bot, Stage.ADULT)
    open_mess(life)
    await bot.lives.save(GUILD_ID, life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.MESS)])

    (sent,) = server.house.send.await_args_list
    assert "file" not in sent.kwargs
    assert only_button(sent.kwargs["view"]).label == "Tidy"


@pytest.mark.parametrize(("stage", "picture"), sorted(TANTRUM_PICTURES.items()))
async def test_the_tantrum_picture_follows_his_stage(
    bot: app.WispBot, server: FakeServer, stage: Stage, picture: str
) -> None:
    life = await lay(bot, stage)
    open_tantrum(life)
    await bot.lives.save(GUILD_ID, life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.TANTRUM)])

    (sent,) = server.house.send.await_args_list
    assert sent.args[0] in lines(Moment.TANTRUM)
    assert filename(sent.kwargs) == picture
    assert sent.kwargs["allowed_mentions"].to_dict() == NO_PING
    button = only_button(sent.kwargs["view"])
    assert (button.label, button.custom_id) == (
        "Scold",
        f"wisp:chore:tantrum:{life.id}",
    )
    assert (await current_life(bot)).tantrum_message_id == FIRST_POST_ID


@pytest.mark.parametrize(
    ("stage", "picture"), [(Stage.BABY, "nap.gif"), (Stage.TEEN, None)]
)
async def test_a_nap_post_shows_nap_gif_for_little_stages_and_text_after(
    bot: app.WispBot, server: FakeServer, stage: Stage, picture: str | None
) -> None:
    life = await lay(bot, stage)
    start_nap(life)
    await bot.lives.save(GUILD_ID, life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.NAP)])

    (sent,) = server.house.send.await_args_list
    assert sent.args[0] in lines(Moment.NAP)
    assert filename(sent.kwargs) == picture
    assert sent.kwargs["allowed_mentions"].to_dict() == NO_PING
    button = only_button(sent.kwargs["view"])
    assert (button.label, button.custom_id) == (
        "Lights off",
        f"wisp:chore:nap:{life.id}",
    )
    assert (await current_life(bot)).nap_message_id == FIRST_POST_ID


async def test_a_post_for_a_chore_already_done_is_not_remembered(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    open_mess(life)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.MESS)])

    server.house.send.assert_awaited_once()
    assert (await current_life(bot)).mess_message_id is None


async def test_a_nap_a_poke_ends_right_after_the_post_leaves_no_button(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    start_nap(life)
    await bot.lives.save(GUILD_ID, life)
    send = server.house.send.side_effect

    async def send_then_poke_awake(text: str, **kwargs: Any) -> Any:
        post = await send(text, **kwargs)
        napping = await current_life(bot)
        wake(napping, discord.utils.utcnow())
        await bot.lives.save(GUILD_ID, napping)
        return post

    server.house.send.side_effect = send_then_poke_awake

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.NAP)])

    post = server.posts[FIRST_POST_ID]
    post.edit.assert_awaited_once()
    assert post.edit.await_args.kwargs["content"] == post.content
    assert post.edit.await_args.kwargs["view"] is None
    assert (await current_life(bot)).nap_message_id is None


async def test_a_late_post_never_replaces_the_stored_post_id(
    bot: app.WispBot, server: FakeServer
) -> None:
    older_id = 777
    life = await open_chore(bot, Chore.NAP, older_id)

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.NAP)])

    assert (await current_life(bot)).nap_message_id == older_id
    late = server.posts[FIRST_POST_ID]
    late.edit.assert_awaited_once()
    assert late.edit.await_args.kwargs["view"] is None


@pytest.mark.parametrize(
    ("chore", "kind"),
    [
        (Chore.MESS, ChoreEventKind.MESS),
        (Chore.TANTRUM, ChoreEventKind.TANTRUM),
        (Chore.NAP, ChoreEventKind.NAP),
    ],
)
async def test_a_failed_chore_post_is_reported_and_the_chore_dropped(
    bot: app.WispBot, server: FakeServer, chore: Chore, kind: ChoreEventKind
) -> None:
    life = await lay(bot)
    {Chore.MESS: open_mess, Chore.TANTRUM: open_tantrum, Chore.NAP: start_nap}[chore](
        life
    )
    await bot.lives.save(GUILD_ID, life)
    server.house.send.side_effect = [
        discord.HTTPException(MagicMock(status=500), "boom"),
        None,
    ]

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(kind)])

    (report,) = house_reports(server)
    assert report.startswith("Error in posting to Wisp's House: HTTPException")
    after = await current_life(bot)
    assert message_id(after, chore) is None
    assert not is_open(after, chore)
    assert (after.health, after.wellbeing) == (life.health, life.wellbeing)
    assert after.mess_gap == 0.0


async def test_the_first_press_before_the_post_is_stored_does_the_chore(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    open_mess(life)
    await bot.lives.save(GUILD_ID, life)
    assert life.id is not None
    life_id = life.id
    send = server.house.send.side_effect
    pressed: list[MagicMock] = []

    async def send_then_press(text: str, **kwargs: Any) -> Any:
        post = await send(text, **kwargs)
        pressed.append(await press(bot, Chore.MESS, life_id, post))
        return post

    server.house.send.side_effect = send_then_press

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.MESS)])

    (interaction,) = pressed
    (receipt,) = private_replies(interaction)
    assert receipt.startswith("♪ You cleaned up.")
    after = await current_life(bot)
    assert not is_open(after, Chore.MESS)
    assert after.mess_message_id == FIRST_POST_ID
    assert await points(bot, USER_ID) == CHORE_POINTS[Chore.MESS]
    post = server.posts[FIRST_POST_ID]
    (done,) = post.edit.await_args_list
    assert f"<@{USER_ID}> cleaned up the mess" in done.kwargs["content"]


async def test_a_chore_view_never_times_out() -> None:
    view = chore_view(Chore.TANTRUM, 7, Stage.CHILD)

    assert view.timeout is None
    assert only_button(view).custom_id == "wisp:chore:tantrum:7"


# ---
# Chores that ran out
# ---


async def test_a_mess_left_too_long_edits_its_post_and_posts_the_cold(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    post = make_post(FIRST_POST_ID - 1)
    server.posts[post.id] = post

    await post_chores(
        bot,
        GUILD_ID,
        life,
        [
            ChoreEvent(ChoreEventKind.MESS_LEFT, post.id),
            ChoreEvent(ChoreEventKind.SNIFFLES),
        ],
    )

    post.edit.assert_awaited_once()
    edit = post.edit.await_args.kwargs
    assert edit["content"] in lines(Moment.MESS_LEFT)
    assert edit["view"] is None
    assert edit["allowed_mentions"].to_dict() == NO_PING
    (sent,) = server.house.send.await_args_list
    assert sent.args[0] in lines(Moment.SNIFFLES)
    assert filename(sent.kwargs) == "wispsick.gif"
    assert sent.kwargs["allowed_mentions"].to_dict() == NO_PING
    assert "view" not in sent.kwargs


async def test_a_mess_left_while_he_has_monster_pox_promises_no_cold(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)
    life.cold_left = SICK_FOR.total_seconds()
    life.nap_slot = latest_nap_start(LATER)
    life.tantrum_due_at = LATER + timedelta(days=1)
    open_mess(life)
    post = make_post(FIRST_POST_ID - 1)
    server.posts[post.id] = post
    life.mess_message_id = post.id

    events = tick_chores(life, LATER, MESS_LEFT_FOR, random.Random(1), frozen=False)
    await post_chores(bot, GUILD_ID, life, events)

    assert events == [ChoreEvent(ChoreEventKind.MESS_LEFT, post.id)]
    edited = post.edit.await_args.kwargs["content"]
    assert edited in lines(Moment.MESS_LEFT)
    assert not [word for word in COLD_WORDS if word in edited.lower()]
    server.house.send.assert_not_awaited()


@pytest.mark.parametrize(
    ("kind", "moment"),
    [
        (ChoreEventKind.TANTRUM_MISSED, Moment.TANTRUM_MISSED),
        (ChoreEventKind.LIGHTS_MISSED, Moment.LIGHTS_MISSED),
    ],
)
async def test_a_missed_tantrum_and_missed_lights_edit_their_posts(
    bot: app.WispBot, server: FakeServer, kind: ChoreEventKind, moment: Moment
) -> None:
    life = await lay(bot)
    post = make_post(FIRST_POST_ID - 1)
    server.posts[post.id] = post

    await post_chores(bot, GUILD_ID, life, [ChoreEvent(kind, post.id)])

    edit = post.edit.await_args.kwargs
    assert edit["content"] in lines(moment)
    assert edit["view"] is None
    assert edit["allowed_mentions"].to_dict() == NO_PING
    server.house.send.assert_not_awaited()


async def test_a_missing_post_to_edit_is_reported(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await lay(bot)

    await post_chores(
        bot, GUILD_ID, life, [ChoreEvent(ChoreEventKind.TANTRUM_MISSED, 1234)]
    )

    (report,) = house_reports(server)
    assert report.startswith("Error in editing a post in Wisp's House: NotFound")


# ---
# Pressing a chore button
# ---


async def test_the_first_eligible_press_cleans_up_and_pays(
    bot: app.WispBot,
) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)

    pressed = await press(bot, Chore.MESS, life.id, post)

    pressed.response.defer.assert_awaited_once_with()
    assert await points(bot, USER_ID) == 2
    after = await current_life(bot)
    assert not is_open(after, Chore.MESS)
    assert (after.health, after.wellbeing) == (55.0, 50.0)
    edit = post.edit.await_args.kwargs
    head, done, line = edit["content"].split("\n")
    assert head == POST_TEXT
    assert done == f"♪ <@{USER_ID}> cleaned up the mess ・ +2 WC"
    assert line in lines(Moment.MESS_CLEANED, name=f"Member{USER_ID}")
    assert edit["view"] is None
    assert edit["allowed_mentions"].to_dict() == NO_PING
    assert private_replies(pressed) == [
        f"♪ You cleaned up. +{CHORE_POINTS[Chore.MESS]} WC. "
        f"Health +{HEALTH_PER_CLEANUP} (now 55)."
    ]


@pytest.mark.parametrize(
    ("chore", "did"),
    [(Chore.TANTRUM, "scolded Wisp"), (Chore.NAP, "turned off the lights")],
)
async def test_the_other_chores_say_what_they_did(
    bot: app.WispBot, chore: Chore, did: str
) -> None:
    life = await open_chore(bot, chore)
    assert life.id is not None

    pressed = await press(bot, chore, life.id, make_post(FIRST_POST_ID))

    assert private_replies(pressed) == [f"♪ You {did}. +{CHORE_POINTS[chore]} WC."]


async def test_the_done_line_calls_the_member_by_the_name_wisp_knows(
    bot: app.WispBot,
) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    await bot.players.set_name(GUILD_ID, USER_ID, "Myra")
    post = make_post(FIRST_POST_ID)

    await press(bot, Chore.MESS, life.id, post)

    line = post.edit.await_args.kwargs["content"].split("\n")[-1]
    assert line in lines(Moment.MESS_CLEANED, name="Myra")


async def test_a_later_press_is_told_it_is_already_done(bot: app.WispBot) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)
    await press(bot, Chore.MESS, life.id, post)

    later = await press(bot, Chore.MESS, life.id, post, OTHER_USER_ID)

    assert private_replies(later) == [ALREADY_DONE]
    assert await points(bot, OTHER_USER_ID) == 0
    post.edit.assert_awaited_once()


@pytest.mark.parametrize(
    ("user_id", "roles", "reason"),
    [(OUTSIDER_ID, (QUALIFYING_ROLE,), NOT_OPENED), (USER_ID, (), NO_ROLE)],
    ids=["board-not-opened", "no-role"],
)
async def test_a_member_who_cannot_feed_is_told_why_and_the_mess_stays(
    bot: app.WispBot, user_id: int, roles: tuple[int, ...], reason: str
) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)

    pressed = await press(bot, Chore.MESS, life.id, post, user_id, roles)

    assert private_replies(pressed) == [reason]
    assert is_open(await current_life(bot), Chore.MESS)
    assert await points(bot, user_id) == 0
    post.edit.assert_not_awaited()


async def test_a_banned_member_is_told_and_the_mess_stays(bot: app.WispBot) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    await bot.players.set_offense(
        GUILD_ID, USER_ID, 1, discord.utils.utcnow() + timedelta(days=1), False
    )
    post = make_post(FIRST_POST_ID)

    pressed = await press(bot, Chore.MESS, life.id, post)

    assert private_replies(pressed) == [BANNED]
    assert is_open(await current_life(bot), Chore.MESS)
    post.edit.assert_not_awaited()


async def test_a_press_with_no_post_to_check_says_so(bot: app.WispBot) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    interaction = make_interaction(bot, make_post(FIRST_POST_ID))
    interaction.message = None

    await ChoreButton(Chore.MESS, life.id, "Press").callback(interaction)

    assert private_replies(interaction) == [NO_POST]
    assert is_open(await current_life(bot), Chore.MESS)


@pytest.mark.parametrize("chore", list(Chore))
async def test_a_chore_while_frozen_says_he_is_frozen(
    bot: app.WispBot, chore: Chore
) -> None:
    life = await open_chore(bot, chore)
    assert life.id is not None
    await bot.settings.update(GUILD_ID, frozen=True)
    post = make_post(FIRST_POST_ID)

    pressed = await press(bot, chore, life.id, post)

    assert private_replies(pressed) == [FROZEN]
    assert is_open(await current_life(bot), chore)
    assert await points(bot, USER_ID) == 0
    post.edit.assert_not_awaited()


async def test_two_presses_at_once_have_one_winner(bot: app.WispBot) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)

    first, second = await asyncio.gather(
        press(bot, Chore.MESS, life.id, post, USER_ID),
        press(bot, Chore.MESS, life.id, post, OTHER_USER_ID),
    )

    assert sorted([await points(bot, USER_ID), await points(bot, OTHER_USER_ID)]) == [
        0,
        2,
    ]
    replies = private_replies(first) + private_replies(second)
    assert sorted(replies) == sorted(
        [
            ALREADY_DONE,
            f"♪ You cleaned up. +{CHORE_POINTS[Chore.MESS]} WC. "
            f"Health +{HEALTH_PER_CLEANUP} (now 55).",
        ]
    )
    post.edit.assert_awaited_once()
    assert (await current_life(bot)).health == 55.0


async def test_a_rebuilt_button_still_cleans_up(bot: app.WispBot) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    custom_id = f"wisp:chore:mess:{life.id}"
    match = ChoreButton.__discord_ui_compiled_template__.fullmatch(custom_id)
    assert match is not None
    post = make_post(FIRST_POST_ID)
    interaction = make_interaction(bot, post)
    pressed = discord.ui.Button[discord.ui.View](label="Clean up", custom_id=custom_id)

    restored = await ChoreButton.from_custom_id(interaction, pressed, match)
    await restored.callback(interaction)

    assert (restored.item.label, restored.item.custom_id) == ("Clean up", custom_id)
    assert await points(bot, USER_ID) == 2
    assert not is_open(await current_life(bot), Chore.MESS)


async def test_a_button_from_an_earlier_mess_is_already_done(
    bot: app.WispBot,
) -> None:
    life = await open_chore(bot, Chore.MESS, posted_id=FIRST_POST_ID + 1)
    assert life.id is not None
    old_post = make_post(FIRST_POST_ID)

    pressed = await press(bot, Chore.MESS, life.id, old_post)

    assert private_replies(pressed) == [ALREADY_DONE]
    assert is_open(await current_life(bot), Chore.MESS)
    assert await points(bot, USER_ID) == 0


async def test_a_button_from_another_life_is_already_done(bot: app.WispBot) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)

    pressed = await press(bot, Chore.MESS, life.id + 1, post)

    assert private_replies(pressed) == [OLD_POST]
    assert is_open(await current_life(bot), Chore.MESS)
    assert await points(bot, USER_ID) == 0


@pytest.mark.parametrize("phase", [Phase.DEAD, Phase.PASSED])
async def test_a_mess_left_open_when_his_life_ended_pays_nothing(
    bot: app.WispBot, phase: Phase
) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    life.phase = phase
    await bot.lives.save(GUILD_ID, life)
    post = make_post(FIRST_POST_ID)

    pressed = await press(bot, Chore.MESS, life.id, post)

    assert private_replies(pressed) == [NOT_ALIVE]
    assert await points(bot, USER_ID) == 0
    after = await current_life(bot)
    assert (after.phase, is_open(after, Chore.MESS)) == (phase, True)
    post.edit.assert_not_awaited()


@pytest.mark.parametrize(
    ("chore", "done", "moment"),
    [
        (Chore.TANTRUM, "scolded Wisp", Moment.SCOLDED),
        (Chore.NAP, "turned off the lights", Moment.LIGHTS_OFF),
    ],
)
async def test_scold_and_lights_off_pay_two_points(
    bot: app.WispBot, chore: Chore, done: str, moment: Moment
) -> None:
    life = await open_chore(bot, chore)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)

    await press(bot, chore, life.id, post)

    assert await points(bot, USER_ID) == 2
    assert not is_open(await current_life(bot), chore)
    head, done_line, line = post.edit.await_args.kwargs["content"].split("\n")
    assert done_line == f"♪ <@{USER_ID}> {done} ・ +2 WC"
    assert line in lines(moment, name=f"Member{USER_ID}")


async def test_a_failure_is_reported_where_the_button_was_pressed(
    bot: app.WispBot, server: FakeServer
) -> None:
    life = await open_chore(bot, Chore.MESS)
    assert life.id is not None
    post = make_post(FIRST_POST_ID)
    post.edit.side_effect = discord.HTTPException(MagicMock(status=500), "boom")
    interaction = make_interaction(bot, post)
    interaction.channel = server.house

    await ChoreButton(Chore.MESS, life.id, "Clean up").callback(interaction)

    (report,) = house_reports(server)
    assert report.startswith("Error in the chore button: HTTPException")


async def test_the_chore_button_is_registered_to_survive_a_restart(
    bot: app.WispBot, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_dynamic_items = MagicMock()
    monkeypatch.setattr(bot, "add_dynamic_items", add_dynamic_items)

    await chore_posts.setup(bot)

    add_dynamic_items.assert_called_once_with(ChoreButton)
    assert "cogs.chores" in app.EXTENSIONS
