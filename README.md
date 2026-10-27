# Wisp

Wisp is a Discord Tamagotchi for a music community. The whole server shares one
pet: members feed him by dropping tracks in the track channel and by buying
snacks from the ViiBR Vault, and he grows from an egg to a rockstar as long as
he is fed. If he is neglected he dies. If he lives a full life he grows old
and passes on as a lump of coal. After every ending Wisp's House asks "Do you
want to begin again?", and the next egg comes only when staff press **Begin
again**; after a full life the coal becomes that egg. Members can also talk to
him in Wisp's House.

## Begin again

- Every ending (a death, a cold egg, an old-age farewell) is announced as
  before: the ending post and its picture, the Last Embers with their goodbyes,
  the badge roles taken back and the Vault card refreshed. Then the House posts
  `♪ Do you want to begin again?` with a **Begin again** button. Nobody is
  pinged.
- Only staff (the app owner, Manage Server, or a staff role) can press it;
  anyone else is told privately that only staff can start a new Wisp.
- A press lays the next egg the way the automatic path used to: the next
  version, a coal egg halfway hatched after a full life, the new-egg post with
  its picture and Poke Wisp button, the status card and the House panel. The
  question's button is then disabled. A press that finds Wisp already here,
  from a second staff member or an old question, lays nothing and disables
  that button too.
- Until someone presses it there is no Wisp: the status card and `/wisp
  status` say `♪ No Wisp right now. Waiting for staff to begin again.`, and
  tracks, snacks, gifts, pokes and duels answer as they do with no living Wisp.
  The waiting status card carries its own Begin again button (and no Feed or
  Poke buttons) with the picture of how he ended, so staff can always begin
  again even if the House question was never posted or was deleted; the
  life loop puts it back if the card is gone. A restart lays nothing and every
  button still works. No favorite song is picked and `!wisp punish` says
  nothing in his voice while he is gone.
- A brand-new server still gets its first egg on the first tick after setup,
  with no button.

## His three meters

The status card shows three meters, each from 0 to 100, plus a Monster Pox
line while he is sick. All the numbers are starting values in `wisp/rules.py`.

- **Hunger** is his food (`Life.full` in the code). Like a Tamagotchi, a full
  bar means well fed. Tracks and snacks fill it and it drains every day (15 a
  day, 10 as an Old Fogey). Below 30 he is hangry, below 10 he is fading, and
  at 0 he dies. Only Hunger can kill him.
- **Happy** is how many different people said hi in the last 24 hours. A
  member's first poke or mention of the UTC day counts and earns them 1 Vault
  point; later ones that day count for nothing. Only members who can feed Wisp
  and are not banned earn the credit, though anyone can still poke and chat.
  Five different people in 24 hours is full. A chat counts toward Wisp learning
  a member's name, but not toward bond, growth, caretakers, the "fed by" line
  or the stage-up keepsake. Staying very happy as an Adult (80 or more for
  seven days) is what makes him a Rockstar.
- **Care** is rhyme duels and gifts. It starts at 50 when he hatches and drains
  10 a day. Each rhyme duel that counts as play adds 10 and pays 1 Vault point
  (at most 5 a day per member), and every gift bought adds 8, kept or not.
  Below 30 he is lonely and grumpy in what he says and posts once in the House
  with a picture for his stage. Hangry beats lonely beats happy, and lonely
  never hurts him: no death, no growth penalty.

**Monster Pox**, his childhood sickness (`is_sick` and the `SICK_*` rules in
the code), comes once per life, at a random time between day 1 and day 12
while he is a Baby, Child or Teen, so every Wisp who grows up has had it. He
is spotty, itchy and feverish. It lasts 48 hours (it carries on if he grows a
stage). While sick his Hunger meter drains 1.5 times as fast, but it never
drops below 1, so he cannot die of it; he can still be hangry and fading. Each
member's daily meal limit goes from 15 to 30 meal points, room for about one
extra song and one extra snack. He posts once when he catches it (with his
sick picture) and once when he is better, and the status card and Poke Wisp
panel show his sick picture meanwhile.

