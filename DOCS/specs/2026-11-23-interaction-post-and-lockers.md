# The Interaction post, and rooms become storage lockers

Myra, 2026-11-23. Marked **my call** where Claude chose.

## Rooms are storage lockers (Myra)

- Each member's private thread (today `♪ {name}'s room`, `cogs/rooms.py`
  `room_name`) is named `{name}'s Storage Locker`, e.g. `Cat's Storage Locker`,
  cut to `ROOM_NAME_MAX`. (Myra offered "Room" too; Storage Locker chosen because
  her Interaction text calls it "your personal storage locker".)
- Existing rooms are renamed to the new name the next time Wisp opens them
  (`open_room` renames a stored room whose name differs from `room_name(...)`;
  one rename call, a failure reported like other room failures and never
  blocking the game) (my call).
- Member-facing text says "storage locker" where it says "room" today: the
  welcome post, refusals ("Open /wisp board first so Wisp can give you a
  storage locker."), the Craving/duel pointers, README, FAQ text, CHANGELOG.
  Code names (`open_room`, `room_thread_id`, ...) stay as they are (my call:
  no storage rename).

## Status is only status (Myra)

- The live status card in the Studio's Status post keeps its picture and text
  but its six buttons (Feed Wisp, Poke Wisp, Vault, Snack Pack, Play,
  Lunchbox, `cogs/status_card.py` `status_buttons`) are replaced by ONE link
  button, **Interaction**, that jumps to the Interaction post. Before the
  Interaction post exists, the card shows no button (my call).
- The card's line "feed Wisp, shop the Vault and play with the buttons below!"
  becomes "feed Wisp, shop the Vault and play: tap Interaction below!" (my
  call).

## The Interaction post (Myra's text)

- A new Studio forum post, made by setup like the others (`STUDIO_THREADS` in
  `cogs/studio.py`): settings attr `interaction_thread_id`, title
  `🕹️ | Interaction` (my call on the emoji; Myra can rename it in Discord),
  locked so only Wisp posts there (my call), no image.
- Its body is one Components V2 message: for each line below, the text, then
  that button on its own row. Text exactly as Myra wrote it, with her typos
  fixed (my call): "WIsp's" → "Wisp's".

```
Feed Wisp a treat other than a music track!
[Feed WiSP]            -> FeedButton (same custom id as today)

Poke Wisp to earn engagement points and Wisp Coins!
[Poke]                 -> PokeButton

Visit the ViiBR Vault to buy presents and vanity roles!
[ViiBR Vault]          -> link to the ViiBR Vault post when there is one,
                          else ShopButton (as the status card does today)

Check your Snack Pack items here or check your personal storage locker
[Snack Pack]           -> SnackPackButton

Play games with Wisp!
[Games]                -> PlayButton (the games menu)

Check out Wisp's Lunchbox with his favorite songs, toys and more!
[Lunchbox]             -> LunchboxButton
```

- The buttons keep their existing persistent custom ids, so presses work after
  restarts and old status cards in the wild keep working; only labels change
  where Myra renamed them (`Feed WiSP`, `Poke`, `ViiBR Vault`, `Games`).
- The post is drawn by setup and redrawn (edited in place) whenever setup runs
  or the ViiBR Vault link changes; a deleted post is made again on the next
  setup (follow the Studio's existing pattern).
- Existing servers: staff run `/wispadmin setup` once after deploy to create
  the post (the same as when the Vault post was added). Until then the status
  card shows no button.
- Storage (additive): `settings.interaction_thread_id BIGINT NULL` and, if
  the pattern needs it, `settings.interaction_message_id BIGINT NULL`.
