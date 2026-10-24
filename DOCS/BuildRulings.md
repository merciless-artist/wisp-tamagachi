# Build rulings

Decisions made during the build where the spec or plan left a choice open. Each line is the decision, why, and what it costs if wrong. Ask to change any of them.

## Plan 1 (core game)

- R1 Stage enum defined in wisp/rules.py, life.py imports it — avoids an import cycle — cost if wrong: one import move.
- R2 add lives.stage_started_at (set on hatch + each stage-up) — spec needs caretakers per stage — cost: one column.
- R3 rhyme section of the Billboard is added in Task 15, not 11 — column doesn't exist before T15 — cost: none.
- R4 Task 15 adds RHYME_START / RHYME_WISP_STUCK / RHYME_PLAYER_STUCK lines — duel needs voice lines — cost: none.
- R5 post_events lives in cogs/announce.py helper module — keeps cogs independent — cost: none.
- R6 Task 11 wires maybe_meet into feeding — function doesn't exist in T9 — cost: none.
- R7 Task 12 makes status repost carry the Feed view — view class doesn't exist in T10 — cost: none.
- R8 Task 1 skips `git init` (controller already did it on branch wisp-core) — cost: none.
- Suno /s/ shortcodes keep their case in the track key (only UUIDs lowercased) — Suno share codes are case-sensitive, lowercasing could merge two different tracks into one dedupe key — cost if wrong: a re-posted link in different case counts twice (negligible).
- add .gitattributes eol=lf + renormalize in Task 4 — tools on Windows wrote CRLF, causing full-file diffs — cost if wrong: one extra commit
- newborn card shows "day 0" (age_days) — matches the stage rules' day counting (Child = day 3+) — cost if wrong: cosmetic, change display to age+1.
- STAGE_UP lines that produce ungrammatical text with {stage} ("I'm teen now") are output bugs, not polish — promoted to the fix round — cost if wrong: a few extra edits
- lines aimed at a specific member ("you're broke", "everyone else, take notes", "then hush") or ranking content as lesser food ("I'd even eat the skits", "a demo. a voice memo. a hum") breach the spec's never-at-a-person / never-about-music rule — promoted to the fix round — cost: a few extra edits
- repository methods that depend on "today"/"since" take an explicit `now: datetime` (or `at`) argument and never use SQL NOW()/CURDATE() — makes UTC-midnight behavior testable and keeps the clock in one place — cost if wrong: signature churn in cogs (none written yet)
- PlayerRepo.spend(cost=0) returns True without touching the row — Database.execute returns changed rows, so a 0-cost UPDATE would report failure — cost: none
- free daily Sine Wave is recorded as InteractionKind.FREE_SNACK ("free") in interactions, no schema change; it counts as an interaction everywhere (happiness, caretakers, distinct days, casual bond, meal cap) — Task 12 must record it with that kind — cost if wrong: one enum value
- record_feed must only treat MySQL error 1062 (duplicate key) as "already fed"; other IntegrityErrors re-raise — a swallowed NOT NULL error would hide real bugs — promoted to fix round — cost: one line
- DMs are ignored at the gateway — intents.dm_messages/dm_reactions/dm_typing = False — so no listener ever sees a DM; listeners still guard `message.guild` defensively only where types require it — cost if wrong: none
- EXTENSIONS starts empty in Task 7; each later cog task appends its module — cost: none
- ActivityRepo attribute on WispBot is `bot.activity_log` (discord.Client.activity is the presence property) — all later tasks use activity_log — cost: none
- tree on_error treats app_commands.CheckFailure (incl. MissingPermissions) as a user-facing refusal — ephemeral "That command is for staff." — and does NOT report it to the error channel — permission refusals aren't errors and would spam staff — promoted into this fix round so Task 8's /wispadmin relies on it — cost: none
- BotMissingPermissions is a bot fault, not a user refusal — tree on_error must report it to staff (user sees the generic apology); other CheckFailures stay silent refusals — carried into Task 8 (small app.py change + test) — cost: none
- forum starter messages are the Status and Billboard cards; Studio threads use 7-day auto-archive and are unarchived on access via studio_thread(bot, guild_id, attr), which recreates missing ones — forum posts auto-archive and deleted threads must self-heal (Review Focus 5) — cost: none
- Mealtime/House posts never ping — every send uses AllowedMentions.none() (mentions render as names) — feeding happens constantly; pings would spam members — cost: none
- with no qualifying roles configured, nobody can feed (fails closed) — the spec gates feeding on level roles — cost: staff must run /wispadmin roles add before launch
- a feed arriving when no life exists yet (before the loop lays egg v1) is ignored silently and its track key is NOT recorded — cost: none
- {name} in lines = the player's chosen name, else the member's display name
- unexpected exceptions in event listeners reach staff through WispBot.on_error (discord.py's listener error hook) -> report_error — the third allowed broad handler — carried into Task 10 as a small app.py change — cost: none
- feeding writes stay non-transactional (autocommit) for v1 — a DB failure between record_feed and lives.save can burn a track key / give points without care; rare and bounded to one track — cost if wrong: a member loses one feed; revisit with a transaction helper if it ever shows up in the error channel
- post_events skips DIED/EGG_COLD lines when the current life is not over (stale ending) — prevents announcing a death with the new egg's version — carried into Task 10 — cost: none
- QUIET_AFTER = 9h lives in rules.py; quiet line once per stretch, tracked in memory per guild, not while frozen — cost: a restart may repeat one quiet line
- a life already over at tick start must self-heal — the loop lays the next egg and posts NEW_EGG — otherwise a crash between saving DEAD and laying the egg freezes the game forever — will be a fix-round item regardless of review — cost: none
- Discord can't run a command group by itself, so the status card is `/wisp status` (not bare `/wisp`) — cost: none
- both command groups live in a shared module cogs/groups.py (`wisp` for members, `wispadmin` for staff, with the guild-only/permission settings); cogs attach subcommands to them, app.py adds the groups to the tree once after loading extensions; Task 11 moves studio's /wispadmin group there — lets Lunchbox, Rhyme Duel and Discipline add subcommands without cross-cog hacks — cost: one refactor of studio.py
- one shared show_in_thread helper (announce.py) for the status card and Billboard; life loop refreshes the Billboard each tick; MEET name button is a persistent DynamicItem keyed by user id — cost: none
- the name button/modal refuses when the player already has a name or is banned; a staff resetname (Task 14) clears the name, which lets the member choose once more — matches "staff can reset anyone's name"; repeat offenders get banned — cost: none
- maybe_meet gets a fast path (read player outside the lock, return if already met, re-check inside) — it runs on every feed against a remote DB — promoted into the fix round — cost: none
- duplicated apology constant (_FAILED vs app._USER_ERROR) moves to wisp/text.py — owner's no-redundancy rule — promoted — cost: none
- the Feed Wisp button is a persistent DynamicItem with a fixed custom_id attached to the status card; show_in_thread gains an optional `view` so the life loop's edit/repost of the status card always carries it — cost: none
- pickles with unknown stance → PICKLE_HEDGE line, no eating GIF (love/hate GIFs need the stance, which arrives with AI in plan 3) — cost: none
- every DynamicItem (Feed button AND Task 11's name button) catches its expected failure types inside interaction_check/callback and reports via report_error — discord.py only logs dynamic-item errors — cost: none
- "no u" sends ASSETS/no_u.gif when present, else the verified imgur link https://i.imgur.com/G0SZAsT.gif (spec) — cost: none
- the same fix round also closes the cooldown race (re-check after the await) and stops a DB error from consuming the cooldown — same few lines — cost: none
- compliment detection is done by Wisp's AI prompt (plan 3), not a keyword matcher — fix round stopped, c7e8c5a reverted (uncommitted partial fix discarded) — COMPLIMENT_COOLDOWN and COMPLIMENT_HANGRY lines stay for plan 3 — cost: no "no u" until the AI voice ships
- punish's read+write of the offense count runs under bot.guild_lock (only the get/set, not the Discord posts), and feeding re-checks the ban inside its own lock — together a ban can't be raced by an in-flight feed and two punishes can't collapse into one — promoted into the fix round — cost: none
- Myra's eat_pickle video (suspicious → eats → smug) is the PICKLE_HEDGE GIF (ASSETS/eating/eat_pickles.gif); the lunchbox must attach it for pickles (Task 12 skipped pickle GIFs) — fix in the final wave — cost: none
- Rhyme Duel's common_words.txt is generated once with the `wordfreq` package installed as a dev-only tool (top English words ∩ CMU dictionary, profanity/slur blocklist applied), committed as data; `wordfreq` is not a runtime dependency — cost: none
- Wisp opens each duel with a word that has at least 8 perfect rhymes in common_words, so the game can't start on a dead end — cost: none
- ASSETS/lunchbox.png (Myra's art, Wisp + every snack) is attached to The Lunchbox forum post when ensure_studio creates it — becomes the forum thumbnail — final wave — cost: none
- a duel only counts as play (PLAY interaction, bond, growth) when the player scored at least one rhyme, and at most PLAYS_PER_DAY = 5 credited duels per member per UTC day (new constant in rules.py); best score is always recorded — matches the spec's "a few times a day" — cost: none
- homophones (identical pronunciation, e.g. right/write) are not rhymes — same-sound words would make the game trivial — promoted — cost: none
- a failed thread archive/lock no longer skips refresh_billboard and maybe_meet (run those first, report the edit failure) — promoted — cost: none
- Task 16 is split — the implementer does the quality gate + README/CHANGELOG/CLAUDE.md + committing Myra's tools/assets; Myra's line/rules review and the live VIIBR smoke test happen with her after the final review; nothing is pushed without asking her — cost: none
- CLAUDE.md "plain section headers, no emoji/decorative borders" stands — Myra explicitly ruled plain headers for Wisp/VIIBR code (all caps, 2026-10-18), overriding her global pretty-header rule — reviewer finding rejected — cost: none
- tools/key_green.py format-only change committed in 1b7540d is accepted (black formatting, no behavior) — cost: none
- commit trailer "Claude Opus 5.5" is the attribution the session reminders specify — reviewer finding rejected — cost: none
- events/hatched.png already exists (controller copied it) so no doc row needed; "rockwisp.gif can stand in" note must say "export a still PNG" and the pickle hedge GIF needs the lunchbox code change — both go to the final fix wave — cost: none

## Plan 2 and the final review

- R1 Prompt lives in a tiny dependency-free module ai/prompt.py (re-exported by ai/chain.py) so wisp/voice.py stays free of aiohttp — keeps the pure layer pure — cost if wrong: one import path.
- schema changes edit _DEFINITIONS in place; live wisp_ tables verified empty (0 rows, 7 tables) 2026-10-22; controller re-checks and drops them before the first live run — cost: one ALTER per column. Superseded 2026-10-23: the live tables now hold real data (Myra's setup), so every new column is also listed in _ADDED_COLUMNS and startup adds it; it stays in _DEFINITIONS for fresh databases — cost: one line per column.
- "half warm" coal egg = egg starts with COAL_EGG_FOOD = EGG_FOOD_NEEDED // 2 — a fresh egg already shows 100% warmth, so a hatching head start is the only "warmer" reading — cost: one constant.
- Old Fogey only from Adult/Rockstar at day 45; farewell only for an Old Fogey at day 60; neglect checked first; peak_stage unchanged by growing old — late bloomers never age early — cost: tick-order tweak.
- Last Ember goes to the top LAST_EMBER_GIFTS=3 "This life" sharers (top_this_life), skipping members banned at that moment — cost: one filter.
- Wisp talks only in the House channel itself (not threads), to mentions and replies; Egg/Hatching canned wobble, Baby canned baby talk, Child+ AI; Adult+ chime in; talking earns no bond/happiness — cost: gating tweaks.
- memory notes + pickle stance arrive as trailing AI tags stripped from the reply; notes kept/used from Adult on; stance at any AI stage — one AI call per reply — cost: parser tweak.
- when every AI provider fails, Wisp answers with a canned CHAT_FALLBACK line AND staff get one plain error per failure streak — spec says he never breaks and errors are never hidden — cost: none.
- /wisp board still activates; Vault buttons do not — cost: none.
- ASSETS/lunchbox.png -> ASSETS/vault.png, attached to the Vault post on creation (forum thumbnail) — cost: rename.
- gift choice = Last Ember keepsake + personal goodbye (spec v24); Myra said "start building" without picking otherwise — cost: swap the gift kind later.
- /wisp board's leaderboard reply carries vault_view(); say_privately gains an optional view — makes the shared intro true and lets members shop from the board — cost: none
- next_life takes an explicit `now` (signature next_life(bot, guild_id, now)) — keeps the clock in one place, matching the plan-1 explicit-now ruling — cost: none (carry to Task 8)
- a banned top-three sharer is skipped and the fourth does not move up — the plan says the top LAST_EMBER_GIFTS "who is not banned"; the gift honors that life's actual podium — cost if wrong: one query change
- the chain skips a provider for AI_PROVIDER_COOLDOWN = 5 min after it fails, and AI_TIMEOUT drops to 12 s — an overloaded primary would otherwise add 20 s to every reply; 3.6 answers in ~1-2 s — cost if wrong: one constant each (carried into Task 6's fix round)
- 401/403 ProviderError reason carries only "HTTP {status}", no body — providers may echo a masked key in auth errors and reasons reach staff; global rule "never print a key" — promoted from review minor — cost: less detail on auth failures
- chime-in prompts carry no pickle/note tags — nobody is being answered and Task 8 saves nothing from a chime-in — cost: none
- parse_reply runs strip_emoji BEFORE removing mass/role mentions (overrides plan step order 4→5) — removing emoji afterwards can glue a ping back together — cost: none
- hangry layer carries the spec's "compliments aren't food" attitude (spec Moment table) while the no-u GIF stays available in every mood with no hedge words (Myra's ruling) — confirmed ⚠️ gap — cost: prompt wording
- Teen layer recognises regulars by name/bond instead of "remembers people" — Teen has no notes, so "remember" invites invented memories — promoted — cost: prompt wording
- tests get an autouse safe AI chain (app.chain_from_config → AIChain([])) in conftest — real keys in .env mean a forgotten fake makes paid network calls — promoted from review minor — cost: none
- Wisp's own mention is dropped from the answered text and context (brief: "stripped of mentions"); other members' mentions render as display names — promoted — cost: none
- I1 loop-level and extension-load errors are posted to every configured guild's staff channel (load errors after ready, once) — "errors are never hidden" — cost: none
- I2 feeding runs find_track before settings; SettingsRepo keeps a write-through in-process cache (one process) — hot path + error channel survives DB outage — cost: stale cache only if a second process ever writes settings
- I3 one shared can_feed check (qualifying role + activated); Feed button/snacks require it; Rhyme Duels stay open to all but only qualifying members get play credit (interaction/bond/growth); best score recorded for all — spec gates feeding and wants Rockstar to mean the community showed up — cost if Myra wants open play: relax one check
- I4 /wispadmin food viibr suno (0-50) stored in nullable settings columns, falling back to rules.MEAL_POINTS; rules_text takes the effective values and the How Wisp Works starter message becomes editable (rules_message_id) and is refreshed — spec Staff controls — cost: two columns + one command
- I5 startup compares information_schema columns with _DEFINITIONS/_ADDED_COLUMNS and raises SchemaError on missing columns — a stale live table would otherwise fail silently — cost: none
- promoted minors M1 (wider emoji filter), M2 (bot-wide AllowedMentions.none()), M3 (fail fast when every provider cools down — overrides the earlier "try them all anyway" ruling, which cost providers×12 s per mention in a total outage), M4 (remove dead compliment code), M5 (tunables into rules.py), M7 (role mention counts as aimed), M8 (README permissions), M9 (drop "song listens" from Vault intro), M10 (refuse paid/free snack at the meal cap, not consumed), M12 (maybe_meet only while ALIVE — the Egg doesn't talk), M13 (pool_recycle) — cost: small edits
- Parked: snack "full" detected as care == 0 (works while every snack has care > 0) — Ruling: stands; fine for the current menu
- Parked: report_error_everywhere only catches pymysql/OSError from settings.guilds(); another type would escape the tick-loop error hook and stop the loop — Ruling: real but very unlikely (aiomysql raises pymysql errors, TimeoutError is OSError); deferred, flagged to Myra
- Parked: a guild that first sees an outage during another guild's cooldown gets "cooling down" reasons with no root cause — Ruling: acceptable, one report per streak per guild still holds
- Parked: food value 0 makes that track kind silently not feed (0-50 per ruling); rules post refreshes only via /wispadmin food; studio _ARCHIVE_AFTER_MINUTES outside rules.py; _record_play no ban check — Ruling: deferred minors

## Snack Packs, Wisp's lunchbox and gifts

- daily gift limits (one buy per collection, one kept gift) count per life and per UTC day, so a new Wisp starts the day fresh as well as restocked — matches "collections are per life" — cost: none
- gift titles take "an" before a vowel ("an Orange Book") in headings; lines never put an article before {gift} — the brief's "a {gift}" read wrong for Orange — cost: none
- favorite songs are picked whatever phase Wisp is in, egg included — the brief only requires a set-up guild, and picks belong to the guild across lives — cost: an egg "puts a track in his lunchbox"
- his favorite snack beats the pickle stance: feeding it always gets SNACK_FAVORITE — "instead of the normal snack line" — cost: none
- the ban refusal reads "snacks or gifts", shared by the Vault, the Feed button and gifts — one check, one wording — cost: none
- the gift RNG lives on a small Gifts cog, reached with bot.get_cog — the Vault's handlers are module functions, not cog methods — cost: a LookupError reported if the cog is not loaded
- ViiBR feeds are detected from the stored url with find_track(url).kind, no kind column on feeds — no migration of live rows — cost: re-parsing a day's urls once per tick
- the favorite snack is never the free Sine Wave; it is picked from the paid snacks only (controller ruling) — otherwise its line would answer every member's daily free snack for the whole life — cost: none
- once he has kept a gift today, the Vault's Gifts section says "Wisp already picked his treasure today. Anything you give him goes back to the Vault." while the select stays open (controller ruling) — members see it before paying — cost: one line
