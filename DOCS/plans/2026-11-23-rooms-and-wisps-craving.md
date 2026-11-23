# Rooms and Wisp's Craving Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every member one private room thread off Wisp's House, move the Rhyme Duel into it, pin a copy of their Snack Pack there, and add Wisp's Craving, a once-a-day snack guessing game.

**Architecture:** A new `cogs/rooms.py` owns finding, making, renaming and reopening a member's room (stored on `players`). A new `db/cravings.py` stores each member's round for the UTC day, so a round survives restarts and the craved snack cannot be rerolled. Pure game rules live in `wisp/craving.py`; the Discord side (command, Play-menu button, persistent guess menu, timeout sweep) lives in `cogs/craving.py`. The Rhyme Duel and Craving share one reward helper.

**Tech Stack:** Python 3.13, discord.py 2.x (private threads, `DynamicItem` selects), aiomysql on MariaDB, pytest with real `wisptest_` tables.

**Spec:** `DOCS/specs/2026-11-23-rooms-and-wisps-craving-design.md`

## Global Constraints

- Wisp is live: every storage change is additive and migrates the live database at startup (`db/schema.py`).
- Every tunable number lives only in `wisp/rules.py`.
- Users are identified by Discord ID everywhere; names are display only. Days are UTC calendar days.
- Bot text: `・` bullets, `♪` flair, no Unicode emoji in canned or AI text, no embeds, no DMs.
- Errors are posted as `Error in <context>: <Type>: <message>` via `bot.report_error`.
- Quality: `PYTHONUTF8=1 .venv/Scripts/python -m black/isort/flake8/mypy --strict` pass on touched files. Section headers are `# ---` rules. No narrating comments, no dead code, no blanket `except Exception`.
- Tests use the real database (`db` fixture, `wisptest_` prefix); Discord objects are fakes. Never run two pytest processes at once.
- Messages stay under 2,000 characters (`text_length`); Components V2 menus under 4,000.
- Members use `/wisp` slash commands. One room per member per server, never a fallback to public threads.
- Hints are written lines, never AI.

## Review Focus

1. A member whose stored room was deleted, or sits under an old House after setup changed it, gets a new room on next use, not an error (Task 3 test `test_a_room_under_an_old_house_is_made_again`).
2. A bot restart mid-round resumes the same snack and guesses; starting again never rerolls (Task 6 test `test_starting_again_resumes_the_same_round`).
3. A stranger (staff can see rooms) pressing someone else's guess menu is refused and changes nothing (Task 6 test `test_only_the_rooms_owner_can_guess`).
4. Feeding a won snack uses the won one first and says so exactly once per won snack (Task 5 test `test_a_won_snack_is_eaten_first_then_it_is_ordinary`).
5. A member who joined before this release gets a room the first time they run `/wisp board`, play, or open their Snack Pack, and only one (Task 3 test `test_an_old_member_gets_one_room_on_next_use`).

## Rulings made while planning

- Spec says "setup's permission check gains them", but no bot-permission check exists. Ruling: Task 3 adds a small one to `set_up` that reports missing House permissions as a warning line; setup still finishes.
- Member notes reach the AI prompt only from Adult on (`keeps_notes`). Ruling: Craving notes are always stored; he brings them up once grown, like every other note. Raise with Myra after shipping.
- "Like a counted Rhyme Duel": the round gives `PLAY_POINTS` (1 WC), `GROWTH_PER_PLAY`, `WELLBEING_PER_PLAY` and capped `BOND_PER_PLAY`, through one helper shared with the duel.
- A won snack beats his favorite-snack line.
- The room's Snack Pack is reposted (old one deleted, new one sent and pinned), not edited.
- Timeouts are swept by the life loop tick (every 5 minutes) and on any late press; a round idle longer than `CRAVING_TIMEOUT` ends as a loss.

---

### Task 1: Storage

**Files:**
- Modify: `db/schema.py`, `db/players.py`, `db/activity.py`, `app.py`
- Create: `db/cravings.py`
- Test: `tests/test_schema.py`, `tests/test_repos.py`

