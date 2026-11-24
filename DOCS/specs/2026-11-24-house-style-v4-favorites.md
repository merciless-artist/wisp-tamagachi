# Wisp house style v4: every menu in WiSP's Favorites style (2026-11-24)

v4 replaces the v3 emoji frame (`2026-11-11-house-style-v3-emoji-frame.md`)
for every menu. v2.1 (`2026-10-27-house-style.md`) still holds for the bot's
text rules (bullet `・`, flair `♪`, no Unicode emoji in canned or AI text).
Marked **my call** where Claude chose.

## Why

Testers said the v3 frame (an edge emoji on every line, bar rows between
sections) was louder than the information and hard to read. Myra's WiSP's
Favorites layout (the lunchbox, `2026-11-23-wisps-favorites-layout.md`)
reads well, so Myra said yes to redoing the status card, the ViiBR Vault
(its three messages), the Snack Pack and the Leaderboard in that style.

## The pieces

All are Wisp's app emojis, by name through `bot.emoji(...)`, never by id.
Every menu gets them from one shared helper, `wisp.text.Frame`, made with
`wisp.text.frame_of(bot.emoji)`; the lunchbox uses the same one. Never
retype a piece.

| piece | markup | `Frame` |
|---|---|---|
| title line | `# {bar} **TITLE** {bar}`, bar = `headerbarright` `wisp_waveform` `headerbarleft` | `frame.title(name)` |
| section heading | `## {icon} **NAME**` | `frame.heading(name, place)` |
| item, long list | ` ・text` | `frame.item(text)` |
| item, short list (the lunchbox) | `### ・text` | `frame.big_item(text)` |
| information line | ` text` | `frame.note(text)` |
| spacer between entries of more than one line | `** **` | `SPACER` |
| footer, every menu | `### ・{long bar}{mic2}https://viibrmusic.com {long bar}・`, long bar = `headerbarright` `headerbar` `wisp_waveform` `headerbar` `headerbarleft` | `frame.footer` |
| divider in a short post | the long bar | `frame.divider` |

- Titles and headings are in capitals with him spelled `WiSP`
  (`heading_case`): `WiSP STATS`, `VIIBR VAULT`, `SNACK PACK`,
  `LEADERBOARD`, `WiSP'S FAVORITES`. **My call:** the title line has a space
  after the first bar, as this task's rule says; Myra's draft had none, and
  the lunchbox now has the space too.
- Myra's header pictures (`stats_title.png`, `vault_title.png`,
  `snack_pack_title.png`, `leaderboard_title.png`) stay above the text; the
  title line sits right under the picture. The lunchbox has no picture: its
  title line is its header.
- No edge emojis, no bar rows between sections, no empty lines. `** **`
  only between entries of more than one line, as the Favorites' songs: the
  lunchbox songs and the status card's meters.
- Dense menus (the status card's needs and facts, the Vault's lists, the
  Snack Pack, the Leaderboard rows) use plain ` ・` items so they stay
  readable and within 4,000 characters; only the lunchbox's short lists use
  `### ・`.
