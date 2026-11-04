# Meters and chores: design

Agreed with Myra on 2026-11-02. Replaces the meter section of
`2026-10-26-status-menu-and-three-meters-design.md`. Wisp is live with real
data, so every storage change is additive and migrates the live database
safely.

This is the first of five projects Myra lined up on 2026-11-02, in this order:

1. **Meters and chores** (this document).
2. Games: a PLAY button offering Rhyme Duel, Wisp's Craving and Wisp's Mood.
3. Channel redo: the Leaderboard under Wisp Stats; the ViiBR Vault post with
   FEED / POKE / PLAY.
4. Emoji menu frames from Myra's app emojis.
5. Rename Mealtime to Mealtime Music.

Nothing here builds projects 2 to 5, but the meter hooks below must be easy
for project 2 to call.

## Why

- The Happy meter sits at 20 or less. It only counts how many different
  people chatted with Wisp in 24 hours (5 fills it), so with a handful of
  members it can never fill.
- Myra wants meters that move because of what people do or don't do, not a
  people count and not a slow drain.
- She looked up how real Tamagotchis are kept alive and wants the classic
  chores: cleaning up after him, disciplining him, and turning off the lights
  when he sleeps.

## Goals

1. Three meters, renamed and re-wired (Myra's words):
   - **Wellbeing** (was Care): chatting, snacks.
   - **Mood** (was Happy): playing games, getting pokes.
   - **Health** (was Full, the food meter): track drops.
2. Meters move only in steps: a plus for something done, a minus for something
   not done. **No continuous drain.**
3. Three chores, each a first-come button race in Wisp's House: **cleanup**,
   **scold** (discipline) and **lights off** (naps).
4. A new illness, **a cold**, caught from a mess left too long and cured with
   **medicine** bought in the shop.

## Non-goals

- No new ways to die. Only Health can kill him, as today.
- Monster Pox is unchanged: random, once per life (Myra, 2026-11-02).
- The games, the PLAY button and the Vault and Stats layout (projects 2 and 3).
- No change to growth thresholds, bond, the snack menu or track points except
  where written below.

## Anti-goals (a failure even if it works)

- Anything a member can farm: every plus below has a per-member daily limit.
- A migration that renames or drops a live column, or a startup that refuses
  to start on the live database.
- A meter that only ever goes up on an active server and makes Rockstar
  automatic.
- Two features called "cold" in code that a reader can't tell apart (see
  Naming).

## Naming

- Monster Pox is already called `cold` in the code (`COLD_EARLIEST`,
  `SICK_FOR`, `schedule_cold`, `is_sick`, ...). The new cold is called
  **`sniffles`** in code (`SNIFFLES_FOR`, `has_sniffles`, ...) and "a cold" in
  everything members read. Do not rename the Monster Pox code or its columns.
- Member-facing words: Wellbeing, Mood, Health, a cold, medicine, mess,
  cleanup, tantrum, scold, nap, lights off.
- The snack game in project 2 is also called "Wisp's Mood". Myra is fine with
  that: playing it fills the Mood meter.

## The meters

All three run 0 to 100 and start at 50 when he hatches. All numbers live in
`wisp/rules.py`; the values here are starting values (all **my call**, marked
so Myra can veto them).

### Health (was Full)

- The existing food meter, stored in the live `lives.care` column as today.
- **Up:** every fed track adds its meal points, as today, inside the existing
  daily meal cap. **Snacks no longer fill Health**: Myra put snacks under
  Wellbeing. Snacks keep their coin prices; what they add moves to Wellbeing.
- **Down:** remove the continuous drain (`FULL_DRAIN_PER_DAY`,
  `OLD_FOGEY_FULL_DRAIN_PER_DAY`). Instead, every **6 hours with no track fed**
  costs **8** (Old Fogey: 6). A "6 hour stretch" is counted from the last
  track, or from the last penalty, whichever is later. **My call.**
- Hangry below 30, fading below 10, and death at 0 stay as today. Monster
  Pox's floor of 1 stays.
- Monster Pox's "drains 1.5 times as fast" becomes: while he has Monster Pox,
  the empty-stretch penalty is 1.5 times as big (12). **My call.**

### Wellbeing (was Care)

- Stored in the existing Care column (added on 2026-10-26).
- **Up:**
  - A chat (a mention of Wisp in his House that he answers): **+5**, for a
    member's first **3** chats of the UTC day. **My call.**
  - A snack given (paid or free): **+8**, whatever snack it is. **My call.**
    The Snack Pack and Vault texts that say "full +N" for snacks change to
    Wellbeing. Snacks **still count against the member's daily meal cap**
    exactly as today (same meal points, same "full from you today"
    refusal), so they keep their daily limit; only the meter they fill
    changes. **My call.**
  - A gift bought: **+8**, as Care is today. Myra listed only chats and snacks;
    gifts are things you give him, like snacks. **My call.**
  - A mess cleaned up: **+5**. **My call.**