**Interfaces:**
- Produces:
  - `Player.room_thread_id: int | None = None`, `Player.room_pack_message_id: int | None = None` (columns `BIGINT NULL`, in `_DEFINITIONS["players"]` and `_ADDED_COLUMNS["players"]`).
  - `PlayerRepo.set_room(guild_id: int, user_id: int, thread_id: int | None) -> None` (also clears `room_pack_message_id`), `PlayerRepo.set_room_pack(guild_id: int, user_id: int, message_id: int | None) -> None`.
  - `inventory.won INT NOT NULL DEFAULT 0` (definition and `_ADDED_COLUMNS["inventory"]`).
  - `ActivityRepo.add_snack(guild_id, user_id, snack, quantity=1, *, won: bool = False) -> None` (won adds to `won` too).
  - `ActivityRepo.take_won_snack(guild_id: int, user_id: int, snack: str) -> bool`: one statement `qty = qty - 1, won = won - 1 WHERE won > 0 AND qty > 0`.
  - `InteractionKind.CRAVING = "craving"`, added to `_CASUAL`.
  - `ActivityRepo.cravings_today(guild_id, user_id, now) -> int`.
  - Table `cravings`: `guild_id BIGINT, user_id BIGINT, day DATE, snack VARCHAR(20), guesses VARCHAR(200) NOT NULL DEFAULT '' (comma-separated wrong keys), last_at DATETIME NOT NULL, ended_at DATETIME NULL, won BOOL NOT NULL DEFAULT 0, bought_at DATETIME NULL, PRIMARY KEY (guild_id, user_id, day), INDEX idx_open (guild_id, ended_at)`.
  - `db/cravings.py`: `@dataclass(frozen=True) class Round(guild_id: int, user_id: int, day: date, snack: str, guesses: tuple[str, ...], last_at: datetime, ended_at: datetime | None, won: bool, bought_at: datetime | None)`; `class CravingRepo` with `today(guild_id, user_id, now) -> Round | None`, `start(guild_id, user_id, snack: str, now) -> Round` (INSERT IGNORE then read back, so a second start returns the first), `add_guess(guild_id, user_id, day, snack: str, now) -> Round`, `end(guild_id, user_id, day, *, won: bool, now) -> bool` (False when already ended), `idle_since(cutoff: datetime) -> list[Round]` (open rounds with `last_at < cutoff`), `mark_bought(guild_id, user_id, day, now) -> bool` (only a lost, ended round with `bought_at IS NULL`).
  - `bot.cravings = CravingRepo(self.db)` in `app.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_schema.py
async def test_create_tables_adds_room_columns_to_a_live_players_table(db): ...
    # drop room_thread_id and room_pack_message_id, create_tables, both back and NULL
async def test_create_tables_adds_won_to_a_live_inventory_table(db): ...
    # drop inventory.won, create_tables, column back with default 0
async def test_create_tables_adds_cravings_beside_live_tables(db): ...
    # pattern of test_create_tables_adds_magazines_beside_live_tables; duplicate (guild, user, day) raises IntegrityError

# tests/test_repos.py
async def test_set_room_stores_the_thread_and_forgets_the_old_pack(db):
    repo = PlayerRepo(db)
    await repo.set_room_pack(GUILD, USER, 55)
    await repo.set_room(GUILD, USER, 77)
    player = await repo.get(GUILD, USER)
    assert (player.room_thread_id, player.room_pack_message_id) == (77, None)

async def test_won_snacks_are_taken_first_and_only_while_held(db):
    log = ActivityRepo(db)
    await log.add_snack(GUILD, USER, "jellywave")
    await log.add_snack(GUILD, USER, "jellywave", won=True)
    assert await log.take_won_snack(GUILD, USER, "jellywave") is True
    assert await log.take_won_snack(GUILD, USER, "jellywave") is False
    assert await log.inventory(GUILD, USER) == {"jellywave": 1}

async def test_a_craving_round_cannot_be_started_twice_a_day(db):
    repo = CravingRepo(db)
    first = await repo.start(GUILD, USER, "jellywave", NOW)
    again = await repo.start(GUILD, USER, "cheese", NOW)
    assert again.snack == first.snack == "jellywave"

async def test_a_round_keeps_its_guesses_and_ends_once(db): ...
    # add_guess twice -> guesses == ("cheese", "pickles"); end(won=False) True, again False
async def test_idle_rounds_are_found_and_ended_ones_are_not(db): ...
async def test_bought_is_marked_once_and_only_after_a_loss(db): ...
async def test_craving_bond_counts_toward_the_casual_cap(db): ...
    # record CRAVING with bond 3 -> casual_bond_today == 3; cravings_today == 1
```

