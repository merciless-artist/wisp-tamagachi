# Changelog

## 2026-11-07 (Feeding cures Monster Pox faster)

- Every meal point fed while he has Monster Pox takes 15 minutes off it, so a
  ViiBR track takes off 75 minutes. The more people feed him, the sooner he is
  better; a meal that ends it posts his "all better" moment straight away.
- While he has Monster Pox, the status card's right now block says how to help:
  feed him tracks in the track drop, every meal gets him better faster.
- The FAQ rules post, the FAQ page, the README and his own sick talk say the
  same.

### For Myra

- `06_growing_4.png` (already on the list) also needs the new rule: feeding
  him gets him better faster.

## 2026-11-06 (Control panel and clarity)

- The Status post is now the control panel: six private buttons (Feed Wisp,
  Poke Wisp, Vault, Snack Pack, Play, Lunchbox) and a "right now" block that
  says what he needs.
- Every press and every command says what it did, or exactly why it could not.
  A track that did not feed him gets a note in his House with the reason, and
  a track that did gets his happy face.
- Wisp tells the House when a meter drops and what would help, and he sounds
  and looks sick when he is sick, with a picture and a pointer to Burrito.
- He sees the pictures and GIFs people send him, and he draws members pictures
  as presents.
- Two meters, not three: Mood folded into Wellbeing, and Health is the sick
  meter. Monster Pox only comes to a Baby or Child, between day 1 and day 5.
- Naps are 7am, 1pm and 10pm Pacific, and freezing him pauses his age too.
- Menus stay open until the bot restarts (and then say so), the Leaderboard
  post is reposted when it changes, and no AI provider is asked to think or
  allowed to send a cut-off reply.
- Staff get `!wisp testlife`, which plays one whole life on the real Wisp.

### For Myra

- FAQ pictures that show old rules. The words in `DOCS/wisp_faq.html` are
  fixed; these pictures in `ASSETS/faq/` need re-rendering from it:
  - `01_basics_1.png`: names The ViiBR Vault as the shop and leaderboard post.
  - `01_basics_2.png`: `/wisp status` and a card with Care, Happy and Hunger
    bars and the old snackpack and Vault hints; the card now has two bars, a
    right now block and six buttons.
  - `01_basics_3.png`: explains Hunger, Happy and Care, with snacks filling
    Hunger; now it is Health and Wellbeing, and snacks fill Wellbeing.
  - `02_feeding_1.png`: says Wisp never posts or reacts in the track drop.
  - `02_feeding_4.png`: says he stays quiet when a post does not feed him; he
    now posts the reason in his House.
  - `03_vault_1.png`: the Vault and the leaderboard as one thing, `/wisp vault`,
    `/wisp snackpack` and the "Shop the Vault" button.
  - `03_vault_2.png`: the snack table has a Hunger column; snacks now give
    Wellbeing and never fill Health.
  - `04_lunchbox_2.png`: gifts fill his Care and he keeps about one in three;
    now it is Wellbeing and a different keep rule.
  - `06_growing_2.png`: the old stage table (Child day 3, Teen day 7, Adult
    day 14, Rockstar Happy 80 for 7 days, Old Fogey day 45).
  - `06_growing_3.png`: hangry below 30 Hunger and lonely below 30 Care; now
    Health and Wellbeing.
  - `06_growing_4.png`: Monster Pox for a "Baby, Child or Teen" and Hunger
    draining faster; a Teen never gets it, and Health drops faster instead.
  - `07_talking_1.png` (tone only): a Rockstar talks with maximum energy; he
    now tries very hard to be zen.
  - `07_talking_3.png`: a poke counts toward Happy; now chats and pokes fill
    Wellbeing.
  - `08_games_2.png`: a duel gives Care; now it is Wellbeing.
  - `09_ending_1.png`: he dies if Hunger hits zero; now it is Health.
  - `09_ending_2.png`: Old Fogey at day 45 and goodbye at day 60; now day 24
    and day 30.
  - The Chores section has no pictures, so nothing shows the new nap times. The
    two new questions (he sees pictures, he draws) and the staff commands have
    no pictures either.
- A new Leaderboard thumbnail: the Leaderboard thread still uses `vault.png`.
- Draft wording for you to redesign: the Status card hint "feed Wisp, shop the
  Vault and play with the buttons below!", the Leaderboard subtitle "The
  leaderboard.", the line "Shop the Vault with the button on the Status post."
  and the right now lines.
- The `adult_spark` picture (`ASSETS/keepsakes/adult_spark.gif`) is in the old
  style.
- The picture worker that draws for Wisp has no sign-in. Its address lives only
  in `.env`, so keep it there and out of anything public.
- The rules post at the end of the Wisp FAQ lost four lines of wording so the
  role names fit under 2,000 characters:
  - "Suno and viibrmusic.com links in the track drop" is now "Links posted in the
    track drop:".
  - "Each link feeds him once and earns leaderboard points" is now "Each link
    feeds him once, for leaderboard points".
  - "Old Fogey around day 24; around day 30 he passes on and the coal becomes
    an egg, 5 of 20 fed" is now "Old Fogey at day 24. At day 30 he passes on;
    his coal is a new egg, 5 of 20 fed".
  - The intro lost "Neglected, he fades."
- Naps at 7am, 1pm and 10pm Pacific are my pick when you were unsure. It is
  one line in the rules to change.
- Behaviour changes to know:
  - Cleaning up a mess now gives Health, not Wellbeing.
  - Giving him a gift now ends the Wellbeing stretch, like a chat or a snack.
  - The bigger sick meal limit (30 instead of 15) is for Monster Pox only, not
    a cold.
  - Badge and magazine buys still work while he is frozen.
- `!wisp testlife` is real: it ends the current Wisp quietly (no farewell),
  gives the runner real points, keepsakes and a drawing, and adds a life to the
  history and leaderboard. The runner needs a feeding role and an opened
  `/wisp board`; the drawing step needs that day's drawing caps free.
- Menus sent before this update fail once ("This interaction failed") on their
  first press after the deploy.
- Right after the update goes live, run `!wisp setup`, so the old Vault thread
  gets its new Leaderboard name and first post. Then run `!wisp faq`, so the FAQ
  text matches. The rules post refreshes itself.
- The picture worker address must be in the server's own environment on fps.ms
  (`CF_IMAGE_WORKER_URL`). Without it he quietly makes no drawings.
- A test life's feed uses up the runner's daily meal limit that day. It can make
  the runner tomorrow's top feeder and can trigger a bond drawing.
- A Wisp ended by a test life shows on the Leaderboard like any Wisp that went
  out.
- The host must install `requirements.txt` on start (new: `tzdata`, `aiohttp`,
  `yarl`).

## 2026-11-06 (`!wisp testlife` plays a whole life)

- Staff get `!wisp testlife`. It plays one whole life on the server's real
  Wisp, one step after another, through the same code the real game uses, so
  every post, picture, button and meter change is the real one. Before each
  step Wisp posts `♪ Test life, step N of 17: <what happens>` in his House.
- A step with a button waits, with no time limit, for the staff member who
  started the run. Anyone else who presses it is told privately it is for the
  runner. Every other step holds 8 seconds (`TEST_STEP_PAUSE`) so its posts can
  be read.
- It is real: it ends the current Wisp quietly (no farewell, no Last Ember),
  the runner earns real points, keepsakes and a drawing, and the life joins the
  history and the leaderboard. The feed is lifted past the daily meal limit and
  the medicine is free, for the test only. Wisp's own five-minute tick leaves
  the server alone while it runs.
- General chat is never told about a test life's hatching or new stages; they
  are announced in the House only.
- `!wisp testlife starve` plays the egg and the hatching, then lets his Health
  run out. `!wisp testlife confirm` goes on when the server has a living Wisp
  past the egg (it first asks, and does nothing else). `!wisp testlife stop`
  ends a run after its current step.
- A step that fails posts `Error in test life step N: <Type>: <message>` and
  the run goes on; it ends with `♪ Test life done: 17 steps passed, 0 failed.`
  One run per server at a time. It is refused up front if the runner cannot
  feed Wisp, if Wisp is frozen, or if the House or Status post is not set.
- `!wisp test_lifestage` and `!wisp test_chore` are gone; this replaces both.

## 2026-11-06 (Naps follow the Pacific clock)

- His three naps are now 7am, 1pm and 10pm Pacific, an hour each (they were
  02:00, 10:00 and 18:00 UTC). They follow daylight saving, so in UTC they
  move by an hour twice a year. The rules post, the status card's "next nap"
  and the Rhyme Duel refusal all say the time the same way, such as
  `next nap 7am Pacific` or `Wisp is napping until 2pm Pacific.`
- Everything else, and everything stored, stays on UTC. A UTC day holds every
  nap that starts in it, so 10pm Pacific falls in the next UTC day. A nap that
  was already running at the deploy finishes, then the naps go Pacific, with no
  second nap on the changeover.
- `tzdata` is pinned in `requirements.txt` so the Pacific clock works on
  Windows.

## 2026-11-06 (Audit fixes)

- Private menus never go quiet. From this deploy on, the Vault and the snack
  menu never time out (a menu sent before the deploy fails once, on its first
  press): their `timeout` is pinned to None (`Lasting` in `cogs/menus.py`), since
  discord.py otherwise gives a private follow-up's view 15 minutes. The
  Snack Pack's one button is persistent, so it works whatever its view's
  timeout. Every menu select carries this run's token in its
  custom id (`wisp:menu:<run>:<slot>`). A press on a menu sent before a
  restart gets `♪ This menu closed when Wisp restarted. Open it again from
  the Status post.` from the new `ClosedMenu` dynamic item, which leaves this
  run's menus to the menus themselves, so no press is answered twice.
- Every private menu is a follow-up sent with `wait=True` (Vault, Shop the
  Vault, Snack Pack, Feed Wisp, `/wisp board`), so discord.py files its view
  under its own message, never under the key shared with the persistent
  buttons, whose removal could unregister `wisp:vault` for everyone.
- `/wisp lunchbox` used in a Studio thread answers privately instead of
  posting between the cards.
- Monster Pox is only ever caught as a Baby or Child: a due time found at a
  later stage is cleared. A staff stage jump to Baby or Child rolls a Pox not
  had yet afresh from now (one to five days on his own clock), so a staff jump
  never starts it at once; any other stage clears it. (The staff jump command,
  `!wisp test_lifestage`, was later replaced by `!wisp testlife`.)
- Chores: the first press on a chore whose post id is not stored yet does
  the chore (and stores the id) instead of hearing "already taken"; a chore
  whose post failed is dropped at no cost, and a dropped mess does not hold
  the next one back.
- The people he saw (which sets how many caretakers growing up takes) no
  longer count chats and pokes, like the caretakers themselves.
- The quiet line follows real talk in the House (`bot.talk.quiet_for`), not
  credited interactions. After a restart the quiet is counted from the first
  tick, so a redeploy never makes him say it at once.
- While he naps, `/wisp play rhyme` and the Status post's Play, Rhyme Duel
  button are refused with `♪ Wisp is napping until 2pm Pacific. Poke him awake
  first.` (naps moved to the Pacific clock later the same day). The time comes
  from `nap_time_text`, the one place nap times are worded (the card's next
  nap uses it too), and is when his nap time left runs out, rounded up to the
  minute.
- Snacks, gifts and medicine still work while he naps, but his House line
  comes from new sleepy sets: eating, getting a gift and taking medicine in
  his sleep, five lines each. A gift he passes on keeps its usual line,
  which says it went back.
- Freezing pauses his age. A frozen living Wisp adds the frozen time to the
  new `frozen_seconds` column (additive, default 0), and `age_days` and the
  Monster Pox due time leave it out (`own_time`), so stage days, Old Fogey,
  farewell and Pox all wait out a freeze. A staff stage jump forgets it.