- **Down:**
  - Every **6 hours with nobody chatting** costs **10**. **My call.**
  - While he has a cold, that penalty is **doubled** (20) (Myra agreed:
    "Wellbeing drains faster").
- Below 30 he is LONELY, as Care is today (his voice only, never harm).

### Mood (was Happy)

- A new stored meter (the old Happy was computed from a people count).
- **Up:**
  - A counted Rhyme Duel: **+10** (already limited to 5 per member per day).
    **My call.** Project 2 adds Wisp's Craving and Wisp's Mood here.
  - A poke: **+5**, for a member's first **3** pokes of the UTC day. A poke
    that wakes him from a nap gives nothing (see Naps). **My call.**
- **Down:**
  - An unscolded tantrum: **−15**. **My call.**
  - Lights not turned off for a nap: **−10**. **My call.**
  - Every **6 hours with no game and no poke**: **−10**. Myra's table had only
    the chore minuses for Mood; without this one, Mood on an active server
    only climbs and Rockstar becomes automatic (an anti-goal). **My call.**
- Rockstar keeps its rule with Mood in place of Happy: Mood at 80 or more for
  4 days.
- Mood precedence for his voice stays: HANGRY (Health low) beats LONELY
  (Wellbeing low) beats HAPPY.

### Empty stretches and time

- Every "6 hours with no ..." stretch, every chore deadline (mess 6 hours,
  tantrum and lights 15 minutes) and the cold's 48 hours run on **counted
  time**, the same way Monster Pox counts down today: at most
  `MAX_CREDITED_GAP` per tick, nothing while frozen, nothing during an outage.
  Freezing keeps its promise that his meters don't drop. Store time left, not
  deadlines, where that is what makes this work. **My call.**
- Exception: the nap **start times** (02:00, 10:00, 18:00 UTC) are wall-clock.
  A nap whose start falls while he is frozen or the bot is down is skipped,
  with no penalty.
- Only **credited** actions end a stretch: a track that fed him, or a chat,
  snack, game or poke that earned a meter plus. A member who can't earn, or a
  member past their 3 a day, does not reset the clock, so casual pokes can't
  hold Mood up forever. **My call.**

### Who earns pluses and points

- Only members who pass `can_feed` and are not banned earn meter pluses and
  chore points, as with play and chat credit today. Anyone may still poke, chat
  and press buttons for fun; a member who can't earn gets a short private
  "only members who can feed Wisp earn points" reply on a chore button.
- Chore points are ordinary points through `add_points` (Vault coins and the
  leaderboards, as chat and play points are today).

## Chores

Every chore posts in Wisp's House, never pings anyone, and has one button. The
first eligible member to press it wins; the post is edited to say who did it
and the button is removed. Later presses get a short private "already done"
reply. A chore never posts while he is an egg, hatching or frozen.

### Messes (cleanup)

- **When:** a random **30 to 90 minutes after a track is fed**, he leaves a
  mess. At most **one mess at a time**, and at least **6 hours** between
  messes, so about 2 or 3 a day on a busy day. **My call.**
- **The mess grows up with him (Myra, 2026-11-03).** Same rules at every
  stage; only the picture, the words and the button change:

  | Stage | Mess | Button | Picture |
  |---|---|---|---|
  | Baby, Child | poop | **Clean up** | `poop.gif` |
  | Teen | a zit breakout | **Hand him face wash** | `pimple.gif` |
  | Adult | takeout boxes and dirty dishes | **Take out the trash** | `trash_adult.gif` (Myra, 2026-11-04) |
  | Rockstar | he trashed the green room after a show | **Clean the green room** | `trash_rockstar.gif` (Myra, 2026-11-04) |
  | Old Fogey | dentures that need a soak | **Soak his teeth** | `dentures.gif` |

  Until a stage's picture exists, its post is the words and the button alone.
- **Post:** the stage's picture (the poop GIF is at
  `C:\Users\Merci\Downloads\VIIBR\viibrmascot\poop.gif`; copy it into
  `ASSETS/moments/`), a short canned or AI line, and the stage's button.
- **Reward:** **2 points** and **+5 Wellbeing**. **My call.**
- **Left too long:** if a mess is still there after **6 hours**, he catches a
  cold and the mess post is edited to say so. The mess then counts as gone (no
  second cold from the same mess). **My call.**

### A cold (sniffles)

- **Catch:** only from a mess left 6 hours. Not while he already has a cold,
  and not while he has Monster Pox.
- **While he has it:**
  - The Wellbeing empty-stretch penalty is doubled.
  - His AI voice is stuffy and sneezy, like Monster Pox.
  - The status card shows a line such as `・he has a cold`.
  - His picture is Myra's sick GIF, `wispsick.gif` (she supplied it at
    `C:\Users\Merci\Downloads\VIIBR\viibrmascot\wisp_tamagachi\wispsick.gif`;
    copy it into `ASSETS/moments/`).