## Setup

1. Install Python 3.13 and create a virtual environment:

   ```
   py -3.13 -m venv .venv
   .venv\Scripts\python -m pip install -r requirements.txt
   ```

   For tests and the quality tools, also run
   `.venv\Scripts\python -m pip install -r requirements-dev.txt`.

2. Create a `.env` file next to `app.py` with these keys (values stay in `.env`
   and are never committed):

   - `DISCORD_BOT_TOKEN`
   - `MYSQL_HOST`
   - `MYSQL_PORT`
   - `MYSQL_USER`
   - `MYSQL_PASSWORD`
   - `MYSQL_DATABASE`
   - `WISP_TABLE_PREFIX` (optional, defaults to `wisp_`)

3. Tables are created on startup.

## Running

```
.venv\Scripts\python app.py
```

## Discord setup checklist

- Developer Portal, Bot tab: turn on the Message Content intent.
- Developer Portal, Installation: User Install off. Public Bot off.
- Bot permissions: Send Messages, Send Messages in Threads, Create Public
  Threads, Manage Threads, Pin Messages, Read Message History, Attach Files
  (event art, eating GIFs, shame images, Studio thumbnails, the status card's
  picture, the FAQ pictures) and Embed Links (the "no u" GIF, track previews).
  Manage Threads also lets Wisp post in the Wisp FAQ thread he locks.
  Manage Roles, to make the badge roles and give and take them; Wisp's own
  role must sit above the badge roles.
- Upload the app emojis listed under Assets.
- In the server, run `!wisp setup #house #studio #tracks`, then
  `!wisp roles add @role` for each role allowed to feed Wisp.

## Commands

Members use `/wisp` slash commands. Staff type `!wisp <command>` text
commands, so they never dig through slash menus. Staff are Wisp's app owner
(in every server), members with Manage Server, and members holding one of the
server's staff roles. Anyone else is ignored without a word. Bare `!wisp` is
kept free for the help menu.

Setup and the FAQ rebuild also work as slash commands, `/wispadmin setup` and
`/wispadmin faq`. They do exactly what `!wisp setup` and `!wisp faq` do, but
answer privately. Discord shows them to members with Manage Server; a server
admin can show them to a staff role under Server Settings, Integrations. Anyone
who is not staff gets a private "That command is for staff."

Staff commands answer publicly in the channel they were used in; from the
track drop the answer goes to Wisp's House. Wrong arguments get one usage
line, an unknown command gets the list of commands, and a failure is posted
where the command was used.

- `!wisp setup #house #studio #tracks` (or `/wispadmin setup`) sets Wisp's
  House, the Studio forum and the track drop channel (mentions, ids or names),
  and creates the Studio threads that are missing (see Wisp's Studio). It also
  pins one Poke Wisp panel in the House: "♪ Poke Wisp" with the Poke Wisp
  button. The panel shows Wisp's current picture (the egg, the coal
  egg or his stage), and the life loop swaps it when the picture changes. A rerun leaves a panel that still exists alone, pins it again or
  gives back its button if needed, and posts a new one if it was deleted.
- `!wisp roles add @role`, `!wisp roles remove @role`, `!wisp roles list`
  choose which roles can feed Wisp.
- `!wisp staff add @role`, `!wisp staff remove @role`, `!wisp staff list`
  choose which roles are Wisp staff. The owner or a Manage Server member adds
  the first one.
- `!wisp food <viibr> <suno>` sets how many meal points a viibrmusic.com
  track and a Suno track feed Wisp (0 to 50 each; leaderboard points match),
  and updates the quick rules post at the end of the Wisp FAQ. Until staff
  set them, the starting values in `wisp/rules.py` apply.
