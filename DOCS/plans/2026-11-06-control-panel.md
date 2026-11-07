# Control panel and clarity: build plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** One place to do everything with Wisp (the Status post), a Leaderboard
post that reposts at the bottom when it changes, and members always told what
happened and, when something did not work or did not count, exactly why.

**Spec:** none written. Myra agreed every point below in chat on 2026-11-06 and
told me to build it without a design document. Her words, in order:

- "all the functions for what you can do with him in one spot ... he should
  only tag in the house and then all the things that you can do with him should
  be in one spot with messages that pop up"
- "a row of buttons in the forum. one channel will have all his buttons and all
  the things" (the Status post; confirmed "yes")
- "the vault should not go away, let's just make it the LEADERBOARD"
- "JUST MAKE IT POST THE LEADERBOARD FRESH EVERY TIME IT REFRESHES AS A NEW
  POST, AND IT WILL SHOW UP AT THE BOTTOM"
- Sick: "whenever someone talks to him he should inform them he is sick"; he
  has "a few pics per sickness" plus the new `ASSETS/moments/sneeze.gif`.
- Monster Pox: "take out that he can get it in his teens ... it should just be
  baby and child after this"
- "people dont know what is happening ever ... infer my meaning" and "when
  things dont work tell them fucking why"

Calls I made (Myra delegated them): pop-ups are private; Wisp's public reactions
stay in the House; the leaderboard reposts only when its text changed and
deletes the old post; the Leaderboard post has no buttons; slash commands stay
as shortcuts; the Pox window becomes day 1 to 5; sick pictures are picked at
random from the sickness's pool; meter drops are announced in the House; a fed
track gets a reaction; a track that did not feed gets a reason in the House.

## Global Constraints

Every task's requirements include all of these. They come from the project's
`CLAUDE.md`, which every worker reads first.

- Python 3.13, discord.py 2.6.4. `mypy --strict wisp db cogs app.py config.py`,
  `black`, `isort`, `flake8` pass, run with `PYTHONUTF8=1`.
- Tests use the real database (`wisptest_` tables), never mock the database.
  Never run two pytest processes at once. The full suite takes over 2 hours;
  run only the test files you touch plus their neighbours.
- Every tunable number and every picture file name lives in `wisp/rules.py`.
- Bot text: bullet `・`, flair `♪`, no Unicode emoji in canned or AI text (Wisp's
  app emojis by name through `bot.emoji(...)` are fine), no embeds, no DMs,
  messages under 2,000 characters, house-style frame pieces from `wisp/text.py`.
- Users by Discord ID everywhere. All times UTC.
- Errors: plain text `Error in <context>: <Type>: <message>` where they happened.
- Storage changes are additive only: never rename or drop a live column. Wisp is
  live with real data.
- Section headers: a `# ---` rule, `# Section name`, a `# ---` rule.
- No comments that narrate the next line, no dead code, no blanket
  `except Exception`.
- Commit on `main` (the only branch), staged by explicit path, message ending
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Never commit
  `.env`, `CLAUDE.md`, `DOCS/wisp_prompts/`, `wisp/1.png`, `wisp/2.png`,
  `ASSETS/dances/` or anything under `.superpowers/`. Do not push.

## Review Focus

1. A member who presses a button but cannot do the thing (banned, no feeder
   role, no living Wisp, frozen, daily limit hit, not enough coins, already
   done) must get a private message naming that exact reason. Silence is a bug.
2. The leaderboard must never post twice in a row with the same text, and must
   never leave two leaderboards in the post (old one deleted; a failed delete is
   reported, not fatal).
3. Restarts: every new button is a persistent `DynamicItem` with a fixed custom
   id, like `FeedButton` in `cogs/snacks.py`, so old Status cards keep working.
4. The status card stays under 2,000 characters with every line showing
   (sick, cold, nap, mess, all three meters low).
5. A track post with no track link in it gets no House note at all.

---

### Task 1: Monster Pox only for a Baby or Child

**Files:** `wisp/rules.py`, `wisp/life.py`, their tests, `README.md`.

