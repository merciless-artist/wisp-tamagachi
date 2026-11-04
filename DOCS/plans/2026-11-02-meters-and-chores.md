# Meters and Chores Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-wire Wisp's three meters as Health, Wellbeing and Mood that move only in steps, and add three first-press chores (cleanup, scold, lights off), a cold caught from messes and medicine to cure it.

**Architecture:** Pure rules stay in `wisp/`: meters and both illnesses in `wisp/life.py`, the chores in a new `wisp/chores.py` (it imports `wisp.life`, never the other way). Storage in `db/` with additive columns only. Discord wiring in `cogs/`: a new `cogs/chores.py` posts chores, owns the persistent chore button and edits posts when a chore ends; the life loop ticks both modules and hands chore events to it. Every timer runs on counted time (`credited_gap`), stored as seconds left.

**Tech Stack:** Python 3.13, discord.py 2.6.4, aiomysql + MariaDB, pytest against real `wisptest_` tables.

**Spec:** `DOCS/specs/2026-11-02-meters-and-chores-design.md` (read it first; every value below comes from it). It replaces the meter section of `DOCS/specs/2026-10-26-status-menu-and-three-meters-design.md`; that spec's card, divider, Monster Pox and storage rules still stand.

## Global Constraints

- Live database with real data: columns are only added, through both `_DEFINITIONS` and `_ADDED_COLUMNS` in `db/schema.py`, and the startup schema check must pass on the live tables. Never rename or drop a live column. `lives.care` keeps storing the food meter (now Health), `lives.fondness` the old Care (now Wellbeing), `lives.high_happiness_since` the Rockstar streak.
- Every tunable number lives only in `wisp/rules.py`.
- Discord IDs identify users everywhere; names are display only. All times are UTC; a day is a UTC calendar day.
- Quality bar from `CLAUDE.md`: no narrating comments, no duplicate helpers, no dead code or TODOs, no blanket `except Exception`, fully typed. Section headers are `# ---` / `# Name` / `# ---`.
- Bot text: no embeds, no DMs, bullet `・`, flair `♪`. Canned lines and AI replies stay Unicode-emoji free; app emojis only by name through `bot.emoji(...)`. Errors post as plain text `Error in <context>: <Type>: <message>` via `bot.report_error` / `report_failure`. Messages under 2,000 counted with `wisp.text.text_length`. House-style frame pieces only from `wisp/text.py` (`heading`, `sub`, `item`, `SECTION_BREAK`, `wrapped`, ...), never retyped.
- Chore and medicine posts never ping anyone (`post_in_house` with `ping=None`).
- Naming: Monster Pox code keeps its names (`cold_*`, `is_sick`, `schedule_cold`, `SICK_*`, `COLD_*`, `EventKind.SICK`, `Moment.SICK`). The new cold is `sniffles` in code (`SNIFFLES_FOR`, `has_sniffles`, ...) and "a cold" in member text.
- Tests use the real database, never mocked; Discord objects are fakes as in the existing test files. Run only the affected test files (the whole suite takes about 45 minutes). Never two pytest processes at once.
- Test command: `PYTHONUTF8=1 .venv/Scripts/python.exe -m pytest <files> -q`.
- Quality tools after every task, all with `PYTHONUTF8=1`: `.venv/Scripts/python.exe -m black --check .`, `-m isort --check-only .`, `-m flake8`, `-m mypy --strict wisp db cogs app.py config.py`.
- Since this plan was written, commit fea4be9 added growth by caretakers and people (`STAGE_RULES`, `tick(..., people=)`) and the staff command `!wisp test_lifestage` with `jump_to`, `ready_to_pass_on` and `starve` in `wisp/life.py` (`starve` sets the food meter, so Task 1 renames it to `health`). Keep all of it working. The full test suite takes about 1 h 50 min; never run it whole inside a task.
- Wisp is live on fps.ms; a push to `main` deploys him. Never start, stop or touch a bot process. Tasks commit locally on `main`; only the controller pushes (Task 13).
- The mess changes with his stage (spec "Messes", Myra 2026-11-03): poop only for Baby and Child; Teen, Adult, Rockstar and Old Fogey each have their own mess, button label and (later) picture from `MESSES`. Mess lines and the AI prompt name the stage's mess instead of saying poop. Add `test_a_teen_mess_is_a_zit_breakout_with_a_face_wash_button` to Task 8.
- `wisp/voice.py` changed after this plan was written (commits b90993d, ac6b398, 8c772d3: more personality in `_WHO_YOU_ARE`, `wisp_child_dance` for the Child, and a separate "you love to dance" reaction rule with "At most one face per message"). Build on that file as it is now and keep those changes.
- Stage files by explicit path. Never `git add -A` or `.`: `CLAUDE.md`, `ASSETS/mags/wisp.zip`, `wisp/1.png` and `DOCS/wisp_prompts/` are not part of this work.

## Decisions this plan makes (the spec left them to the builder)

