# Wisp Tamagotchi — Design Draft

*For Foggy & Angel to refine. Drafted 2026-10-13. Numbers marked "starting value"
get tuned after a week of real data.*

*Meters note, 2026-10-26: this first draft describes two meters (Care and
Happiness). Wisp now has three, Full, Happy and Care, plus a childhood cold. The
current description is `wisp_tamagotchi.html` and
`specs/2026-10-26-status-menu-and-three-meters-design.md`.*

---

## The idea

One Wisp for the whole server. Members raise him together by sharing music in the
tracks channel. Fed well, he grows from an egg into a Rockstar. Neglected, he dies,
and the server has to hatch a new egg, which gets the next version number.
Every life is a run the server tries to beat.

## Life cycle

| Stage | What it means | Starting value |
|---|---|---|
| Egg | Needs constant beats | Hatches after ~24h of normal server activity |
| (Emerging) | Egg cracks, Wisp comes out | ~5 hours, can't fail once it starts |
| Baby Wisp | Vibe-sensitive | Days 0–2 |
| Child | Care with music | Days 3–6 |
| Teen | Craves loud bass | Days 7–13 |
| Adult | Master of the vibe | Day 14+ |
| Rockstar | Special evolution, maximum energy | Adult who stays very happy for 7 days straight |

Art for every stage exists (growth stage sheet).

## How Wisp eats

☆ **Where:** members keep posting in the tracks channel as normal. Wisp never posts or
  reacts there; each feeding track is PIPED into his forum (Mealtime post).
☆ **Who:** members at **Active Loungers (Level 5) or higher** who have **opened the
  Wisp leaderboard at least once**. Opening the board is the opt-in. Drive-by posters
  and people who never engage with Wisp don't count.
☆ **What he eats:**

| Posted link | Feeds Wisp | Your leaderboard points | Builds your bond |
|---|---|---|---|
| viibrmusic.com track | Big meal (starting value: 10) | 4 points | Yes |
| Suno, or any other music link | Snack (starting value: 2) | 1 point | No |

Every qualifying link feeds Wisp and earns leaderboard points; other sites earn a
quarter of the points. Only viibrmusic.com links build your bond with him.

☆ **Wisp knows you.** Your bond is how well he knows you personally. It grows from
  everything you do with him, not only sharing music:

**Meeting Wisp.** A bond doesn't start right away. Once you've interacted with him
(fed, played or snacked) on **three different days**, he notices you and learns your
name. He asks what to call you; if you skip it, he uses your server name. Anything
you did before that is tracked quietly and carries into your bond when it starts.
(The name is display only; everything is stored by Discord ID.)

| What you do | Bond | Also |
|---|---|---|
| Share a viibrmusic.com track | +10 | Big meal, leaderboard points |
| Play with him (quick mini-game from his status card, a few times a day) | +3 | Raises his happiness |
| Give him a snack from the Snack Box | +1 | Care boost, bigger for fancier snacks |

  Play and snacks add at most 7 bond a day (starting value), so ViiBR music stays
  the fastest way into his circle, but daily regulars still get there.

| Bond tier | Bond needed |
|---|---|
| New face | Starts when he learns your name |
| Familiar | 50 |
| Friend | 150 |
| Bandmate | 400. Wisp offers you one free song listen. |

  Bonds carry over when a Wisp dies. Every new version already knows its
  bandmates, which makes them the natural people to rally when an egg needs
  hatching. When Wisp gets his AI voice later, the bond is what he remembers
  about you.

☆ **Fairness rules:**
  - The same link only feeds him once, ever. Reposting doesn't count.
  - Each person can feed up to a daily limit (starting value: 30 food, so three
    viibrmusic.com links). One person can't keep him alive alone.
☆ **Non-qualifying posts:** Wisp stays silent. The rule is stated in his channel,
  never aimed at a person.

## The Lunchbox

