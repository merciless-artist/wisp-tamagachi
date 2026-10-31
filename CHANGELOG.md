# Changelog

## 2026-10-31 (The Studio as a gallery, and Burrito's picture)

- Setup now makes gallery view the Studio forum's default layout
  (`_show_as_gallery` in `cogs/studio.py`), once; a failure, such as a missing
  Manage Channels permission, is posted in Wisp's House.
- Burrito's post gets his picture (`ASSETS/thumbs/burrito.png`, a 600 px copy
  of his pfp), which the forum shows as its thumbnail. Setup adds it to the
  existing post like the other thumbnails.
- Myra will replace the text frames with images, since every device draws
  the frame symbols in a different font, so the frames are left as they are.

## 2026-10-31 (A real kid voice, and the track drop)

- The Child talked like an adult ("hey hey! got any fresh beats for me?"). His
  voice in `wisp/voice.py` is now about five years old, with example lines in
  the same style as Myra's Baby voice (excited, grumpy, sad, sleepy, silly,
  asking for food). Myra approved the draft.
- From Child on, Wisp knows members feed him in the track drop: when he asks
  for a track he sends people there, and a link posted in his House gets
  pointed there too (`_TRACK_DROP_NOTE`). He writes `#track-drop`, and
  `link_track_drop` turns it into a clickable link to the real channel
  (answers, pokes and chime-ins). The Baby still only babbles.
- `DOCS/wisp_prompts.md` regenerated.
- Fixed a stale test: Myra's rewrite says "Right now you're talking to …",
  which `test_named_member_is_called_by_their_wisp_name` still expected with a
  capital Y.

## 2026-10-30 (A 30-day life)

- Myra halved Wisp's life to keep the cute stages coming round more often. In
  `wisp/rules.py`:
  - The egg hatches at 20 meal points (was 30); coal eggs start with 10.
  - Child from day 5 (was 3), Teen from day 11 (was 7), Adult from day 16
    (was 14). Points and caretakers needed are unchanged.
  - Old Fogey at day 24 (was 45), farewell at day 30 (was 60).
  - Rockstar needs 4 days of high happiness (was 7), so it still fits in the
    shorter Adult stretch.
- Monster Pox (day 1 to 12) still comes before Adult. The FAQ's quick rules
  read these numbers, so they update when the FAQ is rebuilt.
- Tests that hard-coded the old days now read them from the rules
  (`tests/test_life.py`, `tests/test_voice.py`). `test_happy_counts_only_chatters`
  now expects the Happy bar on its own line, as house style v2.1 lays it out.

## 2026-10-29 (Myra's rewritten prompts: opening, Baby and Child)