- **Lines are not wrapped by the bot any more (my call).** v3 broke long
  lines onto edge rows so the edge ran down the box; with no edge, Discord's
  own wrapping reads right, and a bot break would look wrong on a wide
  screen. `visual_width`, `WIDTHS` and the wrapping went with the frame. The
  4,000-character fitting (`fit`, `richest`, the Snack Pack's "and N more",
  the lunchbox's gift line) is unchanged.

## Section icons (my call)

The icons take turns in each menu's full section order: `boing_bass`,
`wisp_play`, `wisp_pause`, `wisp_stop`, then again. A section a menu leaves
out (Medicine without a cold, Magazines when he is not a Rockstar or the
member has none, the egg's Day and Right now) keeps its place, so an icon
never shifts when a section comes or goes.

| menu | boing_bass | wisp_play | wisp_pause | wisp_stop |
|---|---|---|---|---|
| WiSP's Favorites | TOP N SONGS | FAVORITE SNACKS | FAVORITE EMOJI | FAVORITE GIFTS |
| Status card | DAY N | RIGHT NOW | LIFE STAGE | |
| ViiBR Vault | SNACKS, GIFTS | MEDICINE | BADGES | MAGAZINES |
| Snack Pack | SNACKS | KEEPSAKES | BADGES | MAGAZINES |
| Leaderboard | THIS LIFE | ALL TIME | RHYME DUEL | VERSIONS |

The Vault's Gifts are its fifth section, so they come round to `boing_bass`.
The lunchbox keeps Myra's own two quirks: `### {wisp_play}**FAVORITE
SNACKS**` (smaller, no space) and `## {wisp_stop}  **FAVORITE GIFTS**` (two
spaces), through `heading(..., size=..., gap=...)`.

## Missing emojis

A piece made of emojis leaves out any that is not uploaded, as the lunchbox
did; the line still reads. With none uploaded the menu is plain text
(`UNICODE_FRAME`): `# **WiSP STATS**`, `## **SNACKS**`, ` ・items` and the
footer `### ・https://viibrmusic.com`. A heading whose icon is missing is
`## **NAME**` (no double space). The short-post divider without its bar is
the plain `SEPARATOR`, as before; the rules post still falls back to a blank
line when the divider would take it over 2,000 characters.

## Each menu

- **Status card** (one message under `stats_title.png`, buttons after):
  title; `DAY N ・ ♫ ♪. ♫‿♪` heading, then any `he has Monster Pox` / `he
  has a cold` items; `RIGHT NOW` heading, the needs as items, then the nap
  line as an item; the meters, each its bold name and its bar on two notes,
  with `** **` before each and after the last; the facts and the two hints
  as items; the `LIFE STAGE ・ X` heading; the footer. An egg's card is the
  title, its bars, the facts and the stage. The waiting card is the title,
  one item and the footer.
- **ViiBR Vault**: still three messages, one under the other, each a part a
  menu redraws on its own (my call). Measured with every emoji up at the
  longest markup, the fullest Teen Vault is 1,229 + 491 + 1,286 characters;
  a Rockstar with a cold adds Medicine and Magazines, and a note and the
  coins line come on top after a purchase. One message would sit near the
  4,000 limit, and it would change which part a purchase redraws, so the
  merge is not done.
  - Part one: any note, `vault_title.png`, the title, `wisp coins`, SNACKS
    (and its menu), MEDICINE while he has a cold (and its menu).
  - Part two: any note and the coins line, BADGES (and its menu),
    MAGAZINES while he is a Rockstar (and its menu).
  - Part three: any note and the coins line, `GIFTS ・ {coin} 15 WC each`,
    the gamble line, `Wisp already picked...` once he kept one today, each
    collection on one item (`Books: {emoji} ・ {emoji}` while there is room,
    else `Books: 3 left`), the collection and gift menus, then the footer in
    its own text display under them.
- **Snack Pack** (under `snack_pack_title.png`, Shop the Vault button
  after): title; notes `<@member> snack pack`, the balance and the drawings;
  SNACKS, KEEPSAKES, BADGES and MAGAZINES (when they own one) as items, cut
  with `and N more` as before; footer.
- **Leaderboard** (under `leaderboard_title.png`): title; one note saying
  where to shop (the private `/wisp board` copy points at its own buttons);
  THIS LIFE, ALL TIME, RHYME DUEL and VERSIONS as items; the oldest versions
  drop first so the footer always fits. "The leaderboard." line is gone: the
  title says it.
- **WiSP's Favorites**: as `2026-11-23-wisps-favorites-layout.md`, through
  the shared helper. Without the bars the footer is `### ・{mic2}https://...`
  (the bars' trailing `・` goes with them).
- **Other users of the old frame**: the badge, magazine and gift sections
  are the Vault's and Snack Pack's sections above; the rules post and the
  Rhyme Duel summary use `frame.divider`. No other post drew a framed box.

## Not changed

CLAUDE.md still describes v3; it is not edited in this change (Myra edits
it). Its "House style v3" block should point here instead.
