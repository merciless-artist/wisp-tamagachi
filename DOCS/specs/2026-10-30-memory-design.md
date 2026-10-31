# Wisp's memory: design

Date: 2026-10-30. Status: draft, waiting for Myra's approval.

## Why

Wisp should feel like he knows people. Right now he forgets who just fed him
(on 2026-10-30 Cat fed him two tracks, then four minutes later he asked her
for fresh tracks). He only keeps notes about people from Adult on, so the
cute stages never remember anyone. Feeding and gift posts are fixed lines
that repeat. Myra wants him to notice people's quirks, know what they've done
for him, and talk about it in his own voice.

## Goals

☆ He keeps notes about people from the Baby stage on, and pays attention to
  their quirks: how they type, pet names they use, running jokes, what
  they're working on, what they like.
☆ He knows facts from the database when he talks to someone: who fed him,
  what, when, and what gifts they gave.
☆ Track-feeding posts and gift posts are written by the AI voice, with the
  current fixed lines as the fallback when the AI is down.
☆ Members can see what he remembers about them and make him forget it
  (`/wisp memory`).
☆ Notes carry over from one Wisp life to the next, and fade for people who
  stop interacting with him (Myra, 2026-10-30).

## Non-goals

☆ No new leveling or bond system. Bond tiers stay as they are.
☆ Snack posts, rhyme duel lines, stage-up and life-event announcements stay
  fixed lines.
☆ No memory of what people say in other channels. He only learns in his
  House.
☆ No staff tools for reading or editing other people's notes.

## Anti-goals (it fails even if it works if...)

☆ He notes anything private or sensitive: health, where someone lives, age,
  real names, relationships, money, anything they'd be uncomfortable seeing
  read back.