- Myra rewrote Wisp's prompts to give him more personality. In `wisp/voice.py`:
  - One opening for every stage (`_WHO_YOU_ARE`): the AI mascot, a dark
    purple fire sprite with flaming orange hair, sick beats, suno tracks.
  - "How you talk": if asked whether he heard a song, he says he ate it
    before he listened; game questions go to Burrito, his fairy god-bot.
  - He no longer pretends not to be an AI: asked, he says yes, he's ViiBR's
    AI mascot, then carries on being Wisp (Myra's call).
  - Reactions: faces one per line, a firmer both-colons rule, and the "no u"
    GIF as a hyperlink, `NO_U_LINK` (`[no u!](url)`). `_cap` keeps the
    hyperlink or bare link whole when it cuts a long reply.
  - The Baby's voice: calls himself "wips", with Myra's example noises.
  - The bond ladder as a numbered list, then "Right now you're talking to
    {name}." with the bond and its number; the Baby is a little shy with
    overwhelming new faces.
- Faces per stage: the Baby and Child use only Myra's list of faces
  (`STAGE_FACES`, in her order, plus the nap face, and the dead face the
  Baby's examples use). Teen and older still get every uploaded face.
- `DOCS/wisp_prompts.md` regenerated.
- Tests: `tests/test_voice.py`, `tests/test_conversation.py`.

## 2026-10-29 (Wisp gets mad at the same member poking again and again)

- Myra wants Wisp to get mad when someone pokes him more than twice. Pokes
  are now counted per member as a streak (`HouseTalk.poke(guild, user, now)`):
  each poke within `POKE_STREAK_GAP` (10 minutes) of that member's last adds
  one; other members' pokes never count toward it.
- `poke_flavor` takes the streak: from `POKE_MAD_AT` (3) he is always
  `PokeFlavor.MAD`, from `POKE_FED_UP_AT` (5) always `FED_UP`. Below that it
  rolls as before; `ANNOYED` now only comes from being hangry.
- Mad and fed-up prompts let him be mean like a kid in a huff ("big meanie
  head") but never cruel. A Baby or Child gets a full tantrum. The egg
  rattles away, or turns its back.
- `POKE_SPAM_WINDOW` and `POKE_SPAM_POKES` are gone.
- Tests: `tests/test_voice.py`, `tests/test_conversation.py` (poke streaks).

## 2026-10-29 (Status and Vault posts locked; prompt reference)

- Myra asked for the Status and ViiBR Vault Studio posts to be locked like the
  FAQ: they are boards Wisp keeps updated, not places to chat. Their
  `StudioThread` specs now have `locked=True`; `!wisp setup` locks existing
  ones. Wisp still edits and posts in them (he does the same in the FAQ).
  Jam Space, Mealtime and Burrito stay open.
- `DOCS/wisp_prompts.md`: every prompt Wisp uses (egg, each stage, poke,
  chiming in, mood and Monster Pox layers, goodbye), generated from the code.

## 2026-10-28 (Wisp's emoji tags with a missing colon)

- Myra saw tags come through broken when the AI dropped a colon. `parse_reply`
  now converts `:name` and `name:` (one colon missing) when the name is a known
  expression and the match is a whole token: not inside a word, a URL, a time
  such as `3:00`, a ratio or a tag. Unknown names in those forms stay plain
  text (`Note: hi`), except names starting `wisp_`, `snack_`, `gift_`,
  `keepsake_` or `badge_`, which are removed like the full form.
- Half-formed Discord codes the AI writes itself (`<:name:>`, `<a:name:>`,
  `<:name:123` with no `>`) are converted when known and removed when not. A
  complete `<:name:id>` / `<a:name:id>` is never touched.
- Converted names still land in `Reply.expressions` (his favorite-emoji count).
- Tests: `tests/test_voice.py` (every form, edges, plain colons, unknown names).

## 2026-10-27 (FAQ banner pictures: one message per question)

- Myra found the page-shaped FAQ pictures shrank in Discord until the text was
  tiny, so the FAQ now uses 35 banner pictures, one per question, in
  `ASSETS/faq/` named `{NN}_{section}_{k}.png`. The 11 one-per-section
  pictures are removed.
- `cogs.faq.FaqSection.pictures` is a tuple of file names (was one `picture`).
  The 11 sections and titles are unchanged. `FAQ_PICTURE_COUNT` is the total.
- `fill_faq` posts every picture as its own message (one file each, so Discord
  shows each large, not as a grid), in order, with no pings. The first post's
  table of contents links each section title to that section's first picture;
  `table_of_contents` takes every picture's message id and raises `ValueError`
  unless there is one per picture. The 11 links come to about 1,200 characters,
  well under the 2,000 limit (tested at the largest possible ids).
- All posted ids are still stored in `settings.faq_message_ids`, even when
  posting stops part way, and the old stored ids, including the earlier
  one-per-section posts, are deleted first. Missing pictures still raise
  `FileNotFoundError` before anything changes.
- `ensure_studio` rebuilds the FAQ when the stored id count is not 35, so a
  restart replaces the earlier 11-picture FAQ by itself.
- No schema change: `faq_message_ids` is `TEXT` (up to 65,535 bytes); 35 ids
  are about 750 bytes as JSON. A repo test round-trips 500 ids on the real
  database.
- Tests: `tests/test_studio.py` (one file per message in order, links to each
  section's first picture, one-per-section posts deleted on rebuild, partial
  failure after 19 pictures stored, missing picture, contents length, code and
  repo pictures agree) and `tests/test_repos.py`. README updated.

## 2026-10-27 (lunchbox artist lookup: review fixes)

- Only a 404 or 410 song page now means "no artist" (kept as ""). Any other
  answer than the page (5xx, 429, 403, a redirect) raises
  `aiohttp.ClientResponseError` from `ShareLinkResolver.artist`, so the
  lunchbox shows `listen ♪`, logs a warning and asks again next time instead
  of keeping "" for good. Share-link resolving (`resolve`) is unchanged; the
  lunchbox is the only caller of `artist`.
- An artist name is put on one line (`cogs.share_links.one_line`: every run
  of whitespace, line breaks included, becomes one space) before it is kept
  and again when the link is drawn, so it can never break a box line.
- Tests: `tests/test_share_links.py` (404/410 name none; 500/503/429/403/301
  raise; names with line breaks) and `tests/test_wisp_lunchbox.py` (a busy
  site leaves the artist unknown and the next view stores it, on the real
  database; a stored name with line breaks is drawn on one line).

## 2026-10-27 (house style v2.1: spacing, matching bars, wrapping)

- Myra's spacing pass (`DOCS/specs/2026-10-27-house-style.md` is updated to
  v2.1). Presentation only; every behaviour stays.
- Burrito's post is her text byte for byte (blank lines, 6 `𝄚` each side, a
  22-`═` box, two wrapped lines), and `!wisp setup` now edits an existing
  Burrito starter whose text differs (`StudioThread.current_content`). A
  starter that is gone is left alone; a failed edit is posted in the thread
  as `Error in updating the first post of Burrito, Fairy God-bot: ...`.
- `wisp.text.visual_width` estimates how wide a line looks in Discord from
  one table (`WIDTHS`), calibrated on her Burrito post (a 22-`═` box holds
  every line and breaks where she broke them; 6 `𝄚` around its title match a
  20-`𝄚` bottom bar) and on her Vault padding (a space is about 0.22 em). A
  custom emoji counts 1.375 em and a mention 6 em.
- `wisp.text.bars(title)` gives the title bar and a bottom bar sized to look
  as wide; every layout's box top and bottom have the same number of `═`.
  Widths: status card (and waiting card) 25 (a full bar line: 10 meter
  emojis and `│100%`), Vault 24 (the widest badge row), Snack Pack,
  lunchbox, leaderboard and Burrito 22.
- `wisp.text.wrap` breaks every line wider than its box at word boundaries
  into `║ ` continuation rows: at single spaces, between emoji (a line of only
  emoji wraps between them) and before a `・`, which then leads the next row
  (never ends one). A full row breaks before its last `・` part so each part
  keeps together (`║ ・ peak Teen` / `║ ・ hatched by @someone`), and a
  badge's reason moves down whole (`║ ・Bandmates only`); never inside Myra's
  padding, bold text or a masked link.
- Blank `║` lines are back exactly where her drafts have them: the status
  card (after the box top, after the DAY section, after the meters, after the
  fed and the tracks lines, after the hints, before the box close; the
  waiting card the same), the Vault (after the box top and after the snack
  rows) and the leaderboard (after the intro sentence and its wrapped lines,
  after each list). The Snack Pack and lunchbox drafts have none.
- Status card meters: each bar moves down onto its own line under its label
  (`║𝄡 Care`, then `║{bar}│65%`), nothing else in the block changes, and the
  three meters follow each other with no blank line. The label padding is
  gone with the bar (`wisp.card.LABEL_PADDING` removed).
- Lunchbox song links are masked links named for the song's artist
  (`║𝄡 [Foggy X Music](url)`), or `[listen ♪](url)` when unknown (Myra: "just
  do the artist"). Never broken across lines; a long artist is shortened with
  `…` to fit the box; markdown in the name is escaped.
- The artist comes from the song page's schema.org `byArtist`
  (`ShareLinkResolver.artist`, `cogs.share_links.artist_on_page`). Small
  calls, made here: it is looked up lazily, the first time the lunchbox shows
  a song (all shown songs at once), not when the favorite is picked, so the
  daily tick never waits on viibrmusic.com and each song is asked about once.
  The result is kept in the new column `favorites.artist` (added on startup;
  NULL = not looked up yet, "" = the page names none). When the site cannot
  be reached, the link reads `listen ♪`, a warning is logged (no channel
  post: the lunchbox itself worked) and the lookup is tried again next time.
- Tests: `tests/test_text.py` (widths, calibration, bars for every layout
  title, wrapping rules), `tests/test_card.py`, `tests/test_studio.py`
  (Burrito's exact text, setup updating the old starter, a missing starter,
  a failed edit), `tests/test_vault.py`, `tests/test_snacks.py`,
  `tests/test_badges.py`, `tests/test_gifts.py`, `tests/test_magazines.py`,
  `tests/test_wisp_lunchbox.py` (artist links against a local song-page
  server) and `tests/test_share_links.py`; `tests/layout.py` gains
  `assert_fits_its_box` for the fullest layouts.

## 2026-10-27 (Rockstar magazines)

- While the living Wisp is a **Rockstar**, the Vault shows a `# **Magazines**`
  section between Badges and Gifts: `VIIBRATIONS cover・{mini} 100 WC` and
  `Music & Science cover・{mini} 100 WC`, `・owned` once bought this life, and a
  "Get a magazine" menu under it with the covers the member can still buy. At
  every other stage (and between Wisps) the section and menu are absent.
- Buying spends 100 WC (`MAGAZINE_COST`), with the usual refusals: banned,
  can't feed, short of WC (Wisp's not-enough-points line), or already owned
  this life (`♪ You already have the VIIBRATIONS cover for Wisp v1.`). A menu
  left open after he stops being a Rockstar answers
  `♪ The magazines are gone from the shelf.` and nothing is spent. A purchase
  refreshes the Vault under `♪ You got the {name}.` and sends the cover's
  picture to the buyer only (ephemeral). A picture that cannot be sent is
  reported as `Error in sending the {name} picture (the purchase went
  through): ...`; the purchase stands.
- Purchases are stored in the new `magazines` table (member, magazine, life,
  version, time; one per member per magazine per life), created by
  `create_tables` beside the live tables.
- The Snack Pack has a `# **Magazines**` section after Badges, only when the
  member owns a cover: `Wisp v3's VIIBRATIONS cover`, every life, newest
  first, cut to fit like keepsakes (at most a quarter of the room).
- Art: posting copies `ASSETS/mags/viibrations_cover.jpg` and
  `ASSETS/mags/musicnscience_cover.jpg` (927x1200, JPEG q88, about 230-250 KB)
  made from the 3477x4500 originals, which are committed alongside.
- FAQ: a "What are the magazines?" Q&A in the Vault and Snack Pack section
  (the section picture needs re-rendering).
- Tests: `tests/test_magazines.py` (section only for a living Rockstar, the
  purchase, the private picture, the refusals, the next life, the Snack Pack
  across lives, the fullest Vault and Snack Pack) and a schema test for the
  new table on a live database.

## 2026-10-27 (`!wisp song`)

- New staff command `!wisp song <link> <words...>`: Wisp posts the words, then
  the link on the line underneath, in the Jam Space thread, exactly as typed
  (no prefix, flair or AI line, no pings, link previews left on so the player
  shows). The staff member's command message is deleted afterwards; a failed
  delete, such as a missing Manage Messages permission, is only logged.
- The link must be an http(s) URL. A missing or bad link, or no words, gets
  the usual one-line usage. A Jam Space that is not set up or cannot be
  reached is reported as `Error in !wisp song: ...` where the command was
  used, nothing is posted and the command message stays.
- Tests: the post, the exact text, the deleted command, bad and missing
  arguments, an unreachable Jam Space, a Discord refusal, a failed delete and
  a non-staff author.

## 2026-10-27 (Monster Pox, Hunger and Burrito's post)

- His once-per-life childhood cold is now **Monster Pox** everywhere members
  read it. His SICK and RECOVERED lines and his AI voice while sick are
  spotty, itchy and feverish with a thermometer instead of sniffly and sneezy,
  and the spots are back. The rules post, FAQ, spec page, README and build
  rulings say Monster Pox. Code names (`is_sick`, `cold_*`, `SICK_*`,
  `Moment.SICK`/`RECOVERED`) are unchanged, and a "cold egg" is still a cold
  egg.
- The food meter's member-facing name is **Hunger** (a full bar means well
  fed): `♪ Wisp ate your Cheese ・ hunger +8`, the Vault and feed menu
  descriptions (`3 WC ・ hunger +5`), the rules post (`・Hunger: tracks and
  snacks...`), two hangry lines that named the meter, the FAQ, the spec page
  and the README. `Life.full` and `FULL_*` keep their names.