1. **Code names follow member words.** `Life.full` becomes `Life.health`, `Life.care` becomes `Life.wellbeing`, the new meter is `Life.mood_meter` (`mood` is taken by the voice-mood function and enum), `Life.high_happiness_since` becomes `Life.high_mood_since`, `Snack.full` becomes `Snack.meal` (it is only meal points against the cap now). Column names never change; `db/lives.py` keeps the one mapping note.
2. **Empty stretches are counters, not timestamps.** Each meter stores `*_stretch`: counted seconds since its last credited action or penalty. Each tick adds `credited_gap`; at 6 h the penalty applies and 6 h is subtracted. A credited action sets it to 0.
3. **What ends which stretch** (spec: "a track that fed him, or a chat, snack, game or poke that earned a meter plus"): a fed track ends Health's; a credited chat or a snack ends Wellbeing's; a counted duel or a credited poke ends Mood's. Gifts and cleanups add Wellbeing but end no stretch; chore penalties end none.
4. **Chat and poke credits** are rows in the existing `interactions` table: `CHAT` for a credited mention (up to 3 a day), new `POKE = "poke"` (fits `VARCHAR(8)`) for a credited poke (up to 3 a day). `CHAT_POINTS` stays as today: paid once a day, on the member's first credited chat or poke. Credits are recorded for egg pokes too (as today); the meter plus only lands while he is alive.
5. **Chore timers are seconds left on the life** (`mess_in`, `mess_left`, `mess_gap`, `tantrum_left`, `nap_left`, `lights_left`, `sniffles_left`); wall-clock fields only where the spec wants wall-clock: `tantrum_due_at` (the random moment), `nap_slot` (the last nap start handled), `spoiled_until`, `cranky_until`.
6. **A mess is scheduled only when a credited track is fed** while no mess is open or pending and `mess_gap` (6 counted hours from the last mess appearing) has run out.
7. **Tantrums** are rolled at a uniformly random moment inside the UTC day's awake windows, which leave out every nap hour and the 15 minutes before it, so a tantrum and a nap never overlap on the clock. One fires, then the next is rolled inside the next UTC day. A due time from an earlier UTC day (frozen or offline all that time) is rolled again for today. A tantrum due while he naps waits until he wakes.
8. **Naps** start on the first tick within `MAX_CREDITED_GAP` (15 min) after 02:00, 10:00 or 18:00 UTC; later than that, or while frozen, that nap is skipped and marked handled. A nap whose start finds a tantrum still open (only possible after a freeze) is skipped. The nap and the lights window run on counted time.
9. **Missed lights** set `cranky_until` to the end of the nap plus 1 h. **A poke that wakes him** also makes him cranky for 1 h (spec: "wakes him early, cranky").
10. **A chore whose House post never went up** (no message id stored when its window ends) costs nothing: no Mood minus, no cold. A failed post is already reported as an error.
11. **Persistence:** chore buttons are `discord.ui.DynamicItem`s with custom id `wisp:chore:{chore}:{life_id}`, registered with `bot.add_dynamic_items` like the Feed and Poke buttons, so they work after any restart. A press is valid only for the current life, an open chore, and the message whose id is stored for it. Expiry edits use the stored message id, so they survive restarts too.
12. **Chore and illness posts use canned lines** (new `Moment`s), not the AI; the AI voice only gets the cold, spoiled and cranky layers.
13. **Post texts:** a won chore keeps the post's text and appends `♪ <@id> {done} ・ +{points} WC` and a moment line; an expired chore's post is replaced by its moment line (the picture stays). Both remove the button.
14. **Medicine** is its own Vault section and one-option select between Snacks and Badges, shown only while he has a cold; the buyer must pass `check_member` like gifts. The thank-you post attaches `ASSETS/moments/medicine.png` (Myra's bottle, copied under that name) and does not ping.
15. **Snacks** confirm `♪ Wisp ate your {name} ・ wellbeing +8`; the old "(daily meal limit)" suffix goes, since the gain no longer depends on the meal points granted.
16. **Card bars** reuse the uploaded emojis: Health `full_full`/`full_left`, Wellbeing `care_full`/`care_left`, Mood `happiness_full`/`happiness_left`. The cold line matches the Monster Pox line: `{SUB_CLEF} he has a cold・{hours} h left`.
17. **While napping** he also skips chiming in and the "House has gone quiet" post.
18. **No House post when a cold wears off** (the spec names only the catch post); his picture simply changes back.
19. **`DOCS/wisp_faq.html`** is updated too, since the FAQ pictures Myra re-renders are drawn from it.

## Review Focus

1. **A chore button pressed after a redeploy.** The bot restarts with a mess open; the rebuilt button still cleans up and pays. (Task 8 test `test_a_rebuilt_button_still_cleans_up`.)
2. **Two members press the same chore at the same moment.** Exactly one wins the points; the other is told it is done. (Task 8 test `test_two_presses_at_once_have_one_winner`.)
3. **The House post for a chore failed.** No Mood minus and no cold when its window ends. (Task 6 tests `test_an_unposted_tantrum_costs_nothing`, `test_an_unposted_mess_gives_no_cold`, `test_unposted_lights_cost_nothing`.)
4. **Freeze or outage in the middle of a chore or at a nap start.** Windows pause, and a nap start missed by more than 15 minutes is skipped without penalty. (Task 6 tests `test_frozen_time_pauses_every_chore`, `test_a_nap_start_while_frozen_is_skipped`, `test_a_nap_start_missed_by_an_outage_is_skipped`.)
5. **A stale button:** an old mess post, or any chore post from a life that died or was replaced. No points, no change, a private "already done". (Task 8 tests `test_a_button_from_an_earlier_mess_is_already_done`, `test_a_button_from_another_life_is_already_done`.)

---

### Task 1: Name the meters' code after Health and Wellbeing

A pure rename; no behaviour or member text changes.

**Files:**
- Modify: `wisp/rules.py`, `wisp/life.py`, `wisp/card.py`, `wisp/bond.py`, `db/lives.py`, `cogs/snacks.py`, `cogs/feeding.py`, `cogs/gifts.py`, `cogs/rhyme_duel.py`, `cogs/players.py`, `cogs/life_loop.py`, and anything else `grep -rn "\.full\b\|\.care\b\|FULL_MAX\|HATCHED_FULL\|CARE_MAX\|CARE_START\|CARE_PER_GIFT\|high_happiness_since" --include=*.py cogs wisp db app.py tools` finds
- Test: every file the same grep finds in `tests/`

**Interfaces:**
- Produces: `Life.health: float` (was `full`), `Life.wellbeing: float` (was `care`), `Life.high_mood_since: datetime | None` (was `high_happiness_since`), `Snack.meal: int` (was `full`); rules `HEALTH_MAX` (was `FULL_MAX`), `HEALTH_START` (was `HATCHED_FULL`), `WELLBEING_MAX` (was `CARE_MAX`), `WELLBEING_START` (was `CARE_START`), `WELLBEING_PER_GIFT` (was `CARE_PER_GIFT`). Keep for now (Task 3 removes them): `add_care`, `FULL_DRAIN_PER_DAY`, `OLD_FOGEY_FULL_DRAIN_PER_DAY`, `CARE_DRAIN_PER_DAY`, `CARE_PER_PLAY`. Never rename: `card.Meter.full`/`.left` (emoji pieces), `HANGRY_BELOW`, `FADING_BELOW`, `LONELY_BELOW`, `lonely_warned`, every Monster Pox name (`SICK_FULL_FLOOR` included), emoji names, column names.

- [ ] **Step 1:** Rename by hand per the list (a blind `sed` on `.full` breaks `card.Meter.full`). Update the mapping note in `db/lives.py`: `care` holds `Life.health`, `fondness` holds `Life.wellbeing`, `high_happiness_since` holds `Life.high_mood_since`.
- [ ] **Step 2:** Add to `tests/test_repos.py` `test_health_and_wellbeing_keep_their_live_columns`: save a life with `health=42.5, wellbeing=17.0`, read the raw `care` and `fondness` columns with SQL, assert `42.5` and `17.0`; load it, assert `life.health == 42.5` and `life.wellbeing == 17.0`.
- [ ] **Step 3:** Run `tests/test_life.py tests/test_repos.py tests/test_card.py tests/test_bond.py tests/test_snacks.py tests/test_feeding.py tests/test_gifts.py tests/test_rhyme_duel.py tests/test_players.py tests/test_life_loop.py` plus any other file the grep found. Expected: all pass. Run the quality tools.
- [ ] **Step 4:** Commit `refactor: name the meters' code after Health and Wellbeing`.

---

### Task 2: Storage for the new meter, stretches, the cold and the chores

**Files:**
- Modify: `wisp/rules.py`, `wisp/life.py` (fields only), `db/schema.py`, `db/lives.py`
- Test: `tests/test_schema.py`, `tests/test_repos.py`

**Interfaces:**
- Produces in `wisp/rules.py` under a new `# Mood` section: `MOOD_MAX = 100.0`, `MOOD_START = 50.0`.
- Produces on `Life` (appended after `had_cold`, with these defaults), stored in the column of the same name:

| Field | Type, default | Column |
|---|---|---|
| `mood_meter` | `float = MOOD_START` | `DOUBLE NOT NULL DEFAULT 50` |
| `health_stretch`, `wellbeing_stretch`, `mood_stretch` | `float = 0.0` | `DOUBLE NOT NULL DEFAULT 0` |
| `sniffles_left` | `float = 0.0` | `DOUBLE NOT NULL DEFAULT 0` |
| `mess_in`, `mess_left`, `mess_gap` | `float = 0.0` | `DOUBLE NOT NULL DEFAULT 0` |
| `mess_message_id` | `int \| None = None` | `BIGINT NULL` |
| `tantrum_due_at` | `datetime \| None = None` | `DATETIME NULL` |
| `tantrum_left` | `float = 0.0` | `DOUBLE NOT NULL DEFAULT 0` |
| `tantrum_message_id` | `int \| None = None` | `BIGINT NULL` |
| `spoiled_until` | `datetime \| None = None` | `DATETIME NULL` |
| `nap_slot` | `datetime \| None = None` | `DATETIME NULL` |
| `nap_left`, `lights_left` | `float = 0.0` | `DOUBLE NOT NULL DEFAULT 0` |
| `nap_message_id` | `int \| None = None` | `BIGINT NULL` |
| `cranky_until` | `datetime \| None = None` | `DATETIME NULL` |

  All `*_stretch` and `*_left`/`mess_in`/`mess_gap` values are counted seconds. Extend the `Life` docstring with one line per group.

- [ ] **Step 1: Write the failing tests.** In `tests/test_schema.py`: `test_the_meters_and_chores_columns_are_defined_and_added_to_live_tables` (every column in the table above is in `_defined_columns("lives")` and in `_ADDED_COLUMNS["lives"]` with the exact definition above), and `test_create_tables_adds_meters_and_chores_to_a_live_lives_table` modelled on `test_create_tables_adds_the_cold_to_a_live_lives_table`: build a lives table without the new columns, insert a row, run `create_tables`, assert every new column exists and the old row reads `mood_meter == 50`, `nap_left == 0`, `mess_message_id is None`. In `tests/test_repos.py`: `test_meters_and_chores_round_trip`: insert a life with every new field set to a non-default (`mood_meter=63.5`, `mess_message_id=1234567890123`, `tantrum_due_at=datetime(2026, 11, 2, 15, 30, tzinfo=UTC)`, ...), save, load, assert equal field by field.
- [ ] **Step 2:** Run `tests/test_schema.py tests/test_repos.py`. Expected: FAIL (unknown columns / fields).
- [ ] **Step 3:** Add the fields, the columns in both `_DEFINITIONS["lives"]` and `_ADDED_COLUMNS["lives"]`, and the columns to `db/lives.py` `_COLUMNS`, `_from_row`, `_values` (datetimes through `from_db_time`/`to_db_time`).
- [ ] **Step 4:** Run the two files again. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: store Mood, stretches, the cold and the chores`.

---

### Task 3: Step meters, the cold and Rockstar on Mood

**Files:**
- Modify: `wisp/rules.py`, `wisp/life.py`, `wisp/bond.py`, `wisp/card.py`, `db/activity.py`, `cogs/players.py`, `cogs/life_loop.py`, `cogs/gifts.py`, `cogs/rhyme_duel.py`
- Test: `tests/test_life.py`, `tests/test_bond.py`, `tests/test_card.py`, `tests/test_life_loop.py`, `tests/test_repos.py`, and any test still using `happiness`/`add_care`

**Interfaces:**
- Consumes: Task 1 names, Task 2 fields.
- Produces in `wisp/rules.py` (replacing the `# Full` and `# Care` drains):
  `HEALTH_STRETCH = timedelta(hours=6)`, `HEALTH_PENALTY = 8.0`, `OLD_FOGEY_HEALTH_PENALTY = 6.0`, `WELLBEING_STRETCH = timedelta(hours=6)`, `WELLBEING_PENALTY = 10.0`, `MOOD_STRETCH = timedelta(hours=6)`, `MOOD_PENALTY = 10.0`, `SNIFFLES_FOR = timedelta(hours=48)`, `SNIFFLES_PENALTY_MULTIPLIER = 2.0`, `ROCKSTAR_MOOD = 80`, `ROCKSTAR_MOOD_FOR = timedelta(days=4)`. `SICK_DRAIN_MULTIPLIER` keeps its name; its comment says it now multiplies the Health penalty. Removed: `FULL_DRAIN_PER_DAY`, `OLD_FOGEY_FULL_DRAIN_PER_DAY`, `CARE_DRAIN_PER_DAY`, `HAPPY_FULL_AT_PEOPLE`, `HAPPINESS_WINDOW`, `ROCKSTAR_HAPPINESS`, `ROCKSTAR_HAPPY_FOR`.
- Produces in `wisp/life.py`:
  - `class Meter(StrEnum): HEALTH, WELLBEING, MOOD` (values `auto()`).
  - `change_meter(life: Life, meter: Meter, amount: float, *, ends_stretch: bool = False) -> None`: only while ALIVE; clamps to 0..max; `ends_stretch` sets that meter's stretch to 0. Health gains re-arm the hungry/fading warnings as `feed` does today; Wellbeing at or above `LONELY_BELOW` clears `lonely_warned`. Negative amounts are for Mood chore penalties; Health only ever drops inside `tick`. Replaces `add_care` (removed; its two callers in `cogs/gifts.py` and `cogs/rhyme_duel.py` call `change_meter(life, Meter.WELLBEING, WELLBEING_PER_GIFT)` and, until Task 4, `change_meter(life, Meter.WELLBEING, CARE_PER_PLAY)`).
  - `feed(life, meal_points, feeder_id, now) -> list[Event]`: unchanged signature; the ALIVE branch becomes `change_meter(life, Meter.HEALTH, meal_points, ends_stretch=True)`.
  - `credited_gap(life: Life, now: datetime, *, frozen: bool) -> timedelta`: today's `elapsed` expression from `tick`, made public; `tick` uses it.
  - `tick(life: Life, now: datetime, *, frozen: bool, caretakers: int, people: int) -> list[Event]` (the `happiness` parameter goes; `people` stays, it drives growth since fea4be9). The `high_mood_since` shift for uncounted time stays.
  - `has_sniffles(life: Life) -> bool` (`sniffles_left > 0`), `catch_sniffles(life: Life) -> bool` (starts `SNIFFLES_FOR` and returns True only while ALIVE without a cold and without Monster Pox), `cure_sniffles(life: Life) -> bool` (ends it at once; True when he had one).
  - `_tick_hatching` also sets `mood_meter = MOOD_START` and the three stretches to 0.
  - `_tick_alive` order: catch due Monster Pox; apply the three stretch penalties; death at Health 0; farewell; count down Monster Pox; count down sniffles; warnings; growth. Penalty algorithm:

```python
def _penalties(life: Life, seconds: float) -> None:
    """Add counted time to each meter's empty stretch; a full stretch costs it."""
    life.health_stretch += seconds
    if life.health_stretch >= HEALTH_STRETCH.total_seconds():
        life.health_stretch -= HEALTH_STRETCH.total_seconds()
        penalty = HEALTH_PENALTY
        if life.stage is Stage.OLD_FOGEY:
            penalty = OLD_FOGEY_HEALTH_PENALTY
        floor = 0.0
        if is_sick(life):
            penalty *= SICK_DRAIN_MULTIPLIER
            floor = min(life.health, SICK_FULL_FLOOR)
        life.health = max(life.health - penalty, floor)
    # Wellbeing and Mood the same way, without a floor; Wellbeing's penalty is
    # multiplied by SNIFFLES_PENALTY_MULTIPLIER while has_sniffles(life).
```

  - Rockstar: `_kept_happy_long_enough(life, now)` reads `life.mood_meter >= ROCKSTAR_MOOD` for `ROCKSTAR_MOOD_FOR`, keeping `high_mood_since`.
- Cascade (keep everything green): remove `wisp.bond.happiness`, `cogs.players.current_happiness`, `ActivityRepo.chatters_since`; `status_text(bot, guild_id, life, now)` and `show_status_card(bot, guild_id, life, now)` lose `happy`; `CardFacts` loses `happiness` and the card's "Happy" bar reads `life.mood_meter / MOOD_MAX * 100` (labels change in Task 11); `LifeLoop._advance` stops passing happiness.

- [ ] **Step 1: Write the failing tests** in `tests/test_life.py` (replace the drain tests; update `alive`/`run`/`tended` helpers: `run` loses `happiness`, `tended` keeps `mood_meter` at `ROCKSTAR_MOOD` each step):
  - `test_nothing_drains_between_penalties`: `run(alive(), timedelta(hours=5, minutes=55))` → health, wellbeing, mood_meter all `50.0`.
  - `test_six_hours_without_a_track_costs_eight_health`: after 6 h → `health == 42.0`.
  - `test_an_old_fogey_loses_six_health`: Old Fogey, 6 h → `44.0`.
  - `test_monster_pox_makes_the_health_penalty_twelve`: `cold_left` set, 6 h → `38.0`.
  - `test_monster_pox_keeps_him_at_one_health`: sick, `health=5.0`, 6 h → `1.0`, no `DIED`.
  - `test_a_fed_track_restarts_the_health_stretch`: run 5 h, `feed(life, 5, FEEDER, now)`, run 5 h 55 m → `health == 55.0`; 5 more minutes → `47.0`.
  - `test_zero_health_from_a_penalty_kills_him`: `health=8.0`, 6 h → `kinds` contains `DIED`.
  - `test_six_hours_without_a_chat_or_snack_costs_ten_wellbeing` (→ `40.0`) and `test_a_cold_doubles_the_wellbeing_penalty` (`sniffles_left` set → `30.0`).
  - `test_six_hours_without_a_game_or_poke_costs_ten_mood` (→ `40.0`).
  - `test_change_meter_ending_a_stretch_restarts_only_that_meter`: stretches all at 3 h; `change_meter(life, Meter.MOOD, 5, ends_stretch=True)` → `mood_stretch == 0`, the other two unchanged, `mood_meter == 55.0`.
  - `test_change_meter_clamps_and_only_counts_while_alive`: `+80` from 50 → `100.0`; `-200` → `0.0`; on an egg nothing changes.
  - `test_frozen_and_offline_time_never_fill_a_stretch`: frozen 7 h → 50s and stretches 0; one tick with a 7 h gap → stretches `== MAX_CREDITED_GAP.total_seconds()`.
  - `test_credited_gap_is_zero_frozen_capped_and_never_negative`.
  - `test_meters_start_at_fifty_when_he_hatches`: after hatching `mood_meter == 50.0` and all stretches `0.0`.
  - `test_rockstar_after_four_days_of_mood_at_eighty`, `test_a_mood_dip_resets_the_rockstar_clock` (adapt the happiness versions).
  - `test_catch_sniffles_starts_a_48_hour_cold`, `test_no_cold_while_he_has_monster_pox_or_one_already` (both return False, `sniffles_left` unchanged), `test_a_cold_wears_off_after_48_counted_hours` (frozen time excluded), `test_cure_sniffles_ends_it_at_once` (True, then False), `test_a_cold_never_touches_health`.
  - Keep and adapt the mood-precedence tests: HANGRY (health < 30) beats LONELY (wellbeing < 30) beats HAPPY.
- [ ] **Step 2:** Run `tests/test_life.py`. Expected: FAIL (imports).
- [ ] **Step 3:** Implement the interfaces above and the cascade. Delete the tests of removed code (`happiness`, `chatters_since`, drain tests).
- [ ] **Step 4:** Run `tests/test_life.py tests/test_bond.py tests/test_card.py tests/test_life_loop.py tests/test_repos.py tests/test_gifts.py tests/test_rhyme_duel.py tests/test_players.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: meters move in steps; a cold; Rockstar on Mood`.

---

### Task 4: Tracks, snacks, duels and gifts fill the right meter

**Files:**
- Modify: `wisp/rules.py`, `cogs/snacks.py`, `cogs/rhyme_duel.py`, `cogs/gifts.py`
- Test: `tests/test_snacks.py`, `tests/test_rhyme_duel.py`, `tests/test_gifts.py`, `tests/test_feeding.py`

**Interfaces:**
- Consumes: `change_meter`, `Meter` (Task 3).
- Produces in rules: `WELLBEING_PER_SNACK = 8`, `MOOD_PER_PLAY = 10` (replaces `CARE_PER_PLAY`, removed).
- `cogs/snacks._eat`: no longer calls `feed`; still computes `meal_grant(eaten, snack.meal, daily_meal_cap(life))`, still refuses with `_FULL` at 0, still records the interaction with the granted meal points; then `change_meter(life, Meter.WELLBEING, WELLBEING_PER_SNACK, ends_stretch=True)`. `_Meal` loses `full`. `_hunger_gain` becomes `_wellbeing_gain() -> str` returning `f"wellbeing +{WELLBEING_PER_SNACK}"`, used by the Vault and feed-menu descriptions. Confirmation: `♪ Wisp ate your {snack.name} ・ wellbeing +{WELLBEING_PER_SNACK}`.
- `cogs/rhyme_duel._record_play`: `change_meter(life, Meter.MOOD, MOOD_PER_PLAY, ends_stretch=True)`. This call is the hook project 2's games reuse.
- `cogs/gifts.give_gift`: `change_meter(life, Meter.WELLBEING, WELLBEING_PER_GIFT)` (no stretch end).

- [ ] **Step 1: Write the failing tests.**
  - `tests/test_snacks.py`: `test_a_snack_fills_wellbeing_by_eight_not_health` (health unchanged, wellbeing `58.0`, for the free Sine Wave and for a Cheese); `test_a_snack_restarts_the_wellbeing_stretch`; `test_snacks_still_count_against_the_daily_meal_cap` (a member at `DAILY_MEAL_CAP` meal points gets `"♪ Wisp is full from you today. Save it for tomorrow."` and the snack stays in the inventory); `test_the_snack_confirmation_says_wellbeing` (`"♪ Wisp ate your Spicy Wave ・ wellbeing +8"`); update the Vault and feed-menu description tests to `"3 WC ・ wellbeing +8"` / `"wellbeing +8"`.
  - `tests/test_rhyme_duel.py`: `test_a_counted_duel_adds_ten_mood_and_restarts_its_stretch` (mood_meter `60.0`, `mood_stretch == 0`, wellbeing unchanged).
  - `tests/test_gifts.py`: `test_every_gift_bought_adds_eight_wellbeing_without_ending_its_stretch` (kept and passed: wellbeing `58.0`, `wellbeing_stretch` unchanged).
  - `tests/test_feeding.py`: `test_a_fed_track_fills_health_and_restarts_its_stretch` (stored `health_stretch=10800.0` → `0.0`, health up by the grant).
- [ ] **Step 2:** Run the four files. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the four files. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: snacks fill Wellbeing, duels fill Mood`.

---

### Task 5: Three chat credits and three poke credits a day

**Files:**
- Modify: `wisp/rules.py`, `db/activity.py`, `cogs/players.py`, `cogs/conversation.py`
- Test: `tests/test_repos.py`, `tests/test_conversation.py`, `tests/test_players.py`

**Interfaces:**
- Produces in rules (`# Meals and points`): `WELLBEING_PER_CHAT = 5`, `MOOD_PER_POKE = 5`, `CHAT_CREDITS_PER_DAY = 3`, `POKE_CREDITS_PER_DAY = 3`. `CHAT_POINTS` stays.
- `db/activity.py`: `InteractionKind.POKE = "poke"` (docstring: CHAT is a credited mention, POKE a credited poke; neither is caring). `caretakers` and `latest_interactor` exclude both (`kind NOT IN (...)`). `chatted_today` is replaced by `chats_today(guild_id, user_id, now) -> int` and `pokes_today(guild_id, user_id, now) -> int` (both through `_count_today`).
- `cogs/players.py`: `credit_chat(bot, guild_id, member, now) -> bool` and `credit_poke(bot, guild_id, member, now) -> bool` (the `life` parameter goes), both through one private `_credit(bot, guild_id, member, kind, meter, amount, per_day, now) -> bool` that, under `bot.guild_lock`: loads the current life (False when none); returns False for a banned member or one who fails `can_feed`; returns False when that kind's count today has reached `per_day`; pays `CHAT_POINTS` when `chats_today + pokes_today == 0`; records the interaction; `change_meter(life, meter, amount, ends_stretch=True)`; saves. Returns True when credited. `maybe_meet` stays outside the lock, after it, as today.
- `cogs/conversation.py`: `_answer` calls `credit_chat`; `_poke` calls `credit_poke`. Docstrings say what a credit is now.

- [ ] **Step 1: Write the failing tests** (`tests/test_conversation.py` unless noted; space actions past `TALK_COOLDOWN` with the existing `Clock`):
  - `test_the_first_three_mentions_a_day_add_five_wellbeing_each`: four mentions → wellbeing `65.0`, three CHAT rows.
  - `test_a_fourth_mention_does_not_restart_the_wellbeing_stretch`: set `wellbeing_stretch=3600.0` after the third credit; the fourth leaves it at `3600.0`.
  - `test_the_first_three_pokes_a_day_add_five_mood_each`: four pokes → mood_meter `65.0`, three POKE rows.
  - `test_the_chat_point_is_paid_once_a_day_across_chats_and_pokes`: two mentions and two pokes → points `== CHAT_POINTS`.
  - `test_a_member_who_cannot_feed_earns_no_credit_and_restarts_nothing`: no rows, meters and stretches unchanged, Wisp still answers.
  - `test_credits_start_again_at_utc_midnight`: three mentions at 23:50, one at 00:05 next day → wellbeing `70.0`.
  - `tests/test_repos.py`: `test_pokes_and_chats_are_not_caring` (a POKE row never counts in `caretakers` or `latest_interactor`), `test_chats_and_pokes_today_count_their_own_kind`.
- [ ] **Step 2:** Run `tests/test_conversation.py tests/test_repos.py tests/test_players.py`. Expected: FAIL.
- [ ] **Step 3:** Implement; replace the old once-a-day credit tests.
- [ ] **Step 4:** Run the three files. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: three chat and three poke credits a day`.

---

### Task 6: The chores, as pure rules

**Files:**
- Create: `wisp/chores.py`
- Modify: `wisp/rules.py`
- Test: `tests/test_chores.py` (new)

**Interfaces:**
- Consumes: `Life`, `Phase`, `change_meter`, `Meter`, `catch_sniffles` (Task 3); fields (Task 2).
- Produces in rules, new `# Chores` section: `class Chore(StrEnum): MESS = "mess"; TANTRUM = "tantrum"; NAP = "nap"`; `CHORE_POINTS: Final[dict[Chore, int]] = {Chore.MESS: 2, Chore.TANTRUM: 2, Chore.NAP: 2}`; `MESS_DELAY_MIN = timedelta(minutes=30)`, `MESS_DELAY_MAX = timedelta(minutes=90)`, `MESS_GAP = timedelta(hours=6)`, `MESS_LEFT_FOR = timedelta(hours=6)`, `WELLBEING_PER_CLEANUP = 5`, `TANTRUM_WINDOW = timedelta(minutes=15)`, `TANTRUM_MOOD_PENALTY = 15.0`, `NAP_HOURS: Final = (2, 10, 18)`, `NAP_FOR = timedelta(hours=1)`, `LIGHTS_WINDOW = timedelta(minutes=15)`, `LIGHTS_MOOD_PENALTY = 10.0`, `CRANKY_FOR = timedelta(hours=1)`. A comment by `TANTRUM_WINDOW` says Myra may stretch it while the server is small.
- Produces in `wisp/chores.py`:
  - `class ChoreEventKind(StrEnum): MESS, MESS_LEFT, SNIFFLES, TANTRUM, TANTRUM_MISSED, NAP, LIGHTS_MISSED`.
  - `@dataclass(frozen=True) class ChoreEvent: kind: ChoreEventKind; message_id: int | None = None` (the post to edit, for the `*_LEFT`/`*_MISSED` kinds).
  - `schedule_mess(life: Life, rng: random.Random) -> None`: when ALIVE and `mess_in == mess_left == mess_gap == 0`, sets `mess_in` to `rng.uniform` between the two delays, in seconds.
  - `is_open(life: Life, chore: Chore) -> bool`: `mess_left > 0`, `tantrum_left > 0`, or `lights_left > 0` for NAP (the lights button is the nap's chore).
  - `is_napping(life: Life) -> bool`: `nap_left > 0`.
  - `message_id(life: Life, chore: Chore) -> int | None` and `set_message_id(life: Life, chore: Chore, message_id: int) -> None`.
  - `do_chore(life: Life, chore: Chore) -> bool`: closes an open chore and returns True (a cleanup also `change_meter(life, Meter.WELLBEING, WELLBEING_PER_CLEANUP)`); False when it was not open.
  - `wake(life: Life, now: datetime) -> bool`: ends a nap at once, closes the lights window, sets `cranky_until = now + CRANKY_FOR`, applies no penalty; returns whether the lights were still on.
  - `latest_nap_start(now: datetime) -> datetime`: the latest of today's and yesterday's `NAP_HOURS` starts at or before `now`.
  - `next_tantrum(after: datetime, rng: random.Random) -> datetime`: uniform over the awake windows of `after`'s UTC day that lie after `after`, else over the next UTC day's.
  - `tick_chores(life: Life, now: datetime, elapsed: timedelta, rng: random.Random, *, frozen: bool) -> list[ChoreEvent]`.
- Algorithms the tests do not pin:

```python
def _awake_windows(day: datetime) -> list[tuple[datetime, datetime]]:
    """The UTC day starting at `day`, minus every nap and the TANTRUM_WINDOW before it.

    Naps starting the day before and the day after count too, clipped to the day.
    """
    end_of_day = day + timedelta(days=1)
    starts = [
        day + timedelta(days=offset, hours=hour)
        for offset in (-1, 0, 1)
        for hour in NAP_HOURS
    ]
    busy = sorted((start - TANTRUM_WINDOW, start + NAP_FOR) for start in starts)
    windows: list[tuple[datetime, datetime]] = []
    cursor = day
    for begin, end in busy:
        if begin > cursor:
            windows.append((cursor, min(begin, end_of_day)))
        cursor = max(cursor, end)
    if cursor < end_of_day:
        windows.append((cursor, end_of_day))
    return [(begin, end) for begin, end in windows if end > begin]
```

```python
def tick_chores(life, now, elapsed, rng, *, frozen):
    if life.phase is not Phase.ALIVE:
        return []
    slot = latest_nap_start(now)
    new_slot = life.nap_slot is None or slot > life.nap_slot
    if new_slot:
        life.nap_slot = slot              # handled even when skipped
    if frozen:
        return []
    seconds = elapsed.total_seconds()
    events = [*_tick_mess(life, seconds), *_tick_tantrum(life, now, seconds),
              *_tick_nap(life, now, seconds)]
    if (new_slot and now - slot <= MAX_CREDITED_GAP and not is_napping(life)
            and not is_open(life, Chore.TANTRUM)):
        start the nap: nap_left = NAP_FOR, lights_left = LIGHTS_WINDOW,
        nap_message_id = None -> NAP
    if life.tantrum_due_at is None or life.tantrum_due_at.date() < now.date():
        life.tantrum_due_at = next_tantrum(now, rng)
    if (not is_napping(life) and not is_open(life, Chore.TANTRUM)
            and life.tantrum_due_at <= now):
        tantrum_left = TANTRUM_WINDOW, tantrum_message_id = None,
        tantrum_due_at = next_tantrum(<next UTC midnight>, rng) -> TANTRUM
    return events
```

  `_tick_mess`: count `mess_gap` down to 0; an open mess counts down and at 0 closes: when `mess_message_id` is set, emit `MESS_LEFT(message_id)` and, if `catch_sniffles(life)`, `SNIFFLES`; a pending `mess_in` counts down and at 0 opens: `mess_left = MESS_LEFT_FOR`, `mess_gap = MESS_GAP`, `mess_message_id = None`, emit `MESS`. `_tick_tantrum`: an open window counts down; at 0, if posted: Mood `-TANTRUM_MOOD_PENALTY`, `spoiled_until` = next UTC midnight, emit `TANTRUM_MISSED(message_id)`. `_tick_nap`: while napping, an open lights window counts down; at 0, if posted: Mood `-LIGHTS_MOOD_PENALTY`, `cranky_until = now + <nap seconds left> + CRANKY_FOR`, emit `LIGHTS_MISSED(message_id)`; then `nap_left` counts down. All counts clamp at 0.

- [ ] **Step 1: Write the failing tests** in `tests/test_chores.py` (`T0 = datetime(2026, 11, 2, 12, 0, tzinfo=UTC)`; a living Baby helper like `tests/test_life.py`'s `alive`; a helper ticking every `TICK_EVERY` through `credited_gap` + `tick_chores`):
  - Messes: `test_a_fed_track_schedules_a_mess_30_to_90_minutes_later` (`1800 <= mess_in <= 5400` over 50 seeds); `test_no_mess_is_scheduled_while_one_is_open_pending_or_too_soon`; `test_a_mess_appears_when_its_delay_runs_out` (one `MESS`, `mess_left == 21600`, `mess_gap == 21600`, `mess_message_id is None`); `test_a_mess_left_six_hours_gives_him_a_cold` (posted: events `[MESS_LEFT(id), SNIFFLES]`, `sniffles_left == 172800`, mess closed); `test_a_mess_left_while_sick_gives_no_second_illness` (Monster Pox or a cold already: only `MESS_LEFT`); `test_an_unposted_mess_gives_no_cold`; `test_a_cleanup_adds_five_wellbeing_and_closes_the_mess` (`do_chore` True, wellbeing `55.0`, `wellbeing_stretch` unchanged; again → False).
  - Tantrums: `test_next_tantrum_is_always_awake` (200 seeds, for `after` at 00:00, 09:50 and 23:59: never within `[h - 15 min, h + 1 h)` of any nap, never before `after`); `test_a_tantrum_starts_when_due` (`TANTRUM`, `tantrum_left == 900`, next due on the next UTC day); `test_a_tantrum_due_during_a_nap_waits_until_he_wakes`; `test_a_due_time_from_an_earlier_day_is_rolled_again`; `test_a_missed_tantrum_costs_fifteen_mood_and_spoils_him_until_midnight` (posted: mood `35.0`, `spoiled_until == datetime(2026, 11, 3, tzinfo=UTC)`, `TANTRUM_MISSED(id)`); `test_an_unposted_tantrum_costs_nothing`; `test_a_scold_closes_the_tantrum`.
  - Naps: `test_naps_start_at_two_ten_and_eighteen_utc` (tick at 10:00 → `NAP`, `nap_left == 3600`, `lights_left == 900`); `test_a_nap_start_missed_by_an_outage_is_skipped` (ticks 09:55 then 10:20 → no `NAP`, `nap_slot == 10:00`, no penalty); `test_a_nap_start_while_frozen_is_skipped` (frozen across 10:00, unfrozen 10:05 → no `NAP`); `test_missed_lights_cost_ten_mood_and_make_him_cranky` (posted: mood `40.0`, `cranky_until == now + 45 min + 1 h` at the tick that closes the window); `test_unposted_lights_cost_nothing`; `test_lights_off_closes_the_window_and_he_sleeps_on`; `test_he_wakes_after_an_hour_of_counted_time`; `test_wake_ends_the_nap_and_says_whether_the_lights_were_on` (True with the window open, False after lights off; no Mood change; `cranky_until == now + 1 h`); `test_no_nap_starts_over_an_open_tantrum`.
  - General: `test_only_a_living_wisp_has_chores` (egg, hatching: `[]`); `test_frozen_time_pauses_every_chore` (open mess, tantrum and nap: a frozen hour leaves every `*_left` unchanged).
- [ ] **Step 2:** Run `tests/test_chores.py`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement `wisp/chores.py` and the rules.
- [ ] **Step 4:** Run `tests/test_chores.py tests/test_rules.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: messes, tantrums and naps as pure rules`.

---

### Task 7: Lines, voice and pictures for chores and the cold

**Files:**
- Modify: `wisp/lines.py`, `wisp/voice.py`, `wisp/rules.py`, `cogs/assets.py`, `cogs/pictures.py`, `cogs/conversation.py` (the two `build_prompt` calls and `poke_flavor` call only)
- Already in place (moved into ASSETS 2026-11-04, nothing to copy): `ASSETS/moments/poop.gif`, `ASSETS/moments/wispsick.gif`, `ASSETS/moments/medicine.png`
- Test: `tests/test_lines.py`, `tests/test_voice.py`, `tests/test_announce.py` (picture tests live there), `tests/test_assets.py`

**Interfaces:**
- Produces in rules (`# Chores`): `MESSES: Final[dict[Stage, tuple[str, str, str | None]]]` (what the mess is, its button label, its picture or None) = {BABY: ("poop", "Clean up", "poop.gif"), CHILD: ("poop", "Clean up", "poop.gif"), TEEN: ("a zit breakout", "Hand him face wash", "pimple.gif"), ADULT: ("takeout boxes and dirty dishes", "Take out the trash", "trash_adult.gif"), ROCKSTAR: ("the green room he trashed after a show", "Clean the green room", "trash_rockstar.gif"), OLD_FOGEY: ("dentures that need a soak", "Soak his teeth", "dentures.gif")} (a None picture posts the words and button alone; Myra will supply the other pictures), `SNIFFLES_PICTURE: Final = "wispsick.gif"`, `MEDICINE_PICTURE: Final = "medicine.png"`, `TANTRUM_PICTURES: Final[dict[Stage, str]] = {BABY: "tantrum_baby.gif", CHILD: "grumpy.gif", TEEN: "cry_teen.gif", ADULT: "grumpy_adult.gif", ROCKSTAR: "grumpy_adult.gif", OLD_FOGEY: "grumpy_old_fogey.gif"}`. Remove `POKE_SLEEP_HOURS` and fix the `# Poking` comment.
- `wisp/lines.py`: new `Moment`s with `FIELDS`: `MESS`, `MESS_LEFT`, `SNIFFLES`, `TANTRUM`, `TANTRUM_MISSED`, `NAP`, `LIGHTS_MISSED`, `NAP_TALK` (all `_NONE`); `MESS_CLEANED`, `SCOLDED`, `LIGHTS_OFF`, `MEDICINE` (`_NAME`). Each gets `_either_mood` lines, at least six, emoji free. Cold lines are stuffy and sneezy, never spots or itching; `NAP_TALK` lines are sleepy noises only (like `"*snore*"`); `SCOLDED` lines pout, then settle down; `TANTRUM` lines whine for no reason.
- `wisp/voice.py`: `class Feeling(StrEnum): MONSTER_POX, SNIFFLES, SPOILED, CRANKY`; `feelings_of(life: Life, now: datetime) -> frozenset[Feeling]` (`is_sick`, `has_sniffles`, `now < spoiled_until`, `now < cranky_until`); `build_prompt(..., feelings: Collection[Feeling] = (), ...)` replaces `sick: bool`, adding one layer per feeling, grown and Baby versions like `_SICK`/`_BABY_SICK` (cold: stuffy, sneezy, never spotty; spoiled: extra bratty for the rest of the day; cranky: just woken and grumpy about it). `poke_flavor(mood, streak, quiet_for, rng)` loses `now`; sleepy is only `quiet_for >= POKE_SLEEP_AFTER`.
- `cogs/assets.py`: `moment_image(name: str) -> Path | None` (the file in `ASSETS/moments` when it exists); `cogs/pictures.sick_image` uses it. `life_image`: while `has_sniffles(life)` and the file exists, `moment_image(SNIFFLES_PICTURE)` (checked after Monster Pox).

- [ ] **Step 1: Write the failing tests.** `tests/test_lines.py`: the existing every-moment-every-mood, no-emoji, fit and fields tests now cover the new moments; add `test_the_chore_and_cold_moments_have_at_least_six_lines`, `test_the_cold_lines_are_sneezy_not_spotty` (no "spot", "itch" or "scratch"), `test_nap_talk_is_only_sleepy_noises` (every line starts and ends with `*`). `tests/test_voice.py`: `test_each_feeling_reaches_the_prompt` (parametrized over `Feeling` × Baby/Teen: its layer text is in `system`), `test_feelings_of_a_life` (spoiled at 23:59 yes, at midnight no; cranky until its time), `test_a_poke_in_the_small_hours_is_not_sleepy` (quiet_for `None`, `HeaviestChoice` never yields `WOKE_UP`); update the existing `sick=` and `poke_flavor` callers. `tests/test_announce.py`: `test_a_wisp_with_a_cold_shows_the_sick_gif` (`life_image(...).name == "wispsick.gif"`). `tests/test_assets.py`: `test_every_chore_picture_is_in_the_moments_folder` (every non-None picture in `MESSES`, `SNIFFLES_PICTURE`, `MEDICINE_PICTURE`, `TANTRUM_PICTURES` exists).
- [ ] **Step 2:** Run `tests/test_lines.py tests/test_voice.py tests/test_announce.py tests/test_assets.py`. Expected: FAIL.
- [ ] **Step 3:** Implement (the three pictures are already in `ASSETS/moments`).
- [ ] **Step 4:** Run the four files plus `tests/test_conversation.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: lines, voice and pictures for chores and the cold` (stage `poop.gif`, `wispsick.gif`, `medicine.png`, `pimple.gif`, `dentures.gif`, `trash.gif`, `trash_adult.gif`, `trash_rockstar.gif` and Myra's already-present `ASSETS/moments/grumpy_adult.gif`, `grumpy_old_fogey.gif`, `tantrum_baby.gif`, and her re-keyed `cry_baby.gif`, `cry_teen.gif`, `grumpy.gif`).

---

### Task 8: Chore posts, the persistent button and the life loop

**Files:**
- Create: `cogs/chores.py`
- Modify: `cogs/announce.py`, `cogs/life_loop.py`, `cogs/feeding.py`, `app.py` (`EXTENSIONS`)
- Test: `tests/test_chore_posts.py` (new), `tests/test_life_loop.py`, `tests/test_feeding.py`, `tests/test_announce.py`

**Interfaces:**
- Consumes: Task 6 (`tick_chores`, `do_chore`, `is_open`, `message_id`, `set_message_id`, `schedule_mess`, `ChoreEvent`), Task 7 (moments, pictures, `moment_image`), `nap_image`, `can_feed`, `say_privately`, `report_failure`, `EXPECTED_FAILURES`.
- `cogs/announce.py`: `_House.say`, `post_in_house` and `say_in_house` return `discord.Message | None` (None when the House is missing or the send failed). New `edit_in_house(bot, guild_id, message_id: int, text: str) -> None`: edits that House message's content and removes its buttons (`view=None`), pinging nobody; a failure, `NotFound` included, is reported, never raised.
- `cogs/chores.py`:
  - `CHORE_ID: Final = r"wisp:chore:(?P<chore>mess|tantrum|nap):(?P<life_id>[0-9]+)"`.
  - `class ChoreButton(discord.ui.DynamicItem[discord.ui.Button[discord.ui.View]], template=re.compile(CHORE_ID))` with `__init__(self, chore: Chore, life_id: int)`; labels: the mess button takes its label from `MESSES[life.stage]` (the custom id stays `mess`), then `Scold`, `Lights off`; `from_custom_id` rebuilds from the match; `callback` runs `_press` and reports `EXPECTED_FAILURES` with `report_failure`.
  - `chore_view(chore: Chore, life_id: int) -> discord.ui.View` (timeout None).
  - `post_chores(bot: "WispBot", guild_id: int, life: Life, events: list[ChoreEvent]) -> None`: `MESS` → `say_in_house(Moment.MESS, image=<moment_image(MESSES[life.stage][2]) or None when that picture is None>, view=chore_view(...))`; `TANTRUM` → `TANTRUM_PICTURES[life.stage]`; `NAP` → `nap_image(life.stage)` (text only after Child); each posted message's id is saved with `_remember(bot, guild_id, life.id, chore, message.id)`, which under the guild lock reloads the life and, when it is still the same life and that chore is still open, `set_message_id` + save. `MESS_LEFT`, `TANTRUM_MISSED`, `LIGHTS_MISSED` → `edit_in_house(event.message_id, <that moment's line>)`. `SNIFFLES` → `say_in_house(Moment.SNIFFLES, image=moment_image(SNIFFLES_PICTURE))`.
  - `_press(interaction, chore, life_id)`: `interaction.response.defer()`; a banned member or one failing `can_feed` gets `say_privately("♪ Only members who can feed Wisp earn points.")` and nothing changes; under the guild lock, the press wins only when the current life's id is `life_id`, `is_open(life, chore)` and `message_id(life, chore) == interaction.message.id`: then `do_chore`, save, `add_points(CHORE_POINTS[chore])`. A loser gets `say_privately("♪ Someone already took care of that.")`. The winner's post is edited outside the lock: its content plus `\n♪ <@{user_id}> {done} ・ +{points} WC\n{line}` with `done` = `cleaned up the mess` / `scolded Wisp` / `turned off the lights` and `line` from `MESS_CLEANED`/`SCOLDED`/`LIGHTS_OFF` (`name` = Wisp name or display name), `view=None`, no pings.
  - `setup(bot)`: `bot.add_dynamic_items(ChoreButton)`.
- `app.EXTENSIONS`: add `"cogs.chores"` before `"cogs.life_loop"`.
- `cogs/life_loop.py`: `_advance` returns `tuple[list[Event], list[ChoreEvent]]`: `elapsed = credited_gap(life, now, frozen=frozen)` before `tick`, then `tick_chores(life, now, elapsed, self.rng, frozen=frozen)`, then one save. `_tick_guild` calls `post_events`, then `post_chores` with the saved life. `_speak_if_quiet` also stays silent while `is_napping`.
- `cogs/feeding.py`: `Feeding.rng = random.Random()`; `_feed` calls `schedule_mess(life, self.rng)` after `feed`, before the save.

- [ ] **Step 1: Write the failing tests** in `tests/test_chore_posts.py`, reusing the fake server/bot/interaction patterns of `tests/test_life_loop.py` and `tests/test_snacks.py`:
  - `test_a_mess_posts_poop_gif_and_a_clean_up_button_without_pings` (custom id `f"wisp:chore:mess:{life.id}"`, `AllowedMentions.none()`, `mess_message_id` saved).
  - `test_the_tantrum_picture_follows_his_stage` (parametrized over `TANTRUM_PICTURES`).
  - `test_a_nap_post_shows_nap_gif_for_little_stages_and_text_after` (Baby has `nap.gif`, Teen no file).
  - `test_the_first_eligible_press_cleans_up_and_pays` (points `+2`, wellbeing `55.0`, post content ends with the done line, `view=None`).
  - `test_a_later_press_is_told_it_is_already_done` (no points).
  - `test_a_member_who_cannot_feed_is_told_and_the_mess_stays` (`is_open` still True).
  - `test_two_presses_at_once_have_one_winner` (`asyncio.gather` of two members' presses: exactly one `+2`, one "already done").
  - `test_a_rebuilt_button_still_cleans_up` (`ChoreButton.from_custom_id` on the custom id, then press: wins).
  - `test_a_button_from_an_earlier_mess_is_already_done` (message id differs from the stored one).
  - `test_a_button_from_another_life_is_already_done`.
  - `test_scold_and_lights_off_pay_two_points` (parametrized).
  - `test_a_mess_left_too_long_edits_its_post_and_posts_the_cold` (edit has no view; a new post with `wispsick.gif`).
  - `test_a_missed_tantrum_and_missed_lights_edit_their_posts`.
  - `tests/test_announce.py`: `test_post_in_house_returns_the_message_or_none`, `test_edit_in_house_reports_a_missing_message`.
  - `tests/test_life_loop.py`: `test_the_tick_posts_a_due_nap` (clock at 10:00 UTC, alive Baby → House post with a Lights off button); `test_nothing_posts_while_frozen`; `test_he_does_not_go_quiet_while_napping`; `"cogs.chores"` is in `app.EXTENSIONS` before `"cogs.life_loop"`.
  - `tests/test_feeding.py`: `test_a_fed_track_schedules_a_mess`.
- [ ] **Step 2:** Run `tests/test_chore_posts.py tests/test_life_loop.py tests/test_feeding.py tests/test_announce.py`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the same files plus `tests/test_app.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: chore posts with first-press buttons`.

---

### Task 9: Asleep in the House

**Files:**
- Modify: `cogs/conversation.py`, `cogs/chores.py`
- Test: `tests/test_conversation.py`

**Interfaces:**
- Consumes: `is_napping`, `wake` (Task 6), `edit_in_house` (Task 8), `Moment.NAP_TALK`, `PokeFlavor.WOKE_UP`, `feelings_of`.
- `cogs/chores.py`: `wake_by_poke(bot, guild_id, user_id: int, now) -> Life | None`: under the guild lock reloads the life; when it is napping, `wake`, save; outside the lock, when the lights were still on and the nap post is stored, `edit_in_house(nap_message_id, f"♪ <@{user_id}> woke Wisp up before the lights went off.")`. Returns the woken life, or None when he was not asleep.
- `cogs/conversation.py`:
  - `_answer`: after `take_turn`, while `is_napping(life)` he replies with `bot.lines.pick(Moment.NAP_TALK, mood(life))`, no AI call and no credit.
  - `_maybe_chime_in`: never while napping.
  - `_poke`: after `take_turn`, `woken = await wake_by_poke(...)`; when not None the flavor is `WOKE_UP`, no `credit_poke`, the prompt uses `woken` (so `CRANKY` is in its feelings), and the House post attaches `nap_image`; otherwise today's path with `credit_poke`.

- [ ] **Step 1: Write the failing tests** in `tests/test_conversation.py`: `test_a_mention_while_napping_gets_sleepy_noises_and_no_credit` (reply is a `NAP_TALK` line, `ai.complete` not awaited, no CHAT row); `test_he_never_chimes_in_while_napping`; `test_a_poke_wakes_him_cranky_with_no_mood_plus` (`nap_left == 0`, `cranky_until == now + 1 h`, mood_meter unchanged, no POKE row, the AI prompt has the cranky layer and the woke-up feeling); `test_waking_him_with_the_lights_on_edits_the_lights_post` (edited to the woken text, `view=None`, mood_meter unchanged); `test_waking_him_after_lights_off_leaves_that_post_alone`.
- [ ] **Step 2:** Run `tests/test_conversation.py`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `tests/test_conversation.py tests/test_chore_posts.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: naps: sleepy answers, pokes wake him cranky`.

---

### Task 10: Medicine in the Vault

**Files:**
- Modify: `wisp/rules.py`, `cogs/snacks.py`
- Test: `tests/test_snacks.py`

**Interfaces:**
- Consumes: `has_sniffles`, `cure_sniffles` (Task 3), `MEDICINE_PICTURE`, `moment_image`, `Moment.MEDICINE` (Task 7), `check_member`, `Refusal`.
- Produces in rules (`# Chores`): `MEDICINE_COST = 10`, `MEDICINE_POINTS = 3`, `MEDICINE_EMOJI: Final = "medicine"`.
- `cogs/snacks.py`:
  - `MedicineSelect(discord.ui.Select[Any])`: placeholder `Give Wisp medicine`, one option: label `Medicine`, value `medicine`, description `10 WC ・ cures his cold` (from the rules), `emoji=bot.emojis_by_name.get(MEDICINE_EMOJI)`; its callback runs `_give_medicine`.
  - `_VaultMenus.medicine: discord.ui.Select[Any] | None`; `_vault` builds it only while the current life `has_sniffles`. `_vault_pieces` adds, between Snacks and Badges and only then, a piece `wrapped([SECTION_BREAK, heading("Medicine"), item(f"cures his cold│{bot.emoji(MEDICINE_EMOJI)}・{_coins(bot, f'{MEDICINE_COST} WC')}")], VAULT_WIDTH)` followed by the select.
  - `_take_medicine(bot, guild_id, member, now) -> tuple[Life, Player]` (call under the guild lock): `check_member`; `Refusal("♪ Wisp doesn't have a cold right now.")` unless alive with `has_sniffles` (checked before any spending, so a second buyer pays nothing); `spend(MEDICINE_COST)` or the `NOT_ENOUGH_POINTS` line; `cure_sniffles`; save; `add_points(MEDICINE_POINTS)`.
  - `_give_medicine(interaction)`: defer, take under the lock, `_confirm(interaction, "♪ You gave Wisp his medicine ・ +3 WC", ...)`, then `say_in_house(Moment.MEDICINE, life, name=..., image=moment_image(MEDICINE_PICTURE))` (no ping).
- Manual step (controller only; it changes the live app; do it before the Task 13 push so the deploy's startup fetch sees the emoji). Scale the bottle whole, longest side 128 px, no crop:

```powershell
Add-Type -AssemblyName System.Drawing
$src = [System.Drawing.Image]::FromFile("<repo>\ASSETS\moments\medicine.png")
$scale = 128 / [Math]::Max($src.Width, $src.Height)
$bmp = New-Object System.Drawing.Bitmap ([int]($src.Width * $scale)), ([int]($src.Height * $scale))
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
$g.DrawImage($src, 0, 0, $bmp.Width, $bmp.Height)
$bmp.Save("<scratchpad>\medicine_emoji.png", [System.Drawing.Imaging.ImageFormat]::Png)
```

  Then upload it with Discord's REST API (no gateway login, so the live Wisp is untouched): `GET https://discord.com/api/v10/applications/@me` for the application id, then `POST https://discord.com/api/v10/applications/{application_id}/emojis` with headers `Authorization: Bot <DISCORD_BOT_TOKEN from .env>`, `Content-Type: application/json`, body `{"name": "medicine", "image": "data:image/png;base64,<base64 of medicine_emoji.png>"}`. A 201 with the emoji JSON means done. Put the few lines of `urllib` in a script in the scratchpad, never in the repo.

- [ ] **Step 1: Write the failing tests** in `tests/test_snacks.py`: `test_medicine_shows_in_the_vault_only_while_he_has_a_cold` (section and select present with `sniffles_left > 0`, absent otherwise); `test_buying_medicine_cures_him_and_pays_three` (balance `-10 + 3`, `sniffles_left == 0`, House post with `medicine.png`, no pings); `test_a_second_buyer_is_refused_before_paying` (after a cure, the next buyer's balance is unchanged and they see "♪ Wisp doesn't have a cold right now."); `test_two_buyers_at_once_pay_once` (`asyncio.gather`: one balance moves); `test_medicine_needs_enough_coins` (balance 9: refused, still sick).
- [ ] **Step 2:** Run `tests/test_snacks.py tests/test_vault.py`. Expected: FAIL.
- [ ] **Step 3:** Implement. Check the fullest Vault still fits `LAYOUT_TEXT_LIMIT` (the existing gift room math takes the new piece into account).
- [ ] **Step 4:** Run `tests/test_snacks.py tests/test_vault.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: medicine cures his cold`.

---

### Task 11: The status card shows Health, Wellbeing and Mood

**Files:**
- Modify: `wisp/card.py`
- Test: `tests/test_card.py`

**Interfaces:**
- Consumes: `has_sniffles`, `MOOD_MAX`, `HEALTH_MAX`, `WELLBEING_MAX`.
- `wisp/card.py`: the emoji dataclass `Meter` is renamed `BarEmoji` (no clash with `life.Meter`); constants `HEALTH_BAR = BarEmoji("full_full", "full_left")`, `WELLBEING_BAR = BarEmoji("care_full", "care_left")`, `MOOD_BAR = BarEmoji("happiness_full", "happiness_left")`; the egg's Warmth bar uses `HEALTH_BAR`, Hatching and Emerging use `MOOD_BAR`, as today's colours. A living Wisp's bars, in order: `Health`, `Wellbeing`, `Mood`. Under the DAY line, while he has a cold: `f"{SUB_CLEF} he has a cold・{hours} h left"` with `hours = math.ceil(life.sniffles_left / 3600)`.

- [ ] **Step 1: Write the failing tests:** `test_the_bars_are_health_wellbeing_then_mood_in_their_meters` (replaces the care/happy/hunger test: labels, order, emoji names, percents from `health`, `wellbeing`, `mood_meter`); `test_a_card_with_a_cold_says_hours_left_under_the_day` (`sniffles_left=129600.0` → `he has a cold・36 h left`); `test_a_well_wisp_has_no_cold_line`; the fullest-card test adds a cold.
- [ ] **Step 2:** Run `tests/test_card.py`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `tests/test_card.py tests/test_life_loop.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: the card shows Health, Wellbeing and Mood`.

---

### Task 12: The words members and staff read

**Files:**
- Modify: `cogs/studio.py` (`rules_text`, `freeze`, `unfreeze`), `DOCS/wisp_tamagotchi.html`, `DOCS/wisp_faq.html`, `README.md`, `DOCS/BuildRulings.md`
- Test: `tests/test_studio.py`

**Interfaces:**
- `rules_text`: "His meters" explains Health (tracks; every 6 h without one costs 8; hangry when low; dies at 0), Wellbeing (chats, 3 a day each; snacks; gifts; cleanups; low is lonely), Mood (rhyme duels and pokes, 3 a day; Rockstar needs it high); a new "Chores" section: first press earns points; clean up messes or he catches a cold, medicine cures it; scold tantrums; turn off the lights at naps (02:00, 10:00, 18:00 UTC). Every number from `rules` (the hours from `NAP_HOURS`). The Monster Pox line says the Health penalty is bigger, not "faster drain". Shorten other lines as needed: it must still fit `MESSAGE_LIMIT` with every number at four digits.
- `freeze`/`unfreeze` replies: `♪ Wisp is frozen. His meters and chores pause until you unfreeze him.` / `♪ Wisp is unfrozen. His meters and chores run again.` (docstrings to match).
- Docs: in `DOCS/wisp_tamagotchi.html` and `DOCS/wisp_faq.html` replace every Hunger/Happy/Care/drain explanation (meters section, snack table header "Wellbeing" with +8 for every snack, gifts, duels, Rockstar 80+ Mood for 4 days, Monster Pox, freeze, the card mock-up's bars), and add the chores, the cold and medicine. README "His three meters", the poke paragraph (no sleepy hours; timed naps), the art list (`poop.gif`, `wispsick.gif`, `medicine.png`, tantrum pictures) and the `medicine` emoji. `DOCS/BuildRulings.md`: a new section `## Meters and chores (2026-11-02)` with one dated line per decision in this plan's "Decisions" list, each with its cost if wrong.
- FAQ pictures: list every `ASSETS/faq/*.png` whose text mentions Hunger, Happy, Care, Full, drain or sleepy hours (map `DOCS/wisp_faq.html` sections to their banner files); the list goes into the CHANGELOG entry in Task 13. Do not edit the pictures.

- [ ] **Step 1: Write the failing tests** in `tests/test_studio.py`: update `test_rules_text_explains_the_three_meters` to Health, Wellbeing, Mood with their numbers; add `test_rules_text_explains_the_chores` (mentions cleanup, cold, medicine with `MEDICINE_COST`, tantrum, lights and each of `NAP_HOURS`); `test_rules_text_fits_with_every_number_at_four_digits` adds the new numeric rules to its monkeypatched list; `test_freezing_says_meters_and_chores_pause`.
- [ ] **Step 2:** Run `tests/test_studio.py`. Expected: FAIL.
- [ ] **Step 3:** Implement the code and the four documents.
- [ ] **Step 4:** Run `tests/test_studio.py tests/test_staff.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `docs: meters and chores in every explanation`.

---

### Task 13: Staff can test every chore

Myra asked (2026-11-04) for a quick way to see every chore without waiting for one: `!wisp test_chore`, next to `!wisp test_lifestage`.

**Files:**
- Modify: `wisp/chores.py`, `cogs/life_loop.py`, `README.md` (staff commands)
- Test: `tests/test_chores.py`, `tests/test_life_loop.py`

**Interfaces:**
- Consumes: Task 6 (`tick_chores`, `is_open`, `ChoreEvent`), Task 8 (`post_chores`), `catch_sniffles` (Task 3), `jump_to` and the `test_lifestage` patterns already in `cogs/life_loop.py` (`StaffContext`, `reply`, `guild_of`, an `Annotated` converter raising `BadArgument`, `usage=`).
- `wisp/chores.py`: the code that opens a chore inside `tick_chores` moves into three public functions that `tick_chores` now calls, so the test and the real thing are the same code: `open_mess(life: Life) -> ChoreEvent` (clears `mess_in`; `mess_left = MESS_LEFT_FOR`, `mess_gap = MESS_GAP`, `mess_message_id = None`), `open_tantrum(life: Life) -> ChoreEvent` (`tantrum_left = TANTRUM_WINDOW`, `tantrum_message_id = None`; rolling the next due time stays in `tick_chores`), `start_nap(life: Life) -> ChoreEvent` (`nap_left = NAP_FOR`, `lights_left = LIGHTS_WINDOW`, `nap_message_id = None`). New `run_out(life: Life) -> timedelta`: the counted time until every open window (`mess_left`, `tantrum_left`, `lights_left`) has run out, i.e. the largest of them as a timedelta, or zero when none is open.
- `cogs/life_loop.py`, new section `# Testing a chore` beside `# Testing a life stage`: `_TEST_CHORES: Final = ("mess", "tantrum", "nap", "cold", "late")`, `usage=f"<{'|'.join(_TEST_CHORES)}>"`, a converter lowercasing like `_test_step`. `@commands.command(name="test_chore")`: under the guild lock, on the current ALIVE life:
  - `mess`: `open_mess` (the mess of his current stage, from `MESSES`); `tantrum`: `open_tantrum`; `nap`: `start_nap`. Each refused with `♪ That chore is already waiting in the House.` when it is already open (for nap: while he naps).
  - `cold`: `catch_sniffles`; `SNIFFLES` event when it returns True, else refused with `♪ Wisp is already sick.`
  - `late`: `events = tick_chores(life, now, run_out(life), rng, frozen=False)`, fast-forwarding chore time so every open chore runs out the way it does for real (left-too-long mess and its cold, missed tantrum, missed lights). Refused with `♪ No chore is waiting to run out.` when `run_out` is zero.
  - Save, then outside the lock `post_chores(bot, guild_id, life, events)` and `self._tick_guild(guild_id, now)` so the card catches up, then reply `♪ Test: Wisp made a mess.` / `♪ Test: Wisp is having a tantrum.` / `♪ Test: Wisp is taking a nap.` / `♪ Test: Wisp caught a cold.` / `♪ Test: every waiting chore ran out.`
  - Refused before any change with `♪ Unfreeze Wisp first: his chores only run while time passes.` while frozen, and `♪ Wisp has to be hatched and alive to test a chore.` when there is no living Wisp. A bad step gets the usage line like `test_lifestage`.
- `README.md`: list `!wisp test_chore <mess|tantrum|nap|cold|late>` with `!wisp test_lifestage`, one line on each step, and the tip that `!wisp test_lifestage baby` first shows the poop.

- [ ] **Step 1: Write the failing tests.** `tests/test_chores.py`: `test_open_mess_tantrum_and_nap_are_what_the_tick_does` (each returns its event kind and sets the same fields the tick sets); `test_run_out_is_the_longest_open_window` (mess 3 h left and lights 10 min → 3 h; nothing open → zero). `tests/test_life_loop.py`, with the `frozen_clock` fixture and a `type_chore` helper like `type_lifestage`: `test_test_chore_mess_posts_the_mess_of_his_stage` (a Baby gets `poop.gif` and a `Clean up` button; a Teen gets `pimple.gif` and `Hand him face wash`); `test_test_chore_tantrum_and_nap_post_their_buttons` (parametrized: `Scold`, `Lights off`); `test_test_chore_cold_gives_him_a_cold_and_posts_it` (`sniffles_left == SNIFFLES_FOR` seconds, `wispsick.gif` post); `test_test_chore_late_runs_out_an_open_mess_into_a_cold` (after `mess`, `late` edits the mess post and posts the cold); `test_test_chore_refuses_an_open_chore_twice`; `test_test_chore_refuses_late_with_nothing_open`; `test_test_chore_refuses_while_frozen` (nothing changes); `test_test_chore_needs_a_living_wisp`; `test_test_chore_takes_any_case_and_rejects_unknown_steps` (usage line names all five steps).
- [ ] **Step 2:** Run `tests/test_chores.py tests/test_life_loop.py`. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run `tests/test_chores.py tests/test_life_loop.py tests/test_chore_posts.py`. Expected: PASS. Quality tools.
- [ ] **Step 5:** Commit `feat: staff can test every chore`.

---

### Task 14: Changelog and ship

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1:** Run every test file this plan touched, one pytest process: `tests/test_life.py tests/test_chores.py tests/test_chore_posts.py tests/test_repos.py tests/test_schema.py tests/test_card.py tests/test_bond.py tests/test_lines.py tests/test_voice.py tests/test_announce.py tests/test_assets.py tests/test_conversation.py tests/test_players.py tests/test_snacks.py tests/test_vault.py tests/test_feeding.py tests/test_gifts.py tests/test_rhyme_duel.py tests/test_life_loop.py tests/test_studio.py tests/test_staff.py tests/test_app.py tests/test_rules.py`. Expected: all pass. Then the whole suite once, in the background (about 1 h 50 min). Run the four quality tools. Expected: clean.
- [ ] **Step 2:** Add `## 2026-11-02 (Meters and chores)` at the top of `CHANGELOG.md`: the three meters and what fills and empties each (with the numbers), credits per day, chores and their points, the cold and medicine, naps replacing the sleepy hours, the additive columns, the decisions list in short, `!wisp test_chore`, and two lists for Myra: the FAQ pictures to re-render (from Task 12) and the missing nap pictures (Teen, Adult, Rockstar and Old Fogey have no nap art; `NAP_STAGES` would need them added).
- [ ] **Step 3:** Commit `docs: changelog for meters and chores`.
- [ ] **Step 4 (controller):** Do the `medicine` emoji upload from Task 10 if it is not done yet.
- [ ] **Step 5 (controller):** `git push origin main` (SSH remote; fps.ms deploys it). Never start a local copy.
- [ ] **Step 6 (controller):** Post the changelog note in the ViiBR Assets changelog channel (`1563692224003313724`).