- [ ] **Step 2: Run them and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_schema.py tests/test_repos.py -q -p no:cacheprovider -k "room or won or craving"`
Expected: FAIL (missing columns, `CravingRepo` import error).

- [ ] **Step 3: Implement the storage above**

Follow `db/magazines.py` for the repo shape and `db/lunchbox.py` for passing a `date` param. `day` is `now.astimezone(UTC).date()`.

- [ ] **Step 4: Run the tests and see them pass**

Same command. Expected: PASS. Then run all of `tests/test_schema.py tests/test_repos.py`.

- [ ] **Step 5: Commit**

`git add db/schema.py db/players.py db/activity.py db/cravings.py app.py tests/test_schema.py tests/test_repos.py` and commit "Store rooms, won snacks and Craving rounds".

---

### Task 2: Rules and lines

**Files:**
- Modify: `wisp/rules.py`, `wisp/lines.py`
- Test: `tests/test_lines.py`, `tests/test_rules.py`

**Interfaces:**
- Produces in `wisp/rules.py`: `CRAVINGS_PER_DAY = 1`, `CRAVING_GUESSES = 3`, `CRAVING_TIMEOUT = timedelta(minutes=5)`, `ROOM_ARCHIVE_MINUTES: Final = 10080`, `ROOM_NAME_MAX: Final = 100`.
- Produces in `wisp/lines.py`:
  - Moments (all one-mood, via `_either_mood`): `CRAVING_START` fields `{"name"}`, `CRAVING_NOPE` fields `{"snack"}` (the wrong guess's name), `CRAVING_WON` fields `{"name", "snack"}`, `CRAVING_LOST` fields `{"snack"}`, `CRAVING_TIMED_OUT` fields `{"snack"}`, `SNACK_WON` fields `{"name", "snack"}` ("this is the one you won for me!").
  - `CRAVING_HINTS: Final[dict[str, tuple[str, str, str]]]` keyed by every `PAID_SNACKS` key, three hints each, clearer each time, never naming the snack.
  - `FIELDS` docstring gains `snack`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lines.py: add "snack" to SAMPLE_FIELDS ("Jelly Wave") and LONGEST_FIELDS
# ("Glitter Wave"); add the six new Moments to ONE_MOOD_MOMENTS. The existing
# parametrized tests then cover them. New tests:
def test_every_paid_snack_has_three_craving_hints():
    assert set(CRAVING_HINTS) == {snack.key for snack in PAID_SNACKS}
    assert all(len(hints) == 3 for hints in CRAVING_HINTS.values())

def test_no_hint_names_its_snack():
    for key, hints in CRAVING_HINTS.items():
        name = SNACK_BY_KEY[key].name.lower()
        assert not any(name in hint.lower() for hint in hints)

def test_hints_follow_the_line_rules(): ...
    # no Unicode emoji, no em/en dashes, no duplicates across all hints, one line each

# tests/test_rules.py
def test_craving_numbers():
    assert (CRAVINGS_PER_DAY, CRAVING_GUESSES) == (1, 3)
    assert CRAVING_TIMEOUT == timedelta(minutes=5)
    assert ROOM_ARCHIVE_MINUTES in (60, 1440, 4320, 10080)
```

