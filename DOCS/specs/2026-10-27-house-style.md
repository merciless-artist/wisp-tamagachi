# Wisp house style v2 (Myra, 2026-10-27)

Myra designed five layouts (raw drafts, kept for reference, NOT to copy blindly:
`DOCS/specs/status_card_v2.txt`, `vault_v2.txt`, `snack_pack_v2.txt`,
`lunchbox_v2.txt`, `leaderboard_v2.txt`) and gave the rule system below. She
asked: "just fix it all and make it make sense". The normalized layouts in this
file are the build target. Where a draft disagrees with this file, this file
wins.

## The rule system (Myra's, like markdown)

| Mark | Piece | Meaning |
|---|---|---|
| `#` | `║𝄡𝄚𝄂𝄆 **Name**` | a section heading (always bold) |
| `##` | `║𝄡𝄚𝄂 text` | a sub-heading or an information line |
| `###` | `║𝄡 text` | an item |
| `>` | `╠═══⇕` | between sections |
| `>>>` | `╚════════════════════╝` | closes the box |

Every line inside the box starts with `║`. A plain note line inside the box is
`║ text` (no clef). There are no empty `║` lines; sections are separated only by
`╠═══⇕`.

## The frame (identical on every layout)

- Title bar: `𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {Title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂` — exactly 4 `𝄚` on each side, one
  space inside each repeat sign.
- Box top: `╔════════════════════╗` (20 `═`).
- Box bottom: `╚════════════════════╝` (20 `═`).
- Bottom bar: `𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂` (20 `𝄚`).
- Titles (copy these exactly):
  - Status card: `𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈`
  - Vault: `𝕍𝒾𝒾𝔹ℝ {viibr_logo emoji} 𝕍𝒶𝓊𝓁𝓉`
  - Snack Pack: `𝕊𝓃𝒶𝒸𝓀 ℙ𝒶𝒸𝓀`
  - Lunchbox: `𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍`
  - Leaderboard: `𝕃𝑒𝒶𝒹𝑒𝓇𝒷𝑜𝒶𝓇𝒹`
- Emojis are always Wisp's own app emojis by name through `bot.emoji(...)`
  (never the server-emoji ids in the drafts). A missing emoji falls back the way
  the code does today (its name or nothing), never a broken `<:x:id>`.
- `{coin}` = `wisp_coin`, `{mini}` = `wisp_coin_mini` (uploaded 2026-10-27).
- Points the member spends are "wisp coins", short "WC". Leaderboard counts stay
  "points" (they are lifetime totals, not a balance).

