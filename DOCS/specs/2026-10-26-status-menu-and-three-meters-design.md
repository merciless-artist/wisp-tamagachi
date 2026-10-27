# Status menu and three meters: design

Agreed with Myra on 2026-10-26. Wisp is live in ViiBR Assets with real data, so
everything here must migrate the live database safely.

## Why

- Myra designed a new status menu and posted it in `ℹ️｜feedback・bug-reports`
  (ViiBR Assets channel 1564098843656720434, message 1564178319543369733).
  The current card and the `・♪ ────────・──────── ♪・` divider look messy to her.
- "Care" did not read as food to her, so it won't to members either.
- She wants pokes and chats to mean something, very rate-limited.
- Games and gifts get their own meter, so playing with Wisp is visible.

## Goals

1. Three meters with clear jobs: **Full** (food), **Happy** (pokes and chats),
   **Care** (rhyme duels and gifts).
2. The status card follows Myra's template.
3. A new divider everywhere.
4. A member's first poke or chat of the UTC day earns them 1 point and counts
   toward Happy.
5. Games pay: each rhyme duel that records a PLAY interaction earns the member
   1 point (Myra: "people will get salty if their interactions mean
   nothing"). PLAY is already limited to `PLAYS_PER_DAY` (5) per member and to
   members who pass `can_feed`, so that is at most 5 points a day from duels.
   Add `PLAY_POINTS = 1` to rules.py.
6. A childhood cold, once per life (see below).

## Non-goals

- No new ways to die. Only Full can kill him, as today.
- No change to how tracks, snacks, growth thresholds or bond work, except
  where written below.
- No help menu. Bare `!wisp` stays reserved for Myra's PNG menu.

## Anti-goals (a failure even if it works)

- Pokes or mentions that can be farmed: anything beyond one credit per person
  per UTC day.
- A migration that renames or drops a live column, or a startup that refuses
  to start on the live database.
- A status card over Discord's 2,000 limit (count with `text_length`).

## The three meters

### Full (food)

- The existing food meter, renamed from Care to Full. Same behaviour: it fills
  from tracks and snacks, drains `CARE_DRAIN_PER_DAY` (Old Fogey: the old-fogey
  drain), makes him hangry below `HANGRY_BELOW`, and he dies at 0.
- Every member-facing "care" that means food becomes "full", e.g.
  "♪ Wisp ate your Cheese ・ full +8" and the Vault dropdown descriptions.

### Happy (pokes and chats)

- A member's **first poke or first mention-chat of the UTC day** records a new
  interaction kind, `CHAT`, and gives them **1 point** (spendable in the Vault).
  Later pokes and chats that day record nothing and give nothing.
  The existing per-member `TALK_COOLDOWN` and poke behaviour are unchanged.
  **Only members who pass `can_feed` and are not banned earn the credit**
  (Myra, 2026-10-26; same rule as play credit, ruling I3). Everyone else can
  still poke and chat for fun. Check it in both the poke path and the
  mention path.
- Happy = distinct members with a `CHAT` interaction in the last
  `HAPPINESS_WINDOW` (24 h), full at `HAPPY_FULL_AT_PEOPLE` (5). Same formula as
  `wisp.bond.happiness`, fed only by CHAT rows.
- Happy still drives Rockstar (`ROCKSTAR_HAPPINESS` for `ROCKSTAR_HAPPY_FOR`).
  Myra knows this means Rockstar now comes from many people saying hi.
- A CHAT credit counts toward Wisp learning a member's name (`distinct_days`).
- A CHAT credit does **not** count toward: growth caretakers, the "fed by"
  line, `latest_interactor` (the stage-up keepsake), bond, growth points, or
  the leaderboards. (Controller's call, from the agreed "no growth".)
- Points earned from chats and duels are ordinary Vault points. Whether they
  count toward the "This life" and "All time" leaderboards follows however
  `add_points` already feeds those boards; do not add a separate path.

### Care (rhyme duels and gifts)

- A new 0 to 100 meter on each life. Starts at `CARE_START` (50) when he
  hatches. Drains `CARE_DRAIN_PER_DAY_NEW` per day while alive.
- Fills by `CARE_PER_PLAY` each time a rhyme duel records a PLAY interaction
  (already capped by `PLAYS_PER_DAY` per member), and by `CARE_PER_GIFT` each
  time a member buys a gift: kept, passed, or turned away because he already
  kept one today (`Outcome.FULL`), since the points are spent either way.
  (Controller's call.)
- Below `LONELY_BELOW` (30) his mood is **LONELY**: grumpy or lonely in what he
  says. It never hurts him: no death, no growth penalty.
- Mood precedence: HANGRY (Full low) beats LONELY (Care low) beats HAPPY.
- When Care first drops below the line, he posts a LONELY moment in the House
  once (warn once per drop, like HUNGRY), with a picture for his stage picked
  at random from that stage's set (all in `ASSETS/moments/`, already there):
  - Baby: `cry_baby.gif`, `grumpy_baby.png`
  - Child: `grumpy.gif`
  - Teen and older: `cry_teen.gif`
  Keep the stage-to-pictures table in one place (rules.py or next to the
  nap-picture rule) so Myra can add pictures later. (Mapping is the
  controller's call.)
- The AI voice is told he is lonely and grumpy when LONELY. Canned lines: a
  moment without LONELY lines falls back to its HAPPY lines; add LONELY lines
  for the new LONELY moment and for poke and talk fallbacks.

All new numbers live in `wisp/rules.py` (starting values; Myra may tune):
`CARE_START = 50`, `CARE_DRAIN_PER_DAY_NEW = 10`, `CARE_PER_PLAY = 10`,
`CARE_PER_GIFT = 8`, `LONELY_BELOW = 30`, `CHAT_POINTS = 1`. Name them better if
you like; keep them in rules.py.

## The childhood cold

Myra, 2026-10-26: "once per life cycle, he should get a cold", "at random
sometime before he is an adult, like the chicken pox", "people can give him
extra food during that time, he might need an extra song and snack", "he
won't die from it", "two days is good".

- **When:** exactly once per life, at a random moment while he is a Baby,
  Child or Teen. Pick the moment so that every life that reaches Adult has had
  its cold (for example, roll the start time when he hatches, inside the time
  he is guaranteed to spend before Adult, or roll a per-tick chance that rises
  to certain before he can grow to Adult). A life that dies before then may
  never catch it. Never while frozen, and never twice.
- **How long:** `SICK_FOR = timedelta(hours=48)`, then he is better on his
  own. If he grows a stage while sick, the cold carries on.
- **Hungrier:** while sick, Full drains `SICK_DRAIN_MULTIPLIER` (1.5) times as
  fast.
- **Room for extra food:** while sick, each member's daily meal cap
  (`DAILY_MEAL_CAP`, 15 meal points) is raised by `SICK_EXTRA_MEAL_CAP` (15),
  room for about one extra song and one extra snack. (Numbers are the
  controller's call.)
- **He can't die of it:** while sick, Full never drops below 1, so neither the
  cold nor normal drain can kill him during those two days. The normal rules
  come back when he is better. He can still be hangry and fading, and those
  warnings still post.
- **Posts:** one House post when he catches it ("SICK") and one when he is
  better ("RECOVERED"), canned lines plus the AI voice like other moments.
  The SICK post attaches the sick picture for the stage he is in when he
  catches it: `ASSETS/moments/sick_baby.png`, `sick_child.png`,
  `sick_teen.png` (all three are in the repo, uncommitted; commit them with
  this work). Text only if a file is missing. The status card shows the same picture while he is
  sick. While sick his AI voice is sniffly and sneezy.
- **Card:** the status card shows he is sick, for example a line under the DAY
  line such as `・he has a cold・{hours} h left`, keeping Myra's frame style.
- **Storage:** the life needs when the cold started (NULL if not yet) so it
  can never happen twice; add columns the same additive way as below.

### Storage

- The live `lives.care` column keeps storing the food meter (Full). Do not
  rename it. Add a new column for the new Care meter (name it, e.g. `fondness
  DOUBLE NOT NULL DEFAULT 50`) through both `_DEFINITIONS` and
  `_ADDED_COLUMNS`, plus a flag column for the lonely warning if needed.
- In code, name things after what members see (`full`, `care`), and map the
  columns in one place in the lives repo with a short note on the mapping.
- `InteractionKind.CHAT = "chat"` fits the existing `kind VARCHAR(8)`.

## The status card

Follow Myra's template exactly. She edited it on 2026-10-26 13:23 UTC (removed
the 🌸 and 🕯️ side decorations); the exact edited text, every space and
symbol, is saved in `DOCS/specs/status_menu_template.txt` (fetched from the
message with Wisp's token). Copy from that file, not from memory, so nothing
is normalised. Changes from the template, agreed with Myra:

- The three bars are, in this order: `・Full` 🟦, `・Happy` 🟪, `・Care` 🟥. Keep
  her label padding style (pad so the bars start in the same column as her
  example). A bar is one square per 10%, rounded half up, filled squares only
  (0% shows no squares), then `│{percent}%`.
- `𝐃𝐀𝐘 **{age_days}**`.
- "Fed by {n:02d} people today": distinct members today (UTC) with a FEED,
  SNACK or FREE_SNACK interaction. "person" when n is 1.
- "{v} ViiBR tracks and {s} Suno tracks": tracks fed today (UTC), counted from
  the `feeds` table by the `viibr:` / `suno:` prefix of `track_key`. Singular
  "track" for 1.
- The hint lines use the real Wisp mention `<@bot user id>` and the guild's
  House channel `<#house_channel_id>` from settings, and say `/wisp snackpack`
  (there is no `/snackpack`).
- `**life stage**・{stage in Mathematical Bold capitals}` (𝐁𝐀𝐁𝐘, 𝐂𝐇𝐈𝐋𝐃, 𝐓𝐄𝐄𝐍,
  𝐀𝐃𝐔𝐋𝐓, 𝐑𝐎𝐂𝐊𝐒𝐓𝐀𝐑, 𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘).
- Label padding: her 6, 3 and 1 spaces were tuned by eye in Discord's
  proportional font. Start from those for Full, Happy and Care and from the
  same idea for the egg labels; Myra checks alignment in Discord and the
  padding is adjusted from her screenshot. (Controller's call.)
- **Egg** and **hatching** cards use the same frame. The DAY line stays out;
  the bars are `・Warmth` 🟧 and `・Hatching` 🟨 (egg) or `・Emerging` 🟨
  (hatching; colours are the controller's call),
  same math as today's card; the life stage reads 𝐄𝐆𝐆 or 𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆; the
  first hint says "Poke the egg" instead of "Poke him". The fed-by and tracks
  lines stay.
- The card is posted wherever it is today (Status thread, `/wisp status`) and
  keeps its picture and buttons. Keep it under 2,000 by `text_length`.

## The divider and emoji

- `wisp.text.SEPARATOR` becomes `❱❱━━━━━━━━━━━━━━━━━━━━━━━━━━❰❰` everywhere
  Wisp uses it. Myra's card has its own longer frame lines; those stay as in
  her template.
- Unicode emoji are now allowed in Wisp's **designed** text: the status card,
  the divider, and anything Myra designs. The **AI voice stays emoji free**:
  keep the "No Unicode emoji" prompt rule and `strip_emoji` on AI replies, and
  keep canned lines emoji free. (Controller's call.) Update `CLAUDE.md` to say
  exactly that, and change "no Unicode emoji" test checks only for the card
  and divider.

## Words members read

Update every place that explains the meters: the How Wisp Works / FAQ text in
`cogs/faq.py` and `cogs/studio.py`, the spec page `DOCS/wisp_tamagotchi.html`,
README, and `DOCS/BuildRulings.md` (add the rulings above). The FAQ pictures in
`ASSETS/faq/` are rendered by the controller from `wisp_faq.html`; list every
picture whose text mentions Care, Happy or feeding so it can be re-rendered.

## Left to the builder

- Column and enum names, the exact LONELY lines, where the lonely flag lives.
- How the card code is split between `wisp/card.py` and `cogs/players.py`.
- Test layout. Tests run against the real database (`wisptest_` tables).

## Process

- Live database: additive migration only, checked by the startup schema check.
- Run only the affected test files plus black, isort, flake8, mypy --strict
  with `PYTHONUTF8=1`. Never two pytest processes at once.
- CHANGELOG entry. Commit; the controller pushes, restarts Wisp by recorded
  PID and posts the changelog note.