- **Post:** one House post when he catches it, with the GIF.
- **Cure:** **medicine**, a shop item for **10 wisp coins**, shown in the shop
  only while he has a cold. The first member to buy it gives it to him: the
  cold ends at once, they get **3 points**, and he posts a short thank-you. A
  second buyer in the same moment is refused before paying. **My call** on the
  price and points.
- **On its own:** the cold wears off after **48 hours** if nobody gives
  medicine. It never kills him.
- **Medicine art:** Myra's bottle, `NOT FOR HUMAN CONSUMPSTION.png`
  (`C:\Users\Merci\Downloads\VIIBR\viibrmascot\wisp_tamagachi\`). Use it as
  the medicine's picture where items show pictures, and upload it, scaled down
  whole (no crop), as an app emoji named `medicine` for the shop dropdown.
  Myra can swap in her own emoji-sized version later. **My call.**

### Tantrums (scold)

- **When:** about **once a day**, at a random time while he is awake (never
  during a nap), he throws a fit for no reason. **My call.**
- **Post:** a grumpy picture for his stage, a whiny line, and a **Scold**
  button. Baby `tantrum_baby.gif`, Child `grumpy.gif`, Teen `cry_teen.gif`,
  Adult and Rockstar `grumpy_adult.gif`, Old Fogey `grumpy_old_fogey.gif`.
  The new GIFs are Myra's videos, keyed
  to transparent 320×320 GIFs on 2026-11-02 and already in
  `ASSETS/moments/`.
- **Window:** **15 minutes** (Myra: "right now it is just me and a few ppl but
  when its a whole server it will be faster"). Keep it in `rules.py`; she may
  stretch it while the server is small.
- **Scolded:** **2 points**; he pouts, then settles down.
- **Missed:** **−15 Mood**, and he is **spoiled** for the rest of the UTC day:
  his AI voice is told he is extra bratty.

### Naps (lights off)

- **When:** three timed naps a day at **02:00, 10:00 and 18:00 UTC**, **1
  hour** each (Myra: three a day, UTC; times and length are my call).
- **Post:** when he dozes off, a sleepy picture and a **Lights off** button.
  `nap.gif` exists for Baby and Child; other stages are text only until Myra
  adds art (list the missing pictures in the handover).
- **Window:** **15 minutes**, like tantrums.
- **Lights off:** **2 points**.
- **Missed:** **−10 Mood**, and he wakes up grumpy: for 1 hour after the nap
  his voice is cranky.
- **While asleep:** he answers chat only with sleepy noises (no AI chat
  credit), and a poke wakes him early, cranky, with no Mood plus. The nap then
  ends. If the lights were still on, the Lights off post is edited to say he
  was woken, the button goes, and **nobody is penalised** (no Mood minus): the
  poker already lost their plus and woke him cranky. **My call.**
- The timed naps replace the "sleepy hours" poke reactions
  (`POKE_SLEEP_HOURS`). The "House has gone quiet" nap (`POKE_SLEEP_AFTER`)
  stays as it is. **My call.**

## Storage

- Additive only, through both `_DEFINITIONS` and `_ADDED_COLUMNS`, checked by
  the startup schema check. Never rename or drop a live column.
- New on the life: Mood, when each meter last took its empty-stretch penalty,
  the open mess (posted at, message id), the cold (started at), today's
  tantrum and nap state (message ids and deadlines), and the "spoiled until" /
  "cranky until" times.
- Per member per day: chat and poke credit counts (3 each). Use the existing
  interactions table if it fits; otherwise a small new table.
- Pending chores must survive a restart: on startup, reload open messes,
  tantrums and naps from the database and reattach their buttons
  (persistent views with custom ids that carry the life id).

## Words members read

Update every place that explains the meters or chores: the status card labels
and bars (Health, Wellbeing, Mood, in that order), the FAQ text in
`cogs/faq.py` and `cogs/studio.py`, `DOCS/wisp_tamagotchi.html`, README and
`DOCS/BuildRulings.md`. List every FAQ picture in `ASSETS/faq/` whose text
mentions Full, Happy or Care so Myra can re-render it.

## Left to the builder

- Column, enum and table names (except the `sniffles` rule above).
- The exact canned lines and AI prompt wording for messes, colds, tantrums,
  naps, spoiled and cranky.
- How the empty-stretch penalties are checked (the life loop's 5-minute tick
  is the natural place).
- Test layout. Tests run against the real database (`wisptest_` tables).

## Process

- Run only the affected test files plus black, isort, flake8 and mypy --strict
  with `PYTHONUTF8=1`. Never two pytest processes at once.
- CHANGELOG entry. Commit and push to main (fps.ms deploys it), then post the
  changelog note.