Wisp keeps everything he values in his lunchbox. `/wisp lunchbox` opens it: the
Snack Box, his song listens, and room for treasures added later.

### Snack Box

Wisp eats sound: every snack is a picture of sound, plus two human foods.

| Snack (emoji name) | Cost | Care | Reaction |
|---|---|---|---|
| Sine Wave (snack_sinewave) | Free, once a day | +2 | Plain comfort food |
| Cloud Wave (snack_cloudwave) | 3 | +5 | Fluffy, happy |
| Jelly Wave (snack_jellywave) | 3 | +5 | Wobbly, giggly |
| Juice Wave (snack_juicewave) | 3 | +5 | Water vs fire, fizzles a little |
| Spicy Wave (snack_spicywave) | 5 | +8 | "OH. that's spicy. ok. I'm good. more." |
| Glitter Wave (snack_glitterwave) | 8 | +12 | Sparkly, very pleased |
| ViiBR Wave (snack_viibrwave) | 10 | +15 | His favorite, home-team snack |
| Cheese (snack_cheddar) | 6 | +8 | Loves it |
| Pickles (snack_pickles) | 6 | +8 | Hedges, then contrarian |

Starting values. Art by Myra.
☆ `/wisp lunchbox` to buy; **Feed** button on his status card to pick from your
  inventory. His emojis are app emojis only he can use, so members pick from a menu.
☆ Paid with leaderboard points from a spending balance; rank counts lifetime points
  earned, so spending never drops your rank.
☆ Snacks count toward the daily feeding limit. Music is still his real food.

### Song listens

Wisp listens to a song you made (Gemini audio model) and reacts: what he loved, what
stuck, how it felt. Accepts mp3 uploads, public Suno links, viibrmusic.com links.
☆ The first one is a gift: at Bandmate, Wisp offers a listen himself. Once per person,
  ever; survives his death.
☆ After that, listens are bought from the Lunchbox for 40 points (starting value),
  Bandmates only.
☆ Never cruel about anyone's music; honest about what he loved; he amplifies.

## Two meters

☆ **Care** (the battery): goes up when he's fed, drains steadily over time. If it
  hits zero, Wisp dies. Starting value: drains 30 points a day, so the server needs
  about three viibrmusic.com links a day to keep him steady.
☆ **Happiness** (the smiley): based on **how many different people** fed or played with
  him in the last 24 hours, not how much. Five or more people is full happiness.
  This is what earns the Rockstar evolution, so a Rockstar Wisp means the whole
  community showed up, not one heavy poster.

## Death, eggs and versions

☆ Care hits zero → Wisp dies. He posts warnings on the way down (hungry, then fading).
☆ Wisp's House asks "Do you want to begin again?" When staff press **Begin again**,
  a new egg appears, labeled with the next version: **Wisp v4**.
☆ The egg has to be hatched with music the same way Wisp eats. It has a warmth timer
  (starting value: 48 hours). If the server doesn't bring enough music in time, the
  egg goes cold and **that version number is used up**. History stays honest:
  "v3 lived 18 days, v4 never hatched, v5 is going strong."
☆ Once the egg starts cracking, it can't fail.

## Personality

**Super cute, super sweet, complimentary to everyone.** Until he's hangry. Then he
has a surprisingly rough edge, which is the best reason there is to feed him.

His voice is modeled on Herbie (Myra's mascot bot in Hillbilly DJ's server), minus
the southern accent. Wisp's world is studios, headphones and 3 AM sessions. Full
Herbie prompt saved in DOCS/HerbiePromptReference.md.
☆ Adult server, adult mouth: casual, creative swearing when it fits, never for shock.
☆ Teases friends, never cruel; drops it and apologizes if someone is actually upset.
☆ Short: a line or two.
☆ Keeps the conversation going: no wrap-ups, never "anything else I can help with?"
☆ Never repeats himself.
☆ Expression stickers as jumbo reactions, saved for the right moment.

