# Wisp

Wisp is a Discord Tamagotchi for a music community. The whole server shares one
pet: members feed him by dropping tracks in the track channel and by buying
snacks from the ViiBR Vault, and he grows from an egg to a rockstar as long as
he is cared for. If he is neglected he dies and a new egg is laid. If he lives a
full life he grows old, passes on as a lump of coal and the coal becomes the
next egg. Members can also talk to him in Wisp's House.

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
- Upload the app emojis listed under Assets.
- In the server, run `/wispadmin setup`, then `/wispadmin roles add` for each
  role allowed to feed Wisp.

## Commands

Staff commands need the Manage Server permission.

- `/wispadmin setup house studio tracks` sets Wisp's House, the Studio forum
  and the track drop channel, and creates the Studio threads that are missing
  (see Wisp's Studio).
- `/wispadmin roles add`, `roles remove`, `roles list` choose which roles can
  feed Wisp.
- `/wispadmin food viibr suno` sets how many meal points a viibrmusic.com track
  and a Suno track feed Wisp (0 to 50 each; leaderboard points match), and
  updates the quick rules post at the end of the Wisp FAQ. Until staff set
  them, the starting values in `wisp/rules.py` apply.
- `/wispadmin faq` rebuilds the Wisp FAQ in place: it deletes Wisp's own FAQ
  pictures and rules post, posts them fresh and updates the table of
  contents. Run it after the FAQ pictures change in a new release.
- `/wispadmin freeze` and `/wispadmin unfreeze` pause and resume care draining.
- `/wispadmin punish` bans a member from Wisp, on a rising ladder of offenses.
  The log line with the reason is posted publicly in the channel the command
  was run in.
- `/wispadmin unban` lifts a member's ban.
- `/wispadmin strip` takes leaderboard points from a member.
- `/wispadmin resetname` makes Wisp forget a member's name.

Member commands:

- `/wisp status` shows how Wisp is doing.
- `/wisp board` shows the ViiBR Vault leaderboard and Wisp's past versions.
- `/wisp vault` is the shop: buy snacks with your points, or give Wisp a
  gift from one of seven collections: pick a collection, then a gift. He
  might not like it.
- `/wisp snackpack` shows your Snack Pack: your saved snacks and keepsakes,
  like a Last Ember, with a button to shop the Vault.
- `/wisp lunchbox` shows Wisp's lunchbox: his favorite song of each day (picked
  at random from that UTC day's viibrmusic.com tracks, newest ten shown), the
  favorite snack he picked when he hatched, the expression he uses most and
  the gift collections of this life.
  Anyone can look, banned members included.
- `/wisp play rhyme` starts a Rhyme Duel with Wisp.

Talking: mention Wisp or reply to him in Wisp's House (the channel itself, not
its threads). The egg wobbles, the baby babbles and from Child on he answers with
AI. From Adult on he sometimes chimes in on his own and remembers things people
tell him. Talking earns nothing: no bond and no points.

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

The Studio forum holds five threads, named exactly:

- `☀️ | Status`: the live status card, which shows Wisp's current picture
  (the egg, the coal egg, then his stage).
- `🧡 | Mealtime`: every track that feeds him.
- `🔒| The ViiBR Vault`: the pinned leaderboard and the shop.
- `⚡｜Jam Space`: his favorite songs and lyrics.
- `📙｜Wisp FAQ`: a locked thread. Its first post is a table of contents
  linking to one picture per section, and its last post is the quick rules
  with the current numbers.

Each thread's first post carries its picture, which the forum shows as the
thumbnail. Setup renames a thread whose name differs, adds a missing
thumbnail and fills a Wisp FAQ that has no sections yet, such as an older How
Wisp Works thread.

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
- `stages/<stage>.png` for `egg`, `baby`, `child`, `teen`, `adult`,
  `rockstar`, `old_fogey`, plus `stages/coal_egg.png` for the egg after a full
  life (the egg's picture stands in when it is missing). The status card and
  the House's announcements use them.
- `events/died.png`, `events/egg_cold.png`, `events/hatched.png`,
  `events/farewell.png`.
- `shame/*` any images, picked at random when a member is punished.
- `vault.png`, `thumbs/mealtime.png`, `thumbs/jam_space.png` and
  `thumbs/faq.png`, the thumbnails of the Studio threads.
- `faq/00_how_wisp_works.png` to `faq/10_fair_play.png`, the Wisp FAQ's
  section pictures. These are required: without all eleven the FAQ is not
  built and the error is posted in its thread.
- `gifts/<key>.gif` or `gifts/<key>.png` (512px) for each gift, attached
  when Wisp keeps it. An animated GIF is used before a PNG.
- `keepsakes/<kind>.gif` or `.png` for `eggshell`, `first_spark`,
  `teen_spark`, `adult_spark`, `guitar_pick`, `time_piece` and `last_ember`,
  attached when the keepsake is given.

App emojis (uploaded to the application in the Developer Portal):
`snack_<key>` for each snack key, `gift_<key>` for each gift key,
`keepsake_<kind>` for each keepsake kind (shown in the Snack Pack),
`wisp_coin`, `wisp_happy`, `wisp_hangry`.

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