- [ ] **Step 2: Run and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_lines.py tests/test_rules.py -q -p no:cacheprovider`
Expected: FAIL (names not defined).

- [ ] **Step 3: Write the rules and lines**

At least 4 lines per Moment (`test_every_moment_has_lines_for_every_mood`), in Wisp's voice (lowercase, playful, like `_KEEPSAKE_WON`). Hints are about taste, texture, color and sound ("something... wobbly", "it jiggles when the bass hits", "purple, and it wiggles"); `CRAVING_NOPE` lines react to the wrong snack ("{snack}? nah, not today").

- [ ] **Step 4: Run and see them pass**

Same command. Expected: PASS.

- [ ] **Step 5: Commit**

`git add wisp/rules.py wisp/lines.py tests/test_lines.py tests/test_rules.py`, commit "Add Craving rules, lines and hints".

---

### Task 3: Rooms

**Files:**
- Create: `cogs/rooms.py`
- Modify: `cogs/vault.py` (`wisp_board`), `cogs/players.py` (`NameModal.on_submit`), `cogs/discipline.py` (resetname), `cogs/studio.py` (`set_up` permission line), `app.py` (`room_games`), `README.md` (permissions list)
- Test: `tests/test_rooms.py` (new), `tests/test_vault.py`, `tests/test_studio.py`

**Interfaces:**
- Consumes: Task 1 `PlayerRepo.set_room`, `Player.room_thread_id`; Task 2 `ROOM_ARCHIVE_MINUTES`, `ROOM_NAME_MAX`.
- Produces in `cogs/rooms.py`:
  - `class RoomError(LookupError)`: the House is not set, cannot be seen or is not a text channel, or Discord refused the thread. Its message is member-safe.
  - `def room_name(name: str) -> str`: `f"♪ {name}'s room"`, clipped to `ROOM_NAME_MAX`.
  - `async def open_room(bot: "WispBot", guild: discord.Guild, member: discord.abc.User) -> discord.Thread`: returns the stored room when `bot.fetch_channel` finds a `discord.Thread` whose `parent_id` is the current House (unarchiving it with `edit(archived=False)` when archived); otherwise creates `house.create_thread(name=room_name(...), type=discord.ChannelType.private_thread, invitable=False, auto_archive_duration=ROOM_ARCHIVE_MINUTES)`, `await thread.add_user(member)`, posts the welcome (below), stores it with `set_room`. Raises `RoomError`. Uses a per-(guild, user) `asyncio.Lock` so two calls make one room.
  - `async def rename_room(bot, guild_id: int, user_id: int, name: str) -> None`: renames a stored, reachable room; failures are reported, never raised.
  - Welcome text (my call, house style): `"♪ This is your room with Wisp, <@id>.\n・Your games with him happen here.\n・Your Snack Pack is pinned here. Open it any time with /wisp snackpack."` sent with `AllowedMentions(users=[member])`.
- `bot.rhyme_duels` is renamed `bot.room_games: set[tuple[int, int]]` (one game per room); Task 4 and Task 6 use it.
- `cogs/studio.py`: `def missing_house_permissions(house: discord.TextChannel, me: discord.Member) -> list[str]` checks `create_private_threads`, `send_messages_in_threads`, `manage_threads`, `pin_messages`; `set_up` adds `・Wisp needs these in his House: ...` when any are missing.

- [ ] **Step 1: Write the failing tests** (`tests/test_rooms.py`, fakes modelled on `tests/test_studio.py` `FakeServer._create_thread`, with `add_user`, `parent_id`, `archived`)

```python
async def test_board_makes_a_private_room_on_first_join(...):
    # /wisp board -> house.create_thread called once with type=private_thread,
    # invitable=False, name "♪ Member1's room"; add_user(member); welcome posted; stored
async def test_the_room_is_reused(...):          # board twice -> one create_thread
async def test_an_old_member_gets_one_room_on_next_use(...):
    # activated player with no room; open_room twice concurrently -> one room
async def test_an_archived_room_is_reopened(...):  # edit(archived=False), no new room
async def test_a_deleted_room_is_made_again(...):  # fetch_channel raises NotFound -> new room
async def test_a_room_under_an_old_house_is_made_again(...):  # parent_id != house -> new room
async def test_no_house_raises_room_error(...)
async def test_board_still_works_when_the_room_fails(...):
    # create_thread raises Forbidden -> leaderboard still sent, "Error in making a room: Forbidden: ..." reported