- The rules post's sickness line reads `・Once before Adult: Monster Pox for
  {h} h. Faster drain, he can't die, meals count up to {n} a day`, and the
  Last Ember line drops "each". At four-digit numbers it is 1,994 of 2,000.
  (Run `!wisp faq` to refresh the live post.)
- Setup keeps a sixth Studio post, `🧚│Burrito, Fairy God-bot`, created when
  missing and renamed back like the others, its id in the new additive
  `settings.burrito_thread_id` column. Its first post is the house-style frame
  titled `𝔹𝓊𝓇𝓇𝒾𝓉𝑜`, saying Burrito is Wisp's fairy god-bot, to ask him
  anything about how Wisp works right there, and that he points people to
  Wisp's live stats. Wisp never answers or chimes in there (Burrito, a separate
  bot, does). Run `!wisp setup` (or `/wispadmin setup`) once to create it.
- The House notice for recreated Studio posts and setup's "Created threads"
  line quote each name (`recreated "Mealtime", "Burrito, Fairy God-bot".`),
  so a name with a comma reads as one post.
- Tests: the feeding tests for endings now check the Begin again flow (the
  ending is announced, staff are asked, no egg is laid), setup expects six
  Studio posts, and the schema adds `burrito_thread_id` to a live table.
- The FAQ page and the spec page show the v2 status card.
- `/wisp lunchbox`: once the lunchbox is posted, a failure to remove the
  private "thinking" reply is ignored, so the member is no longer told it did
  not work.

## 2026-10-27 (house style v2)

- Myra's house style (`DOCS/specs/2026-10-27-house-style.md`) for the status
  card, the Vault, the Snack Pack, the lunchbox and the leaderboard: a title
  bar (`𝄃𝄞𝄚𝄚𝄚𝄚𝄆 {Title} 𝄇𝄡𝄚𝄚𝄚𝄚𝄂`), the box (`╔`/`╚` with 20 `═`), `#`
  headings `║𝄡𝄚𝄂𝄆 **Name**`, `##` lines `║𝄡𝄚𝄂 text`, `###` items `║𝄡 text`,
  `╠═══⇕` between sections and the bottom bar. Every frame piece lives in
  `wisp/text.py` (`title_bar`, `BOX_TOP`, `BOX_CLOSE`, `heading`, `sub`,
  `item`, `note`, `sections`, `framed`); the old `VAULT_RAIL`/`PACK_RAIL` and
  per-module frame strings are gone.
- Status card: `𝕎𝒾𝓈𝓅 𝕊𝓉𝒶𝓉𝓈`, bars Care, Happy, Hunger (Hunger is the Full
  meter) with the meter app emojis: one `_full` per whole 10% of the shown
  percent and one `_left` when its last digit is 5 to 9, else a space before
  `│` (65% is six full and a left; 90% nine full and a space; 0-4% nothing).
  The egg cards use the same frame (Warmth with the `full_` meter, Hatching and
  Emerging with the `happiness_` meter). The sick line reads
  `he has Monster Pox・{n} h left`. The waiting (Begin again) card is the frame
  with one line, `No Wisp right now. Waiting for staff to begin again.`, on the
  status card and in `/wisp status`. `render_status` takes the emoji lookup.
- The Vault is now one Components V2 message (`VaultLayout`, a `LayoutView`
  with no container): text displays with the snack select under the snacks,
  the badge select under the badges and the collection and gift selects under
  the gifts, up to 4,000 characters of text. Myra's snack and badge names and
  padding, prices in WC with the `wisp_coin_mini` emoji, the balance as
  `wisp coins: {coin} {n}`, the gamble line under Gifts. Purchase notes say WC
  (`♪ Bought Cheese for 6 WC.`, `Your WC are back.`) and the select
  descriptions too. Everything else (private, refusals, the two-step gift
  select, errors) works as before.
- Snack Pack, lunchbox and leaderboard in the frame. Empty sections read
  `none yet` (`nothing saved yet` for snacks). Each lunchbox song is a day and
  sharer line, then its link; each collection a progress line, then its gifts
  and givers while there is room.
