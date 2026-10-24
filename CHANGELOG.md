# Changelog

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