- A refusal for a missing feeding role names the server's feeding roles as
  role mentions (pinging nobody): `you don't have a role that can feed Wisp:
  <@&1> or <@&2>.`, at most `FEEDING_ROLES_SHOWN` (2) then "or N more", and
  the old sentence when none is set. The rules post does the same in "Who
  can feed him" and says Pox comes "Once, as a Baby or Child". `!wisp roles
  add|remove|list` moved to `cogs/feeding.py` next to `!wisp food`, so adding
  or removing a role brings the rules post up to date. Worst case measured:
  1,907 UTF-16 units with the real numbers, both foods at 50 and ten 20-digit
  role ids (1,988 with every number at four digits); a few lines were
  shortened to make room ("Links posted in the track drop:", "Each link
  feeds him once, for leaderboard points", "Old Fogey at day 24. At day 30
  he passes on; his coal is a new egg, 5 of 20 fed", and the intro without
  "Neglected, he fades.").
- The rules post at the end of the Wisp FAQ is brought up to date on each
  server's first tick after a restart, so new rules show without a command.
- Lonely lines and the lonely AI layer ask for what fills Wellbeing: chat,
  play (duels), pokes, snacks and gifts, never cleanups.
- `!wisp freeze` and `!wisp unfreeze` say his age pauses too.
- Error reports are cut to 2,000 UTF-16 units with `clip` (a report full of
  characters outside the BMP no longer fails to post).
- `!wisp song` whose words and link come to more than 2,000 units is refused
  with the usage line and the limit, and the command message is kept.
- `STUDIO_THREAD_ARCHIVE_MINUTES`, `PUNISH_REASON_MAX` and `VAULT_WIDTH` live
  in `wisp/rules.py`.
- `requirements.txt` pins `aiohttp==3.14.5` and `yarl==1.25.1`, the versions
  installed (both are imported directly).
- Every picture file the bot opens is closed once its send or edit is done
  or has failed: header pictures (`send_headed`, which drops `art_file`), the
  Vault's gallery files (`gallery_files` is now a context manager), the
  magazine cover, every FAQ picture, and the Studio thumbnails on creating a
  thread, adding a thumbnail and updating a first post.

## 2026-11-06 (The Status post is the control panel)

- The live status card has six buttons, three to a row: Feed Wisp, Poke Wisp,
  Vault, then Snack Pack, Play, Lunchbox. Every answer is private. Vault and
  Snack Pack open exactly what `/wisp vault` and `/wisp snackpack` open (they
  are the Shop the Vault and Open my Snack Pack buttons with shorter labels).
  Play opens a private games menu with one button for now, Rhyme Duel, which
  starts a duel exactly as `/wisp play rhyme` does, refusals and the
  one-duel-at-a-time rule included. Lunchbox shows the lunchbox privately;
  `/wisp lunchbox` still posts it in the channel. The waiting card keeps only
  Begin again.
- The new buttons (`wisp:play`, `wisp:play:rhyme`, `wisp:lunchbox`) are
  persistent, registered at startup by their cogs, so old cards and old games
  menus keep working after a restart. A failure is posted where the button
  was pressed; a duel with no House to open its thread in is reported too.
- The card shows a Right now block under the day (and any sickness): what he
  needs, worst first (hungry with the track drop channel, lonely, a mess, a
  tantrum, the lights left on while he naps), or `happy`, then `next nap
  7am Pacific`. One line pointing at the buttons replaces the two hints about
  `/wisp snackpack` and the ViiBR Vault.
- While he naps, the Right now block's last line says when he wakes, such as
  `napping until 2pm Pacific`, in place of the next nap.
- `status_view` moved from `cogs/snacks.py` to `cogs/status_card.py` (snacks
  importing the duel cog would be an import cycle), and the shared button
  error wrapper is `press` in `cogs/players.py`.

## 2026-11-06 (Every action says what it did, or exactly why not)

- Receipts, private to the member: a snack (`Wellbeing +8 (now 66)`), a gift
  (the same line, then what Wisp did with it), a counted poke (with how many
  pokes are left today that raise it), a counted Rhyme Duel (Wellbeing, Vault
  point, counted games left today) and a chore (its points, and Health for a
  cleanup). The "now" number is what is on the life after the change; the
  change is the difference of the shown whole numbers.
- Reasons: a duel that did not count says why (no rhyme, daily limit, no
  feeding role, board not opened, banned, Wisp not alive); a poke that raised
  nothing says why (daily limit, napping, no role, board not opened, still an
  egg); a refusal to feed or give names the missing role or the unopened board
  instead of one combined sentence; "not enough points" lines add what the
  thing costs and the member's balance; a dead or missing Wisp is "isn't alive
  right now", not "isn't hatched yet"; a chore press names why it failed
  (banned, no role, older post, Wisp gone, already done); the poke cooldown
  message says how long it is.
- Feeding reasons live in one place (`BLOCKER_REASONS`), shared by the track
  drop, snacks, gifts, chores, duels and pokes.
- A member banned during a duel no longer gets that duel counted.

## 2026-11-06 (Mood folds into Wellbeing; sickness moves to Health)

- Two meters remain: Health (his body, the only one that can kill him) and
  Wellbeing (his heart, never kills him). The status card shows Health then
  Wellbeing; the egg's Hatching and Emerging bars keep their look (`EGG_BAR`).
- Everything that moved Mood moves Wellbeing by the same amounts and limits: a
  counted Rhyme Duel +10 (`WELLBEING_PER_PLAY`), a credited poke +5
  (`WELLBEING_PER_POKE`), an unscolded tantrum -15
  (`TANTRUM_WELLBEING_PENALTY`), lights left on -10
  (`LIGHTS_WELLBEING_PENALTY`).
- One Wellbeing stretch: any credited chat, poke, duel, snack, gift or cleanup
  ends it; a full one costs 10. The Mood stretch and penalty are gone.
- Rockstar: an Adult whose Wellbeing stays at 80 or more for 4 days
  (`ROCKSTAR_WELLBEING`, `ROCKSTAR_WELLBEING_FOR`), in the same
  `high_happiness_since` column. A living Wisp's streak, begun on Mood, starts
  over once at the first startup after this upgrade: the data fix
  `rockstar_streak_on_wellbeing`, recorded in the new `data_fixes` table so it
  never runs twice.
- A cleanup adds 5 Health (`HEALTH_PER_CLEANUP`) instead of Wellbeing. A cold,
  like Monster Pox, makes the Health penalty 1.5 times as big and cannot take
  Health below 1; it no longer doubles the Wellbeing penalty
  (`SNIFFLES_PENALTY_MULTIPLIER` is gone).
- Storage is unchanged: `mood_meter` and `mood_stretch` stay in `lives`,
  unread; a new life gets their defaults. The live Wisp keeps his Wellbeing.
- The rules post and README say two meters.

## 2026-11-06 (Wisp makes pictures for people)

- Wisp draws members pictures as presents. Nobody asks for one and there is no
  command. He makes one when a member gives him a gift he loves, when a
  member's bond reaches a new tier, for the member who fed the most tracks the
  day before (at the first tick of the UTC day), and, once a UTC day at a
  random time, for a member who fed him, chatted with him or played with him in
  the last 24 hours ("I like you").
- At most 1 per member and 6 per server each UTC day
  (`DRAWINGS_PER_MEMBER_PER_DAY`, `DRAWINGS_PER_DAY`). Only while he is alive
  and not frozen, for members who can feed him and are not banned.
- His AI writes the picture prompt from why he is making it, the member's name,
  what he remembers about them, his stage and his mood. The prompt always ends
  with a fixed style: a hand-drawn crayon doodle with no words or letters.
  `CF_IMAGE_WORKER_URL` is the Cloudflare worker that draws it
  (`tools/cloudflare_wispimages_worker.js`, now tracked).
- He posts it in the House with a line to the member (pinging them) and the
  picture as `wisp_drawing.jpg`. A failed try is posted as
  `Error in making a drawing for <name>: ...` and not recorded, so the next
  trigger can try again.
- With no `CF_IMAGE_WORKER_URL` he makes no drawings, quietly: nothing is asked
  of his AI and nothing is posted. The test life's drawing step says the address
  is not set.
- New `drawings` table (additive). The caps read it, so a restart keeps them.
  The Snack Pack gets a "Drawings from Wisp" line with the member's count.
- The AI chain, the vision model and the picture client now share one session
  helper (`ai/session.py`).

## 2026-11-06 (He sees pictures and GIFs)

- When a message that mentions or replies to Wisp in his House has a picture or
  a GIF (an attachment, a sticker, or a picture link whose preview shows), he
  looks at it and answers what he sees. A picture with no words works too.
- A preview that Discord adds a moment late is waited for, 2 seconds
  (`VISION_EMBED_WAIT`), and fetched once more. Only real picture previews
  count, not links to videos or articles.
- If he cannot see it (too big, wrong kind, the AI is down) he says so instead
  of guessing, and nothing is posted about the failure; it is only logged.
- He does not look at pictures in chat he was not spoken to in, in pokes, or
  while he is an egg. Only png, jpeg, webp and gif, up to 8 MB
  (`VISION_MAX_BYTES`).
- The sight comes from a Gemini vision model, `GOOGLE_VISION_MODEL` (default
  `gemini-3.6-flash`), in the new `ai/vision.py`.

## 2026-11-06 (Sick replies with pictures)

- While he has Monster Pox or a cold, anyone who talks to him or pokes him gets
  a reply that says plainly what he has and how many hours are left, and tells
  people to ask Burrito, his fairy god-bot, about it. Babies say it in baby
  words. If his AI is down there are pre-written sick lines (eight for each of
  Monster Pox and a cold, for babies and for the rest).
- The reply comes with a picture: his sick picture or `sneeze.gif` for Monster
  Pox, `wispsick.gif` or `sneeze.gif` for a cold. Monster Pox wins when he has
  both. A poke that wakes him from a nap still shows the nap picture.
- If Discord refuses the picture, the words are sent without it and the failure
  is reported in the House once per run of failures.
- `ASSETS/moments/sneeze.gif` is new.

## 2026-11-06 (A track says whether it fed him)

- A track that feeds Wisp gets his `wisp_happy` reaction on the member's post
  (`FED_REACTION`). With no such emoji uploaded there is no reaction, and a
  failed reaction is reported in the House and never undoes the feed. The bot
  now needs Add Reactions in the track drop.
- A post with a track link that did not feed him gets one note in his House,
  naming the member without a ping, with the exact reason: no feeding role
  (naming the roles), the board not opened, banned, no living Wisp, the daily
  limit (how much they have eaten), the link already fed, a share link for no
  song, or the kind of track set to 0 meal points. A post with no track link
  gets nothing. Wisp still never posts in the track drop.
- Banned is told first, then the missing role, then the unopened board, from
  one place (`feeder_blocker`) shared by everything that checks who may feed.
- Chat and `!wisp` commands typed in the track drop are ignored by the feeding
  code.

## 2026-11-06 (Wisp posts when a meter drops)

- When a stretch with nothing done runs out and a meter loses points, Wisp
  posts once in his House per tick: `♪ Wisp's meters dropped`, then one line per
  meter, such as `・Health -8 (now 42): nobody fed him a track for 6 hours.
  Drop a track in <the track drop>.` Wellbeing's line names what fills it (chat,
  play, poke, snack or gift) and links the Status post. Nobody is pinged.
- The numbers are what was really lost, after the sick multiplier and floor,
  and the stretch is worded as it is ("6 hours", "1 hour", "45 minutes"). A
  drop that kills him posts only the death.

## 2026-11-06 (Monster Pox comes earlier, and only to the young)

- Monster Pox is due between day 1 and day 5 (it was day 1 to 7), which always
  falls while he is a Baby or Child. A Teen never catches it. The rules,
  README and FAQ say so.

## 2026-11-06 (No thinking models, no cut-off replies)

- Every AI provider is asked not to think first (Groq `reasoning_effort:
  none`, Gemini `thinkingBudget: 0`, OpenRouter `reasoning.enabled: false`).
  Thinking spent the same budget as the reply, so a long prompt could stop Wisp
  in the middle of a word.
- An answer that stopped at the token limit is refused, so the next provider
  answers instead and a half sentence is never posted.
- The live Groq model is now `qwen/qwen3.8-27b`. The Cloudflare picture worker
  was fixed and its source saved in `tools/cloudflare_wispimages_worker.js`.

## 2026-11-06 (The Vault post becomes the Leaderboard)

- The Studio thread kept in `vault_thread_id` is now `🏆 | Leaderboard`.
  Setup renames the old `🔒| The ViiBR Vault` thread in place.
- The leaderboard card has no buttons. Its intro says to shop the Vault with
  the button on the Status post, linking the Status thread when it is set.
  `/wisp board` still answers privately, with its buttons.
