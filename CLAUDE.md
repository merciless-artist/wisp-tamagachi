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

- Unicode emoji are allowed in designed text: anything Myra designs. AI
  replies and canned lines stay Unicode-emoji free. Wisp's own app emojis are
  allowed, always by name through `bot.emoji(...)`.
- Bullet `・`, flair `♪`, separator (the plain divider, `wisp.text.SEPARATOR`)
  `𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂`.
- House style v2.1 (`DOCS/specs/2026-10-27-house-style.md`) for the status
  card, the Vault, the Snack Pack, the lunchbox, the leaderboard and Burrito's
  post. Every frame piece comes from `wisp/text.py`; never retype a frame
  string:
  - `box_open(title, width)` (title bar `𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {Title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂`, box top)
    and `box_close(title, width)` (box bottom, and the bottom bar `bars(...)`
    sizes to look as wide as the title bar); `framed(...)` does both.
  - Box top and bottom have the same number of `═`: the layout's width (22 by
    default; status card 25, Vault 24). Nothing may look wider than the box:
    `visual_width` estimates it and `wrap`/`wrapped` break long lines into
    `║ ` continuation rows.
  - `#` `heading(name)` `║𝄡𝄚𝄂𝄆 **Name**`, `##` `sub(text)` `║𝄡𝄚𝄂 text`,
    `###` `item(text)` `║𝄡 text`, a plain line `note(text)` `║ text`.
  - Between sections `SECTION_BREAK` `╠═══⇕` (`sections(...)` puts them in).
    A lone `BLANK` (`║`) line goes exactly where Myra's draft has one and
    nowhere else.
- Points members spend are "wisp coins" (WC, with the `wisp_coin_mini` emoji);
  leaderboard counts stay "points".
- Length checks use `text_length` (UTF-16 units): the frames are full of
  characters that count twice.
- No embeds.
- No direct messages. Wisp ignores DMs and is guild-only.
- Members use `/wisp` slash commands; staff use `!wisp` text commands, plus
  `/wispadmin setup` and `/wispadmin faq`.
- Errors are posted as plain text in the channel where they happened:
  `Error in <context>: <Type>: <message>`.
- Keep messages under 2,000 characters. The Vault is the one Components V2
  message (a `LayoutView` of text displays with its menus between them, no
  container): 4,000 characters of text in total, sent with no `content`.

## Process safety

When you start the bot for a live check, record the PID you started and stop only
that PID. Never kill processes by name or command-line pattern: this PC runs
other bots whose command line also contains `app.py`.

## Secrets

Secrets live only in `.env`. Channel IDs, roles and food values live in the
database and are set by staff commands.