- `!wisp faq` (or `/wispadmin faq`) rebuilds the Wisp FAQ in place: it deletes Wisp's own FAQ
  pictures (one per question, or one per section from before) and rules post,
  posts them fresh and updates the table of contents. Run it after the FAQ pictures change in a new release.
- `!wisp freeze` and `!wisp unfreeze` pause and resume the draining of his meters.
- `!wisp begin` does what the Begin again button does, for when no button
  can be pressed: it lays the next egg after an ending, or answers
  `♪ Wisp is already here.`
- `!wisp punish @member <reason>` bans a member from Wisp, on a rising ladder
  of offenses. The reason is the rest of the line, and the answer, reason
  included, is public.
- `!wisp unban @member` lifts a member's ban.
- `!wisp strip @member <points>` takes leaderboard points from a member.
- `!wisp resetname @member` makes Wisp forget a member's name.
- `!wisp song <link> <words...>` makes Wisp post the words and, underneath,
  the link (http or https) in the Jam Space thread, exactly as typed: no
  prefix, flair or AI line, no pings, and the link's player still shows.
  Staff's command message is deleted afterwards (a failed delete is
  ignored). A missing or bad link or missing words get the usage line; a
  Jam Space that cannot be reached is reported where the command was used
  and nothing is posted.

Member commands:

- `/wisp status` shows how Wisp is doing.
- `/wisp board` shows the ViiBR Vault leaderboard and Wisp's past versions.
- `/wisp vault` is the shop: buy snacks with your wisp coins (WC, the points
  you can spend), get a badge, or give Wisp a gift from one of seven
  collections: pick a collection, then a gift. He might not like it. It is one
  private Components V2 message with each menu under its section.
- `/wisp snackpack` shows your Snack Pack: your saved snacks, keepsakes
  like a Last Ember, every badge you ever wore and any magazine covers you
  bought, with a button to shop the Vault.

Magazines: while the living Wisp is a Rockstar, the Vault has a Magazines
section selling two covers, the VIIBRATIONS cover and the Music & Science
cover, at 100 wisp coins each (`MAGAZINE_COST` and `MAGAZINES` in
`wisp/rules.py`), with its own menu under it. Each can be bought once per
member per Wisp life, recorded in the `magazines` table. The buyer gets the
cover's picture in a private message and keeps the cover in their Snack Pack
forever (`Wisp v3's VIIBRATIONS cover`). At any other stage, or once he is
Old Fogey, the section is gone, and a menu left open from before answers
`♪ The magazines are gone from the shelf.`

Badges: the Vault sells four badge roles (Pickle Diplomat at 25 points,
Flame Keeper at 100, Team ViiBR and Bandmate at 250; Bandmate only for
members at the Bandmate bond tier). Each raises your
bond, outside the daily cap, and shows by your name for the current Wisp
only: when his life ends the roles come off, and the next Wisp sells them
again. `!wisp setup` makes the roles, with `ASSETS/badges/<key>.png` as
the role icon when it exists and the server can show role icons. Setup
also renames a badge role whose name is not its badge's, and deletes the
roles Wisp made for badges no longer sold. A badge bought before it was
retired stays in the buyer's Snack Pack. If Discord will not give the role,
the purchase is undone and the points come back.
- `/wisp lunchbox` shows Wisp's lunchbox: his favorite song of each day (picked
  at random from that UTC day's viibrmusic.com tracks, newest ten shown), the
  favorite snack he picked when he hatched, the expression he uses most and
  the gift collections of this life. It is posted publicly where it was asked
  for, pinging nobody and with no link previews; asked for in the track drop,
  it is posted in Wisp's House instead (or shown only to the member when there
  is no House). Anyone can look, banned members included.
- `/wisp play rhyme` starts a Rhyme Duel with Wisp. A duel that counts as play
  (a scored rhyme, a member who can feed Wisp, at most 5 a day) fills his Care
  and pays 1 Vault point.

