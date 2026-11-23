# Rooms and Wisp's Craving: design

Agreed with Myra on 2026-11-23, during the beta. Wisp is live with real data,
so every storage change is additive and migrates the live database safely.
Marked **my call** where Claude chose and Myra has not yet weighed in.

## Why

The snack guessing game (called "Wisp's Mood" in
`2026-11-02-meters-and-chores-design.md`) was decided but never built. Myra
named it **Wisp's Craving**; the old song-genre "Craving" idea is dropped.

Games should not scatter threads around the server. The Rhyme Duel opens a new
public thread off Wisp's House for every game today. Instead each member gets
**one private thread, their room**, where all of their games happen and where
they can look at their Snack Pack any time.

## Goals

- One private room per member per server, off Wisp's House, made once.
- Wisp's Craving: a once-a-day snack guess in the member's room. Winning puts
  that snack in their Snack Pack free, and Wisp remembers they won it for him.
- The Rhyme Duel moves into the room.
- The member's Snack Pack also lives in their room.

## Non-goals

- No change to how the Snack Pack works today: `/wisp snackpack` and the
  Snack Pack buttons still answer privately, exactly as now.
- Wisp does not chat in rooms. He talks only in Wisp's House itself, as now.
- No song-genre game.

## Anti-goals

- Never a pile of threads: one room per member, reused forever, recreated only
  when it was deleted.
- Never a wrong answer from the game: hints are written lines, not AI.
- Never a room for someone who has not joined (`/wisp board`).

## Rooms

- **Made:** the moment a member runs `/wisp board` for the first time (when
  `players.activated_at` is set). A member who joined before this release gets
  their room the next time they run `/wisp board`, play a game or open their
  Snack Pack. No mass creation at deploy.
