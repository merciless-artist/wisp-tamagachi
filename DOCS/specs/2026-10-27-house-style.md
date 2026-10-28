# Wisp house style v2.1 (Myra, 2026-10-27)

Myra designed five layouts (raw drafts, kept for reference, NOT to copy blindly:
`DOCS/specs/status_card_v2.txt`, `vault_v2.txt`, `snack_pack_v2.txt`,
`lunchbox_v2.txt`, `leaderboard_v2.txt`) and gave the rule system below. She
asked: "just fix it all and make it make sense". The normalized layouts in this
file are the build target. Where a draft disagrees with this file, this file
wins.

v2.1 (the same day) is her spacing pass, after the live Burrito post looked "a
little off":

- "the top line and the bottom line should be the same length"
- "it should not be all squashed up either. Foggy has a hard time reading
  squashed text so try to put a blank spot in between stuff"
- "make sure a sentence does not go past the actual encloser thing"
- blank `║` lines: "if i didnt put it in then no"

## The rule system (Myra's, like markdown)

| Mark | Piece | Meaning |
|---|---|---|
| `#` | `║𝄡𝄚𝄂𝄆 **Name**` | a section heading (always bold) |
| `##` | `║𝄡𝄚𝄂 text` | a sub-heading or an information line |
| `###` | `║𝄡 text` | an item |
| `>` | `╠═══⇕` | between sections |
| `>>>` | `╚══════════════════════╝` | closes the box |

Every line inside the box starts with `║`. A plain note line inside the box is
`║ text` (no clef). A lone `║` line (a blank spot) appears exactly where
Myra's draft has one and nowhere else; the layouts below show each one.

## The frame

- Title bar: `𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {Title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂`: 4 `𝄚` on each side (Burrito's post
  has 6), one space inside each repeat sign.
- Bottom bar: `𝄃𝄣` + m `𝄚` + `𝄂`, where m makes it look as wide as the title
  bar (`wisp.text.bars(title)` picks m from `visual_width`, below). Calibrated
  on Myra's Burrito post: 6 `𝄚` each side of `𝔹𝓊𝓇𝓇𝒾𝓉𝑜` looks as wide as 20 `𝄚`.
- Box top `╔═…═╗` and bottom `╚═…═╝` always have the same number of `═`: the
  layout's box width.

| Layout | Box width (`═`) | Why |
|---|---|---|
| Burrito's post | 22 | Myra's own |
| Status card (and the waiting card) | 25 | a full bar line: 10 meter emojis, then `│100%` |
| Vault | 24 | the widest badge row, from its padded name to its price |
| Snack Pack | 22 | |
| Lunchbox | 22 | |
| Leaderboard | 22 | |

- Titles (copy these exactly):
  - Status card: `𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈`
  - Vault: `𝕍𝒾𝒾𝔹ℝ {viibr_logo emoji} 𝕍𝒶𝓊𝓁𝓉`
  - Snack Pack: `𝕊𝓃𝒶𝒸𝓀 ℙ𝒶𝒸𝓀`
  - Lunchbox: `𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍`
  - Leaderboard: `𝕃𝑒𝒶𝒹𝑒𝓇𝒷𝑜𝒶𝓇𝒹`
  - Burrito's post: `𝔹𝓊𝓇𝓇𝒾𝓉𝑜`
- Emojis are always Wisp's own app emojis by name through `bot.emoji(...)`
  (never the server-emoji ids in the drafts). A missing emoji falls back the way
  the code does today (its name or nothing), never a broken `<:x:id>`.
- `{coin}` = `wisp_coin`, `{mini}` = `wisp_coin_mini` (uploaded 2026-10-27).
- Points the member spends are "wisp coins", short "WC". Leaderboard counts stay
  "points" (they are lifetime totals, not a balance).

## Nothing goes past the box's right edge

Discord's font is proportional, so `wisp.text.visual_width(text)` estimates how
wide a line looks, in em, from one table of widths (`wisp.text.WIDTHS`):