Talking: mention Wisp or reply to him in Wisp's House (the channel itself, not
its threads). He never answers in the Studio, so Burrito's post is left to
Burrito. He answers with AI at every stage: the egg wobbles or crackles in
reply to how warm and fed it is (and now and then posts its `wisp_egg` emoji),
the baby answers with noises and single words, and from Child on he talks. If
the AI is down, the egg and baby fall back to their pre-written lines. From
Adult on he sometimes chimes in on his own and remembers things people
tell him. Talking earns no bond. A member's first mention or poke of the UTC
day also earns 1 Vault point and counts toward Happy (see His three meters).

Poking: the Poke Wisp button on the status card and on the House's new-egg
posts pokes him at every stage. The House sees who poked him and his AI
reaction (a pre-written line if the AI is down), which is usually a giggle,
now and then a startle or a curious look; a quiet House or the small hours
(UTC) wake him up, and a flurry of pokes or hunger annoy him. Pokes and
mentions share one cooldown per member, and only the day's first poke or
mention earns anything.

Wisp knows his own emojis: when a message to him uses one of his app emojis
or any emote with "wisp" in its name, his AI is told which of his faces,
gifts, keepsakes or snacks it shows.

## Feeding

Wisp eats the first track link in a qualifying member's post in the track
drop: a viibrmusic.com song (`https://viibrmusic.com/songs/<id>` or the site's
share link `https://viibrmusic.com/s/<code>`) or a Suno song. For a share
link Wisp asks viibrmusic.com which song it names (one request, 5 second
timeout) before feeding, so a share link and the song's own link are the same
track. A share link for no song is ignored. If the site cannot be reached the
post is not fed and the error goes to Wisp's House.

## Keepsakes

Wisp's big moments give a keepsake to the member who was there, kept in their
Snack Pack and announced in Wisp's House:

- the Eggshell, when the egg starts hatching, to the member whose feed filled
  it;
- the First Spark, Teen Spark and Adult Spark when he grows into a Child, Teen
  and Adult, and the Guitar Pick when he becomes a Rockstar, to the member who
  last interacted with him;
- the Time Piece when he grows old, to the member who last interacted
  with him;
- the Last Ember after a full life, to that life's top sharers.

Nobody gets one when nobody was there or the member is banned.

## Wisp's Studio

The Studio forum holds six threads, named exactly:

- `☀️ | Status`: the live status card, which shows Wisp's current picture
  (the egg, the coal egg, then his stage).
- `🧡 | Mealtime`: every track that feeds him.
- `🔒| The ViiBR Vault`: the pinned leaderboard and the shop.
- `⚡｜Jam Space`: his favorite songs and lyrics.
- `📙｜Wisp FAQ`: a locked thread. Its first post is a table of contents
  linking to each section's first picture, then one banner picture per
  question, each in a message of its own, and its last post is the quick rules
  with the current numbers.
- `🧚│Burrito, Fairy God-bot`: Burrito's room. Burrito, a separate bot,
  answers questions about how Wisp works there; Wisp never talks in it. Its
  first post is framed in the house style and has no picture.

Each thread's first post but Burrito's carries its picture, which the forum
shows as the thumbnail. Setup renames a thread whose name differs, adds a
missing thumbnail and fills a Wisp FAQ whose stored pictures are not the
current set (35), such as an older How Wisp Works thread or the earlier
one-picture-per-section FAQ.

## Errors

There is no errors channel. Every error is posted as plain text,
`Error in <context>: <Type>: <message>`, in the channel or thread where it
happened, and the member who hit it is told so privately. Wisp never posts in
the track drop: errors there, and errors with no channel at all (the life loop,
startup, the AI voice), go to Wisp's House. If the post fails where it
happened, the House is tried once; after that the error is only logged.

## Assets

Graphics live in `ASSETS/` and are all optional. Where one is missing, Wisp
posts text only.