## Status card

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔════════════════════╗
║𝄡𝄚𝄂・・𝐃𝐀𝐘 **{day}**・♫ ♪. ♫‿♪
║𝄡𝄚𝄂 he has Monster Pox・{hours} h left          <- only while sick
╠═══⇕
║𝄡 Care      {care bar}│{care}%
║𝄡 Happy   {happy bar}│{happy}%
║𝄡 Hunger {hunger bar}│{hunger}%
╠═══⇕
║𝄡𝄚𝄂 Fed by {nn} people today・♬‿♩. ♪
║𝄡𝄚𝄂 {v} ViiBR tracks and {s} Suno tracks・♪‿♫ ♪
╠═══⇕
║𝄡 Poke him or tag {<@wisp>} in {<#house>} to say hi!!
║𝄡 check your snackpack with /wisp snackpack
║𝄡 check the ViiBR Vault to buy treats and toys for Wisp!
╠═══⇕
║𝄡𝄚𝄂・・**life stage**・{𝐒𝐓𝐀𝐆𝐄}・♪‿♪ ♫.
╚════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Label padding exactly as in Myra's draft: `Care` + 6 spaces, `Happy` + 3,
  `Hunger` + 1. Egg/hatching cards use the same frame: no DAY line, bars
  `Warmth` and `Hatching` (egg) or `Emerging` (hatching), same padding idea,
  stage `𝐄𝐆𝐆` / `𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆`, first hint `Poke the egg or tag ...`.
- Bars use the meter emojis: Care `care_full` / `care_left`, Happy
  `happiness_full` / `happiness_left`, Hunger `full_full` / `full_left`. One
  `_full` per whole 10% of the displayed percent, plus one `_left` when the
  displayed percent's last digit is 5–9 (65% → 6 full + left; 90% → 9 full;
  0–4% → nothing). When a bar has no `_left` piece, put one space before `│`
  (Myra's Happy line). Egg bars: use `full_full` / `full_left` for Warmth and
  `happiness_full` / `happiness_left` for Hatching/Emerging (controller's call).
- `{nn}` is two digits; "person" when 1; "track" when 1.
- The waiting card (no living Wisp, Begin again): same frame, a single
  `║𝄡𝄚𝄂 No Wisp right now. Waiting for staff to begin again.` between the
  box lines.

## Vault (Components V2, one message)

The Vault is too long for a 2,000-character message, so it is sent as a
discord.py `LayoutView` (Components V2) with **no Container** (no box/accent),
made of `TextDisplay` pieces (4,000 characters in total) with the menus placed
between them. The text joined in order reads exactly as below.

```
{optional note line, e.g. ♪ Bought Cheese for 6 WC.}
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕍𝒾𝒾𝔹ℝ {viibr_logo} 𝕍𝒶𝓊𝓁𝓉 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔════════════════════╗
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
╚════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Snack and badge names and their padding before `│` are copied from Myra's
  draft (`vault_v2.txt`), with the typo fixed ("pickle diplomat") and the badge
  named for what it is ("flame keeper"). Prices come from `wisp/rules.py`
  (current prices; the draft's 50 was a mistake). Badge reasons (owned, Bandmates
  only, coming soon, between Wisps) follow `・`.
- Before he hatches, the Gifts lines are replaced by `║𝄡 He takes gifts once he
  has hatched`.
- Gift stock shows each in-stock gift's emoji (gift name when the emoji is
  missing) as today.
- Menus, notes after a purchase, ephemerality, and every existing behaviour stay
  as they are today; only the presentation changes.

## Snack Pack

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕊𝓃𝒶𝒸𝓀 ℙ𝒶𝒸𝓀 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔════════════════════╗
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
╚════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Empty sections: `║𝄡 nothing saved yet` (Snacks) and `║𝄡 none yet`.
- Long lists are cut with `║𝄡 and {n} more` as today.

## Lunchbox (public)

`/wisp lunchbox` now replies **publicly** in the channel where it was used
(no pings: `AllowedMentions.none()`); used in the track drop, it posts in Wisp's
House instead.

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕎𝒾𝓈𝓅'𝓈 𝕃𝓊𝓃𝒸𝒽𝒷𝑜𝓍 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔════════════════════╗
║𝄡𝄚𝄂𝄆 **Favorite songs**
║𝄡𝄚𝄂 {Mon d} ・ {<@sharer>}
║𝄡 {track url}
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
╚════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Song links stay clickable; suppress link previews on the post (`suppress_embeds`)
  so the card isn't buried under preview cards.
- Empty sections: `║𝄡 none yet`. Lists are cut to fit one message as today.

## Leaderboard (the Vault card / `/wisp board`)

```
𝄃𝄞𝄚𝄚𝄚𝄚𝄆 𝕃𝑒𝒶𝒹𝑒𝓇𝒷𝑜𝒶𝓇𝒹 𝄇𝄡𝄚𝄚𝄚𝄚𝄂
╔════════════════════╗
║𝄡𝄚𝄂 Snacks and the leaderboard.
║𝄡 Shop or open your Snack Pack with the buttons below.
╠═══⇕
║𝄡𝄚𝄂𝄆 **This life**
║𝄡 {n}. {<@member>} ・ {points} points
╠═══⇕
║𝄡𝄚𝄂𝄆 **All time**
║𝄡 {n}. {<@member>} ・ {points} points ・ {tier}
╠═══⇕
║𝄡𝄚𝄂𝄆 **Rhyme Duel**
║𝄡 {n}. {<@member>} ・ {points} points
╠═══⇕
║𝄡𝄚𝄂𝄆 **Versions**
║𝄡 {version line}
╚════════════════════╝
𝄃𝄣𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂
```

- Versions are trimmed from the oldest end to fit, as today; the closing lines
  always stay.

## Everything else

- `wisp.text.SEPARATOR` (the one-line divider in short House posts and anywhere
  else) becomes Myra's plain divider `𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂`
  (22 `𝄚`).
- All length checks use `text_length` (UTF-16); every message stays within its
  limit (2,000 for plain messages, 4,000 total text for the Vault's layout).
