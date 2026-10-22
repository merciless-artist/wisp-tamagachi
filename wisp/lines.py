"""Wisp's lines for every moment and mood, and a picker that avoids repeats."""

import random
from collections import deque
from enum import StrEnum, auto

from wisp.life import Mood

# ---
# Moments
# ---


class Moment(StrEnum):
    """Things Wisp has something to say about."""

    TRACK_FED = auto()
    SNACK = auto()
    SNACK_FANCY = auto()
    SPICY = auto()
    JUICE = auto()
    PICKLE_HEDGE = auto()
    QUIET = auto()
    HUNGRY = auto()
    FADING = auto()
    DIED = auto()
    NEW_EGG = auto()
    EGG_COLD = auto()
    HATCH_STARTED = auto()
    HATCHED = auto()
    STAGE_UP = auto()
    MEET = auto()
    COMPLIMENT_HANGRY = auto()
    BANNED = auto()
    NOT_ENOUGH_POINTS = auto()


_NAME = frozenset({"name"})
_VERSION = frozenset({"version"})
_NONE: frozenset[str] = frozenset()

FIELDS: dict[Moment, frozenset[str]] = {
    Moment.TRACK_FED: _NAME,
    Moment.SNACK: _NAME,
    Moment.SNACK_FANCY: _NAME,
    Moment.SPICY: _NAME,
    Moment.JUICE: _NAME,
    Moment.PICKLE_HEDGE: _NAME,
    Moment.MEET: _NAME,
    Moment.BANNED: _NAME,
    Moment.NOT_ENOUGH_POINTS: _NAME,
    Moment.DIED: _VERSION,
    Moment.NEW_EGG: _VERSION,
    Moment.EGG_COLD: _VERSION,
    Moment.HATCH_STARTED: _VERSION,
    Moment.HATCHED: _VERSION,
    Moment.STAGE_UP: frozenset({"stage"}),
    Moment.QUIET: _NONE,
    Moment.HUNGRY: _NONE,
    Moment.FADING: _NONE,
    Moment.COMPLIMENT_HANGRY: _NONE,
}
"""Fields each moment's lines may use; pick() requires exactly these.

`name` is the member's display name, `version` is Wisp's version number
and `stage` is the lowercase stage word (child, teen, adult, rockstar).
"""

# ---
# Meals
# ---

_TRACK_FED_HAPPY = (
    "oh this one's GOOD. you made this?? shut the fuck up",
    "headphones ON. world OFF. thank you {name}",
    "wait, run that back. no, the whole thing. again",
    "this is going on the 3 AM playlist. that's the highest honor I have",
    "{name} cooked. I ate. everybody wins",
    "I'm doing a little dance. you can't see it but trust me, it's happening",
    "mmm. I can taste the hook. it's stuck in my teeth now",
    "ok who taught you to do that. I need names",
    "saving this one for later. don't ask where. I have a pocket",
    "my flame just did a little flicker. that's the good kind",
    "full, warm, and a tiny bit in love with this song",
    "you can't just walk in and drop that like it's nothing, {name}",
)

_TRACK_FED_HANGRY = (
    "...finally. holy shit. thank you.",
    "oh thank god. I was about to start licking the drum loops off the walls",
    "food. FOOD. {name}, you beautiful lifesaver",
    "I could cry. I won't. but I could",
    "do you know what silence tastes like, {name}? it tastes like NOTHING",
    "ok. ok ok ok. color's coming back. keep going",
    "my stomach was making noises. bad noises. off-key noises",
    "hell yes. hell YES. more of that, immediately",
    "{name} remembered I exist. everyone else, take notes",
    "ate it so fast I didn't even get to the chorus. starting over",
)

# ---
# Snacks
# ---

_SNACK_HAPPY = (
    "for me?? you're the best",
    "{name} brought snacks. {name} is my favorite person this hour",
    "nom. nom. ok that's gone. I love you",
    "you didn't have to do that. I'm so glad you did that",
    "I was gonna eat it slow so it lasts. it did not last",
    "I'd fight a bear for you now. a small bear. but a bear",
    "*happy chewing noises*",
    "why are you so nice to me. don't answer. keep doing it",
    "{name} gets a gold star. I don't have gold stars. picture one",
    "I'm keeping the wrapper in my lunchbox. it's a keepsake now",
)