☆ He recites notes or database facts like a report ("You fed me 3 tracks at
  01:04"). Facts are background he uses naturally, in his stage's voice.
☆ He gets numbers wrong or claims something happened that didn't. Facts in
  the prompt must come from the database, in words, never guessed.
☆ A feeding or gift post is lost or delayed by more than a few seconds
  because the AI is slow or down.

## What exists today

☆ `db/notes.py` stores notes per guild and member (not per life), keeps the
  newest `NOTES_KEPT` (8), each up to `NOTE_MAX_CHARS` (200). So carrying
  over already happens.
☆ `keeps_notes(stage)` in `wisp/voice.py` is true only for Adult, Rockstar
  and Old Fogey. The `<note>` tag is only asked for then, and notes only
  reach the prompt then.
☆ `_NOTE_TAG` asks for a note only when "they told you something worth
  remembering about themselves".
☆ The `interactions` table logs FEED, SNACK, FREE_SNACK, PLAY, GIFT and CHAT
  (the day's first poke or mention) with life, member and time. `feeds` logs
  each track (key, url, when). `gift_attempts` logs each gift (which, kept or
  not, when).
☆ Pokes are already AI with fixed-line fallback (`cogs/conversation.py`).
☆ Track feeds post in Mealtime with `bot.lines.pick(Moment.TRACK_FED, ...)`
  (`cogs/feeding.py`, `_forward`). Gifts post in the House with
  `bot.lines.pick(_MOMENTS[outcome], ...)` (`cogs/gifts.py`,
  `announce_gift`).

## The design

### 1. Notes from the Baby on

☆ He keeps and uses notes at every hatched stage. The egg keeps none.
☆ The note tag asks him to notice quirks, not only facts people state. New
  wording (Myra may rewrite it, like the other prompts):
  "If you noticed something about them worth remembering (how they type, a
  pet name they use, a running joke, what they're working on, what they
  love or hate), end with <note>one short fact</note>. Never note anything
  private: health, where they live, their age, real name, relationships or
  money."
☆ The Baby can't talk in words, but the AI still writes the note in plain
  words; only his reply is baby talk. The note is stripped before posting,
  as now.
☆ How notes show in the prompt is unchanged: "What you remember about
  {name}", then "Bring these up when they fit. Don't recite them."
☆ (Claude's call) The Teen voice currently says "you don't recall past
  conversations, so never claim to" (a deliberate ruling from when Teens
  had no notes, `DOCS/BuildRulings.md`). That clause is cut, leaving "You
  know the regulars by name and by how close you are." Myra's Baby and Child
  voices have no such line. Myra will rewrite the Teen voice later anyway.

### 2. Facts from the database

When Wisp answers or gets poked by a member, the prompt gets a short "What
you know" block, in words. All from the current life:

☆ His last meal: who fed him and how long ago ("Cat fed you a track a few
  minutes ago"). If it was the person he's talking to, say "they".
☆ What this person did for him today: tracks fed, snacks given, gifts
  given (with the gift's name and whether he kept it), rhyme duels played.
  Left out when they did nothing today.
☆ How much this person has fed him this life, in words relative to others
  ("one of your biggest feeders", "has fed you a few times", "hasn't fed you
  yet this life").
☆ Times are in words: "just now" (under 2 min), "a few minutes ago" (under
  15), "earlier this hour", "a few hours ago", "earlier today", "yesterday",
  "a few days ago". Never clock times.
☆ (Claude's call) Chime-ins have no speaker, so they get only the "last
  meal" line, no member's notes or per-member facts.
☆ (Claude's call) The egg gets no facts block at all. Its poke, mention and
  feeding prompts keep their own fed-by wording (`_FED_BY`), unchanged.
☆ (Claude's call) Just fed but still hangry: `mood()` keeps him hangry while
  his hunger meter is low, however recently he ate, and the hangry layer says
  he's starving until somebody shares a track. When the person he's talking
  to fed him within `JUST_FED_FOR` (15 minutes, in `wisp/rules.py`), the
  prompt adds, after the mood layer: "{name} just fed you. You're still
  hungry, but thank them for it and don't ask them for more right now." He
  can still grumble to the room. This is the Cat case.

### 3. AI feeding and gift posts

☆ Track feeds: the reaction line under "♪ @member fed Wisp ・ link" is
  written by the AI. The post format, the mood face in front, and where it
  posts (Mealtime) stay the same. The prompt has his stage voice, mood, the
  member's name and bond, his notes about them and the facts block, and asks
  for one short reaction to being fed their track. He hasn't heard the song,
  so he never describes it ("you ate it before you listened").
☆ While he's an egg: an egg-style line (no words, a movement or sound), like
  egg pokes.
☆ Gifts: the House post "♪ {name} gave Wisp a {gift}" keeps its first line;
  the reaction line is AI, told the gift's name and whether he kept it,
  passed on it, or had no room. The collection-complete line stays fixed.
☆ Fallback: if the AI fails or returns nothing usable, post the current
  fixed line, exactly as today. The outage is reported once per streak, as
  for chat.
☆ Neither post may wait on the AI for more than `POST_AI_TIMEOUT`
  (starting value 20 seconds, in `wisp/rules.py`); after that, the request
  is cancelled and the fixed line goes out. (Claude's call) 20 seconds, not
  8, because the provider chain already gives each provider 8 seconds
  (`AI_TIMEOUT`), so this leaves room for a backup provider. Running out of
  time counts as an outage and is reported once per streak, like any other.
☆ These posts don't ask for note or pickle tags.

### 4. Fading

☆ (Claude's call) Wisp answers anyone in his House, but `interactions`
  rows are only written for members who can feed him (qualifying role,
  opened `/wisp board`). So fading can't read `interactions` alone. A new
  table records, per guild and member, when they last talked to him, poked
  him, fed him, snacked, played or gave a gift: `wisp_last_seen` (guild_id,
  user_id, at), updated on each of those. Fading reads that.
☆ A member's last interaction is their `last_seen` time in this guild,
  across all lives.
☆ Once a member's last interaction is older than `NOTE_FADE_AFTER` (30
  days, one life), he forgets their oldest note, then one more every
  `NOTE_FADE_EVERY` (3 days), until none are left. Both in
  `wisp/rules.py`.
☆ Any interaction stops the fading. Faded notes don't come back.
☆ Fading runs once a day in the life loop.
☆ Bond is separate and never fades.

### 5. `/wisp memory`

☆ A new slash command, `/wisp memory`, answered privately (ephemeral), plain
  text, no embeds, house text style.
☆ It lists what he remembers about the member, numbered, newest last. With
  no notes: a short line saying he doesn't remember anything about them yet.
☆ Under the list: a select menu to pick one note to forget, and a "Forget
  everything" button. Forgetting edits the same private message to show the
  updated list.
☆ Only the member's own notes. Nobody can see or clear someone else's.

## Constraints

☆ Wisp's project rules (`CLAUDE.md`): Discord IDs everywhere, every tunable
  number in `wisp/rules.py`, no Unicode emoji in AI or fixed text, no
  embeds, no DMs, errors posted as plain text where they happen, real
  database in tests (`wisptest_` tables), mypy strict, black, isort, flake8.
☆ The AI runs on free models through the existing provider chain. Feeding
  posts add one AI call per track; Myra accepted that.
☆ `DOCS/wisp_prompts.md` is regenerated so Myra can read every new prompt.

## Left to the builder

☆ How the facts block is queried (one query or several), and any new
  methods on `ActivityRepo`.
☆ Exact wording of the facts block and the feeding/gift prompts, inside
  the rules above. Myra will likely rewrite them after reading
  `DOCS/wisp_prompts.md`.
☆ How the fade job tracks which day it last ran.
☆ The `/wisp memory` view's layout within house style.