- `/wisp lunchbox` is public: it posts in the channel where it was used,
  pinging nobody and with link previews suppressed. Used where Wisp never
  posts (the track drop, or a channel that cannot be placed) it posts in Wisp's
  House and tells the member privately; with no House it is shown only to
  them.
- `wisp.text.SEPARATOR` is Myra's plain divider
  `𝄡𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄚𝄂`. `fit()` and `richest()` measure with
  `text_length` (UTF-16), as the frames' music symbols count twice.
- `wisp_coin_mini` is a coin, not one of Wisp's faces: it is left out of his
  expressions and described as the Vault's coin in the AI prompt.
- CLAUDE.md and README describe the house style, the new divider and the
  public lunchbox.
- The new divider costs 18 more UTF-16 units than the old one, so the FAQ's
  quick rules are tightened to fit: the intro reads "One Wisp for the server:
  share music and he grows from egg to Rockstar.", and the Vault lines say WC
  for spending (`/wisp vault spends WC on snacks and gifts`, `Gifts cost 15
  WC`). 1,946 of 2,000 at today's numbers; the all-9999 guard fits again.
  (Run `!wisp faq` to refresh the live post.)
- Rhyme Duel summaries are measured by `text_length`, and the last-resort cut
  uses the new `wisp.text.clip`, which never splits a character.
- `/wisp lunchbox` acknowledges privately and posts the lunchbox as a message
  of its own in the channel (the private acknowledgement is then removed), so
  a failure is told only to the member and still reported in the channel.

## 2026-10-27 (begin again)

- No egg is laid on its own after an ending any more. A death, a cold egg and
  an old-age farewell are each announced as before (the ending post and
  picture, the Last Embers and goodbyes, the badge sweep, the Vault card), then
  Wisp's House asks `♪ Do you want to begin again?` with a persistent **Begin
  again** button (`wisp:begin`), pinging nobody.
- Only staff (`is_staff`: the app owner, Manage Server or a staff role) can
  press it; anyone else hears `♪ Only staff can start a new Wisp.` privately.
  A press lays the next egg under the guild lock exactly as the automatic path
  did (next version, coal egg halfway hatched after a full life, the new-egg
  post with its picture and Poke Wisp button), updates the status card and the
  House panel at once, disables the question's button and answers
  `♪ A new egg is on its way.` A press that finds a life that is not over (a
  second press, two staff at once, an old question) lays nothing and answers
  `♪ Wisp is already here.`, disabling that stale button too. A press also
  gives any Last Embers an unannounced farewell never gave. Failures are
  reported where it was pressed.
- While waiting, the status card says `♪ No Wisp right now. Waiting for staff
  to begin again.` with the picture of how he ended (no picture when that art
  is missing) and only the Begin again button, so a question that was never
  posted or was deleted can never strand the server; `/wisp status` says the
  same line. The life loop lays nothing for an ended life, also after a
  restart.
- `!wisp begin`, a staff command doing the same as the button: lays the next
  egg after an ending, or answers `♪ Wisp is already here.`
- While waiting, the life loop picks no favorite song and `!wisp punish` posts
  nothing in Wisp's voice (the staff answer notes it, as with no life).
- The quick rules now say "Neglected, he fades; staff start the next egg."
  (Run `!wisp faq` to refresh the live post.) `show_in_thread` gains
  `clear_image` to take a card's picture off.
- A server that has never had a Wisp still gets its first egg from the life
  loop, with no button.
- `!wisp eggs on|off` is gone, with its docs and its place in the staff command
  list. The `settings.lay_eggs` column stays in the live database but is no
  longer read, and the `Settings.lay_eggs` field is removed.

## 2026-10-26 (name ask tags the member)

- When Wisp asks a member what to call him, the post starts with their @tag
  and pings only them, so it isn't lost in a busy chat.

## 2026-10-26 (Myra's status menu, three meters and the childhood cold)

One feature, built in seven steps. Wisp's old single meter is now three, each
with its own job, and Myra's status menu shows them.

### The three meters

- **Full** is the food meter, renamed from "Care" because Care did not read as
  food. Same behaviour: tracks and snacks fill it, it drains daily, he is hangry
  when it is low and dies at 0. The snack confirmation, the Vault and Snack Pack
  dropdowns and the status card say "full +n" and "full" instead of "care". The
  database column keeps the name `care` and still holds Full, so nothing is
  renamed or migrated for it.
- **Happy** is how many different members chatted with him in the last 24 hours
  (full at 5). A member's first poke or mention of the UTC day records a new
  `chat` interaction and gives 1 Vault point (`CHAT_POINTS`); later pokes and
  mentions that day give nothing. Only members who can feed Wisp and are not
  banned earn it; everyone else can still talk to him. If the credit fails (a
  database error) it is reported in the channel and Wisp still replies. A chat
  counts toward Wisp learning a member's name, but not toward bond, growth,
  caretakers, the "fed by" line or the stage-up keepsake. Feeding and playing no
  longer raise Happy. It still drives Rockstar.
- **Care** is a new meter for rhyme duels and gifts, 0 to 100. It starts at 50
  when he hatches and drains 10 a day while he is alive (`CARE_*` in
  `wisp/rules.py`). Each Rhyme Duel that counts as play adds 10, and every gift
  bought adds 8, whether he keeps it, passes on it or already kept one today,
  since the points are spent either way. A refused gift adds nothing.
- Each Rhyme Duel that counts as play (the daily limit of 5, a scored rhyme and
  the right to feed) also pays 1 Vault point (`PLAY_POINTS`).
- Below 30 Care he is lonely. Hangry still wins when Full is low too. Lonely only
  changes how he talks: his AI voice is told he is lonely and grumpy (never
  blaming anyone), and pokes, chat fallbacks and Baby talk have lonely lines.
  Every other moment uses its happy lines when he is lonely. It never hurts him:
  no death, no growth penalty.
- The first time Care drops below 30 he posts once in the House (again after it
  climbs back to 30 and drops again), with a picture for his stage picked at
  random from `LONELY_PICTURES`: Baby `cry_baby.gif` or `grumpy_baby.png`,
  Child `grumpy.gif`, Teen and older `cry_teen.gif`. A missing picture means a
  text-only post. A lonely Wisp's track reaction in Mealtime shows `wisp_sad`.
- New repo counts for the card: `chatters_since`, `feeders_since`,
  `chatted_today` and `tracks_today`.

### The childhood cold

- Once per life Wisp catches a cold, like the chicken pox. When he is a living
  Baby, Child or Teen the life loop rolls when it is due: a random time 1 to 12
  days after he hatched (`COLD_EARLIEST`, `COLD_LATEST`). Adult needs 14 days, so
  every Wisp who grows up has had it. A due cold starts before the growth check
  on the same tick, so even after days offline he catches it before he can grow
  to Adult. Adults and older never catch one, and a living young Wisp from before
  this change gets his cold rolled on his next tick.
