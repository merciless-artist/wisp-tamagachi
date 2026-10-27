# Status Menu and Three Meters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Wisp three meters (Full, Happy, Care), points for daily chats and duels, a once-per-life childhood cold, a new divider, and Myra's status menu.

**Architecture:** Pure rules stay in `wisp/` (`life.py`, `bond.py`, `card.py`, `lines.py`, `voice.py`, `rules.py`); storage in `db/` with additive migrations only; Discord wiring in `cogs/`. Each task leaves the bot shippable.

**Tech Stack:** Python 3.13, discord.py 2.6.4, aiomysql, MariaDB, pytest against real `wisptest_` tables.

**Spec:** `DOCS/specs/2026-10-26-status-menu-and-three-meters-design.md` (read it first; it is the source of every value below). Myra's exact card text: `DOCS/specs/status_menu_template.txt`.

## Global Constraints

- Live database: columns and indexes are only added, through both `_DEFINITIONS` and `_ADDED_COLUMNS` (indexes `_ADDED_INDEXES`) in `db/schema.py`. Never rename or drop a live column. The `lives.care` column keeps storing Full.
- Every tunable number lives only in `wisp/rules.py`.
- Users by Discord ID. All times UTC; a day is a UTC calendar day.
- Quality bar from `CLAUDE.md`: no narrating comments, no duplicate helpers, no blanket `except Exception`, fully typed. `black`, `isort`, `flake8`, `mypy --strict` pass, run with `PYTHONUTF8=1`.
- Tests use the real database; never mock it. Run only the affected test files (the full suite takes ~45 min). Never two pytest processes at once.
- Section headers are `# ---` / `# Name` / `# ---`.
- AI replies and canned lines stay Unicode-emoji free. Emoji are allowed only in the card and the divider.
- Wisp is live. Do not start, stop or touch his process. Commit; do not push.
- Messages stay under 2,000 counted by `wisp.text.text_length`.

## Review Focus

1. **The live life after migration.** A living Baby/Child/Teen saved before this work loads with `care` 50, no cold scheduled, and gets one scheduled on its next tick; a live Adult or older never catches a cold. (Task 5 test `test_a_legacy_child_gets_a_cold_scheduled`, `test_an_adult_never_catches_a_cold`.)
2. **Wisp offline for days.** On the first tick back, a due cold starts before any growth check, so no life reaches Adult without its cold; the cold only counts down by credited time. (Task 5 test `test_a_due_cold_starts_before_growth_in_the_same_tick`.)
3. **Fullest card.** 100% bars, 99 feeders, 999 tracks, OLD FOGEY, sick line: still ≤ 2,000 by `text_length`. (Task 6 test `test_the_fullest_card_fits_one_message`.)
4. **Poke then mention the same day.** Only the first earns the credit and the point; a second member the same day still earns theirs. (Task 3 test `test_poke_then_mention_credits_once`.)
5. **Every moment in every mood.** Picking any moment with `Mood.LONELY` never raises; a moment without lonely lines uses its happy lines. (Task 4 test `test_every_moment_has_lines_for_every_mood`.)

---

### Task 1: Rename the food meter to Full

**Files:**
- Modify: `wisp/rules.py`, `wisp/life.py`, `wisp/card.py`, `db/lives.py`, `cogs/snacks.py`, `cogs/feeding.py` and every other file `grep -rn "\.care\b\|CARE_\|HATCHED_CARE" --include=*.py cogs wisp db` finds
- Test: every test file that grep finds in `tests/`

**Interfaces:**
- Produces: `Life.full: float` (was `Life.care`); `Snack.full: int` (was `Snack.care`); rules `FULL_MAX`, `FULL_DRAIN_PER_DAY`, `OLD_FOGEY_FULL_DRAIN_PER_DAY`, `HATCHED_FULL` (were `CARE_MAX`, `CARE_DRAIN_PER_DAY`, `OLD_FOGEY_CARE_DRAIN_PER_DAY`, `HATCHED_CARE`). `HANGRY_BELOW`, `FADING_BELOW` keep their names. `db/lives.py` maps column `care` ↔ `Life.full` with a one-line note at the mapping.