- The card is reposted instead of edited. Each tick the new text is compared
  with the text of the card now in the thread (read from Discord, so a restart
  or a deleted card is handled and no new storage is needed). Unchanged text
  posts nothing; changed text posts a fresh header and card at the bottom,
  stores their ids in the same settings columns, then deletes the old pair. A
  missing old message is fine; any other failed delete is reported in the
  thread.
- The Leaderboard post's notice says it is just for the leaderboard; the Status
  post keeps "just for buttons".
- `!wisp setup` no longer pins the Leaderboard card, so the card stays the
  thread's last post.

### For Myra

- The Leaderboard thread still uses `vault.png` as its thumbnail until you make
  a new one.

## 2026-11-04 (Meters and chores)

Built from `DOCS/specs/2026-11-02-meters-and-chores-design.md` and
`DOCS/plans/2026-11-02-meters-and-chores.md`. Every number below lives in
`wisp/rules.py`.

### His three meters

- **Health** (was Hunger/Full, still the `care` column): filled by tracks. Each
  6 counted hours without a fed track costs 8 (Old Fogey 6, Monster Pox 1.5
  times as much and never below 1). He dies at 0.
- **Wellbeing** (was Care, still the `fondness` column): snacks +8 each (no
  longer Health), gifts +8, cleanups +5, and the first 3 chats a day per
  member +5 each. Each 6 counted hours without a chat or snack costs 10, 20
  while he has a cold.
- **Mood** (new, `mood_meter`, starts at 50): counted rhyme duels +10, the
  first 3 pokes a day per member +5 each. Each 6 counted hours without a game
  or poke costs 10. Missed tantrums and missed lights cost Mood too.
- The meters no longer drain a little every tick; they only drop in those
  6-hour steps (`*_stretch` columns count the counted seconds). Frozen and
  offline time never count.
- Rockstar now needs Mood 80 or more for 4 days (it used to read happiness from
  the people around him).
- The first chat or poke each day still earns 1 point, as before.

### Chores (first press wins 2 WC)

- **A mess:** 30 to 90 minutes after a fed track, at most one at a time and 6
  hours apart. It grows up with him: poop for Baby and Child ("Clean up"), a
  zit breakout for Teen ("Hand him face wash"), takeout and dirty dishes for
  Adult ("Take out the trash"), the green room he trashed after a show for
  Rockstar ("Clean the green room"), dentures that need a soak for Old Fogey
  ("Soak his teeth"). Pictures: `poop.gif`, `pimple.gif`, `trash_adult.gif`,
  `trash_rockstar.gif`, `dentures.gif`. A cleanup also adds 5 Wellbeing.
  Left 6 hours, the post says so and he catches a cold.
- **A tantrum:** once a day at a random awake time (never in the 20 minutes
  before a nap or during one). Scold him within 15 minutes, or he loses 15
  Mood and is spoiled (bratty in his AI voice) until UTC midnight.
- **Naps:** 02:00, 10:00 and 18:00 UTC for an hour. Turn off the lights within
  15 minutes, or he loses 10 Mood and wakes up cranky. While he naps he only
  snores at mentions, never chimes in, and a poke wakes him early and cranky
  (no Mood plus).
- Buttons are persistent: they keep working after a redeploy, only for the
  current life and the post that is still open, and a dead or departed Wisp's
  old buttons pay nothing. Chore posts never ping.

### The cold and medicine

- A mess left too long gives him a cold for 48 counted hours (never while he
  has Monster Pox or a cold already). It doubles the Wellbeing penalty and
  never touches Health. His card shows `he has a cold・N h left` and his
  picture becomes `wispsick.gif`. His AI voice gets stuffy and sneezy.
- While he has a cold the Vault shows **Medicine** (10 WC, cures it at once,
  buyer gets 3 WC back) with the new `medicine` app emoji. The thank-you post
  shows `medicine.png`.

### Staff

- New `!wisp test_chore <mess|tantrum|nap|cold|late>` changes the real Wisp:
  `mess`, `tantrum` and `nap` start that chore now, `cold` gives him a cold,
  `late` fast-forwards chore time so every waiting chore runs out the way it
  does for real. Refused while frozen or with no living Wisp. Tip: run
  `!wisp test_lifestage baby`, then `!wisp test_chore mess`, to see the poop.
- `!wisp freeze` / `unfreeze` now say the meters and chores pause and run.

### Other

- The status card's bars are Health, Wellbeing and Mood.
- `/wispadmin` rules post, `DOCS/wisp_tamagotchi.html`, `DOCS/wisp_faq.html`,
  README and `DOCS/BuildRulings.md` explain all of the above. To fit the rules
  post in 2,000 characters a few old lines were cut ("Adults chime in and
  remember you", "Be there as he grows to win a keepsake", the pinned-post hint,
  "Staff can lift bans"); the FAQ still covers them.
- `ASSETS/events/died.gif` (Myra's stitched death animation) now shows when he
  dies of neglect; `died.png` stays as the fallback.
- Storage: 18 columns added to `lives`, nothing renamed or dropped.
- Key decisions (full list in `DOCS/BuildRulings.md`): chore presses don't
  count as caretaking for growth; a chore whose post failed costs nothing;
  tantrums never open into a nap.

### For Myra

- FAQ pictures to re-render (they still show Hunger/Happy/Care or drains):
  `01_basics_2`, `01_basics_3`, `03_vault_2`, `04_lunchbox_2`, `06_growing_2`,
  `06_growing_3`, `06_growing_4`, `07_talking_3`, `08_games_2`, `09_ending_1`,
  `09_ending_2`. Maybe also `01_basics_1`, `03_vault_1`, `03_vault_3`
  (their text gained chores, medicine or Wellbeing), and check `02_feeding_3`
  and `04_lunchbox_3` by eye. The new "Chores, colds and medicine" FAQ section
  has no pictures yet.
- Nap pictures exist only for Baby and Child; Teen, Adult, Rockstar and Old
  Fogey nap posts are text only until they get art (`NAP_STAGES`).
- The new dance GIFs are in `ASSETS/dances/` but not live yet; posting them
  instead of the dance emotes is the next feature.

## 2026-11-04 (The Rockstar tries very hard to be zen)

- Myra, after his new Rockstar dance: he is "chillaxed like he is a rockstar
  trying to be zen". His Rockstar voice in `wisp/voice.py` is now a big deal
  who knows it, laid-back and a little too mellow, still buzzing from the show
  underneath, instead of "everything at maximum energy". The Rockstar rows in
  `DOCS/wisp_tamagotchi.html` and `DOCS/wisp_faq.html` say the same. The
  snapshot `DOCS/wisp_prompts.md` (generated 2026-10-31) is left as it was.

## 2026-11-03 (Wisp grows up or dies within 30 days; staff can test a stage)

- Myra: "he has to advance or die", "30 days tops", and the caretakers he
  needs should depend on the people he actually sees. Growing up
  (`STAGE_RULES`, now a `StageRule` of growth, share and deadline day) takes:
  at least 3 days in the stage before (`STAGE_MIN_TIME`), the growth points
  as before (20, 60, 150), and caretakers this stage numbering a share of the
  people he saw in the last 7 days (`PEOPLE_WINDOW`), rounded up and at least
  one: a quarter for Child, half for Teen, three quarters for Adult. The old
  minimum ages (5, 11, 16 days) and fixed caretaker counts (3, 5, 8) are gone.
- On day 7, 13 and 20 he grows into Child, Teen and Adult no matter what, so
  every Wisp is an Adult before Old Fogey (day 24) and says his farewell by
  day 30, unless he starves first. Before, a Wisp who never got 8 caretakers
  stayed a Child or Teen forever.
- Monster Pox now comes 1 to 7 days after hatching (`COLD_LATEST` was 12), so
  it still comes and goes before the earliest Adult (day 9).
- New staff command `!wisp test_lifestage <baby|child|teen|adult|rockstar|
  oldfogey|farewell|starve>`. It changes the real Wisp: a stage sets his age
  to match (so he stays in it until he grows on his own), is announced like
  a real one, and his card, House panel and Vault catch up at once. Farewell
  and starve end his life through his own tick, so they need him unfrozen.
- Backup taken first: `ARCHIVE/WISP_BACKUP_2026-11-03_before_lifestage` (code
  at 8c772d3 and every live `wisp_` table as JSON).

## 2026-11-02 (Wisp dances a lot, and the Child dances too)

- Myra wants Wisp to dance a lot. The reaction rules in `wisp/voice.py` now
  limit only faces to one per message; a separate line tells him he loves
  to dance and to add a dance whenever music, a beat, a track, food, good
  news or anything fun comes up, alongside a face if he likes.
- New app emoji `wisp_child_dance`, made from Myra's `dancingchild.gif`
  (128 px, 12 fps, 225 KB). The Child now has it in `STAGE_DANCES`; the Baby
  still has no dance until there is art for one.

## 2026-11-02 (Wisp gets more personality)

- Myra wanted Wisp less bland for the song contest. `_WHO_YOU_ARE` in
  `wisp/voice.py` now adds: curious, jumps in
  before he thinks and talks his way back out, sweet under the sass, would
  drop everything for a friend, hears a beat in everything, secretly worries
  about his rhyming, and big fast feelings (joy, jealousy, stubbornness) that
  never keep him down for long. Every stage gets it, the Baby too.

## 2026-11-02 (Status and Vault posts unlocked; chat there is deleted)

- Myra found on her alt that the locked Status post's buttons don't work for
  members: Discord blocks interactions in a locked post. Status and the
  ViiBR Vault are no longer locked (`STUDIO_THREADS`), and setup now sets
  each post's lock to match its spec, so a rerun unlocks posts locked
  before. Only the Wisp FAQ, which has no buttons, stays locked.
- New `cogs/boards.py`: Wisp deletes what a member types in either post and
  says "This post is just for buttons. Come chat in #house", deleted after
  `BOARD_NOTICE_LIFETIME` (8 s). A burst gets one notice per post at a time.
  Staff, bots and Discord's own notices are left alone. Wisp needs Manage
  Messages; a failed delete is posted in the post.

## 2026-11-02 (Pokes and gifts tag the member)

- Myra: a poke or gift post that only names the member is easy to miss. The
  House post now opens with a tag and pings that one member:
  `♪ @member poked Wisp` and `♪ @member gave Wisp a ...`. Wisp's own reply
  under it still calls them by name.

## 2026-11-01 (Wisp follows the track drop talk)

- Myra told Wisp "sure i just did" and "i gotchu", and he kept sending her
  to the track drop. Two causes:
  - His memory of the House chat dropped channel links, so he read his own
    "put it in #track-drop" as "put it in so i can munch!" and asked again.
    `_clean` now reads the track drop as `#track-drop` and any other channel
    he can see as `#name`, without the emoji and divider its name opens
    with. Role mentions and channels he can't see are still dropped.
  - He had no idea who had fed him. The member he answers or who pokes him
    now comes with how many tracks they fed him today
    (`ActivityRepo.tracks_fed_today`, `Speaker.tracks_today`): with none he
    knows a track they mention hasn't reached him yet; with some he thanks
    them and doesn't ask for another.

## 2026-11-01 (Myra's prompt edits: faces, dances, things he knows)

- From Myra's edits in `DOCS/wisp_prompts/`. Every stage now uses only her
  face list (`STAGE_FACES`); from Teen on he used to get every uploaded
  `wisp_` emoji. The Child gains `wisp_dead`; Teen and up have
  `GROWN_FACES`: the little faces plus dead, sleepy, skeptical and rofl.
- New dance emojis with what each one shows (`DANCES`, `STAGE_DANCES`,
  listed under "Your dances" in his prompt): crazy dance, conductor dance,
  happy dance, head bang and slow dance from Teen on; the Rockstar adds the
  drummer, and the Rockstar and Old Fogey the guitar shred and rocks. The
  drummer is the Rockstar's alone (Myra). `cogs.speech.dances` picks the
  uploaded ones.
- From Teen on his prompt has Myra's "Things you know": the admins, the
  ViiBR site, his ViiBR and Suno profiles and his discography. Which stage of
  life he is on is filled in for each stage (her draft said "third" in all
  four). Typo fixes: `:wisp_happy dance:` is `wisp_happy_dance`, the missing
  colon on `wisp_skeptical`, "a song funk song" and "hip hop song song".

## 2026-11-01 (New stages are shared in general chat)

- Myra missed Wisp becoming a Teen. When he hatches, reaches a new stage or
  becomes an Old Fogey, he now also posts his stage picture in the server's
  general chat with Myra's line, "# Wisp just became a teen today! Go give
  him a birthday poke!" ("just hatched" for hatching, "an" before adult and
  old fogey). It pings nobody, and the House post is unchanged.
