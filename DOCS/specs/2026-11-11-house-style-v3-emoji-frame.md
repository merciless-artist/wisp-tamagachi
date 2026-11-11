# Wisp house style v3: the emoji frame (Myra, 2026-11-10)

v3 replaces the frame pieces of v2.1 (`2026-10-27-house-style.md`). Which
lines each layout has, its widths table and its other rules stay as v2.1 says,
except where this file says otherwise.

Why (Myra): "the emojis need to replace all the other menues instead of the
unicode. we have to do that because some people's phones or PCs dont register
all the unicode the same way and some dont at all". The music symbols
(`𝄡 𝄚 𝄂 𝄆`) and box drawing (`║ ╠ ═ ⇕`) are what fail.

Her design is the lunchbox she pasted on 2026-11-10 (below). The other menus
follow the same pieces.

## The pieces

All are Wisp's app emojis, by name through `bot.emoji(...)`.

| v2.1 mark | v3 piece |
|---|---|
| `#` heading | `:header_edge::header2::header: NAME` (CAPS, not bold) |
| `##` sub / info line | `:header_edge::header: text` |
| `###` item | `:header_edge::header3: text` |
| plain note line | `:header_edge: text` |
| blank `║` | `:header_edge:` |
| `>` between sections | `:header_edge::rest_bar::rest_bar:` |
| between two groups in one section (the lunchbox's collections) | `:header_edge::rest_bar:` |
| `>>>` box bottom | `:header_edge: :clef:` + 16 × `:header2:` + `:header:` |
| box top | none: the header picture sits right above |
| wrapped continuation row | `:header_edge: ` |
| `SEPARATOR`, the plain divider in short posts | `:clef:` + 16 × `:header2:` + `:header:` (**my call**: her bottom line without its edge) |

Myra, 2026-11-11: "no unicode" for the divider too.

- The frame is all or nothing: if any of `header_edge`, `header`, `header2`,
  `header3`, `rest_bar` or `clef` is not uploaded, the whole frame falls back
  to the v2.1 Unicode pieces (and the missing name is logged, as today), so a
  half-emoji box never shows. **My call.**
- No line may look wider than the bottom line. `visual_width` measures it
  (a custom emoji is 1.375 em, so the bottom line is about 26 em), and longer
  lines wrap with `:header_edge: ` rows as before.
- On a narrow phone Discord may wrap the 19-emoji bottom line itself. Check on
  Myra's phone after the lunchbox ships; shorten the `header2` run if needed.

## One message per menu

Every menu (lunchbox, Snack Pack, Vault, status card, Leaderboard) is one
Components V2 message: its header picture as a media gallery, then its text in
text displays, then its buttons or menus in action rows. No container, no
footer picture (the `:clef:` line closes it; Myra: "replace the footer with
clef"), 4,000 characters of text in all. Myra: "use the 4000", "or if you have
to split them in two parts, that is fine too". The header pictures stay as
they are (Myra: "you can keep the headers the same").

## Lunchbox

Her design, with app emoji names (her server copies are `headeredge` and
`rest_bar~1`):

```
{lunchbox_title.png}
:header_edge::header2::header: FAVORITE SONGS
:header_edge::header: Nov 9 ・ @a cat
:header_edge::header3: [#1 LISTEN HERE](https://...)
:header_edge::header: Nov 9 ・ @a cat
:header_edge::header3: [#2 LISTEN HERE](https://...)
:header_edge:
:header_edge::rest_bar::rest_bar:
:header_edge::header2::header: FAVORITE SNACK
:header_edge::header3: :snack_cloudwave: Cloud Wave
:header_edge::rest_bar::rest_bar:
:header_edge::header2::header: FAVORITE EMOJI
:header_edge::header3: :wisp_happy: `:wisp_happy:`
:header_edge::rest_bar::rest_bar:
:header_edge::header2::header: COLLECTIONS
:header_edge::header: BOOKS 1/4
:header_edge::header3: :gift_book_blue: Blue ・ from @thereal_a_cat
:header_edge::rest_bar:
:header_edge::header: TETRIS 2/6
:header_edge::header3: :gift_tetris_handheld: Tetris Handheld ・ from @a cat
:header_edge::header3: :gift_tetris_s: S Block ・ from @a_feline
:header_edge:
:header_edge: :clef::header2: … :header2::header:
```

- Each song's link reads `#N LISTEN HERE`, numbered from 1 in the order shown.
  Myra, 2026-11-10: the artist name goes "because the artist is already
  tagged". So the artist lookup on viibrmusic.com is no longer needed and is
  removed.
- The favorite emoji shows the emoji, then its name in code: `` `:wisp_happy:` ``.
- Collection lines are CAPS: `BOOKS 1/4`, `BOOKS 4/4 COMPLETE ・ finished by @x`.
- One `:rest_bar:` line between collections. Her draft also had one between
  `AFFIRMATION CARDS 1/4` and its gift; treated as a slip, so a collection's
  gifts follow its line directly. **My call.**
- A blank edge line after the songs and before the bottom line, as she drew.
- Empty sections: `:header_edge::header3: none yet`.
- Lists are cut to fit 4,000 as before: the oldest songs go first, and a
  collection drops to its progress line when its gifts do not fit.
