# WiSP's Favorites: the new lunchbox layout

Myra sent this layout on 2026-11-23 for the lunchbox (`/wisp lunchbox` and the
Lunchbox button). It replaces today's framed lunchbox. Marked **my call** where
Claude chose.

## Myra's draft (server emoji markup, as she sent it)

```
#<:headerbarright:…><:wisp_waveform:…><:headerbarleft:…>**WISP'S FAVORITES** <:headerbarright:…><:wisp_waveform:…><:headerbarleft:…>
## <a:boing_bass:…> ** TOP 3 SONGS**
** **
 **01 · NOV 13** — @a cat
 <:portable_speaker:…> 🔥ᗪᕮᕮᑭ ᕮᑕOᒪOGY🔥・[♫ listen here](https://viibrmusic.com/s/B80iQBii)
** **
 **02 · NOV 12** — @a cat
 <:portable_speaker:…> .if・[♫ listen here](https://viibrmusic.com/songs/2b82…)
** **
 **03 · NOV 11** — @Foggy X
 <:portable_speaker:…>Time Goes Foggy X・[♫ listen here](https://viibrmusic.com/songs/fd4d…)
** **
### <:wisp_play:…>**FAVORITE SNACKS**
### ・jellywave <a:snack_jellywave:…>
### ・sinewave <a:snack_sinewave:…>
## <:wisp_pause:…> **FAVORITE EMOJI**
### ・<:wisp_happy:…> `:wisp_happy:`
## <:wisp_stop:…>  **FAVORITE GIFTS**
### ・<:alien_green:…>・<:book_blue:…> ・ <a:tama_welkotchi:…>
### ・<:headerbarright:…><:headerbar:…><:wisp_waveform:…><:headerbar:…><:headerbarleft:…><:mic2:…>https://viibrmusic.com <:headerbarright:…><:headerbar:…><:wisp_waveform:…><:headerbar:…><:headerbarleft:…>・
```

The ten new emojis (`headerbarright`, `wisp_waveform`, `headerbarleft`,
`boing_bass` (animated), `portable_speaker`, `wisp_play`, `wisp_pause`,
`wisp_stop`, `headerbar`, `mic2`) were uploaded as Wisp's app emojis under
those names on 2026-11-23. The code gets every emoji by name through
`bot.emoji(...)`, never by id.

## Rules

- **WiSP (Myra):** headers spell him `WiSP`, even in capitals: the title is
  `WiSP'S FAVORITES`. This holds for every heading the bot draws
  (`Frame.heading` and any other heading), not his spoken lines.
- **Song titles (Myra):** when Wisp keeps a favorite song he reads the song's
  name from its viibrmusic.com page and stores it. The page carries the name
  in its JSON-LD (`"@type"` MusicRecording / `"name"`), and in
  `<meta property="og:title" content="<name> by <artist> · ViiBR Music">`.
  Use the JSON-LD name (my call: the og:title cannot be split safely when a
  name contains " by "). A share link (`/s/<code>`) is read at the song page it
  redirects to. A page that cannot be read, or has no name, leaves the title
  empty and the song is shown without one; it is never an error post. Favorites
  kept before this release have no title: the lunchbox fills in a missing title
  the first time it shows that song (one fetch, stored), within the existing
  `VIIBR_RESOLVE_TIMEOUT`.
- **Layout:** exactly Myra's draft, with these my-calls:
  - `** TOP 3 SONGS**` becomes `**TOP {n} SONGS**` (a leading space inside `**`
    stops Discord bolding it). `n` is `FAVORITE_SONGS_SHOWN` or fewer if he
    has fewer; with none, the section shows `none yet`.
  - Song line one: ` **01 · NOV 13** — <@user>` (number two digits, month in
    capitals, the sharer pinged-looking but sent with no pings).
    Line two: ` {portable_speaker} {title}・[♫ listen here]({url})`, without
    `{title}・` when there is none. `** **` lines between songs as drafted.
  - **Favorite snacks:** his favorite snack this life first, then the snack he
    has eaten most this life if it is a different one: at most two. Each is
    `### ・{display name} {emoji}` (display names, per house style). `none yet`
    when there are none.
  - **Favorite emoji:** as today (his most used expression still uploaded),
    `### ・{emoji} \`:name:\``.
  - **Favorite gifts:** the gifts he kept this life, as their emojis on one
    `### ・` line joined by `・`, trimmed to fit the message. `none yet` when
    there are none.
  - The footer line is exactly the draft's.
  - No header picture: the draft's first line is the header (my call). It is
    sent as one Components V2 text message, as now (4,000 characters,
    `text_length`), and pings nobody.
  - When an emoji in the layout is missing from his app emojis, fall back the
    way the rest of the code does for missing emojis (no broken markup).
- **Mealtime post:** when he keeps a favorite, the Mealtime post names the song
  title when he has it.
- **Storage (additive):** `favorites.title VARCHAR(200) NULL`.