- **Where:** a private thread off Wisp's House (`settings.house_channel_id`),
  not invitable, with the member added. Only the member, Wisp and staff who
  can manage threads see it (Discord's rule).
- **Name (my call):** `♪ {name}'s room`, using the name Wisp knows them by
  (`players.name`) or their display name, cut to fit Discord's 100 characters.
  Renamed when Wisp later learns their name.
- **Stored:** a new nullable `players.room_thread_id`. A stored room that was
  deleted, or that sits under an old House after staff change the House, is
  made again on next use.
- **Archived rooms:** Discord archives idle threads. Wisp unarchives the room
  whenever he uses it.
- **Opening post (my call):** a short welcome: this is your room with Wisp,
  games happen here, your Snack Pack is pinned here.
- **Bot permissions:** Create Private Threads, Send Messages in Threads and
  Pin Messages in the House; setup's permission check gains them.
- **When a room can't be made (my call):** joining with `/wisp board` still
  succeeds. The failure is posted as an error (`Error in <context>: ...`, the
  project's usual way) and the room is tried again on next use. Games refuse
  with the reason until the room exists. Never a fallback to public threads.
- **One game at a time (my call):** a room runs one game at a time; starting a
  Craving or a duel while one is running in that room is refused politely.

## The Snack Pack in the room (my call on the mechanics)

- One pinned Snack Pack message in the room, drawn exactly like the private
  one (same frame, same buttons).
- It is redrawn whenever its owner opens their Snack Pack anywhere
  (`/wisp snackpack` or a Snack Pack button) and after they win a Craving.
  It is not redrawn on every coin change, which would mean an edit on every
  feed.

## Wisp's Craving

- **Start:** `/wisp play craving`, and a Wisp's Craving button beside Rhyme
  Duel in the Play menu. The answer to the command is private and points to
  the room; the game itself runs in the room.
- **Who and when:** the same refusals as the Rhyme Duel: banned, no living
  Wisp, frozen, napping, cannot feed him.
- **How often:** one round per member per UTC day, separate from the Rhyme
  Duel's daily plays. A new `InteractionKind.CRAVING` counts it.
- **A round:**
  1. Wisp picks one snack at random from the snacks you can buy
     (`PAID_SNACKS`, so never the free Sine Wave) (my call).
  2. He posts his first hint and a menu of those snacks.
  3. The member has **3 guesses**. Each wrong guess is taken out of the menu
     and Wisp answers with a short "nope" line and his next hint.
  4. A right guess wins. Three wrong guesses lose, and he says what it was.
  5. The round times out after 5 minutes with no guess, counted between
     guesses (my call), and counts as a loss.
- **The day's craving is fixed (my call):** the snack he craves and the
  guesses used are stored for the member's UTC day as soon as the round
  starts. Starting again cannot reroll the snack. A round cut short by a bot
  restart (every push restarts him) picks up where it was: same snack, same
  guesses left. The day only counts as played when the round ends (win, lose
  or time out).
- **Pinning (my call):** if the pin fails, the Snack Pack is still posted and
  the failure is reported as an error.
- **Hints:** written lines in `wisp/lines.py`, three per snack, in Wisp's
  voice, getting clearer each time ("something... wobbly", then closer).
  Claude writes them; Myra can edit.
- **Winning:**
  - The snack goes into their Snack Pack free and is marked as won.
  - Wisp says he'll be waiting for it.
- **Wisp's notes (Myra):** every finished round leaves a member note saying
  what he craved and whether they won or lost ("I was craving a Jelly Wave
  and they guessed it", "I was craving a Jelly Wave and they couldn't guess
  it"), so he can bring it up when they chat in the House. If they lost and
  then buy that same snack with their own wisp coins on the same UTC day
  (my call on the day), he notes that too ("they lost my Craving but bought
  me the Jelly Wave anyway").
- **No won marker in the Snack Pack (Myra):** members guessed the snack, so
  they know it; the Snack Pack looks the same as today.
- **Feeding a won snack:** while the member holds a won one of that snack,
  feeding any of that snack uses the won one first, and Wisp's line is about it being the one they won **for** him
  ("this is the one you won for me!"). Then it is an ordinary snack.
- **Win or lose (my call):** every finished round raises his Wellbeing and
  casual bond like a counted Rhyme Duel (`WELLBEING_PER_PLAY`,
  `BOND_PER_PLAY`), and the receipt says so. The bond shares the daily casual
  bond cap with snacks and duels (`DAILY_CASUAL_BOND_CAP`); past the cap the
  receipt says the bond is full for today, and Wellbeing still rises.
- **Numbers** (`wisp/rules.py`): `CRAVING_GUESSES = 3`,
  `CRAVING_TIMEOUT = 5 minutes`. One round a day is enforced by the
  `cravings` table's primary key `(guild_id, user_id, day)`, so there is no
  `CRAVINGS_PER_DAY` constant (build note, 2026-11-23).

## The Rhyme Duel in the room

- The duel runs in the member's room instead of a new public thread. The room
  is never archived or locked after a duel, unlike today's duel threads.
- Everything else about the duel stays the same.

## Storage (all additive)

- `players.room_thread_id BIGINT NULL`.
- `players.room_pack_message_id BIGINT NULL`: the pinned Snack Pack in the
  room.
- `inventory.won INT NOT NULL DEFAULT 0`: how many of that snack in the pack
  were won for Wisp; never more than `qty`.
- `InteractionKind.CRAVING = "craving"` in the interactions table, written
  when a round ends.
- A new `cravings` table: `guild_id`, `user_id`, `day` (UTC date), `snack`,
  `guesses` (wrong guesses so far, as snack keys), `ended_at` (NULL while the
  round is open), primary key `(guild_id, user_id, day)`.

## Left to the builder

- Exact wording of the welcome post, receipts and refusals, in house style
  (`・` bullets, `♪`, no Unicode emoji).
- How the room's Snack Pack is pinned and redrawn, within the rules above.
- Tests against real `wisptest_` tables, as the project requires.