- [ ] **Step 1:** Rename across code and tests. Member-facing text that means food says "full": the snack confirmation `♪ Wisp ate your {name} ・ full +{n}`, the Vault dropdown descriptions `{points} ・ full +{n}`, the Snack Pack select descriptions, and the current card row label `full`.
- [ ] **Step 2:** Add `test_the_food_meter_is_stored_in_the_care_column` to `tests/test_repos.py`: save a life with `full=42.5`, read the raw `care` column back with SQL, assert `42.5`; load it and assert `life.full == 42.5`.
- [ ] **Step 3:** Run `tests/test_life.py tests/test_repos.py tests/test_snacks.py tests/test_feeding.py tests/test_card.py` and the other renamed files; all pass. Run the quality tools.
- [ ] **Step 4:** Commit `refactor: call the food meter Full`.

### Task 2: The new divider

**Files:**
- Modify: `wisp/text.py` (`SEPARATOR`), `CLAUDE.md` (bot text rules), every test that hardcodes the old divider (`grep -rln "・♪ ────────・──────── ♪・" tests`)

**Interfaces:**
- Produces: `SEPARATOR == "❱❱━━━━━━━━━━━━━━━━━━━━━━━━━━❰❰"` (copy from the spec).

- [ ] **Step 1:** Tests import or redefine the new value; add `test_separator_is_myras_divider` in `tests/test_text.py` asserting the exact string.
- [ ] **Step 2:** Change the constant. In `CLAUDE.md`: separator is the new divider; Unicode emoji are allowed in designed text (status card, divider); AI replies and canned lines stay emoji free.
- [ ] **Step 3:** Run the affected test files; pass. Commit `feat: Myra's new divider`.

### Task 3: Daily chat credit, Happy from chats, points for duels

**Files:**
- Modify: `db/activity.py`, `wisp/rules.py`, `cogs/players.py`, `cogs/conversation.py`, `cogs/rhyme_duel.py`, `cogs/life_loop.py`
- Test: `tests/test_repos.py`, `tests/test_conversation.py`, `tests/test_rhyme_duel.py`, `tests/test_life_loop.py`, `tests/test_players.py`

**Interfaces:**
- Produces in `db/activity.py`: `InteractionKind.CHAT = "chat"`;
  `async def chatted_today(self, guild_id: int, user_id: int, now: datetime) -> bool`;
  `async def chatters_since(self, guild_id: int, since: datetime) -> int` (CHAT rows only);
  `async def feeders_since(self, guild_id: int, since: datetime) -> int` (FEED, SNACK, FREE_SNACK);
  `async def tracks_today(self, guild_id: int, now: datetime) -> tuple[int, int]` (ViiBR, Suno counts from `feeds` this UTC day by the `viibr:` / `suno:` prefix of `track_key`).
  `caretakers` and `latest_interactor` ignore CHAT rows. `people_since` and `distinct_days` keep counting every kind.
- Produces in `cogs/players.py`: `async def credit_chat(bot: "WispBot", guild_id: int, member: discord.User | discord.Member, life: Life, now: datetime) -> bool` — when the member is not banned, passes `can_feed`, `life.id` is set and they have no CHAT row today: record a CHAT interaction (bond 0, meal points 0), `add_points(CHAT_POINTS)`, return True; otherwise False.
- Rules: `CHAT_POINTS = 1`, `PLAY_POINTS = 1`.

- [ ] **Step 1: Failing tests.**
  - `test_chat_credit_is_once_a_day` (repos/players): first call True, balance +1; second call same day False, balance unchanged; next UTC day True.
  - `test_only_feeders_get_chat_credit`: a member without the qualifying role → False, no row, no point; banned → False.
  - `test_poke_then_mention_credits_once` (conversation): poke then mention (past `TALK_COOLDOWN`) → one CHAT row, +1 point; a second member's poke the same day → their own row.
  - `test_happy_counts_only_chatters` (life_loop or players): two feeders and one chatter in 24 h → happiness `happiness(1)`.
  - `test_chat_rows_do_not_count_as_caretakers_or_last_interactor`.
  - `test_feeders_since_counts_only_feeding`, `test_tracks_today_splits_viibr_and_suno`.
  - `test_a_counted_duel_pays_one_point` (rhyme_duel): a duel that records PLAY → balance +1; a member past `PLAYS_PER_DAY` or without `can_feed` → no point.