- General chat is set with his other channels: `!wisp setup #house #studio
  #tracks [#general]` and the new optional `general` box on `/wispadmin
  setup`. Leaving it out turns the posts off; setup refuses the track drop
  as general chat, and its answer lists "General chat". New column
  `settings.general_channel_id`. A general chat that cannot be seen, or a
  failed post, is reported in the House.

## 2026-11-01 (Wisp warms up to gifts)

- Myra's last four gifts were all passed on (a flat 1 in 3 each). He now
  keeps the first gift of a UTC day half the time (`GIFT_LIKE_CHANCE` 1/2,
  was 1/3), and each gift he passes on that day makes him `GIFT_LIKE_RISE`
  (1/4) more open: 3 in 4 for the second, and the third is always kept.
  Once he keeps one he is still full for the day. `wisp.gifts.like_chance`
  works it out from the collections given from today. The FAQ draft says so.

## 2026-11-01 (Myra's header pictures; Burrito's post is her picture)

- The music-symbol title bars (𝄃𝄞𝄚𝄆 Title 𝄇𝄡𝄚𝄂) did not show on some
  phones and older Macs, so Myra made them as pictures in Canva. The
  Leaderboard, Wisp's Lunchbox, the Snack Pack and the ViiBR Vault now open
  with her header picture (`ASSETS/leaderboard_title.png`,
  `lunchbox_title.png`, `snack_pack_title.png`, `vault_title.png`) and close
  with her footer (`ASSETS/box_footer.png`) instead of the text bars. The box
  lines (`╔═╗`) stay.
- A plain message shows pictures only under its text, so the header goes on
  its own just before the text, which carries the footer (Myra's way, the
  same as the Wisp Stats card). The Vault is a Components V2 message, so its
  header and footer are media galleries inside it.
- The pinned Vault card used to be the Vault post's first message. On the
  first refresh it is brought over like the Status post was: the first
  message keeps only the vault picture (the gallery thumbnail), and the
  Leaderboard header and the card go under it. The header's message id is
  the new `settings.vault_title_message_id` column.
- New `cogs/headers.py` holds the header pieces: `send_headed`, the media
  galleries, and `show_headed_card`, which the Status card now shares.
  `box_open`, `box_close`, `bars` and `title_bar` are gone from
  `wisp/text.py`, along with the Vault's logo emoji in its title.
- Burrito's post is now Myra's picture alone (`ASSETS/burrito_post.png`) with
  no text. An old Burrito post is edited to it on the next Studio setup.

## 2026-11-01 (/wisp only works in Wisp's House and Studio)

- A tester ran `/wisp lunchbox` in the waiting room and Wisp posted it there.
  `WispTree.interaction_check` now lets members' `/wisp` commands (and
  `/wisp play ...`) run only in the House, the Studio, or a thread or post
  inside either. Anywhere else the member gets a private line, "♪ Wisp's
  commands only work in #House and #Studio.", and the command does not run.
  Before staff set Wisp up, his commands work anywhere. `/wispadmin` is not
  held to his channels. A settings read that fails is reported like any
  other command failure.

## 2026-10-31 (Rhyme duels last longer; 4 second talk cooldown)

- Wisp kept giving up after one rhyme: every turn was a flat skill roll (a
  Child failed 35% of the time). Now his first turns always find a rhyme when
  one is left (`RHYME_SURE_TURNS`: Baby 1, Child 3, Teen 4, Adult 5,
  Rockstar 6, Old Fogey 4). After those, his `RHYME_SKILL` chance drops by
  `RHYME_TIRING` (10%) per turn, so he tires out instead of quitting at
  random. `wisp_reply` and `rhyme_chance` take the turn number.
- `TALK_COOLDOWN` is 4 seconds (was 15): the 15 second wait swallowed real
  replies. His House has a 5 second slow mode, set in Discord, so members
  can't outpace him.

## 2026-10-31 (No more /wisp status)

- `/wisp status` is gone (Myra: "it's pointless"). The pinned card in the
  Status post already shows everything, and a tester ran the command in the
  waiting room. `send_status_privately` went with it; the card tests now call
  `players.status_text` directly. README and the FAQ draft point to the
  Status post instead. The command leaves Discord on the next start, when
  the tree syncs.

## 2026-10-31 (Pickles: ask first, then the other side)

- When Wisp doesn't know someone's side on pickles yet, his prompt now says
  (Myra's approved wording): "You don't know where {name} stands on pickles
  yet. If pickles come up, don't pick a side: ask them if they like pickles.
  Once they answer, take the opposite side." Before, he picked a side himself
  and only argued against theirs from his next message on.
- Caught flip-flopping (his side depends on who he talks to), he plays
  innocent, in Myra's words: "If someone calls you out on it, act innocent:
  use :wisp_angel: and say something like "i dont know what you mean!""
  `wisp_angel` was copied from the ViiBR Assets server into Wisp's app emojis.

## 2026-10-31 (The status card as a quote under Myra's title picture)

- Text frames look different on every device, so Myra made the frames into
  pictures. The Status post is now three messages:
  - its first message shows only Wisp's picture, so the Studio's gallery
    shows him (it changes as he grows, gets sick or ends);
  - Myra's Wisp Stats title picture (`ASSETS/stats_title.png`) on its own;
  - the card, with the title picture attached under it, the Feed and Poke
    buttons, pinned and edited in place (`cogs/status_card.py`).
- The card text (`wisp/card.py`) is Myra's draft byte for byte: one Discord
  quote (`> ` lines, `wisp.text.quoted`), same live numbers and emoji meters,
  her blank lines and line breaks. The egg, hatching and waiting cards follow
  the same layout. `/wisp status` answers the same way, title picture first.
- A Status post from before is brought over on the next tick: the card text
  comes off its first message and the title and card are posted under it.
  The title post is remembered in the new `settings.status_title_message_id`
  column, so a deleted card is reposted together with its title.
- Setup pins the Status post to the top of the Studio forum
  (`StudioThread.pinned_post`); a failure is posted in the thread.
- Myra's Burrito card picture is saved as `ASSETS/burrito_post.png`, not used
  yet.

## 2026-10-31 (No shame pictures, one branch)

- `!wisp punish` no longer attaches a picture: Myra's shame GIFs belong to
  the counting game, so the ban line in Wisp's House is text only. The GIFs
  moved out of `ASSETS/shame` to the untracked `RECYCLING/shame`.
- The repo has one branch, `main`; `wisp-core` was deleted (fully merged).
- `CLAUDE.md` is no longer in the repo (it is in `.gitignore`).

## 2026-10-31 (The Studio as a gallery, and Burrito's picture)

- Setup now makes gallery view the Studio forum's default layout
  (`_show_as_gallery` in `cogs/studio.py`), once; a failure, such as a missing
  Manage Channels permission, is posted in Wisp's House.
- Burrito's post gets his picture (`ASSETS/thumbs/burrito.png`, a 600 px copy
  of his pfp), which the forum shows as its thumbnail. Setup adds it to the
  existing post like the other thumbnails.
- Myra will replace the text frames with images, since every device draws
  the frame symbols in a different font, so the frames are left as they are.

## 2026-10-31 (A real kid voice, and the track drop)

- The Child talked like an adult ("hey hey! got any fresh beats for me?"). His
  voice in `wisp/voice.py` is now about five years old, with example lines in
  the same style as Myra's Baby voice (excited, grumpy, sad, sleepy, silly,
  asking for food). Myra approved the draft.
- From Child on, Wisp knows members feed him in the track drop: when he asks
  for a track he sends people there, and a link posted in his House gets
  pointed there too (`_TRACK_DROP_NOTE`). He writes `#track-drop`, and
  `link_track_drop` turns it into a clickable link to the real channel
  (answers, pokes and chime-ins). The Baby still only babbles.
- `DOCS/wisp_prompts.md` regenerated.
- Fixed a stale test: Myra's rewrite says "Right now you're talking to …",
  which `test_named_member_is_called_by_their_wisp_name` still expected with a
  capital Y.

## 2026-10-30 (A 30-day life)

- Myra halved Wisp's life to keep the cute stages coming round more often. In
  `wisp/rules.py`:
  - The egg hatches at 20 meal points (was 30); coal eggs start with 10.
  - Child from day 5 (was 3), Teen from day 11 (was 7), Adult from day 16
    (was 14). Points and caretakers needed are unchanged.
  - Old Fogey at day 24 (was 45), farewell at day 30 (was 60).
  - Rockstar needs 4 days of high happiness (was 7), so it still fits in the
    shorter Adult stretch.
- Monster Pox (day 1 to 12) still comes before Adult. The FAQ's quick rules
  read these numbers, so they update when the FAQ is rebuilt.
- Tests that hard-coded the old days now read them from the rules
  (`tests/test_life.py`, `tests/test_voice.py`). `test_happy_counts_only_chatters`
  now expects the Happy bar on its own line, as house style v2.1 lays it out.

## 2026-10-29 (Myra's rewritten prompts: opening, Baby and Child)

