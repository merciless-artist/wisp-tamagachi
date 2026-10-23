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
  (event art, eating GIFs, shame images, Vault art) and Embed Links (the "no u"
  GIF, track previews).
- Upload the app emojis listed under Assets.
- In the server, run `/wispadmin setup`, then `/wispadmin roles add` for each
  role allowed to feed Wisp.

## Commands

Staff commands need the Manage Server permission.

- `/wispadmin setup house studio tracks` sets Wisp's House, the Studio forum
  and the track drop channel, and creates the Studio threads that are missing.
- `/wispadmin roles add`, `roles remove`, `roles list` choose which roles can
  feed Wisp.
- `/wispadmin food viibr suno` sets how many meal points a viibrmusic.com track
  and a Suno track feed Wisp (0 to 50 each; leaderboard points match), and
  updates the How Wisp Works post. Until staff set them, the starting values
  in `wisp/rules.py` apply.
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
- `/wisp vault` is the shop: buy snacks with your points.
- `/wisp snackpack` shows your Snack Pack: your saved snacks and keepsakes,
  like a Last Ember, with a button to shop the Vault.
- `/wisp lunchbox` shows Wisp's lunchbox: his favorite song of each day (picked
  at random from that UTC day's viibrmusic.com tracks, newest ten shown), the
  favorite snack he picked when he hatched and the expression he uses most.
  Anyone can look, banned members included.
- `/wisp play rhyme` starts a Rhyme Duel with Wisp.

Talking: mention Wisp or reply to him in Wisp's House (the channel itself, not
its threads). The egg wobbles, the baby babbles and from Child on he answers with
AI. From Adult on he sometimes chimes in on his own and remembers things people
tell him. Talking earns nothing: no bond and no points.

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
- `stages/<stage>.png` for `baby`, `child`, `teen`, `adult`, `rockstar`,
  `old_fogey`, plus `stages/coal_egg.png` for the egg after a full life.
- `events/died.png`, `events/egg_cold.png`, `events/hatched.png`,
  `events/farewell.png`.
- `shame/*` any images, picked at random when a member is punished.
- `vault.png` for the first post of The ViiBR Vault thread.

App emojis (uploaded to the application in the Developer Portal):
`snack_<key>` for each snack key, `wisp_coin`, `wisp_happy`, `wisp_hangry`.

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