async def test_learning_a_name_renames_the_room(...)   # NameModal submit -> thread.edit(name="♪ Kit's room")
def test_room_name_fits_discord():
    assert room_name("x" * 200) == clip("♪ " + "x" * 200 + "'s room", 100)
def test_missing_house_permissions_lists_what_is_missing(): ...
```

- [ ] **Step 2: Run and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rooms.py -q -p no:cacheprovider`
Expected: FAIL (`cogs.rooms` missing).

- [ ] **Step 3: Implement `cogs/rooms.py` and the hooks**

`wisp_board` calls `open_room` after activation on every run, catching `RoomError` and `discord.HTTPException` and reporting with context "making a room". `NameModal.on_submit` and the staff resetname call `rename_room`. Update `tests/test_vault.py` fakes so board tests still pass.

- [ ] **Step 4: Run and see them pass**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rooms.py tests/test_vault.py tests/test_players.py tests/test_discipline.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

Commit "Give each member a private room off Wisp's House".

---

### Task 4: The Rhyme Duel in the room, and the shared game reward

**Files:**
- Create: `cogs/games.py`
- Modify: `cogs/rhyme_duel.py`
- Test: `tests/test_rhyme_duel.py`, `tests/test_games.py` (new)

**Interfaces:**
- Consumes: Task 3 `open_room`, `RoomError`, `bot.room_games`.
- Produces in `cogs/games.py`:
  - `@dataclass(frozen=True) class Reward(bond: int, wellbeing: str, coins: str)` (`wellbeing` is the `meter_receipt` text, `coins` the `+1 WC` text).
  - `async def reward_game(bot, guild_id: int, user_id: int, life: Life, life_id: int, kind: InteractionKind, now: datetime) -> Reward`: the body of today's `_count_play` (capped bond, `record_interaction(kind, ...)`, `PLAY_POINTS`, `GROWTH_PER_PLAY`, `WELLBEING_PER_PLAY`, save). Call under `bot.guild_lock`.
  - `ROOM_BUSY: Final = "♪ You already have a game going in your room. Finish that one first."`
- `_host` opens the member's room with `open_room` instead of a public thread; the duel never archives or locks it; `start_duel` uses `bot.room_games` and `ROOM_BUSY`. `_count_play` becomes a call to `reward_game` with `InteractionKind.PLAY`; the duel receipt text is unchanged.

- [ ] **Step 1: Update and add tests**

```python
# tests/test_rhyme_duel.py: FakeServer gains a room thread; replace public-thread
# assertions:
async def test_duel_scores_perfect_and_slant(...):
    ...
    server.house.create_thread.assert_awaited_once()      # the room, made once
    assert server.house.create_thread.await_args.kwargs["type"] is discord.ChannelType.private_thread
    server.thread.edit.assert_not_awaited()               # never archived or locked
async def test_a_second_duel_uses_the_same_room(...)      # replaces the create_thread count in test_one_duel_per_player
async def test_missing_house_fails_and_frees_the_player(...)  # now via RoomError
# delete test_a_thread_that_cannot_close_still_finishes_the_duel (nothing closes now)

# tests/test_games.py
async def test_reward_game_records_the_kind_and_caps_the_bond(db, ...):
    # with casual bond already at DAILY_CASUAL_BOND_CAP: Reward.bond == 0, Wellbeing still +WELLBEING_PER_PLAY
```

- [ ] **Step 2: Run and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhyme_duel.py tests/test_games.py -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Implement**

Remove `NoHouseError` and the duel's `_open_thread`; `RhymeDuelButton` catches `RoomError` in place of `NoHouseError`.

- [ ] **Step 4: Run and see them pass**

Same command. Expected: PASS.

- [ ] **Step 5: Commit**

Commit "Play Rhyme Duels in the member's room".

---

### Task 5: Snack Pack in the room, won snacks, bought-after-loss note

**Files:**
- Modify: `cogs/snacks.py`
- Test: `tests/test_snacks.py`