- Myra rewrote Wisp's prompts to give him more personality. In `wisp/voice.py`:
  - One opening for every stage (`_WHO_YOU_ARE`): the AI mascot, a dark
    purple fire sprite with flaming orange hair, sick beats, suno tracks.
  - "How you talk": if asked whether he heard a song, he says he ate it
    before he listened; game questions go to Burrito, his fairy god-bot.
  - He no longer pretends not to be an AI: asked, he says yes, he's ViiBR's
    AI mascot, then carries on being Wisp (Myra's call).
  - Reactions: faces one per line, a firmer both-colons rule, and the "no u"
    GIF as a hyperlink, `NO_U_LINK` (`[no u!](url)`). `_cap` keeps the
    hyperlink or bare link whole when it cuts a long reply.
  - The Baby's voice: calls himself "wips", with Myra's example noises.
  - The bond ladder as a numbered list, then "Right now you're talking to
    {name}." with the bond and its number; the Baby is a little shy with
    overwhelming new faces.
- Faces per stage: the Baby and Child use only Myra's list of faces
  (`STAGE_FACES`, in her order, plus the nap face, and the dead face the
  Baby's examples use). Teen and older still get every uploaded face.
- `DOCS/wisp_prompts.md` regenerated.
- Tests: `tests/test_voice.py`, `tests/test_conversation.py`.

## 2026-10-29 (Wisp gets mad at the same member poking again and again)

- Myra wants Wisp to get mad when someone pokes him more than twice. Pokes
  are now counted per member as a streak (`HouseTalk.poke(guild, user, now)`):
  each poke within `POKE_STREAK_GAP` (10 minutes) of that member's last adds
  one; other members' pokes never count toward it.
- `poke_flavor` takes the streak: from `POKE_MAD_AT` (3) he is always
  `PokeFlavor.MAD`, from `POKE_FED_UP_AT` (5) always `FED_UP`. Below that it
  rolls as before; `ANNOYED` now only comes from being hangry.
- Mad and fed-up prompts let him be mean like a kid in a huff ("big meanie
  head") but never cruel. A Baby or Child gets a full tantrum. The egg
  rattles away, or turns its back.
- `POKE_SPAM_WINDOW` and `POKE_SPAM_POKES` are gone.
- Tests: `tests/test_voice.py`, `tests/test_conversation.py` (poke streaks).

## 2026-10-29 (Status and Vault posts locked; prompt reference)

- Myra asked for the Status and ViiBR Vault Studio posts to be locked like the
  FAQ: they are boards Wisp keeps updated, not places to chat. Their
  `StudioThread` specs now have `locked=True`; `!wisp setup` locks existing
  ones. Wisp still edits and posts in them (he does the same in the FAQ).
  Jam Space, Mealtime and Burrito stay open.
- `DOCS/wisp_prompts.md`: every prompt Wisp uses (egg, each stage, poke,
  chiming in, mood and Monster Pox layers, goodbye), generated from the code.

## 2026-10-28 (Wisp's emoji tags with a missing colon)

- Myra saw tags come through broken when the AI dropped a colon. `parse_reply`
  now converts `:name` and `name:` (one colon missing) when the name is a known
  expression and the match is a whole token: not inside a word, a URL, a time
  such as `3:00`, a ratio or a tag. Unknown names in those forms stay plain
  text (`Note: hi`), except names starting `wisp_`, `snack_`, `gift_`,
  `keepsake_` or `badge_`, which are removed like the full form.
- Half-formed Discord codes the AI writes itself (`<:name:>`, `<a:name:>`,
  `<:name:123` with no `>`) are converted when known and removed when not. A
  complete `<:name:id>` / `<a:name:id>` is never touched.
- Converted names still land in `Reply.expressions` (his favorite-emoji count).
- Tests: `tests/test_voice.py` (every form, edges, plain colons, unknown names).

## 2026-10-27 (FAQ banner pictures: one message per question)

- Myra found the page-shaped FAQ pictures shrank in Discord until the text was
  tiny, so the FAQ now uses 35 banner pictures, one per question, in
  `ASSETS/faq/` named `{NN}_{section}_{k}.png`. The 11 one-per-section
  pictures are removed.
- `cogs.faq.FaqSection.pictures` is a tuple of file names (was one `picture`).
  The 11 sections and titles are unchanged. `FAQ_PICTURE_COUNT` is the total.
- `fill_faq` posts every picture as its own message (one file each, so Discord
  shows each large, not as a grid), in order, with no pings. The first post's
  table of contents links each section title to that section's first picture;
  `table_of_contents` takes every picture's message id and raises `ValueError`
  unless there is one per picture. The 11 links come to about 1,200 characters,
  well under the 2,000 limit (tested at the largest possible ids).
- All posted ids are still stored in `settings.faq_message_ids`, even when
  posting stops part way, and the old stored ids, including the earlier
  one-per-section posts, are deleted first. Missing pictures still raise
  `FileNotFoundError` before anything changes.
- `ensure_studio` rebuilds the FAQ when the stored id count is not 35, so a
  restart replaces the earlier 11-picture FAQ by itself.
- No schema change: `faq_message_ids` is `TEXT` (up to 65,535 bytes); 35 ids
  are about 750 bytes as JSON. A repo test round-trips 500 ids on the real
  database.
- Tests: `tests/test_studio.py` (one file per message in order, links to each
  section's first picture, one-per-section posts deleted on rebuild, partial
  failure after 19 pictures stored, missing picture, contents length, code and
  repo pictures agree) and `tests/test_repos.py`. README updated.

## 2026-10-27 (lunchbox artist lookup: review fixes)

- Only a 404 or 410 song page now means "no artist" (kept as ""). Any other
  answer than the page (5xx, 429, 403, a redirect) raises
  `aiohttp.ClientResponseError` from `ShareLinkResolver.artist`, so the
  lunchbox shows `listen ♪`, logs a warning and asks again next time instead
  of keeping "" for good. Share-link resolving (`resolve`) is unchanged; the
  lunchbox is the only caller of `artist`.
- An artist name is put on one line (`cogs.share_links.one_line`: every run
  of whitespace, line breaks included, becomes one space) before it is kept
  and again when the link is drawn, so it can never break a box line.
- Tests: `tests/test_share_links.py` (404/410 name none; 500/503/429/403/301
  raise; names with line breaks) and `tests/test_wisp_lunchbox.py` (a busy
  site leaves the artist unknown and the next view stores it, on the real
  database; a stored name with line breaks is drawn on one line).

## 2026-10-27 (house style v2.1: spacing, matching bars, wrapping)

- Myra's spacing pass (`DOCS/specs/2026-10-27-house-style.md` is updated to
  v2.1). Presentation only; every behaviour stays.
- Burrito's post is her text byte for byte (blank lines, 6 `𝄚` each side, a
  22-`═` box, two wrapped lines), and `!wisp setup` now edits an existing
  Burrito starter whose text differs (`StudioThread.current_content`). A
  starter that is gone is left alone; a failed edit is posted in the thread
  as `Error in updating the first post of Burrito, Fairy God-bot: ...`.
- `wisp.text.visual_width` estimates how wide a line looks in Discord from
  one table (`WIDTHS`), calibrated on her Burrito post (a 22-`═` box holds
  every line and breaks where she broke them; 6 `𝄚` around its title match a
  20-`𝄚` bottom bar) and on her Vault padding (a space is about 0.22 em). A
  custom emoji counts 1.375 em and a mention 6 em.
- `wisp.text.bars(title)` gives the title bar and a bottom bar sized to look
  as wide; every layout's box top and bottom have the same number of `═`.
  Widths: status card (and waiting card) 25 (a full bar line: 10 meter
  emojis and `│100%`), Vault 24 (the widest badge row), Snack Pack,
  lunchbox, leaderboard and Burrito 22.
- `wisp.text.wrap` breaks every line wider than its box at word boundaries
  into `║ ` continuation rows: at single spaces, between emoji (a line of only
  emoji wraps between them) and before a `・`, which then leads the next row
  (never ends one). A full row breaks before its last `・` part so each part
  keeps together (`║ ・ peak Teen` / `║ ・ hatched by @someone`), and a
  badge's reason moves down whole (`║ ・Bandmates only`); never inside Myra's
  padding, bold text or a masked link.
- Blank `║` lines are back exactly where her drafts have them: the status
  card (after the box top, after the DAY section, after the meters, after the
  fed and the tracks lines, after the hints, before the box close; the
  waiting card the same), the Vault (after the box top and after the snack
  rows) and the leaderboard (after the intro sentence and its wrapped lines,
  after each list). The Snack Pack and lunchbox drafts have none.
- Status card meters: each bar moves down onto its own line under its label
  (`║𝄡 Care`, then `║{bar}│65%`), nothing else in the block changes, and the
  three meters follow each other with no blank line. The label padding is
  gone with the bar (`wisp.card.LABEL_PADDING` removed).
- Lunchbox song links are masked links named for the song's artist
  (`║𝄡 [Foggy X Music](url)`), or `[listen ♪](url)` when unknown (Myra: "just
  do the artist"). Never broken across lines; a long artist is shortened with
  `…` to fit the box; markdown in the name is escaped.
- The artist comes from the song page's schema.org `byArtist`
  (`ShareLinkResolver.artist`, `cogs.share_links.artist_on_page`). Small
  calls, made here: it is looked up lazily, the first time the lunchbox shows
  a song (all shown songs at once), not when the favorite is picked, so the
  daily tick never waits on viibrmusic.com and each song is asked about once.
  The result is kept in the new column `favorites.artist` (added on startup;
  NULL = not looked up yet, "" = the page names none). When the site cannot
  be reached, the link reads `listen ♪`, a warning is logged (no channel
  post: the lunchbox itself worked) and the lookup is tried again next time.
- Tests: `tests/test_text.py` (widths, calibration, bars for every layout
  title, wrapping rules), `tests/test_card.py`, `tests/test_studio.py`
  (Burrito's exact text, setup updating the old starter, a missing starter,
  a failed edit), `tests/test_vault.py`, `tests/test_snacks.py`,
  `tests/test_badges.py`, `tests/test_gifts.py`, `tests/test_magazines.py`,
  `tests/test_wisp_lunchbox.py` (artist links against a local song-page
  server) and `tests/test_share_links.py`; `tests/layout.py` gains
  `assert_fits_its_box` for the fullest layouts.

## 2026-10-27 (Rockstar magazines)

- While the living Wisp is a **Rockstar**, the Vault shows a `# **Magazines**`
  section between Badges and Gifts: `VIIBRATIONS cover・{mini} 100 WC` and
  `Music & Science cover・{mini} 100 WC`, `・owned` once bought this life, and a
  "Get a magazine" menu under it with the covers the member can still buy. At
  every other stage (and between Wisps) the section and menu are absent.
- Buying spends 100 WC (`MAGAZINE_COST`), with the usual refusals: banned,
  can't feed, short of WC (Wisp's not-enough-points line), or already owned
  this life (`♪ You already have the VIIBRATIONS cover for Wisp v1.`). A menu
  left open after he stops being a Rockstar answers
  `♪ The magazines are gone from the shelf.` and nothing is spent. A purchase
  refreshes the Vault under `♪ You got the {name}.` and sends the cover's
  picture to the buyer only (ephemeral). A picture that cannot be sent is
  reported as `Error in sending the {name} picture (the purchase went
  through): ...`; the purchase stands.
- Purchases are stored in the new `magazines` table (member, magazine, life,
  version, time; one per member per magazine per life), created by
  `create_tables` beside the live tables.
- The Snack Pack has a `# **Magazines**` section after Badges, only when the
  member owns a cover: `Wisp v3's VIIBRATIONS cover`, every life, newest
  first, cut to fit like keepsakes (at most a quarter of the room).
- Art: posting copies `ASSETS/mags/viibrations_cover.jpg` and
  `ASSETS/mags/musicnscience_cover.jpg` (927x1200, JPEG q88, about 230-250 KB)
  made from the 3477x4500 originals, which are committed alongside.
- FAQ: a "What are the magazines?" Q&A in the Vault and Snack Pack section
  (the section picture needs re-rendering).
- Tests: `tests/test_magazines.py` (section only for a living Rockstar, the
  purchase, the private picture, the refusals, the next life, the Snack Pack
  across lives, the fullest Vault and Snack Pack) and a schema test for the
  new table on a live database.

## 2026-10-27 (`!wisp song`)

- New staff command `!wisp song <link> <words...>`: Wisp posts the words, then
  the link on the line underneath, in the Jam Space thread, exactly as typed
  (no prefix, flair or AI line, no pings, link previews left on so the player
  shows). The staff member's command message is deleted afterwards; a failed
  delete, such as a missing Manage Messages permission, is only logged.
- The link must be an http(s) URL. A missing or bad link, or no words, gets
  the usual one-line usage. A Jam Space that is not set up or cannot be
  reached is reported as `Error in !wisp song: ...` where the command was
  used, nothing is posted and the command message stays.
- Tests: the post, the exact text, the deleted command, bad and missing
  arguments, an unreachable Jam Space, a Discord refusal, a failed delete and
  a non-staff author.

## 2026-10-27 (Monster Pox, Hunger and Burrito's post)

- His once-per-life childhood cold is now **Monster Pox** everywhere members
  read it. His SICK and RECOVERED lines and his AI voice while sick are
  spotty, itchy and feverish with a thermometer instead of sniffly and sneezy,
  and the spots are back. The rules post, FAQ, spec page, README and build
  rulings say Monster Pox. Code names (`is_sick`, `cold_*`, `SICK_*`,
  `Moment.SICK`/`RECOVERED`) are unchanged, and a "cold egg" is still a cold
  egg.
- The food meter's member-facing name is **Hunger** (a full bar means well
  fed): `♪ Wisp ate your Cheese ・ hunger +8`, the Vault and feed menu
  descriptions (`3 WC ・ hunger +5`), the rules post (`・Hunger: tracks and
  snacks...`), two hangry lines that named the meter, the FAQ, the spec page
  and the README. `Life.full` and `FULL_*` keep their names.
- The rules post's sickness line reads `・Once before Adult: Monster Pox for
  {h} h. Faster drain, he can't die, meals count up to {n} a day`, and the
  Last Ember line drops "each". At four-digit numbers it is 1,994 of 2,000.
  (Run `!wisp faq` to refresh the live post.)
- Setup keeps a sixth Studio post, `🧚│Burrito, Fairy God-bot`, created when
  missing and renamed back like the others, its id in the new additive
  `settings.burrito_thread_id` column. Its first post is the house-style frame
  titled `𝔹𝓊𝓇𝓇𝒾𝓉𝑜`, saying Burrito is Wisp's fairy god-bot, to ask him
  anything about how Wisp works right there, and that he points people to
  Wisp's live stats. Wisp never answers or chimes in there (Burrito, a separate
  bot, does). Run `!wisp setup` (or `/wispadmin setup`) once to create it.
- The House notice for recreated Studio posts and setup's "Created threads"
  line quote each name (`recreated "Mealtime", "Burrito, Fairy God-bot".`),
  so a name with a comma reads as one post.
