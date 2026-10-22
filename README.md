# Wisp

Wisp is a Discord Tamagotchi for a music community. The whole server shares one
pet: members feed him by dropping tracks in the track channel and by buying
snacks from the Lunchbox, and he grows from an egg to a rockstar as long as he
is cared for. If he is neglected he dies and a new egg is laid.

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
  Threads, Manage Threads, Pin Messages, Manage Roles.
- Upload the app emojis listed under Assets.
- In the server, run `/wispadmin setup`, then `/wispadmin roles add` for each
  role allowed to feed Wisp.

## Commands

Staff commands need the Manage Server permission.

- `/wispadmin setup house studio tracks errors` sets Wisp's House, the Studio
  forum, the track drop channel and the error channel, and creates the Studio
  threads that are missing.
- `/wispadmin roles add`, `roles remove`, `roles list` choose which roles can
  feed Wisp.
- `/wispadmin freeze` and `/wispadmin unfreeze` pause and resume care draining.
- `/wispadmin punish`, `unban`, `strip`, `resetname` ban or unban a member,
  take leaderboard points, or make Wisp forget a member's name.

Member commands:

- `/wisp status` shows how Wisp is doing.
- `/wisp board` shows the Billboard and Wisp's past versions.
- `/wisp lunchbox` buys snacks and shows your own.
- `/wisp play rhyme` starts a Rhyme Duel with Wisp.

## Assets

Graphics live in `ASSETS/` and are all optional. Where one is missing, Wisp
posts text only.

- `eating/eat_<snack>.gif` for each snack key (`sinewave`, `cloudwave`,
  `jellywave`, `juicewave`, `spicywave`, `glitterwave`, `viibrwave`, `cheese`,
  `pickles`).
- `stages/<stage>.png` for `baby`, `child`, `teen`, `adult`, `rockstar`.
- `events/died.png`, `events/egg_cold.png`, `events/hatched.png`.
- `shame/*` any images, picked at random when a member is punished.
- `lunchbox.png` for the Lunchbox menu.

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