**Interfaces:**
- Consumes: Task 1 `take_won_snack`, `set_room_pack`, `CravingRepo.today`/`mark_bought`, `bot.notes`; Task 2 `Moment.SNACK_WON`; Task 3 `open_room`, `RoomError`.
- Produces:
  - `async def show_pack_in_room(bot, guild: discord.Guild, member: discord.abc.User) -> None`: opens the room, deletes the stored pack message (ignoring `NotFound`), sends a fresh one with `send_framed(thread.send, _PACK_HEADER, await _snack_pack_text(...), [[ShopButton()]], allowed_mentions=_NO_PING)`, pins it, stores its id with `set_room_pack`. Failures (`RoomError`, `discord.HTTPException`) are reported with context "showing the Snack Pack in a room", never raised; a failed pin still keeps the post.
  - `_open_snack_pack` calls `show_pack_in_room` after the private reply.
  - `_Meal` gains `won: bool`. `_eat` tries `take_won_snack` before `take_snack` for paid snacks.
  - `_reaction(snack, stance, favorite, *, won: bool = False)`: `won` returns `(Moment.SNACK_WON, snack.gif_name)` first. `_feed` passes `snack=snack.name` to `say_in_house` when the moment is `SNACK_WON`.
  - `buy_snack`, after `add_snack`: when today's round for this member is ended, lost, of this snack, and `mark_bought` returns True, add the note `f"they lost my Craving but bought me the {snack.name} anyway"`.

- [ ] **Step 1: Write the failing tests**

```python
async def test_opening_the_snack_pack_also_pins_it_in_the_room(...):
    # private reply as before AND room.send with the same layout text; pin awaited; id stored
async def test_the_room_pack_is_reposted_not_duplicated(...):
    # open twice -> old message deleted, one pinned pack left
async def test_a_room_that_fails_still_shows_the_private_pack(...)
async def test_a_won_snack_is_eaten_first_then_it_is_ordinary(...):
    # inventory jellywave x2 (1 won): first feed -> pick(Moment.SNACK_WON, mood, name="Member1", snack="Jelly Wave"); second -> Moment.SNACK
async def test_buying_the_craved_snack_after_losing_leaves_one_note(...):
    # lost round today for jellywave; buy jellywave twice -> exactly one note
async def test_buying_after_a_win_or_another_day_leaves_no_note(...)
```

- [ ] **Step 2: Run and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_snacks.py -q -p no:cacheprovider -k "room or won or craving or bought"`
Expected: FAIL.

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run all of `tests/test_snacks.py`** (background; it is long). Expected: PASS.

- [ ] **Step 5: Commit**

Commit "Pin the Snack Pack in rooms and remember won snacks".

---

### Task 6: Wisp's Craving

**Files:**
- Create: `wisp/craving.py`, `cogs/craving.py`
- Modify: `cogs/rhyme_duel.py` (Play menu gains the Craving button), `cogs/life_loop.py` (timeout sweep each tick), `app.py` (load `cogs.craving`)
- Test: `tests/test_craving.py` (new), `tests/test_rhyme_duel.py` (Play menu children)

**Interfaces:**
- Consumes: Tasks 1-5 (`CravingRepo`, `InteractionKind.CRAVING`, Craving Moments and `CRAVING_HINTS`, `open_room`, `bot.room_games`, `reward_game`, `bot.notes`, `add_snack(won=True)`).
- Produces in `wisp/craving.py` (pure):
  - `def pick_craving(rng: random.Random) -> Snack` from `PAID_SNACKS`.
  - `def hint_for(round_snack: str, wrong: int) -> str`: `CRAVING_HINTS[key][min(wrong, 2)]`.
  - `def snacks_left(guesses: tuple[str, ...]) -> tuple[Snack, ...]`: `PAID_SNACKS` minus the wrong guesses, in menu order.
  - `class Verdict(Enum): RIGHT, WRONG, OUT`; `def judge(snack: str, guesses: tuple[str, ...], guess: str) -> Verdict` (`OUT` when the wrong guesses reach `CRAVING_GUESSES`).
- Produces in `cogs/craving.py`:
  - `@play.command(name="craving", description="Guess the snack Wisp is craving.") async def play_craving(...)`.
  - `CravingButton` (`DynamicItem`, custom id `wisp:play:craving`) added to `_offer_games`.
  - `GuessMenu` (`DynamicItem[discord.ui.Select]`, template `wisp:craving:(?P<user>\d+)`): only that user may pick (others get a private "♪ This is someone else's Craving."); each pick reloads today's round from `bot.cravings`, so it works after a restart.
  - Refusals before a round (same order as `_host`, plus `member_blocker`): banned, not alive, frozen, napping, cannot feed him, already played today ("♪ You've already had today's Craving. Next one {daily_reset(now)}."), room busy (`ROOM_BUSY`), room unavailable (`RoomError`).
  - Starting with an open round today re-posts its current hint and menu instead of starting a new one.
  - Ending (`win`, `lose`, `timeout`): `bot.cravings.end`; on a win `add_snack(..., won=True)` then `show_pack_in_room`; `reward_game(..., InteractionKind.CRAVING)` when Wisp is alive and not frozen at the end; a member note: win `f"I was craving a {name} and they guessed it"`, loss/timeout `f"I was craving a {name} and they couldn't guess it"`; receipt in the room naming Wellbeing, bond (or "your bond with him is full for today") and coins.
  - `async def end_idle_cravings(bot, now: datetime) -> None`: ends every open round with `last_at < now - CRAVING_TIMEOUT` as a timeout and posts `CRAVING_TIMED_OUT` in its room; called from the life loop tick; failures reported once.

- [ ] **Step 1: Write the failing tests**

```python
# wisp/craving.py
def test_judge_right_wrong_and_out():
    assert judge("jellywave", (), "jellywave") is Verdict.RIGHT
    assert judge("jellywave", (), "cheese") is Verdict.WRONG
    assert judge("jellywave", ("cheese", "pickles"), "spicywave") is Verdict.OUT