- The cold lasts 48 hours of credited time (`SICK_FOR`); frozen and offline time
  beyond the usual 15 minutes do not count, and a frozen Wisp never starts one.
  If he grows a stage while sick, the cold carries on.
- While sick his Full drains 1.5 times as fast (`SICK_DRAIN_MULTIPLIER`), but the
  drain never takes it below 1 (`SICK_FULL_FLOOR`), so he cannot die while sick.
  He can still be hangry and fading, and those posts still come. Normal rules
  come back when he is better.
- While sick each member's daily meal cap is 30 instead of 15
  (`SICK_EXTRA_MEAL_CAP`), room for about one extra song and one extra snack.
  `meal_grant` takes the cap and `daily_meal_cap(life)` gives it.
- He posts once in the House when he catches it (with `sick_baby.png`,
  `sick_child.png` or `sick_teen.png` from `ASSETS/moments/` for the stage he is
  in; text only if the file is missing) and once when he is better (with his
  stage picture). Both have their own canned lines. While sick the status card
  and the Poke Wisp panel show his sick picture, and his AI voice is sniffly and
  sneezy.

### The status card

- The card follows Myra's template (`DOCS/specs/status_menu_template.txt`) in her
  frame, kept exactly as she wrote it. It is still posted in the Status thread
  and by `/wisp status`, with the same picture and buttons.
- Living Wisp: `𝐃𝐀𝐘 **{day}**`, then the bars Full 🟦, Happy 🟪 and Care 🟥. A bar
  is one square per 10% (rounded half up, filled squares only, so 0% shows none)
  and then `│{percent}%`; the squares follow the shown percent. While he has his
  cold a line under the DAY line says `・he has a cold・{hours} h left` (hours
  rounded up).
- "Fed by {nn} people today" counts only members who fed him or gave a snack
  (FEED, SNACK, FREE_SNACK) since UTC midnight, "person" for one. Chats and games
  no longer count. A new line shows today's ViiBR and Suno tracks.
- The hints mention Wisp and the House channel (or say "in his House" when none
  is set) and point to `/wisp snackpack`. The life stage is in bold capitals,
  such as 𝐎𝐋𝐃 𝐅𝐎𝐆𝐄𝐘.
- Egg and hatching cards use the same frame without the DAY line: Warmth 🟧 and
  Hatching 🟨 for an egg, Emerging 🟨 while hatching, stage 𝐄𝐆𝐆 or 𝐇𝐀𝐓𝐂𝐇𝐈𝐍𝐆, and
  "Poke the egg".
- The card no longer shows the life's version number (her template has none).
- Bar label padding is one table, `LABEL_PADDING` in `wisp/card.py`, to tune from
  Myra's screenshot: Full 8, Happy 3, Care 6, Warmth 3, Hatching 1, Emerging 1
  spaces.

### The divider

- Myra's divider `❱❱━━━━━━━━━━━━━━━━━━━━━━━━━━❰❰` replaces the old
  `・♪ ────────・──────── ♪・` line in every Wisp post that uses it. The project
  rules now allow Unicode emoji in designed text (the status card and the
  divider); AI replies and canned lines stay emoji free.

### Words members read

- The quick rules post in the Wisp FAQ explains the three meters, the points for
  first pokes, chats and duels, and the cold with its bigger meal limit. It was
  already near Discord's 2,000 limit, so some wording is shorter: "takes his
  place" became "takes over", the Snack Pack and lunchbox pointers share a line
  under the Vault, the Old Fogey and farewell lines are one line, the talking
  section keeps what talking earns and who chimes in, and the bond tiers read
  "Familiar 50". It is counted with `text_length` and still fits at four-digit
  numbers.
- The README has a section on the three meters and the cold, the spec page
  `DOCS/wisp_tamagotchi.html` describes them (Full, Happy, Care, the cold, duel
  points and the new card), and `DOCS/BuildRulings.md` has the rulings.
- The FAQ pictures in `ASSETS/faq/` still show the old wording and need
  re-rendering; the sentences are listed in the task 7 report.

### Database

- Five new `lives` columns, all added to the live table at startup, nothing
  renamed or dropped: `fondness DOUBLE NOT NULL DEFAULT 50` (the Care meter),
  `lonely_warned BOOL NOT NULL DEFAULT 0`, `cold_due_at DATETIME NULL`,
  `cold_left DOUBLE NOT NULL DEFAULT 0` and `had_cold BOOL NOT NULL DEFAULT 0`.
  The old `care` column still holds Full. The `chat` interaction fits the
  existing `kind` column.

## 2026-10-25 (farewell art)

- When Wisp dies of old age, the farewell post shows his flame burning down
  until only a coal and his headphones are left. It plays once. The Last
  Ember posts after it keep the coal picture.

## 2026-10-25 (Old Fogey sigh)

- Removed again the same day: Myra is making a better one. The grew-old post
  uses the still Old Fogey picture until then.

## 2026-10-25 (Vault and Snack Pack frames)

- The Vault shop follows Myra's template: the balance above a ViiBR Vault
  frame with the `viibr_logo` emoji, and inside it each snack and badge as its
  emoji and price, then the gift collections. Names, care and bond stay in the
  dropdowns.
- The Snack Pack follows her template: a box with the member's mention and
  balance, then Snacks ("cheese :snack_cheese: x2"), Keepsakes and Badges
  ("Wisp v1's" and the item's emoji). An item whose emoji is missing shows
  its name.
- Message length is counted in UTF-16 units, so the frame's music symbols can
  never push a message past Discord's limit.

## 2026-10-25 (egg art)

- New egg picture for the status card, the Poke Wisp panel and new-egg posts.
- An egg born from the Last Ember's coal has its own glowing coal egg picture.
- An egg that goes cold is posted with a cold blue egg picture.

## 2026-10-24 (faster answers, the free snack in the Vault)

- The AI chain asks Groq first, then the Gemini fallback model, the Gemini
  chat model and OpenRouter. Each provider gets 8 seconds (was 12).
- The AI chain and the share-link resolver open no new HTTP session once
  closed, so a request still running at shutdown no longer leaves an
  unclosed session behind.
- The log has one line per AI answer (provider and time) and one per poke or
  mention (time from receiving it to posting). Keys and prompts are never
  logged.
- The Vault's Snack Box starts with the free Sine Wave and how to feed it;
  the buy select still lists only paid snacks.

## 2026-10-24 (staff review fixes)

- `!wisp staff add` refuses @everyone, and a stored @everyone row never makes
  anyone staff.
- Retired badges keep their real names in the Snack Pack ("ViiBR Roadie").
- Setup refuses a House that is also the track drop.
- When staff cannot be told apart because the database or Discord failed,
  nobody counts as staff and nothing is posted; the failure is logged.
- `!wisp eggs` takes on or off in any case.
- Bare `!wisp` is not talk to Wisp either.
- The Snack Box is ordered by price: Sine Wave, Cloud, Jelly and Juice Wave,
  Spicy Wave, Cheese, Pickles, Glitter Wave, ViiBR Wave.

## 2026-10-24 (panel picture)

- The Poke Wisp panel in Wisp's House shows his current picture, the same one
  as the status card. Setup attaches it to a new panel, or to an existing one
  without a picture. The life loop changes only the attachment, only when the
  picture changes (once more after a restart), and leaves a missing panel,
  missing art or an ended life alone. A refused picture uses the status
  card's fallback.

## 2026-10-24 (four badges)

- The Vault sells four badges: Pickle Diplomat (25 points, bond +5), Flame
  Keeper (100, +15), Team ViiBR (250, +25, replacing Team Wisp) and Bandmate
  (250, +25, Bandmate tier only). Egg Warmer and ViiBR Roadie are no longer
  sold.
- Startup moves stored `team_wisp` badge roles and purchases to
  `team_viibr`; repeating it changes nothing.
- Setup renames a badge role whose name is not its badge's ("Team Wisp"
  becomes "Team ViiBR"), and deletes the roles Wisp stored for badges no
  longer sold, then forgets them. A failure is posted where setup ran and
  the role stays stored for the next setup.
