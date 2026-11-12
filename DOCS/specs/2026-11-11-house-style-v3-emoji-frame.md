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
| `>>>` box bottom | `:header_edge: :clef:` + 8 × `:header2:` + `:header:` |
| box top | none: the header picture sits right above |
| wrapped continuation row | `:header_edge: ` |
| `SEPARATOR`, the plain divider in short posts | `:clef:` + 8 × `:header2:` + `:header:` (**my call**: her bottom line without its edge) |

Myra, 2026-11-11: "no unicode" for the divider too.

- The frame is all or nothing: if any of `header_edge`, `header`, `header2`,
  `header3`, `rest_bar` or `clef` is not uploaded, the whole frame falls back
  to the v2.1 Unicode pieces (and the missing name is logged, as today), so a
  half-emoji box never shows. **My call.**
- No line may look wider than the bottom line. `visual_width` measures it
  (a custom emoji is 1.375 em, so the bottom line is about 15 em), and longer
  lines wrap with `:header_edge: ` rows as before.
- The bottom line is 11 emojis so it stays on one line on a phone. A
  phone's message area fits about 12 inline emojis (22 px each in about
  300 px); her first 19-emoji line would have wrapped there. Myra,
  2026-11-11: "make them whatever that works". **My call: 8 `header2`.**

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

## The other menus (2026-11-11)

Myra, 2026-11-11: "yes do all the cards, dont ask for permission, just do
them all". Every menu now follows the lunchbox. What changed from v2.1 in
each, beyond the pieces above, all **my calls**:

- **Every item leads with its emoji**, as the lunchbox's favorite snack
  does: `:snack_cloudwave: Cloud Wave ・ 3 WC`. Her hand-tuned padding before
  the Vault's `│` only lined up the old Unicode bar, so the `│` and the
  padding are gone, for snacks and badges alike, and items use the
  display names (`Cloud Wave`, `Team ViiBR`), not the keys.
- **No box top**, since the header picture sits right above, and a blank
  edge line before the bottom line, as in her lunchbox.
- **Snack Pack**: one V2 message: header picture, the pack, then the
  Shop the Vault button in a row. 4,000 characters, so far more keepsakes
  and badges show before "and N more".
- **Vault**: its footer picture is gone and the frame's bottom line closes
  it. The Gifts heading reads `GIFTS ・ 15 WC each`. It is **two
  messages**, one right under the other, so it still reads as one box (Myra:
  "or if you have to split them in two parts, that is fine too"). In the
  emoji frame each line carries about 64 characters of frame emoji
  text, so with every emoji uploaded the one-message Vault measured 5,074
  characters, over the 4,000 limit, and Discord would have refused it.
  - Part one: a note when there is one, the header picture, wisp coins,
    Snacks, then Medicine while he has a cold. No bottom line.
  - Part two: Badges, Magazines while he is a Rockstar, Gifts, a blank edge
    line and the bottom line. Measured: 2,214 and 3,955 characters, with
    every gift's emoji shown.
  - A menu redraws only its own part, with its note on top. Part one's coin
    count cannot be changed from part two, so after a badge, magazine or
    gift, part two shows `wisp coins` again under its note.
- **Leaderboard**: one V2 message, posted card and `/wisp board` alike.
  The posted card's header used to be a message of its own; that old
  header is deleted the first time the card is posted again. Whether the
  card changed is read from the posted layout's text.
- **Status card**: one V2 message under the Wisp Stats title, edited in
  place, with its six buttons three to a row. Her quote layout keeps its
  lines and blank lines, with these changes:
  - the `𝄡𝄚𝄂` and `𝄡` marks are the frame's sub and item marks, and
    `**right now**` is a heading, `RIGHT NOW`;
  - her Mathematical Bold words (`𝐃𝐀𝐘`, `𝐁𝐀𝐁𝐘`) are plain capitals: they
    are the same kind of character some phones cannot show;
  - the frame fits a phone, so lines wrap; her flourishes after Fed by,
    the tracks and the life stage (`・♬‿♩. ♪`) would wrap onto rows of
    their own, so they are gone; the day keeps its `♫ ♪. ♫‿♪`;
  - the two hint lines are one item, wrapped by the frame;
  - the bars stay on their own line with no edge before them, as in her
    quote where they had no clef: a full bar is 10 emojis and the percent,
    and with an edge it would be wider than the bottom line and break on a
    phone. The `│` before the percent is a space now.
  - The old card, two messages, is replaced the first time it is shown;
    after that it is edited in place. Begin again pressed on the waiting
    card leaves it as it is: the egg's card replaces it straight away.
