# Wisp project rules

## Origin

Wisp is written fresh from his own spec at `DOCS/wisp_tamagotchi.html`. DJ Xo is
inspiration only. Never copy or adapt DJ Xo code.

## Quality bar

- No comments that narrate the next line. No duplicate helpers. No dead code or
  TODOs.
- No blanket `except Exception` anywhere except the top-level error reporters.
  Catch specific exceptions.
- Fully typed. `mypy --strict`, `black`, `isort` and `flake8` must pass.
- Tests run against the real database using `wisptest_` tables. Never mock the
  database.
- Run the quality tools with `PYTHONUTF8=1`, or isort silently skips files with
  Unicode.
- Section headers are a `# ---` rule, `# Section name`, a `# ---` rule. No emoji
  or decorative borders.

## Numbers

Every tunable number and the snack menu live only in `wisp/rules.py`. Spec
numbers are starting values.

## Users and time

Identify users by Discord ID everywhere. Names are display only. All times are
UTC and a day is a UTC calendar day.

## Bot text

- No Unicode emoji. Wisp's own app emojis are allowed.
- Bullet `・`, flair `♪`, separator `・♪ ────────・──────── ♪・`.
- No embeds.
- No direct messages. Wisp ignores DMs and is guild-only.
- Slash commands only, under `/wisp` and `/wispadmin` (staff need Manage Server).
- Errors reach staff as plain text: `Error in <context>: <Type>: <message>`.
- Keep messages under 2,000 characters.

## Process safety

When you start the bot for a live check, record the PID you started and stop only
that PID. Never kill processes by name or command-line pattern: this PC runs
other bots whose command line also contains `app.py`.

## Secrets

Secrets live only in `.env`. Channel IDs, roles and food values live in the
database and are set by staff commands.