- `eating/eat_<snack>.gif` for each snack key (`sinewave`, `cloudwave`,
  `jellywave`, `juicewave`, `spicywave`, `glitterwave`, `viibrwave`, `cheese`,
  `pickles`), plus `eating/eat_pickles_love.gif` and
  `eating/eat_pickles_hate.gif` for pickles with a member whose pickle stance he
  knows.
- `moments/` pictures for his lonely and sick posts: `cry_baby.gif` and
  `grumpy_baby.png` (Baby), `grumpy.gif` (Child), `cry_teen.gif` (Teen and
  older) when Care drops below the lonely line, and `sick_baby.png`,
  `sick_child.png` and `sick_teen.png` for his Monster Pox. The sick picture
  is also on the status card and the Poke Wisp panel while he is sick.
- `stages/<stage>.png` for `egg`, `baby`, `child`, `teen`, `adult`,
  `rockstar`, `old_fogey`, plus `stages/coal_egg.png` for the egg after a full
  life (the egg's picture stands in when it is missing). The status card and
  the House's announcements use them.
- `events/died.png`, `events/egg_cold.png`, `events/hatched.png`,
  `events/farewell.png`.
- `shame/*` any images, picked at random when a member is punished.
- `badges/<key>.png` for each badge key (`pickle_diplomat`,
  `flame_keeper`, `team_viibr`, `bandmate`), the badge role icons, and the
  app emojis `badge_<key>` for the Vault and Snack Pack.
- `mags/viibrations_cover.jpg` and `mags/musicnscience_cover.jpg`, the
  magazine covers sent to their buyers (posting copies, 1200px tall, of the
  full-size `mags/viibrations_mag.png` and `mags/musicNscience_mag.png`).
- `vault.png`, `thumbs/mealtime.png`, `thumbs/jam_space.png` and
  `thumbs/faq.png`, the thumbnails of the Studio threads.
- `faq/<NN>_<section>_<k>.png`, the Wisp FAQ's banner pictures, one per
  question: `00_how_wisp_works_1`, `01_basics_1` to `_4`, `02_feeding_1` to
  `_4`, `03_vault_1` to `_5`, `04_lunchbox_1` to `_3`, `05_bond_1` to `_3`,
  `06_growing_1` to `_4`, `07_talking_1` to `_4`, `08_games_1` and `_2`,
  `09_ending_1` to `_3`, `10_fair_1` and `_2` (35 in all). These are
  required: without all of them the FAQ is not built and the error is posted
  in its thread.
- `gifts/<key>.gif` or `gifts/<key>.png` (512px) for each gift, attached
  when Wisp keeps it. An animated GIF is used before a PNG.
- `keepsakes/<kind>.gif` or `.png` for `eggshell`, `first_spark`,
  `teen_spark`, `adult_spark`, `guitar_pick`, `time_piece` and `last_ember`,
  attached when the keepsake is given.

App emojis (uploaded to the application in the Developer Portal):
`snack_<key>` for each snack key, `gift_<key>` for each gift key,
`keepsake_<kind>` for each keepsake kind (shown in the Snack Pack),
`wisp_coin`, `wisp_coin_mini` (prices and balances), `viibr_logo` (the Vault's
title), the status card's meters `care_full` / `care_left`, `happiness_full` /
`happiness_left` and `full_full` / `full_left`, `wisp_happy`, `wisp_hangry`,
`wisp_sad`. The layouts are Myra's house style,
`DOCS/specs/2026-10-27-house-style.md`.

## Testing

```
.venv\Scripts\python -m pytest -q
```

Tests run against the real MySQL database using their own `wisptest_` tables,
so the `.env` must be filled in. Quality checks:

```
.venv\Scripts\python -m black --check .
.venv\Scripts\python -m isort --check-only .
.venv\Scripts\python -m flake8
.venv\Scripts\python -m mypy --strict wisp db cogs app.py config.py
```

Set `PYTHONUTF8=1` when running them, or isort skips files containing Unicode.