- Tests: the feeding tests for endings now check the Begin again flow (the
  ending is announced, staff are asked, no egg is laid), setup expects six
  Studio posts, and the schema adds `burrito_thread_id` to a live table.
- The FAQ page and the spec page show the v2 status card.
- `/wisp lunchbox`: once the lunchbox is posted, a failure to remove the
  private "thinking" reply is ignored, so the member is no longer told it did
  not work.

## 2026-10-27 (house style v2)

- Myra's house style (`DOCS/specs/2026-10-27-house-style.md`) for the status
  card, the Vault, the Snack Pack, the lunchbox and the leaderboard: a title
  bar (`𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {Title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂`), the box (`╔`/`╚` with 20 `═`), `#`
  headings `║𝄡𝄚𝄂𝄆 **Name**`, `##` lines `║𝄡𝄚𝄂 text`, `###` items `║𝄡 text`,
  `╠═══⇕` between sections and the bottom bar. Every frame piece lives in
  `wisp/text.py` (`title_bar`, `BOX_TOP`, `BOX_CLOSE`, `heading`, `sub`,
  `item`, `note`, `sections`, `framed`); the old `VAULT_RAIL`/`PACK_RAIL` and
  per-module frame strings are gone.
- Status card: `𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈`, bars Care, Happy, Hunger (Hunger is the Full
  meter) with the meter app emojis: one `_full` per whole 10% of the shown
  percent and one `_left` when its last digit is 5 to 9, else a space before
  `│` (65% is six full and a left; 90% nine full and a space; 0-4% nothing).
  The egg cards use the same frame (Warmth with the `full_` meter, Hatching and
  Emerging with the `happiness_` meter). The sick line reads
  `he has Monster Pox・{n} h left`. The waiting (Begin again) card is the frame
  with one line, `No Wisp right now. Waiting for staff to begin again.`, on the
  status card and in `/wisp status`. `render_status` takes the emoji lookup.
- The Vault is now one Components V2 message (`VaultLayout`, a `LayoutView`
  with no container): text displays with the snack select under the snacks,
  the badge select under the badges and the collection and gift selects under
  the gifts, up to 4,000 characters of text. Myra's snack and badge names and
  padding, prices in WC with the `wisp_coin_mini` emoji, the balance as
  `wisp coins: {coin} {n}`, the gamble line under Gifts. Purchase notes say WC
  (`♪ Bought Cheese for 6 WC.`, `Your WC are back.`) and the select
  descriptions too. Everything else (private, refusals, the two-step gift
  select, errors) works as before.
- Snack Pack, lunchbox and leaderboard in the frame. Empty sections read
  `none yet` (`nothing saved yet` for snacks). Each lunchbox song is a day and
  sharer line, then its link; each collection a progress line, then its gifts
  and givers while there is room.
- `/wisp lunchbox` is public: it posts in the channel where it was used,
  pinging nobody and with link previews suppressed. Used where Wisp never
  posts (the track drop, or a channel that cannot be placed) it posts in Wisp's
  House and tells the member privately; with no House it is shown only to
  them.
- `wisp.text.SEPARATOR` is Myra's plain divider
  `𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂`. `fit()` and `richest()` measure with
  `text_length` (UTF-16), as the frames' music symbols count twice.
- `wisp_coin_mini` is a coin, not one of Wisp's faces: it is left out of his
  expressions and described as the Vault's coin in the AI prompt.
- CLAUDE.md and README describe the house style, the new divider and the
  public lunchbox.
- The new divider costs 18 more UTF-16 units than the old one, so the FAQ's
  quick rules are tightened to fit: the intro reads "One Wisp for the server:
  share music and he grows from egg to Rockstar.", and the Vault lines say WC
  for spending (`/wisp vault spends WC on snacks and gifts`, `Gifts cost 15
  WC`). 1,946 of 2,000 at today's numbers; the all-9999 guard fits again.
  (Run `!wisp faq` to refresh the live post.)
- Rhyme Duel summaries are measured by `text_length`, and the last-resort cut
  uses the new `wisp.text.clip`, which never splits a character.
- `/wisp lunchbox` acknowledges privately and posts the lunchbox as a message
  of its own in the channel (the private acknowledgement is then removed), so
  a failure is told only to the member and still reported in the channel.

## 2026-10-27 (begin again)

- No egg is laid on its own after an ending any more. A death, a cold egg and
  an old-age farewell are each announced as before (the ending post and
  picture, the Last Embers and goodbyes, the badge sweep, the Vault card), then
  Wisp's House asks `♪ Do you want to begin again?` with a persistent **Begin
  again** button (`wisp:begin`), pinging nobody.
- Only staff (`is_staff`: the app owner, Manage Server or a staff role) can
  press it; anyone else hears `♪ Only staff can start a new Wisp.` privately.
  A press lays the next egg under the guild lock exactly as the automatic path
  did (next version, coal egg halfway hatched after a full life, the new-egg
  post with its picture and Poke Wisp button), updates the status card and the
  House panel at once, disables the question's button and answers
  `♪ A new egg is on its way.` A press that finds a life that is not over (a
  second press, two staff at once, an old question) lays nothing and answers
  `♪ Wisp is already here.`, disabling that stale button too. A press also
  gives any Last Embers an unannounced farewell never gave. Failures are
  reported where it was pressed.
- While waiting, the status card says `♪ No Wisp right now. Waiting for staff
  to begin again.` with the picture of how he ended (no picture when that art
  is missing) and only the Begin again button, so a question that was never
  posted or was deleted can never strand the server; `/wisp status` says the
  same line. The life loop lays nothing for an ended life, also after a
  restart.
- `!wisp begin`, a staff command doing the same as the button: lays the next
  egg after an ending, or answers `♪ Wisp is already here.`
- While waiting, the life loop picks no favorite song and `!wisp punish` posts
  nothing in Wisp's voice (the staff answer notes it, as with no life).
- The quick rules now say "Neglected, he fades; staff start the next egg."
  (Run `!wisp faq` to refresh the live post.) `show_in_thread` gains
  `clear_image` to take a card's picture off.
- A server that has never had a Wisp still gets its first egg from the life
  loop, with no button.
- `!wisp eggs on|off` is gone, with its docs and its place in the staff command
  list. The `settings.lay_eggs` column stays in the live database but is no
  longer read, and the `Settings.lay_eggs` field is removed.

## 2026-10-26 (name ask tags the member)

- When Wisp asks a member what to call him, the post starts with their @tag
  and pings only them, so it isn't lost in a busy chat.

## 2026-10-26 (Myra's status menu, three meters and the childhood cold)

One feature, built in seven steps. Wisp's old single meter is now three, each
with its own job, and Myra's status menu shows them.

### The three meters

- **Full** is the food meter, renamed from "Care" because Care did not read as
  food. Same behaviour: tracks and snacks fill it, it drains daily, he is hangry
  when it is low and dies at 0. The snack confirmation, the Vault and Snack Pack
  dropdowns and the status card say "full +n" and "full" instead of "care". The
  database column keeps the name `care` and still holds Full, so nothing is
  renamed or migrated for it.
- **Happy** is how many different members chatted with him in the last 24 hours
  (full at 5). A member's first poke or mention of the UTC day records a new
  `chat` interaction and gives 1 Vault point (`CHAT_POINTS`); later pokes and
  mentions that day give nothing. Only members who can feed Wisp and are not
  banned earn it; everyone else can still talk to him. If the credit fails (a
  database error) it is reported in the channel and Wisp still replies. A chat
  counts toward Wisp learning a member's name, but not toward bond, growth,
  caretakers, the "fed by" line or the stage-up keepsake. Feeding and playing no
  longer raise Happy. It still drives Rockstar.
- **Care** is a new meter for rhyme duels and gifts, 0 to 100. It starts at 50
  when he hatches and drains 10 a day while he is alive (`CARE_*` in
  `wisp/rules.py`). Each Rhyme Duel that counts as play adds 10, and every gift
  bought adds 8, whether he keeps it, passes on it or already kept one today,
  since the points are spent either way. A refused gift adds nothing.
- Each Rhyme Duel that counts as play (the daily limit of 5, a scored rhyme and
  the right to feed) also pays 1 Vault point (`PLAY_POINTS`).
- Below 30 Care he is lonely. Hangry still wins when Full is low too. Lonely only
  changes how he talks: his AI voice is told he is lonely and grumpy (never
  blaming anyone), and pokes, chat fallbacks and Baby talk have lonely lines.
  Every other moment uses its happy lines when he is lonely. It never hurts him:
  no death, no growth penalty.
- The first time Care drops below 30 he posts once in the House (again after it
  climbs back to 30 and drops again), with a picture for his stage picked at
  random from `LONELY_PICTURES`: Baby `cry_baby.gif` or `grumpy_baby.png`,
  Child `grumpy.gif`, Teen and older `cry_teen.gif`. A missing picture means a
  text-only post. A lonely Wisp's track reaction in Mealtime shows `wisp_sad`.
- New repo counts for the card: `chatters_since`, `feeders_since`,
  `chatted_today` and `tracks_today`.

### The childhood cold

- Once per life Wisp catches a cold, like the chicken pox. When he is a living
  Baby, Child or Teen the life loop rolls when it is due: a random time 1 to 12
  days after he hatched (`COLD_EARLIEST`, `COLD_LATEST`). Adult needs 14 days, so
  every Wisp who grows up has had it. A due cold starts before the growth check
  on the same tick, so even after days offline he catches it before he can grow
  to Adult. Adults and older never catch one, and a living young Wisp from before
  this change gets his cold rolled on his next tick.
- The cold lasts 48 hours of credited time (`SICK_FOR`); frozen and offline time
  beyond the usual 15 minutes do not count, and a frozen Wisp never starts one.
  If he grows a stage while sick, the cold carries on.
- While sick his Full drains 1.5 times as fast (`SICK_DRAIN_MULTIPLIER`), but the
  drain never takes it below 1 (`SICK_FULL_FLOOR`), so he cannot die while sick.
  He can still be hangry and fading, and those posts still come. Normal rules
  come back when he is better.
- While sick each member's daily meal cap is 30 instead of 15
  (`SICK_EXTRA_MEAL_CAP`), room for about one extra song and one extra snack.
  `meal_grant` takes the cap and `daily_meal_cap(life)` gives it.
- He posts once in the House when he catches it (with `sick_baby.png`,
  `sick_child.png` or `sick_teen.png` from `ASSETS/moments/` for the stage he is
  in; text only if the file is missing) and once when he is better (with his
  stage picture). Both have their own canned lines. While sick the status card
  and the Poke Wisp panel show his sick picture, and his AI voice is sniffly and
  sneezy.

### The status card

- The card follows Myra's template (`DOCS/specs/status_menu_template.txt`) in her
  frame, kept exactly as she wrote it. It is still posted in the Status thread
  and by `/wisp status`, with the same picture and buttons.
- Living Wisp: `𝐃𝐀𝐘 **{day}**`, then the bars Full 🟦, Happy 🟪 and Care 🟥. A bar
  is one square per 10% (rounded half up, filled squares only, so 0% shows none)
  and then `│{percent}%`; the squares follow the shown percent. While he has his
  cold a line under the DAY line says `・he has a cold・{hours} h left` (hours
  rounded up).
- "Fed by {nn} people today" counts only members who fed him or gave a snack
  (FEED, SNACK, FREE_SNACK) since UTC midnight, "person" for one. Chats and games
  no longer count. A new line shows today's ViiBR and Suno tracks.
- The hints mention Wisp and the House channel (or say "in his House" when none
  is set) and point to `/wisp snackpack`. The life stage is in bold capitals,
  such as 𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘.
- Egg and hatching cards use the same frame without the DAY line: Warmth 🟧 and
  Hatching 🟨 for an egg, Emerging 🟨 while hatching, stage 𝐄𝐆𝐆 or 𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆, and
  "Poke the egg".
- The card no longer shows the life's version number (her template has none).
- Bar label padding is one table, `LABEL_PADDING` in `wisp/card.py`, to tune from
  Myra's screenshot: Full 8, Happy 3, Care 6, Warmth 3, Hatching 1, Emerging 1
  spaces.

### The divider