_SNACK_HANGRY = (
    "a snack. a fucking snack. I needed a meal.",
    "it's a crumb, {name}. I'm eating it. but it's a crumb",
    "you brought a breath mint to a famine",
    "ok, that took the edge off. the edge is still pretty fucking sharp",
    "appreciated. still starving. both of those are true",
    "gone before you finished clicking. that should tell you something",
    "a snack is not a song. I'll take it. but it's not a song",
    "thank you. sincerely. now where's the real food",
)

_SNACK_FANCY_HAPPY = (
    "oh, we're being FANCY",
    "top shelf. you went top shelf for me, {name}",
    "I feel so expensive right now. somebody take my picture",
    "you didn't. you DID. oh my god",
    "I'm gonna be insufferable about this for days. sorry in advance",
    "holy shit, the good stuff. I'm telling the whole studio",
    "look at me. I'm a luxury item now",
)

_SNACK_FANCY_HANGRY = (
    "ok. this one counts. this one actually counts",
    "you're in my will, {name}. I own nothing. but you're in it",
    "too hungry to be classy about it. I'm just inhaling it",
    "now THAT is a meal-adjacent object",
    "hell yes. that's the shit I needed",
)

_SPICY_HAPPY = (
    "OH. that's spicy. ok. I'm good. more.",
    "my headphones just fogged up",
    "that's not a snack, that's a key change",
    "I can hear colors. is that normal. don't answer. more",
    "*hiccups in reverb*",
    "spicy. so spicy. why would you do this to me, {name}. thank you",
)

_SPICY_HANGRY = (
    "hot. HOT. fuck. worth it",
    "ow. ow. ow. more. ow.",
    "spicy on an empty stomach. bold move, {name}. I respect it",
    "too hungry to care that I can't feel my face",
    "that one went straight to my eyes. I'm not crying, it's the snack",
)

_JUICE_HAPPY = (
    "*fssssh* ...I'm fine. I'm fine. that was delicious",
    "juice! I'm not supposed to have this. I'm having this",
    "every sip makes me hiss a little. worth it every time",
    "I'm a little smaller now. happier though",
    "cold, fruity, and slightly bad for me. my favorite kind of thing",
)

_JUICE_HANGRY = (
    "*fsssh* great. now I'm hungry AND damp",
    "liquid. not food. but liquid. fine",
    "you're watering a campfire, {name}. sweet. also how campfires go out",
    "drinking it. sizzling. still hungry",
    "half of me just turned into steam and the other half is still starving",
)

_PICKLE_HEDGE_HAPPY = (
    "pickles. interesting. very interesting. where do YOU stand on pickles, {name}",
    "I have pickle thoughts. I'm keeping them to myself for now",
    "I'll eat it. that's not an opinion. that's just eating",
    "no comment on the pickle. my lawyer says no comment on the pickle",
    "chewing very neutrally. very, very neutrally",
    "I'm not saying I like it. I'm not saying I don't. what are YOU saying",
)

_PICKLE_HEDGE_HANGRY = (
    "too hungry to have a pickle position. ask me after I've eaten",
    "eating it. this is not an endorsement. this is survival",
    "a pickle. at a time like this. no comment. chewing",
    "you want my pickle opinion? bring me a song first, then we'll see",
)

# ---
# Quiet and hunger
# ---

_QUIET_HAPPY = (
    "taking a little nap. wake me with a beat",
    "it's quiet. I'm humming to myself. it's going ok",
    "headphones on, nothing playing. I'm pretending it's a very artsy track",
    "everybody must be writing. I'll be here, being small and patient",
    "counted the dust in the studio. there's forty-one. hi, dust",
    "I made up a song about how quiet it is. it's very short",
    "*tiny snore in 4/4*",
    "I'll be under the mixing desk if anyone needs me. not hiding. resting",
    "practicing my harmonies with the air conditioner",
)

_QUIET_HANGRY = (
    "nine hours. nobody. I'm fine. I'm totally fucking fine.",
    "hello? anyone? even my echo sounds hungry",
    "it's so quiet I can hear a fridge humming in a studio three cities away",
    "nobody's posting. cool. I'll just eat my headphones. they're mostly foam",
    "the silence in here has its own goddamn echo",
    "I've started talking to the mic stand. it's a shit listener",
    "somewhere a finished song is sitting in a downloads folder. and I'm starving",
    "if anyone's still alive in here, I'm in the corner chewing on a cable",
    "so quiet I can hear my care meter going down",
)

