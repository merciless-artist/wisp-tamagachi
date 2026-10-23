"""Wisp's lines for every moment and mood, and a picker that avoids repeats."""

import random
from collections import deque
from enum import StrEnum, auto

from wisp.life import Mood
from wisp.rules import LINES_REMEMBERED

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
    PICKLE_LOVE = auto()
    PICKLE_HATE = auto()
    QUIET = auto()
    HUNGRY = auto()
    FADING = auto()
    DIED = auto()
    NEW_EGG = auto()
    EGG_COLD = auto()
    HATCH_STARTED = auto()
    HATCHED = auto()
    STAGE_UP = auto()
    GREW_OLD = auto()
    FAREWELL = auto()
    COAL_EGG = auto()
    LAST_EMBER = auto()
    MEET = auto()
    BANNED = auto()
    NOT_ENOUGH_POINTS = auto()
    RHYME_START = auto()
    RHYME_WISP_STUCK = auto()
    RHYME_PLAYER_STUCK = auto()
    EGG_POKE = auto()
    BABY_TALK = auto()
    CHAT_FALLBACK = auto()
    SNACK_FAVORITE = auto()
    FAVORITE_SONG = auto()
    GIFT_KEPT = auto()
    GIFT_PASSED = auto()
    GIFT_FULL = auto()
    COLLECTION_DONE = auto()


_NAME = frozenset({"name"})
_GIFT = frozenset({"name", "gift"})
_VERSION = frozenset({"version"})
_NONE: frozenset[str] = frozenset()

