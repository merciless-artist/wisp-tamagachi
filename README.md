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
  button. A rerun leaves a panel that still exists alone, pins it again or
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
  pictures and rules post, posts them fresh and updates the table of
  contents. Run it after the FAQ pictures change in a new release.
- `!wisp freeze` and `!wisp unfreeze` pause and resume care draining.
- `!wisp eggs on|off` turns new eggs on or off. Off, no egg is laid when
  Wisp's life ends (the ending, Last Embers and badge roles still happen as
  usual) and the House says so once; on, the next tick lays the egg. A living
  Wisp is not affected.
- `!wisp punish @member <reason>` bans a member from Wisp, on a rising ladder
  of offenses. The reason is the rest of the line, and the answer, reason
  included, is public.
- `!wisp unban @member` lifts a member's ban.
- `!wisp strip @member <points>` takes leaderboard points from a member.
- `!wisp resetname @member` makes Wisp forget a member's name.

Member commands:

- `/wisp status` shows how Wisp is doing.
- `/wisp board` shows the ViiBR Vault leaderboard and Wisp's past versions.
- `/wisp vault` is the shop: buy snacks with your points, get a badge, or
  give Wisp a gift from one of seven collections: pick a collection, then a
  gift. He might not like it.
- `/wisp snackpack` shows your Snack Pack: your saved snacks, keepsakes
  like a Last Ember, and every badge you ever wore, with a button to shop
  the Vault.

Badges: the Vault sells six badge roles (Egg Warmer and Pickle Diplomat at
25 points, Flame Keeper and ViiBR Roadie at 100, Team Wisp and Bandmate at
250; Bandmate only for members at the Bandmate bond tier). Each raises your
bond, outside the daily cap, and shows by your name for the current Wisp
only: when his life ends the roles come off, and the next Wisp sells them
again. `!wisp setup` makes the roles, with `ASSETS/badges/<key>.png` as
the role icon when it exists and the server can show role icons. If Discord
will not give the role, the purchase is undone and the points come back.
- `/wisp lunchbox` shows Wisp's lunchbox: his favorite song of each day (picked
  at random from that UTC day's viibrmusic.com tracks, newest ten shown), the
  favorite snack he picked when he hatched, the expression he uses most and
  the gift collections of this life.
  Anyone can look, banned members included.
- `/wisp play rhyme` starts a Rhyme Duel with Wisp.

Talking: mention Wisp or reply to him in Wisp's House (the channel itself, not
its threads). He answers with AI at every stage: the egg wobbles or crackles in
reply to how warm and fed it is (and now and then posts its `wisp_egg` emoji),
the baby answers with noises and single words, and from Child on he talks. If
the AI is down, the egg and baby fall back to their pre-written lines. From
Adult on he sometimes chimes in on his own and remembers things people
tell him. Talking earns nothing: no bond and no points.

Poking: the Poke Wisp button on the status card and on the House's new-egg
posts pokes him at every stage. The House sees who poked him and his AI
reaction (a pre-written line if the AI is down), which is usually a giggle,
now and then a startle or a curious look; a quiet House or the small hours
(UTC) wake him up, and a flurry of pokes or hunger annoy him. Pokes and
mentions share one cooldown per member, and a poke earns nothing.

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
- `badges/<key>.png` for each badge key (`egg_warmer`, `pickle_diplomat`,
  `flame_keeper`, `viibr_roadie`, `team_wisp`, `bandmate`), the badge role
  icons, and the app emojis `badge_<key>` for the Vault and Snack Pack.
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