def test_hints_get_clearer_with_each_wrong_guess(): ...
def test_never_craves_the_free_snack(): ...   # 200 seeded picks, none cost 0

# cogs/craving.py
async def test_a_round_starts_in_the_room_with_a_hint_and_a_menu(...)
async def test_a_right_guess_wins_the_snack_free_and_marked_won(...)
async def test_three_wrong_guesses_lose_and_name_the_snack(...)
async def test_a_wrong_guess_leaves_the_menu_and_gives_the_next_hint(...)
async def test_one_round_a_day(...)
async def test_starting_again_resumes_the_same_round(...)
async def test_only_the_rooms_owner_can_guess(...)
async def test_an_idle_round_times_out_as_a_loss(...)       # end_idle_cravings
async def test_a_late_press_after_the_timeout_counts_as_a_loss(...)
async def test_every_finished_round_leaves_a_note_and_a_receipt(...)
async def test_refused_while_frozen_napping_banned_or_unable_to_feed(...)   # parametrized
async def test_a_room_game_already_running_is_refused(...)
# tests/test_rhyme_duel.py
async def test_play_opens_a_private_menu_of_the_games(...):
    duel, craving = view.children   # was a single child
```

- [ ] **Step 2: Run and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_craving.py -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Implement**

- [ ] **Step 4: Run** `tests/test_craving.py tests/test_rhyme_duel.py tests/test_life_loop.py` (background). Expected: PASS.

- [ ] **Step 5: Commit**

Commit "Add Wisp's Craving, the daily snack guess".

---

### Task 7: Docs, full suite, ship

**Files:**
- Modify: `README.md` (Rooms and Wisp's Craving sections, commands list, permissions list gains Create Private Threads), `CHANGELOG.md` (2026-11-23 entry), `DOCS/wisp_faq.html` (a Craving and Rooms paragraph; picture re-render is a follow-up for Myra)

- [ ] **Step 1: Write the docs.**
- [ ] **Step 2: Quality tools** on every touched file: black, isort, flake8, mypy --strict. Expected: clean.
- [ ] **Step 3: Full suite in the background** (about 3 hours): `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider`. Expected: all pass; fix and re-run any failing file.
- [ ] **Step 4: Commit by explicit paths, push to main** (auto-deploys), post the changelog note.