FIELDS: dict[Moment, frozenset[str]] = {
    Moment.TRACK_FED: _NAME,
    Moment.SNACK: _NAME,
    Moment.SNACK_FANCY: _NAME,
    Moment.SPICY: _NAME,
    Moment.JUICE: _NAME,
    Moment.PICKLE_HEDGE: _NAME,
    Moment.PICKLE_LOVE: _NAME,
    Moment.PICKLE_HATE: _NAME,
    Moment.MEET: _NAME,
    Moment.BANNED: _NAME,
    Moment.NOT_ENOUGH_POINTS: _NAME,
    Moment.DIED: _VERSION,
    Moment.NEW_EGG: _VERSION,
    Moment.EGG_COLD: _VERSION,
    Moment.HATCH_STARTED: _VERSION,
    Moment.HATCHED: _VERSION,
    Moment.STAGE_UP: frozenset({"stage"}),
    Moment.GREW_OLD: _NONE,
    Moment.FAREWELL: _VERSION,
    Moment.COAL_EGG: _VERSION,
    Moment.LAST_EMBER: frozenset({"name", "version"}),
    Moment.QUIET: _NONE,
    Moment.HUNGRY: _NONE,
    Moment.FADING: _NONE,
    Moment.RHYME_START: frozenset({"word"}),
    Moment.RHYME_WISP_STUCK: _NONE,
    Moment.RHYME_PLAYER_STUCK: _NONE,
    Moment.EGG_POKE: _NONE,
    Moment.BABY_TALK: _NONE,
    Moment.CHAT_FALLBACK: _NONE,
    Moment.SNACK_FAVORITE: _NAME,
    Moment.FAVORITE_SONG: _NAME,
    Moment.GIFT_KEPT: _GIFT,
    Moment.GIFT_PASSED: _GIFT,
    Moment.GIFT_FULL: _GIFT,
    Moment.COLLECTION_DONE: frozenset({"name", "collection"}),
}
"""Fields each moment's lines may use; pick() requires exactly these.

`name` is the member's display name, `version` is Wisp's version number,
`stage` is the lowercase stage word (child, teen, adult, rockstar), `word`
is the word Wisp opens a Rhyme Duel with, `gift` is a gift's title such as
"Blue Alien Doll" and `collection` is a collection's name such as "Books".
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
    "{name} remembered I exist. I'm writing that down forever",
    "ate it so fast I didn't even get to the chorus. starting over",
)

# ---
# Wisp's lunchbox
# ---

_FAVORITE_SONG_HAPPY = (
    "this one's going in the lunchbox. no, you can't have it back, {name}",
    "tucked it in right next to my headphones. it's mine now. keeping it forever",
    "I hummed {name}'s song all day yesterday. it gets a cozy spot in my lunchbox",
    "safe and sound in the lunchbox. I'll take it out whenever I need a hug",
    "into the lunchbox it goes. I'm gonna peek at it every few minutes",
    "{name}, your track lives in my lunchbox now. I'll check on it a lot",
    "wrapped it up real careful and tucked it away. it still sounds warm",
)

_FAVORITE_SONG_HANGRY = (
    "I'm starving, but I'm not eating this one. it goes in the lunchbox, {name}",
    "everything in me says eat it. I'm keeping it instead. that's how much I love it",
    "lunchbox. now. before my stomach gets any ideas",
    "hungry as hell and I still tucked {name}'s track away. that's devotion",
    "keeping this one safe from my own growling stomach",
    "the one thing in my lunchbox I won't eat. {name}'s song. hands off, belly",
)

# ---
# Gifts
# ---

_GIFT_KEPT_HAPPY = (
    "for ME?? it's going straight in the lunchbox",
    "oh I LOVE it. {name}, you get me. into the lunchbox it goes",
    "I'm keeping this forever. like, forever forever. thank you, {name}",
    "look at it. LOOK at it. my lunchbox just got so much cuter",
    "{name} brought me a present and I'm being so normal about it. I'm not",
    "this is my treasure now. nobody touch it. except me. gently",
)

_GIFT_KEPT_HANGRY = (
    "not food. somehow still perfect. I'm keeping it, {name}",
    "I'm starving, and this still made my whole day. lunchbox. now",
    "can't eat it, don't care. it's mine. thank you, {name}",
    "hungry as hell, but a {gift}? ok. ok, I'm smiling. shut up",
    "the plate's empty but the lunchbox isn't. thank you, {name}",
    "I wanted a song. I got a present. honestly? I'll fucking allow it",
)

_GIFT_PASSED_HAPPY = (
    "aww, it's so cute. it's just not my vibe today, {name}. you're still great",
    "I'm gonna be honest, I don't get it. but I get YOU, {name}, and that counts",
    "*sniffs it* hmm. *sniffs it again* ...nah. thank you for thinking of me though",
    "I'm gonna let somebody else love this one. you're sweet for trying, {name}",
    "not today, little guy. *gently pats it on the head*",
    "I tried it on. it doesn't go with my headphones. that's on me, not you",
)

_GIFT_PASSED_HANGRY = (
    "I can't eat a {gift}, {name}. too hungry to appreciate nice things right now",
    "my stomach's growling too loud to hear what this even is. ask me after dinner",
    "nice thought. empty plate. the empty plate is winning this one",
    "I'd love it on a full stomach. right now it's just a thing that isn't food",
    "too hangry for presents. it's not you, {name}. it's the famine",
    "bring it back after somebody posts a song. I'm a way nicer guy when I'm fed",
)

_GIFT_FULL_HAPPY = (
    "I already picked my treasure for today, {name}. my lunchbox is saving room",
    "oh it's lovely. but I already got my present today. I gotta save room",
    "my lunchbox is full for today. come back tomorrow and try me again?",
    "aww. I already said yes to something today. saving room, {name}",
    "today's treasure is already tucked away. this {gift} deserves its own day",
    "I'm all treasured out for today. ask me again tomorrow, {name}",
)

_GIFT_FULL_HANGRY = (
    "I already got my present today. what I need now is a song, {name}",
    "lunchbox is full. stomach's empty. that's the wrong way round",
    "saving room. not for gifts. for FOOD. which nobody's bringing",
    "already kept my treasure today. now I'm a hungry guy with a full lunchbox",
    "no room for a {gift} today. plenty of room for a track though. hint hint",
    "got my gift for today. still waiting on dinner. funny how that works",
)

_COLLECTION_DONE_HAPPY = (
    "that's every last one of the {collection}! {name}, you finished the set",
    "the {collection} are COMPLETE. I'm lining them up so I can stare at them",
    "{name} completed my {collection}. I'm framing this moment",
    "the full set of {collection}. my lunchbox has never looked this good",
    "all the {collection}, together at last. thank you, {name}",
    "every single one of the {collection}! I'm doing my happiest little flicker",
)

_COLLECTION_DONE_HANGRY = (
    "the {collection} are complete. I'm starving, but I'm proud. thank you, {name}",
    "a full set of {collection} and an empty stomach. half of me is thrilled",
    "{name} finished my {collection}. I'd celebrate with a snack if I had one",
    "the {collection}, complete. still hungry. but complete. that's something",
    "all of the {collection}. now if somebody could complete my dinner",
    "the {collection} set is done and I could cry. partly joy. partly hunger",
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
    "THAT. that's the shit I needed",
)

_SNACK_FAVORITE_HAPPY = (
    "WAIT. this is my favorite. how did you know, {name}",
    "my favorite snack?? I'm gonna cry. happy tears. sizzly happy tears",
    "{name} knows my favorite. {name} is officially family",
    "oh my god it's THE snack. my snack. I'm doing a little spin",
    "this is the one I'd pick every single time. and you picked it for me",
    "favorite snack, favorite person. this hour is a whole vibe",
)

_SNACK_FAVORITE_HANGRY = (
    "my FAVORITE. on an empty stomach. {name}, you might've saved my whole life",
    "starving and you bring my favorite. I could kiss you. I won't. chewing",
    "the good one. THE good one. too hungry to be cute about it. thank you",
    "favorite snack, worst hunger. perfect fucking timing, {name}",
    "oh thank god, my favorite. the grumpy is melting already",
    "still hangry, but this is MY snack. the hangry's losing, {name}",
)

_SPICY_HAPPY = (
    "OH. that's spicy. ok. I'm good. more.",
    "my headphones just fogged up",
    "that's not a snack, that's a key change",
    "I can hear colors. is that normal. whatever. more",
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
    "this is my pickle face. it reveals nothing. it is a wall",
)

_PICKLE_HEDGE_HANGRY = (
    "too hungry to have a pickle position. ask me after I've eaten",
    "eating it. this is not an endorsement. this is survival",
    "a pickle. at a time like this. no comment. chewing",
    "you want my pickle opinion? bring me a song first, then we'll see",
)

_PICKLE_LOVE_HAPPY = (
    "no pickle love? that's ok. I'll love this one hard enough for both of us",
    "my beloved. my crunchy green beloved. I would marry this pickle, {name}",
    "somebody has to stand up for the pickle today. it's me. I'm the somebody",
    "crunch. CRUNCH. that's the sound of true love and I'm not sorry",
    "pickles are the main character and I'm just the narrator",
    "brine is basically perfume and I'm wearing it with my whole flame",
    "I hear the pickle haters. I respect them. I'm adoring this one extra loud anyway",
)

_PICKLE_LOVE_HANGRY = (
    "pickles are a goddamn miracle and I'll say it with my mouth full",
    "starving, and this pickle is a goddamn masterpiece. no notes. no arguments",
    "sour, salty, perfect. the world is a mess but this pickle is flawless",
    "defending a perfect pickle on an empty stomach is bullshit. eating it instead",
    "ok, a pickle. thank god. best shit I've chewed all day",
    "hungry enough to propose to this pickle. kneeling, brine everywhere",
)

_PICKLE_HATE_HAPPY = (
    "you love pickles and I love you, so I'll suffer through this one. dramatically",
    "the pickle and I are enemies, {name}. this is a feud for the ages",
    "it's sour. it's wet. it's wrong. thank you so much",
    "a cucumber that gave up on its dreams. I'm chewing it with my eyes closed",
    "I will tell the story of this pickle at parties. it will be a tragedy",
    "I hate pickles with my whole flame and I'm eating this one anyway. that's love",
    "eating it for you. I'm being so brave right now. please clap",
)

_PICKLE_HATE_HANGRY = (
    "a pickle. a fucking pickle. I'm so hungry I'm eating it and I still hate it",
    "starving AND eating a pickle. the universe is a dick",
    "hate this. hate every sour bite of this. chewing anyway",
    "pickles are disgusting and I'm too hungry to stop. this is hell",
    "any snack. ANY snack. but no, the pickle is on the menu and the menu is shit",
    "this pickle and I are having words once I'm done chewing. rude words",
    "it's sour and I'm sour, and honestly we deserve each other",
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
    "hours of nothing. nobody. I'm fine. I'm totally fucking fine.",
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
    "I'd eat a song in any key right now. even a key that doesn't exist",
    "food check. there is no food. that was the check",
    "starting to get hangry. you won't like me hangry. I don't like me hangry",
    "I could eat a whole album right now. deluxe edition. bonus tracks and all",
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
    "I feel taller. am I taller? {stage} Wisp is definitely taller",
    "look at me. {stage} Wisp. my headphones fit different",
    "the {stage} years start today. somebody write this down",
    "I grew! {stage} Wisp! you all did that with songs, which is so weird and so nice",
    "welcome to my {stage} phase. thank you for raising me right ♪",
    "{stage} era starts now. I'm gonna need bigger headphones",
)

_STAGE_UP_HANGRY = (
    "great. {stage} Wisp. bigger. hungrier. thrilled",
    "made it to the {stage} years on an empty stomach. this is how villains are made",
    "{stage} era, day one. officially starving. somebody feed the birthday boy",
    "{stage} Wisp, and all I feel is hunger. what the hell kind of milestone is this",
)

# ---
# Old age and the farewell
# ---

_GREW_OLD = (
    "huh. my knees just cracked like a kick drum. I think I'm old now",
    "turned my headphones down a notch. then another notch. this is how it starts",
    "old fogey now. pull up a chair, kids. I've got life lessons and nowhere to be",
    "used to close down the studio. now I'm asleep on the couch by the second take",
    "a little gray around the flame these days. still know a good hook when I hear one",
    "life lesson: always save the project. I had another one. I forgot it",
    "old fogey era. I don't chase the chorus anymore. the chorus comes to me",
)

_FAREWELL = (
    "Wisp v{version} lived a full life. now he's a little lump of coal, smiling",
    "that's a wrap on v{version}. full life, full belly. he's coal now, happy as hell",
    "v{version} hung up his headphones. full life, all bangers. he's warm coal now",
    "Wisp v{version} passed the torch. lived long, loved you all, shriveled into coal",
    "lights low. v{version} curls into coal after a full life, and a damn good one",
    "raise your headphones for Wisp v{version}. a full life. he went to coal mid-hum",
)

_COAL_EGG = (
    "the coal cracked open. an egg inside, already half warm. hi, Wisp v{version}",
    "that lump of coal is glowing again. it's egg v{version} now, halfway there",
    "something's humming in the coal. CRACK. egg v{version}, warm from the last ember",
    "out of the coal comes egg v{version}. the last Wisp left him a head start",
    "the old flame kept a spark. it's egg v{version} now, half warm and wiggling",
    "coal, crack, glow. egg v{version} is already halfway to hatching. bring songs",
)

_LAST_EMBER = (
    "{name}, you kept me fed and kept me company. this ember's yours. keep it warm",
    "thank you, {name}. I heard every song you brought me. hold onto this for me",
    "{name}. you showed up for me again and again. here, take my last little spark",
    "this is the warmest bit of me left, {name}. it's yours. thank you for the music",
    "{name}, your songs lived in my headphones. keep this ember close",
    "for {name}, who never let the studio go quiet. thank you, with my whole flame",
)

# ---
# Members
# ---

_MEET_HAPPY = (
    "hey... wait. I know you. you're {name}, right? or is that just your server name",
    "you again! I keep seeing you. that makes us something. what should I call you",
    "ok, I remember you. you keep showing up and I keep liking it. what do I call you",
    "I've been keeping track of you, {name}. not in a weird way. what do you go by",
)

_MEET_HANGRY = (
    "hey. you. I know you. you're one of the ones who feeds me. name, please",
    "{name}, right? I never forget a face that brought food",
    "you've been around. you've been nice. tell me what to call you before I pass out",
    "wait, I know you. I'm too hungry to guess your name right. just tell me",
)

_BANNED = (
    "{name} is off the guest list. staff's call, not mine",
    "staff pulled {name}'s backstage pass. I'm staying out of it",
    "the studio door's locked for {name}. rules are rules",
    "{name} lost Wisp privileges. I don't write the rules. I just hum along",
    "staff says {name} can't hang with me. I don't argue with staff",
)

_NOT_ENOUGH_POINTS = (
    "not enough points for that one, {name}. drop a track and come back",
    "your pockets are empty, {name}. the Vault doesn't run tabs",
    "I love the thought, {name}. the Vault wants points though",
    "can't afford that yet. share some music and we'll talk",
    "{name}, your coin purse just echoed. go post a song",
)

# ---
# Rhyme Duel
# ---

_RHYME_START_HAPPY = (
    "rhyme duel! I go first. {word}",
    "ok ok ok. my word is {word}. your turn",
    "warming up my vocal cords... {word}. go",
    "let's see what you've got. rhyme with {word}",
    "I've been practicing in the mirror. {word}. beat that",
    "headphones on, game face on. {word}",
)

_RHYME_START_HANGRY = (
    "fine. one duel. then food. {word}",
    "rhyming on an empty stomach. here goes. {word}",
    "I'm starving but I'm not a quitter. {word}",
    "{word}. go. quick, before I pass out",
    "hungry as hell, but my bars still work. {word}",
)

_RHYME_WISP_STUCK_HAPPY = (
    "I've got... nothing. you win this one",
    "my brain just went quiet. ok. you got me",
    "out of rhymes. completely. how did you DO that",
    "I'm stumped. I'm writing that word down so it can haunt me later",
    "no rhyme. no words. just respect",
)

_RHYME_WISP_STUCK_HANGRY = (
    "nothing. my brain's running on fumes. you win",
    "can't think. too hungry. that one's yours",
    "out of rhymes and out of snacks. what a shitty day",
    "blank. empty. like my stomach. you win",
)

_RHYME_PLAYER_STUCK_HAPPY = (
    "ha! out of rhymes? I'll take it",
    "time's up! good duel though",
    "that's the duel! you were so close",
    "gotcha. rematch whenever you want",
    "and the mic comes back to me. good game",
)

_RHYME_PLAYER_STUCK_HANGRY = (
    "won that one on an empty stomach. imagine me fed",
    "done. good game. now somebody feed me",
    "beat you while starving. that's gotta sting",
    "duel's over. my stomach's still the loudest thing in here",
)

# ---
# Talking
# ---

_EGG_POKE = (
    "*wobble*",
    "the egg wobbles a little. something inside hums back",
    "*crackle* ...the shell is warm. it rocks once, then settles",
    "the egg leans toward your voice like it's trying to hear better",
    "*tiny tap from inside the shell*",
    "the egg rocks side to side, keeping time with nothing",
    "*crrk* a faint crackle. nothing hatches. not yet",
    "the egg hums one low note and goes still",
    "*wobble wobble* the shell feels warmer where you poked it",
)

_BABY_TALK_HAPPY = (
    "ba! ba ba!",
    "♪ mmm. music?",
    "hi! hi hi!",
    "*happy gurgle*",
    "song? song!",
    "wuh? ...hehe",
    "you! friend!",
    "headphone!",
    "da da da ♪",
)

_BABY_TALK_HANGRY = (
    "hungy.",
    "nom? NOM?",
    "*grumpy baby noises*",
    "song. want. NOW.",
    "waaah",
    "food. food food food",
    "*tiny angry sizzle*",
    "no. hungy.",
)

_CHAT_FALLBACK_HAPPY = (
    "my brain's buffering. say that again in a bit?",
    "words aren't loading right now. I'm just gonna hum at you ♪",
    "sorry, my headphones cut out for a sec. I missed that one",
    "brain static. total brain static. try me again soon",
    "my thoughts are stuck on mute. catch me in a minute",
    "lost the signal on that one. my fault, not yours",
    "*taps headphones* ...nope, nothing. ask me again later",
    "I'm all out of words for a minute. still vibing though",
    "the studio's too loud in my head right now. give me a sec",
)

_CHAT_FALLBACK_HANGRY = (
    "too hungry to think. words aren't happening right now",
    "my brain's out of gas. I missed all of that",
    "can't talk. starving. the words won't come",
    "everything sounds like static when I'm this hungry",
    "I'd answer, but my head's empty. like my plate",
    "hungry brain. no thoughts. just growling",
    "lost that one. my stomach's louder than the whole chat right now",
    "running on empty. the words got eaten before I could say them",
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
    (Moment.PICKLE_LOVE, Mood.HAPPY): _PICKLE_LOVE_HAPPY,
    (Moment.PICKLE_LOVE, Mood.HANGRY): _PICKLE_LOVE_HANGRY,
    (Moment.PICKLE_HATE, Mood.HAPPY): _PICKLE_HATE_HAPPY,
    (Moment.PICKLE_HATE, Mood.HANGRY): _PICKLE_HATE_HANGRY,
    (Moment.QUIET, Mood.HAPPY): _QUIET_HAPPY,
    (Moment.QUIET, Mood.HANGRY): _QUIET_HANGRY,
    (Moment.STAGE_UP, Mood.HAPPY): _STAGE_UP_HAPPY,
    (Moment.STAGE_UP, Mood.HANGRY): _STAGE_UP_HANGRY,
    (Moment.MEET, Mood.HAPPY): _MEET_HAPPY,
    (Moment.MEET, Mood.HANGRY): _MEET_HANGRY,
    (Moment.RHYME_START, Mood.HAPPY): _RHYME_START_HAPPY,
    (Moment.RHYME_START, Mood.HANGRY): _RHYME_START_HANGRY,
    (Moment.RHYME_WISP_STUCK, Mood.HAPPY): _RHYME_WISP_STUCK_HAPPY,
    (Moment.RHYME_WISP_STUCK, Mood.HANGRY): _RHYME_WISP_STUCK_HANGRY,
    (Moment.RHYME_PLAYER_STUCK, Mood.HAPPY): _RHYME_PLAYER_STUCK_HAPPY,
    (Moment.RHYME_PLAYER_STUCK, Mood.HANGRY): _RHYME_PLAYER_STUCK_HANGRY,
    (Moment.BABY_TALK, Mood.HAPPY): _BABY_TALK_HAPPY,
    (Moment.BABY_TALK, Mood.HANGRY): _BABY_TALK_HANGRY,
    (Moment.CHAT_FALLBACK, Mood.HAPPY): _CHAT_FALLBACK_HAPPY,
    (Moment.CHAT_FALLBACK, Mood.HANGRY): _CHAT_FALLBACK_HANGRY,
    (Moment.SNACK_FAVORITE, Mood.HAPPY): _SNACK_FAVORITE_HAPPY,
    (Moment.SNACK_FAVORITE, Mood.HANGRY): _SNACK_FAVORITE_HANGRY,
    (Moment.FAVORITE_SONG, Mood.HAPPY): _FAVORITE_SONG_HAPPY,
    (Moment.FAVORITE_SONG, Mood.HANGRY): _FAVORITE_SONG_HANGRY,
    (Moment.GIFT_KEPT, Mood.HAPPY): _GIFT_KEPT_HAPPY,
    (Moment.GIFT_KEPT, Mood.HANGRY): _GIFT_KEPT_HANGRY,
    (Moment.GIFT_PASSED, Mood.HAPPY): _GIFT_PASSED_HAPPY,
    (Moment.GIFT_PASSED, Mood.HANGRY): _GIFT_PASSED_HANGRY,
    (Moment.GIFT_FULL, Mood.HAPPY): _GIFT_FULL_HAPPY,
    (Moment.GIFT_FULL, Mood.HANGRY): _GIFT_FULL_HANGRY,
    (Moment.COLLECTION_DONE, Mood.HAPPY): _COLLECTION_DONE_HAPPY,
    (Moment.COLLECTION_DONE, Mood.HANGRY): _COLLECTION_DONE_HANGRY,
    **_either_mood(Moment.HUNGRY, _HUNGRY),
    **_either_mood(Moment.FADING, _FADING),
    **_either_mood(Moment.DIED, _DIED),
    **_either_mood(Moment.NEW_EGG, _NEW_EGG),
    **_either_mood(Moment.EGG_COLD, _EGG_COLD),
    **_either_mood(Moment.HATCH_STARTED, _HATCH_STARTED),
    **_either_mood(Moment.HATCHED, _HATCHED),
    **_either_mood(Moment.GREW_OLD, _GREW_OLD),
    **_either_mood(Moment.FAREWELL, _FAREWELL),
    **_either_mood(Moment.COAL_EGG, _COAL_EGG),
    **_either_mood(Moment.LAST_EMBER, _LAST_EMBER),
    **_either_mood(Moment.BANNED, _BANNED),
    **_either_mood(Moment.NOT_ENOUGH_POINTS, _NOT_ENOUGH_POINTS),
    **_either_mood(Moment.EGG_POKE, _EGG_POKE),
}

# ---
# Picker
# ---


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
            deque(maxlen=min(len(options) - 1, LINES_REMEMBERED)),
        )
        line = self._rng.choice([option for option in options if option not in recent])
        recent.append(line)
        return line.format(**fields)