| Kind | em | Examples |
|---|---|---|
| space | 0.22 | from Myra's padding before the Vault's `│` |
| thin / narrow letters | 0.25 / 0.35 | `i l . ' !` / `f r t / -` |
| letters / digits / capitals / wide | 0.52 / 0.55 / 0.65 / 0.8 | `a` / `5` / `A` / `m w M W %` |
| superscript letters | 0.35 | `ᵗʰᵉˢᵉ` |
| mathematical and letterlike letters | 0.54 | `𝕎 𝒾 ℙ 𝐃` |
| `𝄚` / other music symbols | 0.75 / 0.6 | `𝄃 𝄞 𝄡 𝄂 𝄆 𝄇 𝄣` |
| box drawing | 0.662 | `═ ║ ╔ │` |
| `・` | 1.0 | |
| custom or Unicode emoji | 1.375 | `<:name:id>`, `<a:name:id>` |
| mention | 6.0 | `<@id>`, `<#id>` (a name of typical length) |
| unseen | 0 | `**`, the address of a masked link, the `\` of an escape |
| anything else | 0.6 | `♪ ♫ ‿ ⇕` |

Calibration: in Myra's Burrito post a 22-`═` box holds every line, and the
widths break her two long sentences exactly where she broke them.

- A line fits when its `visual_width` is at most the box top's.
- Each layout's box is at least as wide as its widest line that cannot wrap
  (the table above), and every other line is wrapped at word boundaries by
  `wisp.text.wrap`: at a single space, between two emoji (so a line of only
  emoji wraps between them), and before a `・`. A `・` never ends a row; it
  leads the next one, like one of her bullets, and a row that runs out of
  room breaks before its last `・` part so each part keeps together (unless
  that would leave the first row less than half full). So a badge's reason
  moves down whole (`║ ・Bandmates only`) and a long version line reads
  `║𝄡 v1 ・ went out after 18 days` / `║ ・ peak Teen` /
  `║ ・ hatched by @someone`. Never inside Myra's padding (a run of spaces),
  bold text or a masked link. A wrapped continuation line starts
  with `║ ` (as in her Burrito post), never with a clef.
- Message limits still hold (`text_length`; 2,000, or 4,000 for the Vault).

## Burrito's post

The starter of the Burrito thread, exactly. `!wisp setup` edits an existing
Burrito starter to this text.

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄚𝄚𝄆 𝔹𝓊𝓇𝓇𝒾𝓉𝑜 𝄇𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄂
╔══════════════════════╗
║𝄡𝄚𝄂 Burrito is Wisp's fairy god-bot.
║
║𝄡 Ask him anything about how
║ Wisp works, right here.
║
║𝄡 He'll point you to where to look
║ for Wisp's live stats.
╚══════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

## Status card

Shown before wrapping; the hints and other long lines wrap to the box.

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔═════════════════════════╗
║
║𝄡𝄚𝄂・・𝐃𝐀𝐘 **{day}**・♫ ♪. ♫‿♪
║𝄡𝄚𝄂 he has Monster Pox・{hours} h left          <- only while sick
║
╠═══⇕
║𝄡 Care
║{care bar}│{care}%
║𝄡 Happy
║{happy bar}│{happy}%
║𝄡 Hunger
║{hunger bar}│{hunger}%
║
╠═══⇕
║𝄡𝄚𝄂 Fed by {nn} people today・♬‿♩. ♪
║
║𝄡𝄚𝄂 {v} ViiBR tracks and {s} Suno tracks・♪‿♫ ♪
║
╠═══⇕
║𝄡 Poke him or tag {<@wisp>} in {<#house>} to say hi!!
║𝄡 check your snackpack with /wisp snackpack
║𝄡 check the ViiBR Vault to buy treats and toys for Wisp!
║
╠═══⇕
║𝄡𝄚𝄂・・**life stage**・{𝐒𝐓𝐀𝐆𝐄}・♪‿♪ ♫.
║
╚═════════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Each meter is its label's line (`║𝄡 Care`), then its bar on its own line
  under it (`║{bar}│65%`); the three meters follow each other with no blank
  line between them (Myra: "i made the ones i made the way i made them").
  Egg/hatching cards use the same frame with no DAY section (so the blank
  line after the box top comes straight before the bars): bars `Warmth` and
  `Hatching` (egg) or `Emerging` (hatching), stage `𝐄𝐆𝐆` / `𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆`, first
  hint `Poke the egg or tag ...`.
- Bars use the meter emojis: Care `care_full` / `care_left`, Happy
  `happiness_full` / `happiness_left`, Hunger `full_full` / `full_left`. One
  `_full` per whole 10% of the displayed percent, plus one `_left` when the
  displayed percent's last digit is 5–9 (65% → 6 full + left; 90% → 9 full;
  0–4% → nothing). When a bar has no `_left` piece, put one space before `│`
  (Myra's Happy line). Egg bars: use `full_full` / `full_left` for Warmth and
  `happiness_full` / `happiness_left` for Hatching/Emerging (controller's call).
- `{nn}` is two digits; "person" when 1; "track" when 1.
- The waiting card (no living Wisp, Begin again): the same frame and its
  blank lines around a single
  `║𝄡𝄚𝄂 No Wisp right now. Waiting for staff to begin again.`.

## Vault (Components V2, one message)

The Vault is too long for a 2,000-character message, so it is sent as a
discord.py `LayoutView` (Components V2) with **no Container** (no box/accent),
made of `TextDisplay` pieces (4,000 characters in total) with the menus placed
between them. The text joined in order reads exactly as below (before
wrapping).

```
{optional note line, e.g. ♪ Bought Cheese for 6 WC.}
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕍𝒾𝒾𝔹ℝ {viibr_logo} 𝕍𝒶𝓊𝓁𝓉 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔════════════════════════╗
║
║𝄡𝄚𝄂 wisp coins: {coin} {balance}
╠═══⇕
║𝄡𝄚𝄂𝄆 **Snacks**
║𝄡 sinewave    │{e}・free once a day
║𝄡 cloudwave │{e}・{mini} 3 WC
║𝄡 jellywave    │{e}・{mini} 3 WC
║𝄡 juicewave   │{e}・{mini} 3 WC
║𝄡 spicywave  │{e}・{mini} 5 WC
║𝄡 cheese        │{e}・{mini} 6 WC
║𝄡 pickles        │{e}・{mini} 6 WC
║𝄡 glitterwave│{e}・{mini} 8 WC
║𝄡 viibrwave   │{e}・{mini} 10 WC
║
[snack select]
╠═══⇕
║𝄡𝄚𝄂𝄆 **Badges**
║𝄡 pickle diplomat  │{e}・{mini} 25 WC{・reason}
║𝄡 flame keeper       │{e}・{mini} 100 WC{・reason}
║𝄡 team viibr              │{e}・{mini} 250 WC{・reason}
║𝄡 bandmate              │{e}・{mini} 250 WC{・reason}
[badge select, when any badge can be bought]
╠═══⇕
║𝄡𝄚𝄂𝄆 **Gifts**・{mini} 15 WC each
║ ᵗʰᵉˢᵉ ᵃʳᵉ ᵃ ᵍᵃᵐᵇˡᵉ... ʰᵉ ᵐⁱᵍʰᵗ ⁿᵒᵗ ʷᵃⁿᵗ ⁱᵗ ᵗʰᵃᵗ ᵈᵃʸ
║{kept-today warning line, when he already kept a gift today}
║𝄡 Lunchbox Liners: {in-stock gift emojis, or "back tomorrow" / "all kept this life"}
║𝄡 Alien Dolls: ...
║𝄡 Books: ...
║𝄡 Affirmation Cards: ...
║𝄡 Tamagotchis: ...
║𝄡 Tetris: ...
║𝄡 Jewels: ...
[collection select, then the gift select once a collection is picked]
╚════════════════════════╝
{bottom bar matching the title bar}
```

- Snack and badge names and their padding before `│` are copied from Myra's
  draft (`vault_v2.txt`), with the typo fixed ("pickle diplomat") and the badge
  named for what it is ("flame keeper"). Prices come from `wisp/rules.py`
  (current prices; the draft's 50 was a mistake). Badge reasons (owned, Bandmates
  only, coming soon, between Wisps) follow `・` and wrap onto the next line
  when they do not fit.
- Before he hatches, the Gifts lines are replaced by `║𝄡 He takes gifts once he
  has hatched`.
- Gift stock shows each in-stock gift's emoji (gift name when the emoji is
  missing) as today; a collection's line wraps between its emojis.
- The Magazines section (while Wisp is a Rockstar) sits between Badges and
  Gifts, as before.
- Menus, notes after a purchase, ephemerality, and every existing behaviour stay
  as they are today; only the presentation changes.

## Snack Pack

No blank lines (her draft has none).

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕊𝓃𝒶𝒸𝓀 ℙ𝒶𝒸𝓀 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔══════════════════════╗
║𝄡𝄚𝄂 {<@member>} snack pack
║𝄡𝄚𝄂・{mini} {balance} WC (wisp coins)
╠═══⇕
║𝄡𝄚𝄂𝄆 **Snacks**
║𝄡 {key} {e} x{n}
║𝄡 sinewave {e} free today
╠═══⇕
║𝄡𝄚𝄂𝄆 **Keepsakes**
║𝄡 Wisp v{n}'s {e}
╠═══⇕
║𝄡𝄚𝄂𝄆 **Badges**
║𝄡 Wisp v{n}'s {e}
╚══════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Empty sections: `║𝄡 nothing saved yet` (Snacks) and `║𝄡 none yet`.
- Long lists are cut with `║𝄡 and {n} more` as today.

## Lunchbox (public)

`/wisp lunchbox` replies **publicly** in the channel where it was used (no
pings: `AllowedMentions.none()`); used in the track drop, it posts in Wisp's
House instead. No blank lines (her draft has none).

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔══════════════════════╗
║𝄡𝄚𝄂𝄆 **Favorite songs**
║𝄡𝄚𝄂 {Mon d} ・ {<@sharer>}
║𝄡 [{Artist}]({track url})
╠═══⇕
║𝄡𝄚𝄂𝄆 **Favorite snack**
║𝄡 {e} {Snack Name}
╠═══⇕
║𝄡𝄚𝄂𝄆 **Favorite emoji**
║𝄡 {e}
╠═══⇕
║𝄡𝄚𝄂𝄆 **Collections**
║𝄡𝄚𝄂 {Collection} {kept}/{total}
║𝄡 {e} {Gift Name} ・ from {<@giver>}
╚══════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Each song's link is a masked link named for the song's artist (Myra: "just
  do the artist"), or `[listen ♪]({track url})` when the artist is unknown. It
  is never broken across lines; an artist too long for the box is shortened
  with `…`.
- The artist is the one viibrmusic.com's song page names (its schema.org
  `byArtist`). It is looked up the first time the lunchbox shows that song and
  kept in `favorites.artist` ("" when the page names none or is gone: 404 or
  410), so each song is asked about once. When the site cannot be reached or
  gives any other answer (5xx, 429, 403, a redirect) the link reads
  `listen ♪` and the lookup is tried again next time. The name is put on one
  line (whitespace and line breaks collapse to single spaces) before it is
  kept and before it is shown.
- Link previews stay suppressed (`suppress_embeds`).
- Empty sections: `║𝄡 none yet`. Lists are cut to fit one message as today.

## Leaderboard (the Vault card / `/wisp board`)

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕃𝑒𝒶𝒹𝑒𝓇𝒷𝑜𝒶𝓇𝒹 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔══════════════════════╗
║𝄡𝄚𝄂 Snacks and the leaderboard.
║
║𝄡 Shop or open your Snack Pack with the buttons below.
║
╠═══⇕
║𝄡𝄚𝄂𝄆 **This life**
║𝄡 {n}. {<@member>} ・ {points} points
║
╠═══⇕
║𝄡𝄚𝄂𝄆 **All time**
║𝄡 {n}. {<@member>} ・ {points} points ・ {tier}
║
╠═══⇕
║𝄡𝄚𝄂𝄆 **Rhyme Duel**
║𝄡 {n}. {<@member>} ・ {points} points
║
╠═══⇕
║𝄡𝄚𝄂𝄆 **Versions**
║𝄡 {version line}
║
╚══════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Versions are trimmed from the oldest end to fit, as today; the closing lines
  always stay.

## Everything else

- `wisp.text.SEPARATOR` (the one-line divider in short House posts and anywhere
  else) is Myra's plain divider `𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂`
  (22 `𝄚`).
- All length checks use `text_length` (UTF-16); every message stays within its
  limit (2,000 for plain messages, 4,000 total text for the Vault's layout).