- `COLD_LATEST` becomes 5 days (a Teen cannot arrive before day 6: Baby and
  Child each take at least `STAGE_MIN_TIME`, 3 days). Update the comment above
  it to say why.
- The stages that can roll Pox (`_COLD_STAGES` in `wisp/life.py`) become Baby
  and Child only. A Wisp already sick keeps his Pox through a stage-up, as
  today, so `SICK_PICTURES` keeps its Teen entry.
- Tests: a Teen who has not had Pox never gets a due time; a Baby's due time is
  between 1 and 5 days after hatching; a Child whose Pox is running carries it
  into Teen.
- README "Monster Pox" paragraph: "between day 1 and day 5 while he is a Baby or
  Child".

### Task 2: He tells people he is sick, with a picture

**Files:** `wisp/rules.py`, `wisp/voice.py`, `cogs/conversation.py`,
`cogs/speech.py` (pokes), the canned fallback lines in `wisp/lines.py` if the
sick moments use them, tests.

- When a member talks to Wisp in the House (mention or reply) or pokes him while
  he has Monster Pox or a cold, his reply clearly says he is sick and with what
  ("I have Monster Pox" / "I have a cold", in his stage voice; a Baby says it in
  baby words). Put the instruction in the sick and sniffles prompt pieces in
  `wisp/voice.py`; the pre-written fallback lines used while sick must say it
  too.
- That reply carries one picture picked at random from the sickness's pool,
  defined in `wisp/rules.py`:
  - `POX_PICTURES`: his stage's `SICK_PICTURES` entry (when there is one) and
    `sneeze.gif`.
  - `COLD_PICTURES`: `wispsick.gif` and `sneeze.gif`.
  All live in `ASSETS/moments/`. A missing file means that file is skipped; an
  empty pool means words only.
- Pox wins when he somehow has both.
- Tests: the pool by stage and sickness; a sick reply is sent with one file from
  the pool; a healthy reply has no picture.

### Task 3: Meter drops are announced in the House

**Files:** `wisp/life.py`, `wisp/rules.py` (wording numbers only),
`cogs/announce.py` (or wherever tick events are posted), tests.

- When a stretch fills and a meter loses its step (`_penalties`), emit an event
  saying which meter, how much it lost and its new value. Extend `Event` with
  optional fields rather than a second event type per meter.
- After each tick, all drops of that tick go into ONE House post, pinging
  nobody, e.g.:

  ```
  ♪ Wisp's meters dropped
  ・Health -8 (now 51): nobody fed him a track for 6 hours. Drop a track in <#track drop>.
  ・Wellbeing -10 (now 40): nobody chatted, played or poked him, or gave him a snack, for 6 hours. Talk to him here or use the Status post.
  ```

  (Task 13 runs first: there are only Health and Wellbeing.) Use the real stretch
  length from `wisp/rules.py`, not a typed "6". The track drop and Status
  links are channel mentions from settings; a missing setting falls back to the
  plain words "the track drop" / "the Status post".
- The Monster Pox and cold multipliers show in the number (e.g. "-12").
- No post when nothing dropped. Frozen time never drops (unchanged).
- Tests: one tick with two drops makes one post with two lines; no drop, no
  post; the sick multiplier shows.

### Task 4: Every action says what it did, or exactly why not

**Files:** `cogs/snacks.py`, `cogs/gifts.py`, `cogs/rhyme_duel.py`,
`cogs/speech.py`, `cogs/chores.py`, `cogs/players.py`, `wisp/rules.py`, tests.

This is the core of Myra's "people don't know what is happening ever" and "when
things don't work tell them why".

- **Receipts.** After a member action that changed something, the member gets a
  private line saying what it did with the new value and what is left today,
  e.g.:
  - snack: `♪ Wisp ate your Cheese. Wellbeing +8 (now 66).`
  - gift: `♪ You gave Wisp a <gift>. Wellbeing +8 (now 74).`
  - poke (button press): `♪ Poke counted. Wellbeing +5 (now 25). 2 pokes left today that raise it.`
  - Rhyme Duel that counted: `♪ Your duel counted. Wellbeing +10 (now 35). 1 Vault point. 4 counted games left today.`
  - chore button: `♪ You cleaned up. +2 points.` (and the Wellbeing plus for a cleanup).
  Where the action already answers privately, add the numbers to that answer
  instead of sending a second message.