- Myra's divider `❱❱━━━━━━━━━━━━━━━━━━━━━━━━━━❰❰` replaces the old
  `・♪ ────────・──────── ♪・` line in every Wisp post that uses it. The project
  rules now allow Unicode emoji in designed text (the status card and the
  divider); AI replies and canned lines stay emoji free.

### Words members read

- The quick rules post in the Wisp FAQ explains the three meters, the points for
  first pokes, chats and duels, and the cold with its bigger meal limit. It was
  already near Discord's 2,000 limit, so some wording is shorter: "takes his
  place" became "takes over", the Snack Pack and lunchbox pointers share a line
  under the Vault, the Old Fogey and farewell lines are one line, the talking
  section keeps what talking earns and who chimes in, and the bond tiers read
  "Familiar 50". It is counted with `text_length` and still fits at four-digit
  numbers.
- The README has a section on the three meters and the cold, the spec page
  `DOCS/wisp_tamagotchi.html` describes them (Full, Happy, Care, the cold, duel
  points and the new card), and `DOCS/BuildRulings.md` has the rulings.
- The FAQ pictures in `ASSETS/faq/` still show the old wording and need
  re-rendering; the sentences are listed in the task 7 report.

### Database

- Five new `lives` columns, all added to the live table at startup, nothing
  renamed or dropped: `fondness DOUBLE NOT NULL DEFAULT 50` (the Care meter),
  `lonely_warned BOOL NOT NULL DEFAULT 0`, `cold_due_at DATETIME NULL`,
  `cold_left DOUBLE NOT NULL DEFAULT 0` and `had_cold BOOL NOT NULL DEFAULT 0`.
  The old `care` column still holds Full. The `chat` interaction fits the
  existing `kind` column.

## 2026-10-25 (farewell art)

- When Wisp dies of old age, the farewell post shows his flame burning down
  until only a coal and his headphones are left. It plays once. The Last
  Ember posts after it keep the coal picture.

## 2026-10-25 (Old Fogey sigh)

- Removed again the same day: Myra is making a better one. The grew-old post
  uses the still Old Fogey picture until then.

## 2026-10-25 (Vault and Snack Pack frames)

- The Vault shop follows Myra's template: the balance above a ViiBR Vault
  frame with the `viibr_logo` emoji, and inside it each snack and badge as its
  emoji and price, then the gift collections. Names, care and bond stay in the
  dropdowns.
- The Snack Pack follows her template: a box with the member's mention and
  balance, then Snacks ("cheese :snack_cheese: x2"), Keepsakes and Badges
  ("Wisp v1's" and the item's emoji). An item whose emoji is missing shows
  its name.
- Message length is counted in UTF-16 units, so the frame's music symbols can
  never push a message past Discord's limit.

## 2026-10-25 (egg art)

- New egg picture for the status card, the Poke Wisp panel and new-egg posts.
- An egg born from the Last Ember's coal has its own glowing coal egg picture.
- An egg that goes cold is posted with a cold blue egg picture.

## 2026-10-24 (faster answers, the free snack in the Vault)

- The AI chain asks Groq first, then the Gemini fallback model, the Gemini
  chat model and OpenRouter. Each provider gets 8 seconds (was 12).
- The AI chain and the share-link resolver open no new HTTP session once
  closed, so a request still running at shutdown no longer leaves an
  unclosed session behind.
- The log has one line per AI answer (provider and time) and one per poke or
  mention (time from receiving it to posting). Keys and prompts are never
  logged.
- The Vault's Snack Box starts with the free Sine Wave and how to feed it;
  the buy select still lists only paid snacks.

## 2026-10-24 (staff review fixes)

- `!wisp staff add` refuses @everyone, and a stored @everyone row never makes
  anyone staff.
- Retired badges keep their real names in the Snack Pack ("ViiBR Roadie").
- Setup refuses a House that is also the track drop.
- When staff cannot be told apart because the database or Discord failed,
  nobody counts as staff and nothing is posted; the failure is logged.
- `!wisp eggs` takes on or off in any case.
- Bare `!wisp` is not talk to Wisp either.
- The Snack Box is ordered by price: Sine Wave, Cloud, Jelly and Juice Wave,
  Spicy Wave, Cheese, Pickles, Glitter Wave, ViiBR Wave.

## 2026-10-24 (panel picture)

- The Poke Wisp panel in Wisp's House shows his current picture, the same one
  as the status card. Setup attaches it to a new panel, or to an existing one
  without a picture. The life loop changes only the attachment, only when the
  picture changes (once more after a restart), and leaves a missing panel,
  missing art or an ended life alone. A refused picture uses the status
  card's fallback.

## 2026-10-24 (four badges)

- The Vault sells four badges: Pickle Diplomat (25 points, bond +5), Flame
  Keeper (100, +15), Team ViiBR (250, +25, replacing Team Wisp) and Bandmate
  (250, +25, Bandmate tier only). Egg Warmer and ViiBR Roadie are no longer
  sold.
- Startup moves stored `team_wisp` badge roles and purchases to
  `team_viibr`; repeating it changes nothing.
- Setup renames a badge role whose name is not its badge's ("Team Wisp"
  becomes "Team ViiBR"), and deletes the roles Wisp stored for badges no
  longer sold, then forgets them. A failure is posted where setup ran and
  the role stays stored for the next setup.
- A badge bought before it was retired stays in the Snack Pack under a name
  made from its key ("Egg Warmer"), and the sweep still takes its role back.
- Badge icons for the four badges are in `ASSETS/badges`.

## 2026-10-24 (staff command follow-ups)

- `/wispadmin setup` and `/wispadmin faq` are back as slash commands beside
  `!wisp setup` and `!wisp faq`, sharing their logic. The group needs Manage
  Server by default, answers privately, and turns away anyone who is not
  staff with "That command is for staff."
- Setup pins a Poke Wisp panel in Wisp's House ("♪ Poke Wisp", with the Poke
  Wisp button). Its id is kept in the new settings column
  `house_panel_message_id`, added to a live table at startup. A rerun leaves
  it alone, re-pins it or gives back its button, and posts a new one when it
  was deleted. A failure, such as a missing Pin Messages permission, is
  posted where setup ran.
- Wisp's House conversation ignores `!wisp` commands: they are not answered,
  not chimed in on and not kept as chat context.

## 2026-10-24 (staff commands move to !wisp)

- Staff commands are typed text commands now: `!wisp setup`, `roles`,
  `food`, `freeze`, `unfreeze`, `eggs`, `faq`, `punish`, `unban`, `strip`
  and `resetname`, with the same behaviour as before. The `/wispadmin` slash
  group is gone; members' `/wisp` commands are unchanged.
- Staff are the app owner, Manage Server holders and members with a staff
  role. `!wisp staff add|remove|list` manages the staff roles, kept in the new
  `staff_roles` table (created at startup when missing). Anyone else is
  ignored without a reply.
- Answers are public, in the channel the command was used in, or in Wisp's
  House from the track drop. Wrong arguments get a usage line, an unknown
  command gets the list of commands, and a failure is posted where the
  command was used. `!wisp punish` now posts one public answer, the log line
  with the reason, instead of a log line plus a private reply.
- Bare `!wisp` gets no reply; it is kept for the help menu. Mentioning Wisp
  never runs a command.
- Bot messages that named `/wispadmin` now name the `!wisp` command.

## 2026-10-24 (eggs switch)

- `/wispadmin eggs on|off`. Off: when a life ends no egg is laid, by the
  ending or by the life loop's self-heal, and the House says once "No new egg
  for now". The ending is still announced, the Last Embers still given and
  the badge roles still taken back. On: the next tick lays the egg, a coal egg
  after a full life. A living Wisp is unaffected.
- New settings column `lay_eggs` (default on), added to a live table at
  startup.

## 2026-10-24 (poke and badge review fixes)

- A badge bought again in a new life keeps its role: the purchase marks the
  member's older purchases of it as done, and a sweep that takes a role off
  while the same badge is bought for the current life gives it straight back.
- A purchase found already recorded is refunded and refused, and a role that
  fails to be given for a network reason (not only a Discord error) is
  refunded too.
- Setup stops at the first missing permission and reports it once; a new
  badge role that cannot be stored is deleted again and reported.
- The badge sweep stops for the tick at a missing permission.
- Wisp's own emojis: only names Discord allows (2 to 32 ASCII letters,
  digits and underscores) are read, a server emote's name is never read out
  as words ("a ViiBR emote of Wisp"), and `badge_<key>` emojis read as "your
  <Badge> badge".

## 2026-10-24 (badges, take two)

- Badge roles come off through a sweep on every life loop tick: each
  purchase of an ended life whose role is still on is taken back and marked
  (new `badges.removed_at` column and an index on it, added to a live table
  at startup). A restart between the new egg and the removal heals on the
  next tick, a marked purchase is never handled again, and a failure is
  retried each tick and reported once per streak.
- Each badge has its own House phrase: "joined Team Wisp", "is now an Egg
  Warmer", "is now one of Wisp's Bandmates" and so on. The member's note
  reads "You got the Team Wisp badge".

## 2026-10-24 (badges)

- The ViiBR Vault sells six badges, vanity roles worn for the current Wisp:
  Egg Warmer and Pickle Diplomat (25 points, bond +5), Flame Keeper and ViiBR
  Roadie (100, +15), Team Wisp and Bandmate (250, +25; Bandmate only at the
  Bandmate bond tier). Badge bond is outside the daily casual cap. The Vault
  lists them with "owned" or "Bandmates only", and a "Get a badge" select
  offers the ones the member can get now.
- A purchase is made under the guild lock; the role is given after it. If
  Discord will not give the role, the points, the purchase and the bond are
  all undone, the failure is posted where it happened and the member is told.
- The House announces "{name} is now a {badge}" with a new Badge Bought line.
- When a life ends, its buyers lose those roles (members are fetched by id; a
  member who left is skipped). The next Wisp sells every badge again.
- The Snack Pack has a Badges section: every badge ever bought, as "Wisp vN's
  {badge}", with its `badge_<key>` emoji when uploaded.
- `/wispadmin setup` creates the missing badge roles (by stored id, so a
  deleted one is recreated), with `ASSETS/badges/<key>.png` as the icon when
  it exists and the server has role icons, and adds icons later. Wisp needs
  Manage Roles.
- New tables: `badge_roles` and `badges`, created at startup.

## 2026-10-24 (Poke Wisp)

- A Poke Wisp button on the status card (next to Feed Wisp) and on the
  House's new-egg and coal-egg posts. A poke posts "{name} poked Wisp" (or
  "poked the egg") and his AI reaction in the House, in his stage's voice,
  and answers the member privately. Each poke rolls a flavor: tickled most
  often, sometimes startled or curious, woken up after 2 quiet hours or
  between 3 and 7 AM UTC, annoyed by 3 pokes in 2 minutes or when hangry.
  The egg has its own sleepy, grumpy and ticklish versions. A failed AI
  falls back to an egg poke line or a new Poked line. Banned members, no
  life and the cooldown are refused privately. A poke earns nothing.
- Mentions and pokes share one talk cooldown per member, kept on the bot
  with the House's recent chat.