- A badge bought before it was retired stays in the Snack Pack under a name
  made from its key ("Egg Warmer"), and the sweep still takes its role back.
- Badge icons for the four badges are in `ASSETS/badges`.

## 2026-10-24 (staff command follow-ups)

- `/wispadmin setup` and `/wispadmin faq` are back as slash commands beside
  `!wisp setup` and `!wisp faq`, sharing their logic. The group needs Manage
  Server by default, answers privately, and turns away anyone who is not
  staff with "That command is for staff."
- Setup pins a Poke Wisp panel in Wisp's House ("♪ Poke Wisp", with the Poke
  Wisp button). Its id is kept in the new settings column
  `house_panel_message_id`, added to a live table at startup. A rerun leaves
  it alone, re-pins it or gives back its button, and posts a new one when it
  was deleted. A failure, such as a missing Pin Messages permission, is
  posted where setup ran.
- Wisp's House conversation ignores `!wisp` commands: they are not answered,
  not chimed in on and not kept as chat context.

## 2026-10-24 (staff commands move to !wisp)

- Staff commands are typed text commands now: `!wisp setup`, `roles`,
  `food`, `freeze`, `unfreeze`, `eggs`, `faq`, `punish`, `unban`, `strip`
  and `resetname`, with the same behaviour as before. The `/wispadmin` slash
  group is gone; members' `/wisp` commands are unchanged.
- Staff are the app owner, Manage Server holders and members with a staff
  role. `!wisp staff add|remove|list` manages the staff roles, kept in the new
  `staff_roles` table (created at startup when missing). Anyone else is
  ignored without a reply.
- Answers are public, in the channel the command was used in, or in Wisp's
  House from the track drop. Wrong arguments get a usage line, an unknown
  command gets the list of commands, and a failure is posted where the
  command was used. `!wisp punish` now posts one public answer, the log line
  with the reason, instead of a log line plus a private reply.
- Bare `!wisp` gets no reply; it is kept for the help menu. Mentioning Wisp
  never runs a command.
- Bot messages that named `/wispadmin` now name the `!wisp` command.

## 2026-10-24 (eggs switch)

- `/wispadmin eggs on|off`. Off: when a life ends no egg is laid, by the
  ending or by the life loop's self-heal, and the House says once "No new egg
  for now". The ending is still announced, the Last Embers still given and
  the badge roles still taken back. On: the next tick lays the egg, a coal egg
  after a full life. A living Wisp is unaffected.
- New settings column `lay_eggs` (default on), added to a live table at
  startup.

## 2026-10-24 (poke and badge review fixes)

- A badge bought again in a new life keeps its role: the purchase marks the
  member's older purchases of it as done, and a sweep that takes a role off
  while the same badge is bought for the current life gives it straight back.
- A purchase found already recorded is refunded and refused, and a role that
  fails to be given for a network reason (not only a Discord error) is
  refunded too.
- Setup stops at the first missing permission and reports it once; a new
  badge role that cannot be stored is deleted again and reported.
- The badge sweep stops for the tick at a missing permission.
- Wisp's own emojis: only names Discord allows (2 to 32 ASCII letters,
  digits and underscores) are read, a server emote's name is never read out
  as words ("a ViiBR emote of Wisp"), and `badge_<key>` emojis read as "your
  <Badge> badge".

## 2026-10-24 (badges, take two)

- Badge roles come off through a sweep on every life loop tick: each
  purchase of an ended life whose role is still on is taken back and marked
  (new `badges.removed_at` column and an index on it, added to a live table
  at startup). A restart between the new egg and the removal heals on the
  next tick, a marked purchase is never handled again, and a failure is
  retried each tick and reported once per streak.
- Each badge has its own House phrase: "joined Team Wisp", "is now an Egg
  Warmer", "is now one of Wisp's Bandmates" and so on. The member's note
  reads "You got the Team Wisp badge".

## 2026-10-24 (badges)

- The ViiBR Vault sells six badges, vanity roles worn for the current Wisp:
  Egg Warmer and Pickle Diplomat (25 points, bond +5), Flame Keeper and ViiBR
  Roadie (100, +15), Team Wisp and Bandmate (250, +25; Bandmate only at the
  Bandmate bond tier). Badge bond is outside the daily casual cap. The Vault
  lists them with "owned" or "Bandmates only", and a "Get a badge" select
  offers the ones the member can get now.
- A purchase is made under the guild lock; the role is given after it. If
  Discord will not give the role, the points, the purchase and the bond are
  all undone, the failure is posted where it happened and the member is told.
- The House announces "{name} is now a {badge}" with a new Badge Bought line.
- When a life ends, its buyers lose those roles (members are fetched by id; a
  member who left is skipped). The next Wisp sells every badge again.
- The Snack Pack has a Badges section: every badge ever bought, as "Wisp vN's
  {badge}", with its `badge_<key>` emoji when uploaded.
- `/wispadmin setup` creates the missing badge roles (by stored id, so a
  deleted one is recreated), with `ASSETS/badges/<key>.png` as the icon when
  it exists and the server has role icons, and adds icons later. Wisp needs
  Manage Roles.
- New tables: `badge_roles` and `badges`, created at startup.

## 2026-10-24 (Poke Wisp)

- A Poke Wisp button on the status card (next to Feed Wisp) and on the
  House's new-egg and coal-egg posts. A poke posts "{name} poked Wisp" (or
  "poked the egg") and his AI reaction in the House, in his stage's voice,
  and answers the member privately. Each poke rolls a flavor: tickled most
  often, sometimes startled or curious, woken up after 2 quiet hours or
  between 3 and 7 AM UTC, annoyed by 3 pokes in 2 minutes or when hangry.
  The egg has its own sleepy, grumpy and ticklish versions. A failed AI
  falls back to an egg poke line or a new Poked line. Banned members, no
  life and the cooldown are refused privately. A poke earns nothing.