- **Reasons.** Every refusal and every "did not count" names the reason:
  - not counted Rhyme Duel: `♪ This duel didn't count toward his Wellbeing: you didn't score a rhyme.` /
    `... you've already played 5 counted games today (resets at 00:00 UTC).` /
    `... you don't have a role that can feed Wisp.` / `... Wisp isn't alive right now.`
  - poke that raised nothing: `♪ Poke sent, but it didn't raise his Wellbeing: you've used your 3 pokes for today.` /
    `... he was napping, so you woke him up cranky.`
  - snack/gift/shop refusals already have reasons (`NOT_TAKING`, `CANNOT_FEED`,
    not enough coins, ...): audit every refusal path in these cogs and make
    sure each one says the specific reason, including daily meal limit hit,
    frozen, and no living Wisp.
- Daily limits come from `wisp/rules.py` (`PLAYS_PER_DAY`, the chat/poke credit
  limits); never type the number.
- Chatting in the House is a plain message, so it gets no receipt (his reply is
  the answer) and is out of scope.
- Tests: one per receipt and one per reason above.

### Task 5: The track drop says whether a track fed him

**Files:** `cogs/feeding.py`, `cogs/announce.py` if needed, `wisp/rules.py`,
`README.md` (permissions), tests.

- A track that fed Wisp gets a reaction from Wisp on the member's post: his app
  emoji named by `FED_REACTION` in `wisp/rules.py` (start with `wisp_happy`).
  If that emoji is not uploaded, no reaction. A failed reaction is reported the
  normal way (the House), never fatal.
- A post with a track link that did NOT feed him gets one House post naming the
  member (mention, no ping) and the exact reason: no feeder role, banned, daily
  meal limit reached (show their total and the limit), no living Wisp, Wisp is
  frozen, that track was already fed (if the code refuses repeats), or a share
  link for no song. A post with no track link gets nothing. Wisp still never
  posts in the track drop itself.
- README: add Add Reactions to the bot permissions list.
- Tests: fed track gets the reaction; each reason; a plain message gets nothing.

### Task 6: The Status post is the control panel

**Files:** `cogs/snacks.py` (`status_view`), `cogs/status_card.py`,
`wisp/card.py`, `cogs/rhyme_duel.py`, `cogs/wisp_lunchbox.py`, `cogs/speech.py`,
tests.

- The live status card's buttons, in this order (two rows if needed):
  **Feed Wisp** (exists), **Poke Wisp** (exists), **Vault** (opens the shop, the
  same private message `ShopButton` / `/wisp vault` opens), **Snack Pack** (same
  as `/wisp snackpack`, private), **Play** (a private pop-up listing the games;
  for now one button, **Rhyme Duel**, which starts a duel exactly like
  `/wisp play rhyme`), **Lunchbox** (the lunchbox, sent privately from the
  button; `/wisp lunchbox` keeps its public behaviour).
- Every new button is a persistent `DynamicItem` with a fixed custom id (see
  `FeedButton`), registered at startup like the existing ones, wrapped in the
  same `_press` error handling.
- The waiting card (no Wisp) keeps only Begin again, as today.
- (Task 13 runs first: the card has only the Health and Wellbeing bars.)
- Card text (`wisp/card.py`, `_card`): replace the two hint lines that point at
  `/wisp snackpack` and the ViiBR Vault with one line in the same style pointing
  at the buttons below, keep the poke/tag line, and add a **Right now** line
  under the day heading listing what he needs, worst first, from the live
  state:
  - Health under `HANGRY_BELOW`: `hungry: drop a track in <#track drop>`
  - Wellbeing under `LONELY_BELOW`: `lonely: chat, play, poke or give him a snack`
  - a mess, tantrum or nap chore waiting: `a mess is waiting in his House` /
    `he's having a tantrum in his House` / `he's asleep: turn the lights off in his House`
  - nothing: `happy`
  and a `next nap HH:MM UTC` line. Keep Myra's clef style (`SUB_CLEF`,
  `ITEM_CLEF`) and `quoted(...)`.