- [ ] **Step 2:** Run them; they fail.
- [ ] **Step 3:** Implement the repo methods; `credit_chat`; call it in `Conversation._answer` and `_poke` right after `take_turn` succeeds (credit failures are reported like other errors and never block the reply); in `rhyme_duel` add `add_points(PLAY_POINTS)` inside the existing PLAY block; compute happiness from `chatters_since(guild_id, now - HAPPINESS_WINDOW)` in both `cogs/life_loop.py` and `cogs/players.py`.
- [ ] **Step 4:** Run the five test files; pass. Quality tools. Commit `feat: daily chat credit and points for duels`.

### Task 4: The Care meter and the lonely mood

**Files:**
- Modify: `wisp/rules.py`, `wisp/life.py`, `db/schema.py`, `db/lives.py`, `wisp/lines.py`, `wisp/voice.py`, `cogs/announce.py`, `cogs/rhyme_duel.py`, `cogs/gifts.py`, `cogs/feeding.py` (`_MOOD_EMOJIS`), `cogs/conversation.py` (pass mood unchanged)
- Commit with it: `ASSETS/moments/cry_baby.gif`, `grumpy_baby.png`, `grumpy.gif`, `cry_teen.gif`
- Test: `tests/test_life.py`, `tests/test_lines.py`, `tests/test_voice.py`, `tests/test_announce.py`, `tests/test_gifts.py`, `tests/test_rhyme_duel.py`, `tests/test_repos.py`, `tests/test_schema.py`