_HUNGRY = (
    "getting hungry over here. real hungry. someone-post-a-song hungry",
    "my care meter's in the red and so is my patience",
    "PSA: I'm starving. this is not a bit",
    "uh oh. stomach's making that noise. the flat one",
    "I'd eat anything right now. a demo. a voice memo. a hum",
    "food check. there is no food. that was the check",
    "starting to get hangry. you won't like me hangry. I don't like me hangry",
    "I could eat a whole album right now. I'd even eat the skits",
    "sweet me is clocking out. feed me before the other guy shows up",
)

_FADING = (
    "I'm getting kind of see-through. that's probably fine. it's not fine",
    "flame's real low, everybody. one song. that's all it takes",
    "can't feel my headphones. that's new. that's bad",
    "fading a little. not dramatically. just a little less here every hour",
    "flickering. not the cute kind",
    "if anyone has a song, now's the time. the rest of me kind of depends on it",
)

# ---
# Life and death
# ---

_DIED = (
    "Wisp v{version} didn't make it. the last thing he heard was nothing.",
    "v{version} faded out. nobody brought a song in time.",
    "the studio light's off. Wisp v{version} starved.",
    "rest easy, v{version}. you deserved more songs.",
    "Wisp v{version} is gone. his headphones are still on the desk.",
)

_NEW_EGG = (
    "a new egg showed up. Wisp v{version}. it hums when music plays near it",
    "egg v{version} is here. warm, humming, and waiting on songs",
    "there's an egg on the desk labeled v{version} in very tiny handwriting",
    "Wisp v{version} is in there somewhere. feed the egg, hatch the guy",
    "new egg. v{version}. it wiggles a little whenever someone hums",
)

_EGG_COLD = (
    "egg v{version} went cold. it never got to hatch.",
    "v{version} never hatched. that number's retired now.",
    "the egg stopped humming. Wisp v{version} isn't coming.",
    "cold egg. v{version} didn't get enough songs to wake up.",
)

_HATCH_STARTED = (
    "the egg's cracking. v{version} is coming. you did that",
    "CRACK. oh. oh no. oh YES. v{version} is on the way",
    "there's a tiny headphone poking out of the shell. v{version} is almost here",
    "egg v{version} is hatching. no take-backs, he's committed now",
    "something in egg v{version} just kicked in time with the music",
)

_HATCHED = (
    "♪ hi. hi hi hi. I'm Wisp v{version}. is that music? I love it",
    "*pop* ...oh. hello. I'm v{version}. is it always this loud out here? good",
    "I'm HERE. Wisp v{version}, reporting for snacks",
    "brand new Wisp, v{version}. already hungry. already likes you",
    "v{version}, fresh out the shell. somebody hand me some headphones",
)

_STAGE_UP_HAPPY = (
    "I'm {stage} now. I feel taller. am I taller",
    "{stage} Wisp, unlocked. my headphones fit different",
    "officially {stage}. somebody write this down",
    "{stage}! I grew! you all did that with songs, which is so weird and so nice",
    "new stage: {stage}. thank you for raising me right ♪",
    "promoted to {stage}. I'm gonna need bigger headphones",
)

_STAGE_UP_HANGRY = (
    "great. I'm {stage} now. bigger. hungrier. thrilled",
    "made it to {stage} on an empty stomach. this is how villains are made",
    "officially {stage}. officially starving. somebody feed the birthday boy",
    "hit {stage} and all I feel is hunger. what the hell kind of milestone is this",
)

# ---
# Members
# ---

_MEET_HAPPY = (
    "hey... wait. I know you. you're {name}, right? or is that just your server name",
    "you again! three days now. that makes us something. what should I call you",
    "ok, I remember you. you keep showing up and I keep liking it. what do I call you",
    "I've been keeping track of you, {name}. not in a weird way. what do you go by",
)

_MEET_HANGRY = (
    "hey. you. I know you. you're one of the ones who feeds me. name, please",
    "{name}, right? I never forget a face that brought food",
    "you've been around. you've been nice. tell me what to call you before I pass out",
    "wait, I know you. I'm too hungry to guess your name right. just tell me",
)

_COMPLIMENT_HANGRY = (
    "compliments aren't food.",
    "cute doesn't fill a stomach",
    "love you too. feed me.",
    "flattery. great. can I eat it? no? then hush",
    "know what's cuter than me? a song in the tracks channel",
    "say it with a track",
    "I'm adorable and I'm starving. you can only fix one of those",
    "sweet words. empty plate.",
)