- The status card says "poke him, or mention @Wisp in his House" ("poke the
  egg" for the egg).
- Wisp recognises his own emojis: a message to him that uses one of his app
  emojis or an emote with "wisp" in its name tells the AI what it shows (his
  happy face, a gift, a keepsake, a snack).
- The Baby is no longer offered the "no u" GIF.

## 2026-10-24 (the egg and baby talk, and dropped connections)

- The egg and the baby answer through the AI, so pokes stop repeating. The
  egg (hatching too) replies with one short line of wordless third-person
  action, reacting to how fed and warm it is, whether it is a coal egg, how
  far its hatching is, and whether the poker fed it or fed it most. Now and
  then it posts its own `wisp_egg` emoji, which no hatched stage is offered.
  The baby answers with baby noises and single words, fussy when hangry,
  never swearing; he keeps the pickle tag and may use one expression. When
  the AI fails, the old egg and baby lines are the fallback. The egg's
  replies save nothing; the baby's save a pickle stance.
- Database reads retry once on another connection when the connection was
  lost (MySQL errors 2006 and 2013); the lost connection is closed so the pool
  never hands it out again. Writes are never retried, since a lost write may
  already have been applied. Pooled connections are recycled after 4 idle
  minutes instead of an hour, since the network drops idle ones.

## 2026-10-24 (new toys)

- Three new gift collections in the ViiBR Vault: Tamagotchis (Hawaikotchi,
  Mimitchi, Tamagotchi Nano, Welcotchi), Tetris (Tetris Handheld and the I,
  L, T, S and Z Blocks; six gifts) and Jewels (Amethyst, Crystal, Rainbow
  Jewel, Ruby). Their gifts are named as they are, without a collection
  noun, and "an L Block" and "an S Block" read right.
- Giving a gift is two steps: pick a collection (its first gift's emoji and
  how many are left), then one of its gifts. Neither select can pass
  Discord's 25 options. A collection someone gave from a moment ago is
  refused with the reason.
- Gift and keepsake art is looked up as an animated GIF first, then a PNG.
- The Old Fogey keepsake is the Time Piece (it was the Reading Glasses,
  which nobody had earned yet).
- The Vault's Gifts and the lunchbox's Collections fit one message in the
  worst case: a collection shows each gift while there is room, else only
  how many are left or its progress.

## 2026-10-24 (milestone keepsakes)

- Wisp's big moments give a keepsake to the member who was there: the
  Eggshell when the egg starts hatching (to the member whose feed filled it),
  the First Spark, Teen Spark, Adult Spark and Guitar Pick when he grows into
  a Child, Teen, Adult and Rockstar, and the Reading Glasses when he grows
  old (to the member of the latest interaction with that life). Nobody gets
  one when nobody was there or the member is banned; each is given once.
- Wisp's House announces it with a new line, and attaches
  `ASSETS/keepsakes/<kind>.png` when it exists. The Last Ember post attaches
  `ASSETS/keepsakes/last_ember.png` the same way.
- The Snack Pack shows each keepsake's app emoji `keepsake_<kind>` when it is
  uploaded.
- The rules post says "Be there as he grows to win a keepsake".
- Share links: a redirect with an unparseable address names no song instead
  of raising, and link patterns match ASCII only, so Unicode case folding
  cannot pass a non-ASCII URL for a link.
- New keepsake kinds; no new columns.

## 2026-10-24 (viibrmusic.com share links)

- Fix: viibrmusic.com share links (`https://viibrmusic.com/s/<code>`, the
  links members actually post) feed Wisp. Before, only
  `viibrmusic.com/songs/<id>` links counted, so ViiBR tracks were ignored.
- `wisp/links.py` recognises a share link as a `ShareLink`; the feeding cog
  asks viibrmusic.com which song it names (one request, redirects read, not
  followed, one www hop allowed, `User-Agent: WispBot/1.0`), outside the
  guild lock. The song's key is `viibr:<id>`, so a share link and the song's
  own link feed him only once. Mealtime shows the link as posted.
- A share link for no song (404, or a redirect that is not a song page) is
  ignored. A timeout or network error skips the feed and is posted in Wisp's
  House.
- New rule `VIIBR_RESOLVE_TIMEOUT` (5 seconds).

## 2026-10-23 (the Studio's look)

- The Studio threads have Myra's names: `☀️ | Status`, `🧡 | Mealtime`,
  `⚡｜Jam Space`, `🔒| The ViiBR Vault` and `📙｜Wisp FAQ` (was How Wisp
  Works). Setup renames a thread whose name differs. Wisp's messages use the
  plain titles, without emoji.
- Each Studio thread's first post carries its thumbnail picture
  (`ASSETS/thumbs/`, `ASSETS/vault.png`); setup adds one to a first post that
  has no attachment.
- The status card shows Wisp's current picture: the egg (or the coal egg),
  then his stage. It is uploaded only when it changes, once more after a
  restart, and missing art leaves the picture as it is. The House's new egg
  post carries the egg picture too.
- The Wisp FAQ thread is built from pictures: a table of contents with jump
  links, one picture per section (`ASSETS/faq/`), then the quick rules post
  with the current numbers, which `/wispadmin food` keeps editing. An existing
  How Wisp Works thread is renamed and filled.
- `/wispadmin faq` ("Rebuild the Wisp FAQ thread.") deletes Wisp's own FAQ
  posts and posts them fresh.
- The rules post is headed "Quick rules (current numbers)".
- New column `settings.faq_message_ids` (TEXT, a JSON list of message ids).

## 2026-10-23 (gifts)

- Gifts: the ViiBR Vault sells four collections of four gifts (Lunchbox
  Liners, Alien Dolls, Books, Affirmation Cards) for 15 points each. Buying a
  gift is giving it to Wisp, from a second select under the snack select.
- It is a gamble: he keeps a gift one time in three. A kept gift leaves the
  Vault for this life and gives its giver 5 bond (outside the daily cap) and
  him a bond moment's growth; finishing a collection gives 25 bond more. A
  passed gift goes back to the Vault. Points are spent either way.
- Each collection can be given from once a UTC day, server-wide, and he keeps
  at most one gift a day: later gifts that day go back to the Vault.
- Collections are per life: every new Wisp starts empty and the Vault is
  fully restocked.
- Wisp's House hears every gift, with its picture when he keeps it, and
  `/wisp lunchbox` shows this life's collections.
- The How Wisp Works post explains gifts. To stay under 2,000 characters a
  few of its lines are shorter, and the three ban lines are now one.
- New table `gift_attempts`; interactions gain the kind `gift`.

## 2026-10-23 (Wisp's lunchbox)

- `/wisp lunchbox` ("See the things Wisp keeps in his lunchbox.") shows, only to
  the member who asks, what Wisp keeps: his favorite songs, his favorite snack
  and his favorite emoji. Anyone may look; it is read-only.
- Favorite songs: the first life-loop tick after UTC midnight picks one of the
  previous day's viibrmusic.com feeds at random and posts it in Mealtime with a
  new line from Wisp. A day without viibrmusic.com tracks has no pick, and a
  day is never picked twice. Picks belong to the guild and carry across lives.
  The lunchbox shows the newest ten.
- Favorite snack: every Wisp picks a random favorite snack when he hatches.
  Feeding it to him gets its own delighted line instead of the usual one.
- Favorite emoji: the expression he has used most in his AI replies and
  chime-ins in the guild, skipping any that is no longer uploaded.
- The How Wisp Works post and the README list Wisp's lunchbox.
- New tables `favorites` and `expression_uses`; new column
  `lives.favorite_snack`.

## 2026-10-23 (Snack Packs)

- Members' own box is now the Snack Pack. `/wisp lunchbox` is renamed
  `/wisp snackpack` ("See your snacks and keepsakes."), and the Vault card's
  button is "Open my Snack Pack" (custom id `wisp:snackpack`). It still holds
  saved snacks and keepsakes such as a Last Ember.
- The Vault intro, the How Wisp Works post and this README say Snack Pack; a
  Last Ember goes in its sharer's Snack Pack.
- The cog is `cogs/snacks.py` (the Snack Box shop, the Snack Pack and the Feed
  button). The lunchbox name now belongs to Wisp's own lunchbox.

## 2026-10-23 (errors in place)

- There is no errors channel any more. Every error is posted as plain text in
  the channel or thread where it happened: a command, button or form failure
  in the channel it was used in (the Status thread for the Feed button), a
  Mealtime forward in Mealtime, a Studio card or pin in its thread, a Rhyme
  Duel in its thread, a conversation reply in Wisp's House.
- Wisp never posts in the track drop. Errors there, and errors with no channel
  (the life loop, startup, the next egg, recreated Studio threads, the AI
  voice), go to Wisp's House, the life loop and startup ones to every guild's
  House. If the post fails where it happened, the House is tried once; then
  the error is only logged.
- The member is told "That didn't work. The error is posted in this channel."
- `/wispadmin setup` no longer takes an `errors` channel, and the
  `error_channel_id` setting is gone. A live table that still has the column
  only logs a schema warning.
- `/wispadmin punish` posts its log line, reason included, publicly in the
  channel the command was run in. If that post fails, the reply says so.

## 2026-10-23 (plan 2 final fixes)

- Staff see every error: a life loop failure is posted to every guild's errors
  channel, and a cog that fails to load at startup is posted once the bot is
  ready.
- Startup refuses a stale database: a table missing a column stops the bot
  with a SchemaError naming it. Extra columns are only logged.
- Guild settings and qualifying roles are cached in the bot, so most messages
  no longer wait on the database, and the errors channel still works during a
  database outage. The track drop only reads settings for messages with a
  track link.
- Only qualifying members (Active Lounger or higher who have opened
  `/wisp board`) can use the Feed Wisp button or eat snacks with him. Rhyme
  Duels stay open to everyone, but only qualifying members get play credit.
- `/wispadmin food viibr suno` sets each track's meal points per guild and
  updates the How Wisp Works post. Until set, the values in `wisp/rules.py`
  apply.
- At the daily meal limit a snack, the free Sine Wave included, is refused and
  kept for tomorrow.
- Wisp only meets members once he has hatched.
- Mentioning Wisp's role counts as talking to him.
- When every AI provider is cooling down, Wisp falls back to his canned lines
  at once instead of waiting on each provider.
- No send can ping anyone, and more emoji are filtered from AI replies.
- Database connections are recycled every hour.
- The README permission list now matches what Wisp uses, and the Vault intro no
  longer mentions song listens, which are not built yet.

## 2026-10-22 (plan 2)

- The ViiBR Vault: the Studio's Lunchbox and Billboard threads are replaced by
  one thread, The ViiBR Vault. Its pinned first post is the leaderboard with
  the Shop the Vault and Open my lunchbox buttons, and carries
  `ASSETS/vault.png` when it exists. Version lines now show the stage, "from
  coal" eggs and full lives.
- Old age and the farewell: Wisp's House hears him grow into an Old Fogey and,
  after a full life, a celebrated farewell as he shrivels into coal. The top
  three sharers of that life who are not banned each get its Last Ember with a
  goodbye from him, then the coal cracks into the next egg, already halfway
  hatched. A neglect death still leaves no gifts and a fresh egg.
- Vault and lunchbox: `/wisp vault` is the shop where points buy snacks.
  `/wisp lunchbox` is the member's own box of saved snacks and keepsakes such as
  Last Embers, with a Shop the Vault button. Pickles now get a reaction that
  depends on the member's pickle stance.
- Talking: members mention or reply to Wisp in Wisp's House. The egg wobbles,
  the baby babbles and from Child on he talks with AI. From Adult on he
  sometimes chimes in on his own and remembers what people tell him. Talking
  earns no bond and no points.
- The How Wisp Works post now explains the Vault, lunchboxes, his whole life
  (Old Fogey, the farewell, the coal egg and Last Embers) and talking to him.
- Wisp's "not enough points" lines point at the Vault instead of the lunchbox.
- Art: `stages/old_fogey.png`, `stages/coal_egg.png`, `events/farewell.png`,
  `eating/eat_pickles_love.gif`, `eating/eat_pickles_hate.gif` and `vault.png`
  are read by the bot when they exist. `DOCS/ArtToMake.md` lists what is left.

## 2026-10-22

Wisp v1 core.

- Feeding: a Suno or ViiBR link posted in the track channel feeds Wisp. One feed
  per message, each link counts once ever, and edits are ignored. Tracks from a
  forum or its threads count.
- Life cycle: care drains over time and is capped per tick so downtime never
  punishes him. He hatches from an egg, grows through baby, child, teen, adult
  and rockstar, and can die of neglect, after which a new egg is laid. Past
  versions are kept.
- Status card: a pinned card in Wisp's Studio that is reposted if staff delete it,
  plus announcements in Wisp's House for hatching, growth and death.
- Billboard: `/wisp board` shows the leaderboard and Wisp's past versions.
- Meeting and names: Wisp meets members as they take part and learns their
  names. Bond grows with daily activity, and happiness reflects recent care.
- Lunchbox: members earn coins, buy snacks and feed them to Wisp with a button,
  with one free snack a day. Most snacks have an eating GIF; the rest post text
  until their art lands.
- Rhyme Duel: `/wisp play rhyme` trades perfect and slant rhymes with Wisp.
- Staff tools: `/wispadmin setup`, role management, freeze and unfreeze, punish,
  unban, strip points and reset name. Errors are reported to staff as plain text.

Not yet: AI voice, compliments and "no u", more games, badges.