- Mentions and pokes share one talk cooldown per member, kept on the bot
  with the House's recent chat.
- The status card says "poke him, or mention @Wisp in his House" ("poke the
  egg" for the egg).
- Wisp recognises his own emojis: a message to him that uses one of his app
  emojis or an emote with "wisp" in its name tells the AI what it shows (his
  happy face, a gift, a keepsake, a snack).
- The Baby is no longer offered the "no u" GIF.

## 2026-10-24 (the egg and baby talk, and dropped connections)

- The egg and the baby answer through the AI, so pokes stop repeating. The
  egg (hatching too) replies with one short line of wordless third-person
  action, reacting to how fed and warm it is, whether it is a coal egg, how
  far its hatching is, and whether the poker fed it or fed it most. Now and
  then it posts its own `wisp_egg` emoji, which no hatched stage is offered.
  The baby answers with baby noises and single words, fussy when hangry,
  never swearing; he keeps the pickle tag and may use one expression. When
  the AI fails, the old egg and baby lines are the fallback. The egg's
  replies save nothing; the baby's save a pickle stance.
- Database reads retry once on another connection when the connection was
  lost (MySQL errors 2006 and 2013); the lost connection is closed so the pool
  never hands it out again. Writes are never retried, since a lost write may
  already have been applied. Pooled connections are recycled after 4 idle
  minutes instead of an hour, since the network drops idle ones.

## 2026-10-24 (new toys)

- Three new gift collections in the ViiBR Vault: Tamagotchis (Hawaikotchi,
  Mimitchi, Tamagotchi Nano, Welcotchi), Tetris (Tetris Handheld and the I,
  L, T, S and Z Blocks; six gifts) and Jewels (Amethyst, Crystal, Rainbow
  Jewel, Ruby). Their gifts are named as they are, without a collection
  noun, and "an L Block" and "an S Block" read right.
- Giving a gift is two steps: pick a collection (its first gift's emoji and
  how many are left), then one of its gifts. Neither select can pass
  Discord's 25 options. A collection someone gave from a moment ago is
  refused with the reason.
- Gift and keepsake art is looked up as an animated GIF first, then a PNG.
- The Old Fogey keepsake is the Time Piece (it was the Reading Glasses,
  which nobody had earned yet).
- The Vault's Gifts and the lunchbox's Collections fit one message in the
  worst case: a collection shows each gift while there is room, else only
  how many are left or its progress.

## 2026-10-24 (milestone keepsakes)

- Wisp's big moments give a keepsake to the member who was there: the
  Eggshell when the egg starts hatching (to the member whose feed filled it),
  the First Spark, Teen Spark, Adult Spark and Guitar Pick when he grows into
  a Child, Teen, Adult and Rockstar, and the Reading Glasses when he grows
  old (to the member of the latest interaction with that life). Nobody gets
  one when nobody was there or the member is banned; each is given once.
- Wisp's House announces it with a new line, and attaches
  `ASSETS/keepsakes/<kind>.png` when it exists. The Last Ember post attaches
  `ASSETS/keepsakes/last_ember.png` the same way.
- The Snack Pack shows each keepsake's app emoji `keepsake_<kind>` when it is
  uploaded.
- The rules post says "Be there as he grows to win a keepsake".
- Share links: a redirect with an unparseable address names no song instead
  of raising, and link patterns match ASCII only, so Unicode case folding
  cannot pass a non-ASCII URL for a link.
- New keepsake kinds; no new columns.

## 2026-10-24 (viibrmusic.com share links)

- Fix: viibrmusic.com share links (`https://viibrmusic.com/s/<code>`, the
  links members actually post) feed Wisp. Before, only
  `viibrmusic.com/songs/<id>` links counted, so ViiBR tracks were ignored.
- `wisp/links.py` recognises a share link as a `ShareLink`; the feeding cog
  asks viibrmusic.com which song it names (one request, redirects read, not
  followed, one www hop allowed, `User-Agent: WispBot/1.0`), outside the
  guild lock. The song's key is `viibr:<id>`, so a share link and the song's
  own link feed him only once. Mealtime shows the link as posted.
- A share link for no song (404, or a redirect that is not a song page) is
  ignored. A timeout or network error skips the feed and is posted in Wisp's
  House.
- New rule `VIIBR_RESOLVE_TIMEOUT` (5 seconds).

## 2026-10-23 (the Studio's look)

- The Studio threads have Myra's names: `☀️ | Status`, `🧡 | Mealtime`,
  `⚡｜Jam Space`, `🔒| The ViiBR Vault` and `📙｜Wisp FAQ` (was How Wisp
  Works). Setup renames a thread whose name differs. Wisp's messages use the
  plain titles, without emoji.
- Each Studio thread's first post carries its thumbnail picture
  (`ASSETS/thumbs/`, `ASSETS/vault.png`); setup adds one to a first post that
  has no attachment.
- The status card shows Wisp's current picture: the egg (or the coal egg),
  then his stage. It is uploaded only when it changes, once more after a
  restart, and missing art leaves the picture as it is. The House's new egg
  post carries the egg picture too.
- The Wisp FAQ thread is built from pictures: a table of contents with jump
  links, one picture per section (`ASSETS/faq/`), then the quick rules post
  with the current numbers, which `/wispadmin food` keeps editing. An existing
  How Wisp Works thread is renamed and filled.
- `/wispadmin faq` ("Rebuild the Wisp FAQ thread.") deletes Wisp's own FAQ
  posts and posts them fresh.
- The rules post is headed "Quick rules (current numbers)".
- New column `settings.faq_message_ids` (TEXT, a JSON list of message ids).

## 2026-10-23 (gifts)

- Gifts: the ViiBR Vault sells four collections of four gifts (Lunchbox
  Liners, Alien Dolls, Books, Affirmation Cards) for 15 points each. Buying a
  gift is giving it to Wisp, from a second select under the snack select.
- It is a gamble: he keeps a gift one time in three. A kept gift leaves the
  Vault for this life and gives its giver 5 bond (outside the daily cap) and
  him a bond moment's growth; finishing a collection gives 25 bond more. A
  passed gift goes back to the Vault. Points are spent either way.
- Each collection can be given from once a UTC day, server-wide, and he keeps
  at most one gift a day: later gifts that day go back to the Vault.
- Collections are per life: every new Wisp starts empty and the Vault is
  fully restocked.
- Wisp's House hears every gift, with its picture when he keeps it, and
  `/wisp lunchbox` shows this life's collections.
- The How Wisp Works post explains gifts. To stay under 2,000 characters a
  few of its lines are shorter, and the three ban lines are now one.
- New table `gift_attempts`; interactions gain the kind `gift`.

## 2026-10-23 (Wisp's lunchbox)

- `/wisp lunchbox` ("See the things Wisp keeps in his lunchbox.") shows, only to
  the member who asks, what Wisp keeps: his favorite songs, his favorite snack
  and his favorite emoji. Anyone may look; it is read-only.
- Favorite songs: the first life-loop tick after UTC midnight picks one of the
  previous day's viibrmusic.com feeds at random and posts it in Mealtime with a
  new line from Wisp. A day without viibrmusic.com tracks has no pick, and a
  day is never picked twice. Picks belong to the guild and carry across lives.
  The lunchbox shows the newest ten.
- Favorite snack: every Wisp picks a random favorite snack when he hatches.
  Feeding it to him gets its own delighted line instead of the usual one.
- Favorite emoji: the expression he has used most in his AI replies and
  chime-ins in the guild, skipping any that is no longer uploaded.
- The How Wisp Works post and the README list Wisp's lunchbox.
- New tables `favorites` and `expression_uses`; new column
  `lives.favorite_snack`.

## 2026-10-23 (Snack Packs)

- Members' own box is now the Snack Pack. `/wisp lunchbox` is renamed
  `/wisp snackpack` ("See your snacks and keepsakes."), and the Vault card's
  button is "Open my Snack Pack" (custom id `wisp:snackpack`). It still holds
  saved snacks and keepsakes such as a Last Ember.
- The Vault intro, the How Wisp Works post and this README say Snack Pack; a
  Last Ember goes in its sharer's Snack Pack.
- The cog is `cogs/snacks.py` (the Snack Box shop, the Snack Pack and the Feed
  button). The lunchbox name now belongs to Wisp's own lunchbox.

## 2026-10-23 (errors in place)

- There is no errors channel any more. Every error is posted as plain text in
  the channel or thread where it happened: a command, button or form failure
  in the channel it was used in (the Status thread for the Feed button), a
  Mealtime forward in Mealtime, a Studio card or pin in its thread, a Rhyme
  Duel in its thread, a conversation reply in Wisp's House.
- Wisp never posts in the track drop. Errors there, and errors with no channel
  (the life loop, startup, the next egg, recreated Studio threads, the AI
  voice), go to Wisp's House, the life loop and startup ones to every guild's
  House. If the post fails where it happened, the House is tried once; then
  the error is only logged.
- The member is told "That didn't work. The error is posted in this channel."
- `/wispadmin setup` no longer takes an `errors` channel, and the
  `error_channel_id` setting is gone. A live table that still has the column
  only logs a schema warning.
- `/wispadmin punish` posts its log line, reason included, publicly in the
  channel the command was run in. If that post fails, the reply says so.

## 2026-10-23 (plan 2 final fixes)

- Staff see every error: a life loop failure is posted to every guild's errors
  channel, and a cog that fails to load at startup is posted once the bot is
  ready.
- Startup refuses a stale database: a table missing a column stops the bot
  with a SchemaError naming it. Extra columns are only logged.
- Guild settings and qualifying roles are cached in the bot, so most messages
  no longer wait on the database, and the errors channel still works during a
  database outage. The track drop only reads settings for messages with a
  track link.
- Only qualifying members (Active Lounger or higher who have opened
  `/wisp board`) can use the Feed Wisp button or eat snacks with him. Rhyme
  Duels stay open to everyone, but only qualifying members get play credit.
- `/wispadmin food viibr suno` sets each track's meal points per guild and
  updates the How Wisp Works post. Until set, the values in `wisp/rules.py`
  apply.
- At the daily meal limit a snack, the free Sine Wave included, is refused and
  kept for tomorrow.
- Wisp only meets members once he has hatched.
- Mentioning Wisp's role counts as talking to him.
- When every AI provider is cooling down, Wisp falls back to his canned lines
  at once instead of waiting on each provider.
- No send can ping anyone, and more emoji are filtered from AI replies.
- Database connections are recycled every hour.
- The README permission list now matches what Wisp uses, and the Vault intro no
  longer mentions song listens, which are not built yet.

## 2026-10-22 (plan 2)

- The ViiBR Vault: the Studio's Lunchbox and Billboard threads are replaced by
  one thread, The ViiBR Vault. Its pinned first post is the leaderboard with
  the Shop the Vault and Open my lunchbox buttons, and carries
  `ASSETS/vault.png` when it exists. Version lines now show the stage, "from
  coal" eggs and full lives.
- Old age and the farewell: Wisp's House hears him grow into an Old Fogey and,
  after a full life, a celebrated farewell as he shrivels into coal. The top
  three sharers of that life who are not banned each get its Last Ember with a
  goodbye from him, then the coal cracks into the next egg, already halfway
  hatched. A neglect death still leaves no gifts and a fresh egg.
- Vault and lunchbox: `/wisp vault` is the shop where points buy snacks.
  `/wisp lunchbox` is the member's own box of saved snacks and keepsakes such as
  Last Embers, with a Shop the Vault button. Pickles now get a reaction that
  depends on the member's pickle stance.
- Talking: members mention or reply to Wisp in Wisp's House. The egg wobbles,
  the baby babbles and from Child on he talks with AI. From Adult on he
  sometimes chimes in on his own and remembers what people tell him. Talking
  earns no bond and no points.
- The How Wisp Works post now explains the Vault, lunchboxes, his whole life
  (Old Fogey, the farewell, the coal egg and Last Embers) and talking to him.
- Wisp's "not enough points" lines point at the Vault instead of the lunchbox.
- Art: `stages/old_fogey.png`, `stages/coal_egg.png`, `events/farewell.png`,
  `eating/eat_pickles_love.gif`, `eating/eat_pickles_hate.gif` and `vault.png`
  are read by the bot when they exist. `DOCS/ArtToMake.md` lists what is left.

## 2026-10-22

Wisp v1 core.

- Feeding: a Suno or ViiBR link posted in the track channel feeds Wisp. One feed
  per message, each link counts once ever, and edits are ignored. Tracks from a
  forum or its threads count.
- Life cycle: care drains over time and is capped per tick so downtime never
  punishes him. He hatches from an egg, grows through baby, child, teen, adult
  and rockstar, and can die of neglect, after which a new egg is laid. Past
  versions are kept.
- Status card: a pinned card in Wisp's Studio that is reposted if staff delete it,
  plus announcements in Wisp's House for hatching, growth and death.
- Billboard: `/wisp board` shows the leaderboard and Wisp's past versions.
- Meeting and names: Wisp meets members as they take part and learns their
  names. Bond grows with daily activity, and happiness reflects recent care.
- Lunchbox: members earn coins, buy snacks and feed them to Wisp with a button,
  with one free snack a day. Most snacks have an eating GIF; the rest post text
  until their art lands.
- Rhyme Duel: `/wisp play rhyme` trades perfect and slant rhymes with Wisp.
- Staff tools: `/wispadmin setup`, role management, freeze and unfreeze, punish,
  unban, strip points and reset name. Errors are reported to staff as plain text.

Not yet: AI voice, compliments and "no u", more games, badges.