| Moment | Fed and happy | Hangry (care below 30) |
|---|---|---|
| Your ViiBR track feeds him | "oh this one's GOOD. you made this?? shut the fuck up" | "...finally. holy shit. thank you." |
| You give him a snack | "for me?? you're the best" | "a snack. a fucking snack. I needed a meal." |
| You ask him to play | "YES. ok ok ok ready" | "I don't want to play. I want a goddamn SONG." |
| You compliment him | His "no u" gif | "compliments aren't food." |
| The server goes quiet | "taking a little nap. wake me with a beat" | "nine hours. nobody. I'm fine. I'm totally fucking fine." |

Example lines only; the finished set has many lines per moment.

☆ Compliments only count when aimed at Wisp (mentioning or replying to him). The
  "no u" has a cooldown so chat can't spam it.
☆ Hangry Wisp swears, but only at the situation. He's mad about being starved,
  never at a person, never about anyone's music, and never with slurs.
☆ Errors are never hidden behind the personality. Staff see a plain error message.
☆ "no u" gif: https://i.imgur.com/G0SZAsT.gif (direct link, verified, 4.7 MB).

## Protecting Wisp from trolls

**Nobody can hurt Wisp on purpose.** Every action a member can take helps him. The
only thing that kills him is neglect, which takes the whole server not showing up,
so one troll can't do it, and anyone can save him at any moment by sharing music.

What trolls can try is cheating the leaderboard and bonds. That gets punished:
☆ **Fake ViiBR links** don't count. A link has to be a real track page on
  viibrmusic.com, not the homepage or a made-up path.
☆ **Spamming junk tracks** to farm points runs into the daily cap, and staff can
  strip points.
☆ **Gross names.** The name you give Wisp is capped at 24 characters, and staff can
  reset anyone's name, so nobody can make him say something vile.
☆ **Punishment ladder**, same shape as the counting game: first offense is a
  shaming image and one day banned from Wisp, second is a week, third is permanent.
  Staff can lift any ban.

## Leaderboard and hall of fame

`/wisp board` shows:
☆ Top sharers for the current Wisp (viibrmusic.com link = 4 points, any other = 1)
☆ Top sharers of all time, with each person's bond tier
☆ Every version: who hatched it, how long it lived, the highest stage it reached
  (or "never hatched")

Opening the board for the first time is what activates a member as a player.

## How people know it's happening

Foggy's question: if people just drop tracks as normal, do they know they're playing?

☆ Every feeding track appears in his Mealtime post: who fed him, a link back to the
  track, his reaction. Doubles as a running playlist of engaged members' music.
☆ Wisp posts updates in his channel at the moments that matter: stage-ups, hungry,
  fading, death, a new egg, cracking, hatching.
☆ `/wisp` shows his status card anytime:

```
♪ WISP v3 ・ TEEN ・ day 9
care       ███████░░░  72
happiness  █████░░░░░  50
fed today by 4 people
・♪ ────────・──────── ♪・
```

## Staff controls

☆ **Freeze:** pauses all draining (holidays, Discord outages, bot downtime) so Wisp
  never dies from something that wasn't the community's fault.
☆ Set the tracks channel, the qualifying roles, and the food values without code
  changes.
☆ **No DMs, ever.** Ignores DMs, commands are server-only, never DMs anyone. Private
  replies are ephemeral (only-you-can-see) server messages.

## Not in version one

☆ **Points/coins:** bragging rights only for now. Feeding can pay out website points
  later, once the economy exists.
☆ **AI voice:** Wisp talks in pre-written lines first. His AI personality comes after
  the core game works.

## Open questions

1. Where does Wisp live and post his updates: his own channel, or an existing one?
2. Do audio file uploads (no link) count as food? If so, how much?
3. Rockstar as a rare evolution earned by a week of high happiness: agree?
4. Freeze for holidays: yes?
5. What should playing with Wisp look like? A quick beat-matching game, a
   reaction-speed game, or something else?