**Interfaces:**
- Rules: `CARE_MAX = 100.0`, `CARE_START = 50.0`, `CARE_DRAIN_PER_DAY = 10.0`, `CARE_PER_PLAY = 10`, `CARE_PER_GIFT = 8`, `LONELY_BELOW = 30.0`, `LONELY_PICTURES: Final[dict[Stage, tuple[str, ...]]]` = Baby `("cry_baby.gif", "grumpy_baby.png")`, Child `("grumpy.gif",)`, Teen, Adult, Rockstar, Old Fogey `("cry_teen.gif",)`.
- `Life.care: float = CARE_START`, `Life.lonely_warned: bool = False`; columns `fondness DOUBLE NOT NULL DEFAULT 50`, `lonely_warned BOOL NOT NULL DEFAULT 0` (note the mapping beside Task 1's).
- `def add_care(life: Life, points: float) -> None` in `wisp/life.py` (alive only, capped at `CARE_MAX`, clears `lonely_warned` once back at or above `LONELY_BELOW`).
- `Mood.LONELY`; `mood(life)`: HANGRY when Full < `HANGRY_BELOW`, else LONELY when alive and Care < `LONELY_BELOW`, else HAPPY.
- `EventKind.LONELY`, `Moment.LONELY` (fields none), `Event(EventKind.LONELY, stage=life.stage)`.
- `LinePicker.pick` falls back to `(moment, Mood.HAPPY)` when `(moment, Mood.LONELY)` has no lines.

- [ ] **Step 1: Failing tests.**
  - `test_care_starts_at_half_when_he_hatches`, `test_care_drains_ten_a_day`, `test_add_care_caps_at_max_and_only_while_alive`.
  - `test_mood_hangry_beats_lonely`, `test_mood_lonely_below_the_line`.
  - `test_lonely_warns_once_per_drop`: dropping below 30 gives one LONELY event; staying low gives none; `add_care` back above 30 and dropping again gives another.
  - `test_every_moment_has_lines_for_every_mood` (lines): `pick(moment, mood, **fields)` works for every `Moment` × `Mood`; `Moment.LONELY` has its own lines (about 8, grumpy or lonely, never mean, emoji free).
  - `test_lonely_mood_reaches_the_prompt` (voice): `build_prompt(..., mood=Mood.LONELY, ...)` system text tells him he feels lonely and grumpy.
  - `test_lonely_post_has_a_picture_for_his_stage` (announce): Baby → one of the two Baby files; Child → `grumpy.gif`; Teen → `cry_teen.gif`.
  - `test_a_counted_duel_adds_care`, `test_every_gift_attempt_adds_care` (kept, passed and FULL all +`CARE_PER_GIFT`; a refused attempt that spent nothing adds nothing).
  - `test_care_round_trips_through_the_fondness_column` (repos); schema test that the new columns are in both lists.
- [ ] **Step 2:** Run; fail.
- [ ] **Step 3:** Implement. Drain Care in `_tick_alive`; emit LONELY from `_warnings`. `add_care` in the duel PLAY block and in `give_gift` after recording the attempt (save the life). The lonely picture is chosen at random from the stage's files that exist; text only if none.
- [ ] **Step 4:** Run the listed test files; pass. Quality tools. Commit `feat: Care meter and lonely mood`.

### Task 5: The childhood cold

**Files:**
- Modify: `wisp/rules.py`, `wisp/life.py`, `wisp/bond.py`, `db/schema.py`, `db/lives.py`, `wisp/lines.py`, `wisp/voice.py`, `cogs/life_loop.py`, `cogs/announce.py`, `cogs/pictures.py`, `cogs/feeding.py`, `cogs/snacks.py`, `cogs/conversation.py`
- Commit with it: `ASSETS/moments/sick_baby.png`, `sick_child.png`, `sick_teen.png`
- Test: `tests/test_life.py`, `tests/test_bond.py`, `tests/test_life_loop.py`, `tests/test_announce.py`, `tests/test_feeding.py`, `tests/test_snacks.py`, `tests/test_voice.py`, `tests/test_repos.py`, `tests/test_schema.py`

**Interfaces:**
- Rules: `SICK_FOR = timedelta(hours=48)`, `SICK_DRAIN_MULTIPLIER = 1.5`, `SICK_EXTRA_MEAL_CAP = 15`, `COLD_EARLIEST = timedelta(days=1)`, `COLD_LATEST = timedelta(days=12)` (after hatching; Adult needs 14 days, so the cold always ends first), `SICK_PICTURES: Final[dict[Stage, str]]` Baby `sick_baby.png`, Child `sick_child.png`, Teen `sick_teen.png`.
- `Life.cold_due_at: datetime | None = None`, `Life.cold_left: float = 0.0` (credited seconds of cold remaining), `Life.had_cold: bool = False`; columns `cold_due_at DATETIME NULL`, `cold_left DOUBLE NOT NULL DEFAULT 0`, `had_cold BOOL NOT NULL DEFAULT 0`.
- `def schedule_cold(life: Life, rng: random.Random) -> None` — alive, Baby/Child/Teen, not `had_cold`, no `cold_due_at`: set `cold_due_at = hatched_at + uniform(COLD_EARLIEST, COLD_LATEST)`. Called by `LifeLoop._advance` with `self.rng` before `tick`.
- `def is_sick(life: Life) -> bool` (`cold_left > 0`).
- `def daily_meal_cap(life: Life | None) -> int` in `wisp/bond.py`: `DAILY_MEAL_CAP + SICK_EXTRA_MEAL_CAP` while sick, else `DAILY_MEAL_CAP`; `meal_grant(fed_today: int, points: int, cap: int) -> int`.
- `EventKind.SICK` (carries `stage`), `EventKind.RECOVERED`; `Moment.SICK`, `Moment.RECOVERED` (fields none), about 8 lines each per mood, emoji free.
- `build_prompt(..., sick: bool = False)`: while sick his voice is sniffly and sneezy.

- [ ] **Step 1: Failing tests.**
  - `test_schedule_cold_lands_between_day_one_and_twelve` (stub rng at both ends).
  - `test_a_legacy_child_gets_a_cold_scheduled`; `test_an_adult_never_catches_a_cold`; `test_schedule_cold_never_twice`.
  - `test_the_cold_starts_when_due_and_lasts_48_credited_hours`: SICK event with his stage, `is_sick` true, then RECOVERED after 48 h of ticks and never again.
  - `test_a_due_cold_starts_before_growth_in_the_same_tick` (Review Focus 2).
  - `test_frozen_time_does_not_count_down_the_cold`.
  - `test_sick_drains_full_one_and_a_half_times_as_fast`.
  - `test_he_cannot_die_while_sick`: Full stays ≥ 1 through the whole cold with no feeding; HUNGRY and FADING still fire; after RECOVERED normal death applies.
  - `test_the_meal_cap_doubles_while_sick` (bond, feeding, snacks): a member at 15 meal points today can still feed while sick, up to 30.
  - `test_sick_post_shows_his_stage_picture` (announce); `test_the_card_picture_is_the_sick_one_while_sick` (pictures: `life_image`).
  - `test_sick_reaches_the_prompt` (voice).
  - Repos and schema round-trip for the three columns.
- [ ] **Step 2:** Run; fail.
- [ ] **Step 3:** Implement. In `_tick_alive` the order is: start a due cold, drain (×1.5 while sick, floor at 1 while sick), death check, farewell, count down the cold by `elapsed`, warnings, growth.
- [ ] **Step 4:** Run the listed files; pass. Quality tools. Commit `feat: the childhood cold`.

### Task 6: Myra's status menu

**Files:**
- Modify: `wisp/card.py`, `cogs/players.py` (`status_text`), `cogs/life_loop.py` (`_update_card`), `tests/test_card.py`, `tests/test_players.py`

**Interfaces:**
- Consumes: Tasks 1–5 (`Life.full`, `Life.care`, `is_sick`, `Life.cold_left`, `feeders_since`, `tracks_today`, happiness from chatters).
- Produces in `wisp/card.py`:
  ```python
  @dataclass(frozen=True)
  class CardFacts:
      happiness: int
      fed_today: int
      viibr_tracks: int
      suno_tracks: int
      wisp_id: int
      house_id: int | None
  def render_status(life: Life, now: datetime, facts: CardFacts) -> str
  ```
  `status_text(bot, guild_id, life, now, happy)` keeps its signature and builds `CardFacts` (fed today from `feeders_since` since UTC midnight; tracks from `tracks_today`; `bot.user.id`; settings `house_channel_id`).

- [ ] **Step 1: Failing tests** in `tests/test_card.py`, comparing against `DOCS/specs/status_menu_template.txt` read in the test:
  - `test_a_living_baby_matches_myras_template`: with Full 50, Happy 90, Care 60, fed 3, tracks 6/2, day 1, BABY, the card equals the template line for line except the agreed changes (bars `・Full` 🟦 / `・Happy` 🟪 / `・Care` 🟥 in that order, `/wisp snackpack`). Build the expected text from the template file with those substitutions, so spaces and symbols are Myra's.
  - `test_bars_are_one_square_per_ten_percent` (0 → no squares and `│0%`, 45 → 5, 100 → 10).
  - `test_fed_by_is_two_digits_and_singular_for_one` (`03 people`, `01 person`).
  - `test_tracks_line_is_singular_for_one`.
  - `test_stage_is_in_bold_letters` for every alive stage (𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘 etc.).
  - `test_egg_and_hatching_cards_use_the_frame` (no DAY line, `・Warmth` 🟧 and `・Hatching` 🟨, or `・Emerging` 🟨; stage 𝐄𝐆𝐆 / 𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆; "Poke the egg").
  - `test_a_sick_card_says_hours_left` (`・he has a cold・{ceil(cold_left/3600)} h left` under the DAY line).
  - `test_no_house_channel_says_his_house` (mention line uses "in his House" when `house_id` is None).
  - `test_the_fullest_card_fits_one_message` (Review Focus 3).
- [ ] **Step 2:** Run; fail.
- [ ] **Step 3:** Implement `render_status` and `CardFacts`; wire `status_text`.
- [ ] **Step 4:** Run `tests/test_card.py tests/test_players.py tests/test_life_loop.py`; pass. Quality tools. Commit `feat: Myra's status menu`.

### Task 7: Words members read

**Files:**
- Modify: `cogs/faq.py`, `cogs/studio.py` (How Wisp Works / FAQ text), `README.md`, `DOCS/BuildRulings.md`, `DOCS/wisp_tamagotchi.html`, `CHANGELOG.md`
- Test: `tests/test_studio.py` and any test asserting that text

- [ ] **Step 1:** Rewrite every explanation of the meters to the three meters (Full: tracks and snacks; Happy: your first poke or chat of the day, which also earns 1 point; Care: rhyme duels and gifts), points for duels, and the childhood cold. Add the rulings from the spec to `BuildRulings.md`. One CHANGELOG entry for the whole feature.
- [ ] **Step 2:** In the task report, list every `ASSETS/faq/` picture whose text mentions Care, Happy, feeding or points, with the sentence that must change, so the controller can re-render them from `wisp_faq.html`.
- [ ] **Step 3:** Run the affected test files; pass. Quality tools. Commit `docs: three meters and the cold`.