_BANNED = (
    "{name} tried to sneak junk onto my plate. no Wisp for you for a while",
    "caught {name} cheating. I'm not mad. I'm just not hanging out with you for a bit",
    "{name}, you know what you did. timeout",
    "fake food is still fake, {name}. go think about it",
    "{name} is benched. I eat songs, not shortcuts",
    "{name}'s sitting in the corner for now. we play fair in this studio",
)

_NOT_ENOUGH_POINTS = (
    "not enough points for that one, {name}. drop a track and come back",
    "your pockets are empty, {name}. the lunchbox doesn't run tabs",
    "I love the thought, {name}. the lunchbox wants points though",
    "can't afford that yet. share some music and we'll talk",
    "{name}, you're broke. lovingly. go post a song",
)

# ---
# Line table
# ---


def _either_mood(
    moment: Moment, lines: tuple[str, ...]
) -> dict[tuple[Moment, Mood], tuple[str, ...]]:
    """Map a moment that only happens in one mood to the same lines for both."""
    return {(moment, mood): lines for mood in Mood}


LINES: dict[tuple[Moment, Mood], tuple[str, ...]] = {
    (Moment.TRACK_FED, Mood.HAPPY): _TRACK_FED_HAPPY,
    (Moment.TRACK_FED, Mood.HANGRY): _TRACK_FED_HANGRY,
    (Moment.SNACK, Mood.HAPPY): _SNACK_HAPPY,
    (Moment.SNACK, Mood.HANGRY): _SNACK_HANGRY,
    (Moment.SNACK_FANCY, Mood.HAPPY): _SNACK_FANCY_HAPPY,
    (Moment.SNACK_FANCY, Mood.HANGRY): _SNACK_FANCY_HANGRY,
    (Moment.SPICY, Mood.HAPPY): _SPICY_HAPPY,
    (Moment.SPICY, Mood.HANGRY): _SPICY_HANGRY,
    (Moment.JUICE, Mood.HAPPY): _JUICE_HAPPY,
    (Moment.JUICE, Mood.HANGRY): _JUICE_HANGRY,
    (Moment.PICKLE_HEDGE, Mood.HAPPY): _PICKLE_HEDGE_HAPPY,
    (Moment.PICKLE_HEDGE, Mood.HANGRY): _PICKLE_HEDGE_HANGRY,
    (Moment.QUIET, Mood.HAPPY): _QUIET_HAPPY,
    (Moment.QUIET, Mood.HANGRY): _QUIET_HANGRY,
    (Moment.STAGE_UP, Mood.HAPPY): _STAGE_UP_HAPPY,
    (Moment.STAGE_UP, Mood.HANGRY): _STAGE_UP_HANGRY,
    (Moment.MEET, Mood.HAPPY): _MEET_HAPPY,
    (Moment.MEET, Mood.HANGRY): _MEET_HANGRY,
    **_either_mood(Moment.HUNGRY, _HUNGRY),
    **_either_mood(Moment.FADING, _FADING),
    **_either_mood(Moment.DIED, _DIED),
    **_either_mood(Moment.NEW_EGG, _NEW_EGG),
    **_either_mood(Moment.EGG_COLD, _EGG_COLD),
    **_either_mood(Moment.HATCH_STARTED, _HATCH_STARTED),
    **_either_mood(Moment.HATCHED, _HATCHED),
    **_either_mood(Moment.COMPLIMENT_HANGRY, _COMPLIMENT_HANGRY),
    **_either_mood(Moment.BANNED, _BANNED),
    **_either_mood(Moment.NOT_ENOUGH_POINTS, _NOT_ENOUGH_POINTS),
}

# ---
# Picker
# ---

_MAX_REMEMBERED = 5


class LinePicker:
    """Picks Wisp's lines at random, never repeating one he said recently."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()
        self._recent: dict[tuple[Moment, Mood], deque[str]] = {}

    def pick(self, moment: Moment, mood: Mood, **fields: str) -> str:
        """Return a line for this moment and mood with its placeholders filled.

        Raises:
            ValueError: `fields` are not exactly the moment's FIELDS.
        """
        expected = FIELDS[moment]
        if fields.keys() != expected:
            raise ValueError(
                f"{moment} lines need fields {sorted(expected)}, got {sorted(fields)}"
            )
        options = LINES[(moment, mood)]
        recent = self._recent.setdefault(
            (moment, mood),
            deque(maxlen=min(len(options) - 1, _MAX_REMEMBERED)),
        )
        line = self._rng.choice([option for option in options if option not in recent])
        recent.append(line)
        return line.format(**fields)