- Tests: the view's buttons and custom ids; each button's private answer; the
  Right now line for each case; the card stays under 2,000 characters with
  everything showing.

### Task 7: The Vault post becomes the Leaderboard post

**Files:** `cogs/studio.py`, `cogs/vault.py`, `cogs/headers.py`,
`cogs/boards.py`, `wisp/rules.py`, `README.md`, tests.

- The Studio thread stored in `vault_thread_id` (keep the column and attribute
  names) is now named `🏆 | Leaderboard`, title `Leaderboard`; setup renames the
  old `🔒| The ViiBR Vault` thread in place (the existing rename path). Its
  thumbnail stays `vault.png` until Myra makes a new one (note it in the
  changelog's For Myra list).
- The leaderboard card has no buttons and its intro says where to shop: the
  Vault button on the Status post (link the Status thread when set).
- `refresh_vault` becomes a repost: render the text; if it equals the text of
  the card it last posted, do nothing; otherwise post the header picture and
  the card fresh at the bottom of the thread, store their ids in the same
  settings attributes, then delete the old header and card. A missing old
  message is fine; any other failed delete is reported in the thread. Never
  leave two leaderboards. Store what you need to compare (the posted card's
  text, or fetch the old message) so a restart does not repost an unchanged
  board.
- `boards.py`: the Leaderboard post's notice says it is just for the
  leaderboard; the Status post keeps "just for buttons".
- `/wisp board` keeps working (private, as today).
- Tests: unchanged text posts nothing; changed text posts new and deletes old;
  a deleted old card is fine; the setup rename.

### Task 8: Docs

**Files:** `README.md`, `CHANGELOG.md`.

- README: the Studio section (five threads plus Leaderboard naming), the status
  card buttons and Right now line, receipts and reasons, track reactions and
  House notes, meter drop posts, sick replies, Pox window.
- CHANGELOG: a new top entry `## 2026-11-06 (Control panel and clarity)` in the
  existing style, with a "For Myra" list: FAQ pictures that mention the Vault
  post, `/wisp vault`, `/wisp snackpack` or Pox in the teens; a new Leaderboard
  thumbnail; the new Status card hint wording is a draft for her to redesign.

---

Added 2026-11-06 after the first eight, from Myra in chat. Task 8 (docs) runs
last and covers these too.

Already done outside the task loop (commit 017368c, pushed): every AI provider
is asked not to think (Groq `reasoning_effort: none`, Gemini `thinkingBudget: 0`,
OpenRouter `reasoning.enabled: false`) and an answer cut off at the token limit
is refused so the next provider answers. Myra: "no dont use any thinking
models", "yes to the never post". The live Groq model is now
`qwen/qwen3.8-27b`. The Cloudflare image worker was fixed and its source saved
in `tools/cloudflare_wispimages_worker.js`.

### Task 9: He knows how long he is sick, and points to Burrito

**Files:** `wisp/voice.py`, tests.

- Myra: "foggy asked how long he has pox. his answer was correct but in case it
  isnt or he doesnt know he should tell people to ask burrito".
- The sick and sniffles prompt pieces tell him how long he has left, in whole
  hours rounded up, from `life.cold_left` (Pox) and `life.sniffles_left` (a
  cold), the same numbers the status card shows.
- They also tell him: if someone asks something about his sickness he is not
  sure of, tell them to ask Burrito, his fairy god-bot, in Wisp's Studio.
- Tests: the prompt for a sick Wisp holds the hours left; the Burrito pointer is
  in the sick and cold pieces.

### Task 10: He can see pictures and GIFs

**Files:** `ai/vision.py` (new), `cogs/conversation.py`, `wisp/voice.py`,
`wisp/rules.py`, `config.py`, `app.py`, tests.

- Myra: "we need a vision model, foggy sent a gif and he couldnt see it. people
  will send gifs ... we gotta get some free model to give him pic descriptions".
- Checked live on 2026-11-06: Gemini `gemini-3.6-flash` with
  `thinkingConfig.thinkingBudget: 0` describes an `image/gif` sent as
  `inline_data` correctly, on the existing `GOOGLE_API_KEY` (free tier).
- When a message aimed at Wisp in the House carries a picture, take the first
  one of: an image attachment (png, jpeg, webp, gif), a sticker image, or an
  embed's image or thumbnail (Tenor and Giphy links show as embeds). Download
  it (limit `VISION_MAX_BYTES`, 8 MB, in rules; time limit `AI_TIMEOUT`), ask
  the vision model for one or two plain sentences describing it, and put that
  in his prompt as what the member sent ("They sent a picture: ..."). He
  answers as if he saw it.
- Vision model: `config.GOOGLE_VISION_MODEL`, optional, defaulting to
  `gemini-3.6-flash` when unset (so the live `.env` needs no change). No
  thinking, same rule as the chain. Errors are `ProviderError`s.
- If the picture can't be read (too big, download failed, model failed), his
  prompt says they sent a picture he couldn't see right now, so he says so
  instead of pretending. A failure is logged, not posted (it is not the
  member's fault and he answers anyway).
- A message with no picture makes no vision call.
- Tests: fake HTTP server like `tests/test_ai_chain.py`; each picture source;
  too big; model failure; no picture means no call.

### Task 11: He makes pictures for people

**Files:** `ai/images.py` (new), `cogs/drawings.py` (new) or the closest
existing cog, `db/` (new table), `wisp/rules.py`, `wisp/voice.py`,
`cogs/gifts.py`, `cogs/snacks.py` (Snack Pack), `config.py`, tests.

- Myra: "he does images, we need to wire that in as a reward and i want him to
  MAKE PICS FOR PEOPLE not have them request, he should make them for people as
  thank you or i like you or whatever". Members never ask for one; there is no
  command.
- Image source: `config.CF_IMAGE_WORKER_URL` (already in `.env`), POST JSON
  `{"prompt": "..."}`, answers `image/jpeg` bytes or a plain-text reason with
  400/502. Time limit `IMAGE_TIMEOUT` (60 s) in rules.
- When he makes one (my calls, numbers in `wisp/rules.py`):
  - a member gives him a gift he loves (the gift's reaction already decides
    love vs not);
  - a member's bond reaches a new tier;
  - once a UTC day, the member who fed him the most tracks that day, at the
    first tick after midnight UTC;
  - "I like you": once a UTC day at a random time, a member who fed him, chatted
    with him or played with him in the last 24 hours, picked at random.
  Caps: at most `DRAWINGS_PER_MEMBER_PER_DAY` (1) per member and
  `DRAWINGS_PER_DAY` (6) per server per UTC day. Only living Wisp, not frozen,
  members who can feed him and are not banned.
- The picture prompt is written by his AI (thinking off) from: why he is making
  it, the member's display name, what he remembers about them, his stage and
  mood. It always asks for a hand-drawn crayon doodle in his style, with no
  words or letters in the picture (Flux misspells names). Keep the prompt under
  `IMAGE_PROMPT_MAX_CHARS` (500).
- He posts it in the House: a line in his voice to the member, mentioning them
  (this mention pings, it is their present), with the picture attached as
  `wisp_drawing.jpg`. `♪` flair, no Unicode emoji.
- Record every drawing in a new `drawings` table (guild_id, user_id, life_id,
  reason, message_id, at), additive. The caps read it, so a restart keeps them.
  The Snack Pack gets a "Drawings from Wisp" line with the member's count.
- A failure (worker down, bad answer) is posted in the House as
  `Error in making a drawing for <member name>: <Type>: <message>` (errors stay
  public during beta) and the drawing is not recorded, so it can be tried again
  on the next trigger.
- Tests: each trigger; both caps; frozen/dead/banned/no role make none; worker
  failure posts the error and records nothing; the prompt has no-words wording;
  the Snack Pack count.

### Task 12: Audit fixes

**Files:** as each item says, plus tests. The full audit with file:line and
failure scenarios is `.superpowers/sdd/2026-11-06-control-panel/audit-report.md`;
read each item there before fixing it. Myra asked for the audit ("check for any
missed things or loose ends or unfinished code and bugs") and delegated the
calls; mine are below.

- **I1 menus die quietly.** Vault/snack/gift/badge/magazine/medicine menus must
  never answer "This interaction failed". Give the menu views `timeout=None`, and
  make any press on a menu the bot no longer holds (after a restart) answer
  privately: `♪ This menu closed when Wisp restarted. Open it again from the
  Status post.` Check discord.py 2.6.4's view dispatch (`ViewStore`) to choose a
  mechanism that never double-handles a live menu (e.g. a fixed custom-id prefix
  plus a catch-all `DynamicItem` only if dispatch order allows it). Test both.
- **M1** `/wisp lunchbox` used in any Studio thread answers privately instead of
  posting there.
- **M2** The track drop ignores messages that are staff `!wisp` commands
  (same `is_command` check `cogs/conversation.py` uses).
- **M3** `_catch_due_cold` only starts Pox for a Baby or Child (a due time found
  at a later stage is cleared, never caught), and `jump_to` clears `cold_due_at`
  so it re-rolls from the new hatch time.
- **M4** While he naps, `/wisp play rhyme` (and the Play button later) is refused
  with the reason: `♪ Wisp is napping until HH:MM UTC. Poke him awake first.`
  Snacks, gifts and medicine still work, but his line comes from new canned
  sleepy sets (eating / getting a gift in his sleep, a few lines each, no Unicode
  emoji), not his awake lines.
- **M5** The quiet line uses real House activity (`bot.talk.quiet_for()`), not
  credited interactions.
- **M6** A chore's first presser is never told "already taken" while the post id
  is still being stored, and a chore never stays open without a post: if posting
  fails, the chore is closed (no penalty) so the next one can come.
- **M7** Lonely lines and the lonely AI layer ask for what fills Wellbeing (chat,
  snacks, gifts, cleanups), not duels; fix the two stale docstrings.
- **M8** Rules post: Pox "once, as a Baby or Child". `CANNOT_FEED` and the rules
  post name the server's actual feeding roles (from settings, as role mentions
  without pings) instead of a hard-coded role name, falling back to "a role that
  can feed Wisp" when none is set.
- **M9** `_report_line` cuts with `wisp.text.clip` / `text_length`.
- **M10** `!wisp song` over 2,000 units is refused with a usage-style line naming
  the limit.
- **M11** Move `_ARCHIVE_AFTER_MINUTES`, `_REASON_MAX` and `VAULT_WIDTH` into
  `wisp/rules.py`.
- **M12 (code part)** Pin `aiohttp` and `yarl` in `requirements.txt` at the
  versions installed in `.venv`. The README parts belong to Task 8.
- **U1** `people_since` (people he saw, for caretakers needed) counts only the
  kinds `caretakers` counts, so chats and pokes no longer raise the bar
  (BuildRulings 2026-10-26: a chat does not count toward growth caretakers).
- **U2** Freezing pauses his age too: add a `frozen_seconds` total (additive
  column, default 0) that the tick adds frozen time to, and have `age_days`
  subtract it, so stage days, Old Fogey, farewell and the Pox due time all wait
  out a freeze.
- I2 (FAQ pictures) is Myra's art: Task 8 lists every wrong picture in the
  changelog's For Myra list and fixes the text in `DOCS/wisp_faq.html`.
- U3 checked live: no `reading_glasses` keepsakes exist. Nothing to do.
- **Files left open.** Every `discord.File` the bot opens is closed in a `finally`
  after the send, good or failed, as `Picture.attach` and `say` now do
  (fcc90e9): check `cogs/studio.py`, `cogs/faq.py`, `cogs/snacks.py`,
  `cogs/headers.py` and any other site, with a test per helper.

### Task 14: Naps on the Pacific clock

**Files:** `wisp/rules.py`, `wisp/chores.py`, `cogs/studio.py` (rules post),
`requirements.txt`, tests, README naps line.

- Myra, 2026-11-06: naps at 7am and 1pm Pacific "and whatever other time ...
  still run him on utc but whatever that is for pacific"; she couldn't pick the
  third, so my call: **7am, 1pm and 10pm Pacific** (US members awake for all
  three; 10pm Pacific is 6am in the UK).
- Rules: `NAP_TIMEZONE = "America/Los_Angeles"` and `NAP_LOCAL_HOURS = (7, 13,
  22)` replace `NAP_HOURS`. Nap slots follow the Pacific clock all year (so they
  move in UTC when daylight saving starts and ends); everything else, storage
  and comparisons included, stays UTC. Convert each local slot to a UTC
  `datetime` with `zoneinfo`; never store local times.
- `zoneinfo` needs the `tzdata` package on Windows: add `tzdata==2026.6` to
  `requirements.txt` and install it in `.venv`.
- Everything that uses nap slots (the pre-nap quiet buffer for tantrums, the nap
  slot stored as `nap_slot`, skipping a nap whose start fell while frozen or
  down) keeps working across a daylight-saving change: test a day on each side
  of the March and November changes (slots stay at 7, 13, 22 local; no slot is
  skipped or doubled).
- The rules post shows the nap times in Pacific (`7am, 1pm, 10pm Pacific`), and
  any member-facing nap time (the Task 12 duel refusal "napping until ...")
  shows Pacific too, e.g. `until 2pm Pacific`.
- A nap already stored in `nap_slot` on the live Wisp at deploy finishes
  normally.

### Task 13: Mood folds into Wellbeing (runs right after Task 2)

**Files:** `wisp/rules.py`, `wisp/life.py`, `wisp/card.py`, `wisp/voice.py`,
`wisp/lines.py`, `wisp/chores.py`, `cogs/rhyme_duel.py`, `cogs/players.py`,
`cogs/speech.py`, `cogs/studio.py` (rules post), `db/` (no column changes),
tests, `README.md` meters section.

- Myra, 2026-11-06, after hearing duels raise Mood but lonely is low
  Wellbeing: "let's just combine mood and wellbeing and have it just be
  wellbeing". Two meters remain: Health and Wellbeing.
- Everything that moved Mood moves Wellbeing instead, same amounts and the same
  daily limits: Rhyme Duel that counts +10 (`WELLBEING_PER_PLAY`), a credited
  poke +5 (`WELLBEING_PER_POKE`), an unscolded tantrum -15, lights left on -10.
- One stretch: Wellbeing's 6-hour stretch is ended by any credited chat, snack,
  gift, cleanup, duel or poke; a full stretch costs `WELLBEING_PENALTY` (x2 with
  a cold), as now. The Mood stretch and penalty go away.
- Rockstar: an Adult whose Wellbeing stays at `ROCKSTAR_WELLBEING` (80) or more
  for `ROCKSTAR_WELLBEING_FOR` (4 days) of counted time becomes a Rockstar
  (reuse the existing `high_mood_since` column; do not rename it).
- Storage stays additive: keep the `mood_meter` and `mood_stretch` columns in
  the table (unused, still saved with their defaults) so nothing is dropped. The
  `Life` fields for them may go if nothing reads them, but loading a live row
  must keep working.
- The status card shows two bars, Health then Wellbeing. The waiting/egg cards
  that used `MOOD_BAR` for Hatching/Emerging keep their look (rename the
  constant to fit). Unused `happiness_*` emoji names go from the README list.
- `mood(life)` / the `Mood` enum in `wisp/life.py` (happy / hangry / lonely
  voice) is a different thing: keep it. Remove "Mood" the meter from every line,
  prompt, rules post and README sentence; the rules post's numbers come from
  `wisp/rules.py`.
- The live Wisp keeps his current Wellbeing; his Mood value is dropped.
- Sickness moves to Health (my split, 2026-11-06, Myra: "health should be his
  sick meter too?" and "go over all his functions and assign them"):
  - **Health is his body and the only meter that can kill him.** Tracks feed it
    (the only real food; snacks stay Wellbeing so coins can't keep him alive
    instead of music). A cleanup adds `HEALTH_PER_CLEANUP` (5) to Health instead
    of Wellbeing. Monster Pox and a cold both make the Health penalty
    `SICK_DRAIN_MULTIPLIER` (1.5) times as big and neither can take Health below
    `SICK_FULL_FLOOR` (1) on its own (a cold no longer doubles the Wellbeing
    penalty; drop `SNIFFLES_PENALTY_MULTIPLIER`). A mess left 6 hours still gives
    the cold; medicine still cures it at once.
  - **Wellbeing is his heart and never kills him:** chat, poke, duel, snack,
    gift; missed tantrum and missed lights; the 6-hour stretch; lonely; Rockstar.
    Naps stay on Wellbeing so nobody asleep at night can slowly kill him.
- Also do the minors parked from Task 9 in `wisp/voice.py`: rename the
  `build_prompt` parameter `hours_left` to `sickness_hours` (it shadows the
  `hours_left()` function), use `wisp.text.count` for the hour plural, build the
  `_hours_note` sentence once, simplify `sick_hours`.
- Tests: each former Mood plus and minus now moves Wellbeing; one stretch ended
  by each action; Rockstar on Wellbeing; the card has two bars; a live-shaped row
  with `mood_meter` still loads.

### Task 15: One whole-life tester for staff

**Files:** `cogs/life_loop.py` (or a new `cogs/life_test.py`), `wisp/rules.py`,
tests, README staff commands.

- Myra, 2026-11-06: "instead of a !test whatever command which i dont even
  understand how it would work, just give me a whole life tester that i can use
  to test every single function one right after the other in a row", and on
  buttons: "it doesnt wait a minute, it waits until I COME PRESS IT AND ONLY ME".
- `!wisp testlife` (staff only) replaces `!wisp test_chore` and
  `!wisp test_lifestage` (remove both, their helpers and tests only they use;
  README too). `!wisp testlife stop` ends a run early.
- It plays one whole life on the server's real Wisp, one step after another,
  each step through the real code paths so every post, picture, button and
  meter change is the real one. Before each step Wisp posts in the House:
  `♪ Test life, step N of M: <what happens>`. Steps in order:
  1. a new egg is laid; 2. it is fed until it hatches (Baby); 3. Monster Pox;
  4. a mess with its button; 5. a second mess left too long, so he catches a
  cold; 6. medicine cures the cold; 7. a tantrum with Scold; 8. a nap with
  Lights off; 9. a meter drop post (one stretch passes); 10. lonely post;
  11. Child (keepsake); 12. Teen (keepsake); 13. Adult (keepsake); 14. a drawing
  for the member who ran the test; 15. Rockstar (Guitar Pick, magazines shelf);
  16. Old Fogey (Time Piece); 17. the farewell (Last Ember) and Begin again.
  `!wisp testlife starve` runs steps 1-2, then lets Health run out (he dies),
  then Begin again.
- **Button steps wait with no time limit until the member who started the run
  presses the button** (matched by Discord ID). Anyone else pressing a test
  button is told privately `♪ This button is for <name>'s test run.` and nothing
  happens. Only `!wisp testlife stop` ends a wait early. Non-button steps pause
  `TEST_STEP_PAUSE` (8 s) so each post can be read.
- Safety: if the server has a living Wisp past the egg, the first run asks
  `♪ This ends the current Wisp (vN). Type !wisp testlife confirm to go on.` and
  does nothing else. One run per server at a time (a second gets
  `♪ A test life is already running.`). A frozen server refuses with the reason.
- A failing step posts `Error in test life step N: <Type>: <message>` and the
  run goes on; it ends with `♪ Test life done: N steps passed, K failed (steps ...)`.
- Step work under `bot.guild_lock`, Discord posts and button waits outside it.
- Tests: confirm guard; steps run in order with fakes (pause 0, presses faked);
  a press by someone else is refused and the step keeps waiting; a failing step
  is reported and the run continues; stop; one run at a time.
- Runs LAST, after every other task, so it exercises all of them.
