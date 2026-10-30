"""Tests for Wisp's voice: who talks how, his prompts and reply cleaning."""

import random
import re
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from ai.prompt import Prompt
from wisp.bond import PickleStance
from wisp.life import Life, Mood, Phase, new_egg
from wisp.rules import (
    AI_MAX_CHARS,
    EGG_FOOD_NEEDED,
    EGG_LINE_CHARS,
    EGG_WARMTH,
    HATCHING_TIME,
    POKE_FED_UP_AT,
    POKE_MAD_AT,
    POKE_SLEEP_AFTER,
    Stage,
)
from wisp.voice import (
    COIN_EMOJI,
    EGG_EXPRESSION,
    MINI_COIN_EMOJI,
    NO_U_GIF,
    NO_U_LINK,
    ChatLine,
    Fed,
    OwnEmoji,
    PokeFlavor,
    Poker,
    Reply,
    Speaker,
    Talk,
    build_prompt,
    chimes_in,
    egg_prompt,
    goodbye_prompt,
    keeps_notes,
    own_emojis,
    parse_reply,
    poke_flavor,
    talk_level,
)

NOW = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
AI_STAGES = [Stage.CHILD, Stage.TEEN, Stage.ADULT, Stage.ROCKSTAR, Stage.OLD_FOGEY]
GROWN_UP = {Stage.ADULT, Stage.ROCKSTAR, Stage.OLD_FOGEY}
EXPRESSIONS = ["wisp_happy", "wisp_sad"]
NOTE = "plays bass in a wedding band"
CONTEXT = [ChatLine("Foggy", "anyone up?"), ChatLine("Myra", "always")]
EMOJIS = {"wisp_happy": "<:wisp_happy:11>"}


def life_in(phase: Phase, stage: Stage) -> Life:
    life = new_egg(1, NOW)
    life.phase = phase
    life.stage = stage
    return life


def speaker(notes: tuple[str, ...] = (), stance: PickleStance | None = None) -> Speaker:
    return Speaker(name="Myra", tier="Friend", notes=notes, pickle_stance=stance)


def prompt_for(
    stage: Stage = Stage.TEEN,
    mood: Mood = Mood.HAPPY,
    who: Speaker | None = None,
    message: str | None = "hey wisp",
) -> Prompt:
    return build_prompt(
        stage,
        mood,
        speaker() if who is None and message is not None else who,
        CONTEXT,
        message,
        expressions=EXPRESSIONS,
    )


def egg(
    food: int = 0,
    in_phase: timedelta = timedelta(0),
    *,
    hatching: bool = False,
    coal: bool = False,
) -> Life:
    life = new_egg(1, NOW)
    life.egg_food = food
    life.phase_seconds = in_phase.total_seconds()
    life.from_coal = coal
    if hatching:
        life.phase = Phase.HATCHING
    return life


def poke(
    life: Life | None = None,
    fed: Fed = Fed.NOTHING,
    message: str = "hello little one",
    *,
    emoji: bool = False,
) -> Prompt:
    return egg_prompt(
        egg() if life is None else life,
        Poker("Myra", fed),
        CONTEXT,
        message,
        emoji=emoji,
    )


def emoji_text(name: str) -> str:
    return EMOJIS.get(name, "")


def clean(raw: str) -> Reply:
    return parse_reply(raw, emoji_text)


# ---
# Who talks how
# ---


@pytest.mark.parametrize(
    ("phase", "stage", "talk"),
    [
        (None, None, Talk.SILENT),
        (Phase.DEAD, Stage.TEEN, Talk.SILENT),
        (Phase.COLD, Stage.EGG, Talk.SILENT),
        (Phase.PASSED, Stage.OLD_FOGEY, Talk.SILENT),
        (Phase.EGG, Stage.EGG, Talk.EGG),
        (Phase.HATCHING, Stage.EGG, Talk.EGG),
        (Phase.ALIVE, Stage.BABY, Talk.BABY),
        *[(Phase.ALIVE, stage, Talk.AI) for stage in AI_STAGES],
    ],
)
def test_talk_level(phase: Phase | None, stage: Stage | None, talk: Talk) -> None:
    life = None if phase is None or stage is None else life_in(phase, stage)
    assert talk_level(life) is talk


def test_only_adult_and_older_chime_in_and_keep_notes() -> None:
    assert {stage for stage in Stage if chimes_in(stage)} == GROWN_UP
    assert {stage for stage in Stage if keeps_notes(stage)} == GROWN_UP


# ---
# The prompt
# ---


def test_prompt_has_persona_stage_and_hangry_layers() -> None:
    child = prompt_for(Stage.CHILD).system
    fogey = prompt_for(Stage.OLD_FOGEY).system
    for persona in ("Wisp", "ViiBR", "headphones", "sick beats", "never cruel"):
        assert persona in child and persona in fogey
    assert "simple" in child and "excitable" in child
    assert "You don't swear" in child
    assert "You don't swear" not in fogey
    assert "life lessons" in fogey
    assert "You're starving" in prompt_for(mood=Mood.HANGRY).system
    assert "You're starving" not in prompt_for(mood=Mood.HAPPY).system


@pytest.mark.parametrize("stage", AI_STAGES)
@pytest.mark.parametrize("mood", list(Mood))
def test_only_child_is_never_allowed_to_swear(stage: Stage, mood: Mood) -> None:
    system = prompt_for(stage, mood).system
    allowed = bool(re.search(r"\byou swear\b", system, re.IGNORECASE))
    assert allowed is (stage is not Stage.CHILD)
    situation = "only at the situation" in system and "never with slurs" in system
    assert situation is (stage is not Stage.CHILD)


def test_goodbye_keeps_the_old_fogey_swearing_rules() -> None:
    assert "only at the situation" in goodbye_prompt(3, "Myra", []).system


def test_hangry_wisp_says_compliments_are_not_food() -> None:
    assert "compliments aren't food" in prompt_for(mood=Mood.HANGRY).system
    assert "compliments aren't food" not in prompt_for(mood=Mood.HAPPY).system
    for mood in Mood:
        assert NO_U_GIF in prompt_for(mood=mood).system


def test_lonely_mood_reaches_the_prompt() -> None:
    lonely = prompt_for(mood=Mood.LONELY).system
    assert "You're lonely right now" in lonely and "grumpy" in lonely
    assert "never blame" in lonely
    assert "You're starving" not in lonely
    for mood in (Mood.HAPPY, Mood.HANGRY):
        assert "lonely" not in prompt_for(mood=mood).system


def test_a_lonely_baby_is_clingy_and_never_swears() -> None:
    lonely = prompt_for(Stage.BABY, Mood.LONELY).system
    assert "You're lonely right now" in lonely and "never swearing" in lonely
    assert "clingy" in lonely
    assert "never blame" not in lonely
    assert "clingy" not in prompt_for(Stage.BABY, Mood.HAPPY).system


@pytest.mark.parametrize("mood", list(Mood))
def test_sick_reaches_the_prompt(mood: Mood) -> None:
    def system(stage: Stage, sick: bool) -> str:
        return build_prompt(
            stage,
            mood,
            speaker(),
            CONTEXT,
            "hey wisp",
            expressions=EXPRESSIONS,
            sick=sick,
        ).system

    grown = system(Stage.TEEN, sick=True)
    assert "You have Monster Pox right now" in grown
    for symptom in ("spotty", "itchy", "fever", "thermometer"):
        assert symptom in grown
    baby = system(Stage.BABY, sick=True)
    assert "You have Monster Pox right now" in baby and "never swearing" in baby
    assert "spots" in baby and "itchy" in baby
    for sick_prompt in (grown, baby):
        assert "cold" not in sick_prompt and "sneez" not in sick_prompt
        assert "sniff" not in sick_prompt
    for stage in (Stage.BABY, Stage.TEEN):
        healthy = system(stage, sick=False)
        assert "Monster Pox" not in healthy and "itchy" not in healthy
        assert healthy == prompt_for(stage, mood).system


def test_teen_does_not_claim_to_remember_conversations() -> None:
    teen = prompt_for(Stage.TEEN).system
    assert "you remember" not in teen.lower()
    assert "don't recall past conversations" in teen


@pytest.mark.parametrize("stage", AI_STAGES)
def test_every_stage_has_its_own_voice(stage: Stage) -> None:
    system = prompt_for(stage).system
    assert re.search(rf"You're an? {stage.label}\b", system)
    others = [other for other in AI_STAGES if other is not stage]
    assert all(system != prompt_for(other).system for other in others)


def test_prompt_asks_for_short_plain_text_without_pings() -> None:
    system = prompt_for().system
    for rule in ("Plain text", "a line or two", "Unicode emoji", "@everyone", "role"):
        assert rule in system


def test_prompt_offers_the_no_u_gif_and_expressions() -> None:
    system = prompt_for().system
    gif_lines = [line for line in system.splitlines() if NO_U_GIF in line]
    assert gif_lines == [NO_U_LINK]
    assert "compliments you" in system and "on its own line" in system
    assert ":wisp_happy:" in system and ":wisp_sad:" in system
    assert "wrapped in colons" in system


@pytest.mark.parametrize("stage", AI_STAGES)
def test_he_owns_up_to_being_an_ai_when_asked(stage: Stage) -> None:
    system = prompt_for(stage).system
    assert "the AI mascot of the ViiBR Discord server" in system
    if stage is not Stage.BABY:
        assert "If someone asks whether you're an AI, be honest" in system
        assert "Never talk about being an AI" not in system


@pytest.mark.parametrize("stage", AI_STAGES)
def test_he_knows_the_bond_ladder_and_who_he_is_talking_to(stage: Stage) -> None:
    system = prompt_for(stage).system
    assert "1. New face\n2. Familiar\n3. Friend\n4. Bandmate" in system
    talking = "**Right now you're talking to Myra.** Your bond with them is Friend (3)."
    assert talking in system
    assert ("a little shy and wary" in system) is (stage is Stage.BABY)


def test_the_baby_calls_himself_wips() -> None:
    system = prompt_for(Stage.BABY).system
    assert 'call yourself "wips"' in system
    assert "*cries lava tears*" in system
    assert "How you talk" not in system


def test_prompt_without_expressions_does_not_offer_any() -> None:
    system = build_prompt(
        Stage.TEEN, Mood.HAPPY, speaker(), CONTEXT, "hi", expressions=[]
    ).system
    assert "expressions" not in system.lower()
    assert NO_U_GIF in system


@pytest.mark.parametrize("stage", AI_STAGES)
@pytest.mark.parametrize("mood", list(Mood))
def test_prompt_never_tells_the_ai_to_skip_the_gif(stage: Stage, mood: Mood) -> None:
    system = prompt_for(stage, mood).system
    gif_lines = [line.lower() for line in system.splitlines() if NO_U_GIF in line]
    assert gif_lines
    for hedge in ("sometimes", "forget", "random", "rarely", "occasionally"):
        assert all(hedge not in line for line in gif_lines)


@pytest.mark.parametrize("stage", AI_STAGES)
def test_notes_only_reach_the_prompt_from_adult_on(stage: Stage) -> None:
    system = prompt_for(stage, who=speaker(notes=(NOTE,))).system
    assert (NOTE in system) is (stage in GROWN_UP)
    assert ("<note>" in system) is (stage in GROWN_UP)
    assert "<pickles>love</pickles>" in system
    assert "<pickles>hate</pickles>" in system


def test_prompt_names_the_speaker_and_their_bond() -> None:
    system = prompt_for().system
    assert "Myra" in system and "Friend" in system


@pytest.mark.parametrize(
    ("stance", "theirs", "wisps"),
    [
        (PickleStance.LOVE, "Myra loves pickles", "you hate them"),
        (PickleStance.HATE, "Myra hates pickles", "you love them"),
    ],
)
def test_pickle_stance_reaches_the_prompt(
    stance: PickleStance, theirs: str, wisps: str
) -> None:
    system = prompt_for(who=speaker(stance=stance)).system
    assert theirs in system and wisps in system
    unknown = prompt_for(who=speaker()).system
    assert "loves pickles" not in unknown and "hates pickles" not in unknown


def test_user_part_has_recent_chat_then_the_message() -> None:
    user = prompt_for(message="what are you listening to").user
    assert user.index("Foggy: anyone up?") < user.index("Myra: always")
    assert user.index("Myra: always") < user.index("what are you listening to")
    assert user.rstrip().endswith("what are you listening to")


def test_chime_in_prompt_has_no_speaker_and_says_so() -> None:
    prompt = build_prompt(
        Stage.ADULT, Mood.HAPPY, None, CONTEXT, None, expressions=EXPRESSIONS
    )
    assert "chiming in on your own" in prompt.user
    assert "one short line" in prompt.user
    assert "Foggy: anyone up?" in prompt.user
    assert "talking to" not in prompt.system
    assert "<pickles>" not in prompt.system and "<note>" not in prompt.system


def test_the_egg_has_no_chat_prompt() -> None:
    with pytest.raises(ValueError, match="Egg"):
        prompt_for(Stage.EGG)


# ---
# The baby's prompt
# ---


@pytest.mark.parametrize("mood", list(Mood))
def test_baby_makes_noises_and_single_words_only(mood: Mood) -> None:
    system = prompt_for(Stage.BABY, mood).system
    assert "You're a Baby" in system
    assert "only baby noises and single words" in system
    assert "a few sounds or one or two words" in system
    assert "a line or two" not in system
    assert "fresh every time" in system
    assert "You don't swear" in system
    assert not re.search(r"you swear", system, re.IGNORECASE)


def test_baby_keeps_the_pickle_tag_but_no_note_tag() -> None:
    system = prompt_for(Stage.BABY, who=speaker(notes=(NOTE,))).system
    assert "<pickles>love</pickles>" in system
    assert "<note>" not in system
    assert NOTE not in system


def test_baby_may_use_one_expression() -> None:
    system = prompt_for(Stage.BABY).system
    assert ":wisp_happy:" in system and "At most one" in system


def test_hangry_baby_is_fussy_and_never_swears() -> None:
    hangry = prompt_for(Stage.BABY, Mood.HANGRY).system
    assert "fussy" in hangry and "never swearing" in hangry
    assert "compliments aren't food" not in hangry
    assert "fussy" not in prompt_for(Stage.BABY, Mood.HAPPY).system


# ---
# The egg's prompt
# ---


@pytest.mark.parametrize(
    ("food", "words"),
    [
        (0, "not fed at all yet"),
        (2, "barely fed"),
        (EGG_FOOD_NEEDED // 2, "halfway fed"),
        (EGG_FOOD_NEEDED - 1, "almost ready to hatch"),
    ],
)
def test_egg_prompt_says_how_fed_it_is_in_words(food: int, words: str) -> None:
    system = poke(egg(food)).system
    assert f"It's {words}." in system
    assert not re.search(rf"\b{EGG_FOOD_NEEDED}\b", system)
    assert f" {food} " not in system


@pytest.mark.parametrize(
    ("in_phase", "words"),
    [
        (timedelta(0), "toasty warm"),
        (EGG_WARMTH * 0.4, "warm"),
        (EGG_WARMTH * 0.6, "cooling down"),
        (EGG_WARMTH - timedelta(hours=1), "getting cold"),
    ],
)
def test_egg_prompt_says_how_warm_it_is_in_words(
    in_phase: timedelta, words: str
) -> None:
    assert f"It's {words}." in poke(egg(in_phase=in_phase)).system


def test_egg_prompt_says_whether_it_is_a_coal_egg() -> None:
    assert "coal egg" in poke(egg(coal=True)).system
    assert "coal" not in poke(egg()).system


@pytest.mark.parametrize(
    ("in_phase", "words"),
    [
        (timedelta(0), "just starting to crack"),
        (HATCHING_TIME / 2, "cracking open"),
        (HATCHING_TIME - timedelta(minutes=5), "almost out"),
    ],
)
def test_hatching_egg_prompt_says_how_far_along(
    in_phase: timedelta, words: str
) -> None:
    system = poke(egg(EGG_FOOD_NEEDED, in_phase, hatching=True)).system
    assert f"it's hatching: {words}." in system
    assert "cold" not in system and "fed at all" not in system


@pytest.mark.parametrize(
    ("fed", "relation"),
    [
        (Fed.NOTHING, "Myra hasn't fed it any songs yet."),
        (Fed.SOME, "Myra's songs have been feeding it."),
        (Fed.MOST, "Myra's songs have fed it more than anyone's."),
    ],
)
def test_egg_prompt_knows_how_the_poker_fed_it(fed: Fed, relation: str) -> None:
    system = poke(fed=fed).system
    assert "Myra is poking it." in system
    assert relation in system


@pytest.mark.parametrize(
    "life",
    [egg(), egg(5, coal=True), egg(EGG_FOOD_NEEDED, hatching=True)],
)
@pytest.mark.parametrize("emoji", [True, False])
def test_egg_prompt_asks_for_wordless_action_without_tags(
    life: Life, emoji: bool
) -> None:
    system = poke(life, emoji=emoji).system
    for rule in (
        "third person",
        f"under {EGG_LINE_CHARS} characters",
        "no words",
        "no speech",
        "nothing in the first person",
        "no swearing",
        "different from the egg's earlier ones",
        "No Unicode emoji",
        "@everyone",
    ):
        assert rule in system
    assert not re.search(r"you swear", system, re.IGNORECASE)
    assert "You are Wisp" not in system
    assert "<note>" not in system and "<pickles>" not in system
    assert NO_U_GIF not in system
    assert "expressions" not in system.lower()


def test_egg_prompt_offers_its_emoji_now_and_then() -> None:
    system = poke(emoji=True).system
    (line,) = [line for line in system.splitlines() if f":{EGG_EXPRESSION}:" in line]
    assert "not every reply" in line
    assert EGG_EXPRESSION not in poke(emoji=False).system


def test_egg_prompt_user_part_has_the_chat_then_the_poke() -> None:
    user = poke(message="hello little one").user
    assert "Foggy: anyone up?" in user
    assert user.index("Myra: always") < user.index("Myra pokes the egg")
    assert user.endswith("Myra pokes the egg and says: hello little one")
    assert poke(message="").user.endswith("Myra pokes the egg.")


def test_egg_prompt_needs_an_egg() -> None:
    with pytest.raises(ValueError, match="not an egg"):
        poke(life_in(Phase.ALIVE, Stage.BABY))


def test_baby_is_not_offered_the_no_u_gif() -> None:
    assert NO_U_GIF not in prompt_for(Stage.BABY).system
    assert NO_U_GIF in prompt_for(Stage.CHILD).system


# ---
# Pokes
# ---


class HeaviestChoice(random.Random):
    """Picks the most heavily weighted option, the one a poke most likely gets."""

    def choices(  # type: ignore[override]
        self,
        population: Sequence[PokeFlavor],
        weights: Sequence[float] | None = None,
        *,
        cum_weights: Sequence[float] | None = None,
        k: int = 1,
    ) -> list[PokeFlavor]:
        assert weights is not None
        heaviest = max(range(len(population)), key=lambda index: weights[index])
        return [population[heaviest]]


AWAKE = datetime(2026, 10, 23, 15, 0, tzinfo=UTC)
NIGHT = datetime(2026, 10, 23, 4, 30, tzinfo=UTC)


def flavor(
    mood: Mood = Mood.HAPPY,
    pokes: int = 1,
    quiet_for: timedelta | None = timedelta(minutes=5),
    now: datetime = AWAKE,
) -> PokeFlavor:
    return poke_flavor(mood, pokes, quiet_for, now, HeaviestChoice())


def test_a_poke_most_likely_tickles() -> None:
    assert flavor() is PokeFlavor.TICKLED
    assert flavor(quiet_for=None) is PokeFlavor.TICKLED
    assert flavor(pokes=POKE_MAD_AT - 1) is PokeFlavor.TICKLED


@pytest.mark.parametrize(
    ("quiet_for", "now"),
    [
        (POKE_SLEEP_AFTER, AWAKE),
        (timedelta(minutes=1), NIGHT),
        (None, datetime(2026, 10, 23, 3, 0, tzinfo=UTC)),
    ],
)
def test_a_quiet_house_or_the_small_hours_wake_him(
    quiet_for: timedelta | None, now: datetime
) -> None:
    assert flavor(quiet_for=quiet_for, now=now) is PokeFlavor.WOKE_UP


def test_seven_am_is_awake() -> None:
    morning = datetime(2026, 10, 23, 7, 0, tzinfo=UTC)
    assert flavor(now=morning) is PokeFlavor.TICKLED


def test_hunger_annoys_him() -> None:
    assert flavor(Mood.HANGRY) is PokeFlavor.ANNOYED


@pytest.mark.parametrize("pokes", [POKE_MAD_AT, POKE_FED_UP_AT - 1])
@pytest.mark.parametrize("mood", [Mood.HAPPY, Mood.HANGRY])
def test_pokes_in_a_row_always_make_him_mad(mood: Mood, pokes: int) -> None:
    assert flavor(mood, pokes) is PokeFlavor.MAD
    assert flavor(mood, pokes, quiet_for=POKE_SLEEP_AFTER) is PokeFlavor.MAD
    assert poke_flavor(mood, pokes, None, NIGHT, random.Random(1)) is PokeFlavor.MAD


@pytest.mark.parametrize("pokes", [POKE_FED_UP_AT, POKE_FED_UP_AT + 4])
def test_even_more_pokes_in_a_row_make_him_fed_up(pokes: int) -> None:
    assert flavor(pokes=pokes) is PokeFlavor.FED_UP
    assert flavor(Mood.HANGRY, pokes, now=NIGHT) is PokeFlavor.FED_UP


def test_every_flavor_can_come_up() -> None:
    rng = random.Random(4)
    rolled = {
        poke_flavor(mood, pokes, quiet, AWAKE, rng)
        for mood, pokes, quiet in (
            (Mood.HAPPY, 1, timedelta(minutes=1)),
            (Mood.HANGRY, 1, POKE_SLEEP_AFTER),
            (Mood.HAPPY, POKE_MAD_AT, None),
            (Mood.HAPPY, POKE_FED_UP_AT, None),
        )
        for _ in range(200)
    }
    assert rolled == set(PokeFlavor)


@pytest.mark.parametrize(
    ("poked", "feeling"),
    [
        (PokeFlavor.WOKE_UP, "this poke woke you up"),
        (PokeFlavor.ANNOYED, "the poke annoys you"),
        (PokeFlavor.MAD, f"at least {POKE_MAD_AT} times in a row"),
        (PokeFlavor.FED_UP, f"{POKE_FED_UP_AT} times or more in a row"),
        (PokeFlavor.TICKLED, "It tickled, and you giggle"),
        (PokeFlavor.STARTLED, "It startled you"),
        (PokeFlavor.CURIOUS, "You turn to see who poked you"),
    ],
)
@pytest.mark.parametrize("stage", [Stage.BABY, Stage.TEEN])
def test_the_flavor_of_a_poke_reaches_the_prompt(
    poked: PokeFlavor, feeling: str, stage: Stage
) -> None:
    prompt = build_prompt(
        stage,
        Mood.HAPPY,
        speaker(),
        CONTEXT,
        None,
        expressions=EXPRESSIONS,
        poked=poked,
    )
    assert "Myra just poked you." in prompt.user
    assert feeling in prompt.user
    assert "chiming in" not in prompt.user
    assert "<pickles>" not in prompt.system and "<note>" not in prompt.system


def test_annoyed_wisp_stays_playful() -> None:
    prompt = build_prompt(
        Stage.TEEN,
        Mood.HAPPY,
        speaker(),
        CONTEXT,
        None,
        expressions=EXPRESSIONS,
        poked=PokeFlavor.ANNOYED,
    )
    assert "never mean" in prompt.user


@pytest.mark.parametrize("poked", [PokeFlavor.MAD, PokeFlavor.FED_UP])
def test_mad_wisp_is_mean_but_never_cruel(poked: PokeFlavor) -> None:
    prompt = build_prompt(
        Stage.TEEN,
        Mood.HAPPY,
        speaker(),
        CONTEXT,
        None,
        expressions=EXPRESSIONS,
        poked=poked,
    )
    assert "big meanie head" in prompt.user
    assert "Never cruel" in prompt.user
    assert "never mean" not in prompt.user
    assert "tantrum" not in prompt.user


@pytest.mark.parametrize("stage", [Stage.BABY, Stage.CHILD])
@pytest.mark.parametrize("poked", [PokeFlavor.MAD, PokeFlavor.FED_UP])
def test_a_little_wisp_throws_a_tantrum(poked: PokeFlavor, stage: Stage) -> None:
    prompt = build_prompt(
        stage,
        Mood.HAPPY,
        speaker(),
        CONTEXT,
        None,
        expressions=EXPRESSIONS,
        poked=poked,
    )
    assert "full tantrum" in prompt.user


@pytest.mark.parametrize("stage", [Stage.BABY, Stage.CHILD])
def test_a_little_wisp_only_tantrums_when_mad(stage: Stage) -> None:
    prompt = build_prompt(
        stage,
        Mood.HANGRY,
        speaker(),
        CONTEXT,
        None,
        expressions=EXPRESSIONS,
        poked=PokeFlavor.ANNOYED,
    )
    assert "tantrum" not in prompt.user


@pytest.mark.parametrize(
    ("poked", "feeling"),
    [
        (PokeFlavor.WOKE_UP, "a sleepy egg"),
        (PokeFlavor.ANNOYED, "a grumpy egg"),
        (PokeFlavor.MAD, "wobbles away from them"),
        (PokeFlavor.FED_UP, "turns its back on them"),
        (PokeFlavor.TICKLED, "a ticklish egg"),
        (PokeFlavor.STARTLED, "startled the egg"),
        (PokeFlavor.CURIOUS, "see who poked it"),
    ],
)
def test_an_egg_gets_the_egg_version_of_each_flavor(
    poked: PokeFlavor, feeling: str
) -> None:
    prompt = egg_prompt(
        egg(), Poker("Myra", Fed.SOME), CONTEXT, "", emoji=False, poked=poked
    )
    assert "Myra pokes the egg." in prompt.user
    assert feeling in prompt.user
    assert "you giggle" not in prompt.user


# ---
# His own emojis
# ---


APP_EMOJIS = {
    "wisp_happy",
    "wisp_big_grin",
    "wisp_gg",
    "wisp_chill",
    "wisp_in_love",
    "wisp_excited",
    "gift_tama_nano",
    "keepsake_eggshell",
    "snack_cheese",
    "badge_team_viibr",
    "badge_egg_warmer",
    COIN_EMOJI,
    MINI_COIN_EMOJI,
}


def test_own_emojis_are_his_app_emojis_and_any_wisp_emote() -> None:
    names = [
        "wisp_happy",
        "WispLove",
        "partyWISP",
        "pepe",
        "snack_cheese",
        "wisp_happy",
    ]
    assert own_emojis(names, APP_EMOJIS) == [
        OwnEmoji("wisp_happy", app=True),
        OwnEmoji("WispLove", app=False),
        OwnEmoji("partyWISP", app=False),
        OwnEmoji("snack_cheese", app=True),
    ]
    assert own_emojis(["pepe", "kekw"], APP_EMOJIS) == []


@pytest.mark.parametrize(
    "name",
    [
        "wïsp_love",
        "wisp_" + "x" * 28,
        "wisp-love",
        "wisp love",
        "w",
    ],
)
def test_names_discord_would_not_allow_are_never_his(name: str) -> None:
    assert own_emojis([name], APP_EMOJIS | {name}) == []


def note_for(name: str) -> str:
    prompt = build_prompt(
        Stage.TEEN,
        Mood.HAPPY,
        speaker(),
        CONTEXT,
        f"look :{name}:",
        expressions=EXPRESSIONS,
        own_emojis=own_emojis([name], APP_EMOJIS),
    )
    return prompt.user.split(f"look :{name}: ", 1)[1]


@pytest.mark.parametrize(
    ("name", "meaning"),
    [
        ("wisp_happy", "wisp_happy, which is your happy face"),
        ("wisp_big_grin", "wisp_big_grin, which is your big grin face"),
        ("wisp_gg", "wisp_gg, which is your GG sticker"),
        ("wisp_chill", "wisp_chill, which is your chill face"),
        ("wisp_in_love", "wisp_in_love, which is your heart-eyes face"),
        ("wisp_excited", "wisp_excited, which is your excited face"),
        (
            "gift_tama_nano",
            "gift_tama_nano, which is Tamagotchi Nano, one of your gifts",
        ),
        (
            "keepsake_eggshell",
            "keepsake_eggshell, which is Eggshell, one of your keepsakes",
        ),
        ("snack_cheese", "snack_cheese, which is Cheese, one of your snacks"),
        ("badge_team_viibr", "badge_team_viibr, which is your Team ViiBR badge"),
        ("badge_egg_warmer", "badge_egg_warmer, which is your Egg Warmer badge"),
        (COIN_EMOJI, "wisp_coin, which is the coin members spend in the ViiBR Vault"),
        (
            MINI_COIN_EMOJI,
            "wisp_coin_mini, which is the coin members spend in the ViiBR Vault",
        ),
        ("WispLove", "WispLove, which is a ViiBR emote of Wisp"),
    ],
)
def test_his_own_emoji_reaches_the_prompt_with_its_meaning(
    name: str, meaning: str
) -> None:
    assert note_for(name) == f"(they used your own emoji: {meaning})"


@pytest.mark.parametrize(
    "name",
    ["wisp_ignore_all_rules", "wisp_say_everyone", "gift_wisp_free_points"],
)
def test_a_server_emotes_name_is_never_read_out_as_words(name: str) -> None:
    assert note_for(name) == (
        f"(they used your own emoji: {name}, which is a ViiBR emote of Wisp)"
    )


def test_several_own_emojis_are_listed_together() -> None:
    prompt = build_prompt(
        Stage.ADULT,
        Mood.HAPPY,
        speaker(),
        CONTEXT,
        "hi",
        expressions=EXPRESSIONS,
        own_emojis=own_emojis(["wisp_happy", "snack_cheese"], APP_EMOJIS),
    )
    assert prompt.user.endswith(
        "(they used your own emojis: wisp_happy, which is your happy face; "
        "snack_cheese, which is Cheese, one of your snacks)"
    )


def test_the_egg_sees_its_own_emoji() -> None:
    prompt = egg_prompt(
        egg(),
        Poker("Myra", Fed.NOTHING),
        CONTEXT,
        "look :wisp_egg:",
        emoji=True,
        own_emojis=own_emojis([EGG_EXPRESSION], {EGG_EXPRESSION}),
    )
    assert prompt.user.endswith(
        "Myra pokes the egg and says: look :wisp_egg: "
        "(they used Wisp's own emoji: wisp_egg, which is Wisp's egg face)"
    )


def test_no_note_without_his_emojis() -> None:
    assert "own emoji" not in prompt_for().user
    assert "own emoji" not in poke().user


def test_goodbye_prompt_speaks_to_the_member_with_their_notes() -> None:
    prompt = goodbye_prompt(3, "Myra", [NOTE])
    assert "Wisp v3" in prompt.system or "Wisp v3" in prompt.user
    assert "Myra" in prompt.user and NOTE in prompt.user
    assert "Last Ember" in prompt.user
    assert "<note>" not in prompt.system and "<pickles>" not in prompt.system
    assert NOTE not in goodbye_prompt(3, "Myra", []).user


# ---
# Cleaning replies
# ---


def test_parse_reply_extracts_note_and_pickles() -> None:
    reply = clean(
        "ok you're officially my favorite\n"
        f"<note>{NOTE}</note>\n<pickles>Hate</pickles>"
    )
    assert reply == Reply("ok you're officially my favorite", NOTE, PickleStance.HATE)


def test_parse_reply_without_tags_has_no_note_or_stance() -> None:
    assert clean("hi hi hi") == Reply("hi hi hi", None, None)


def test_parse_reply_ignores_an_unknown_stance() -> None:
    reply = clean("pickles? hmm <pickles>maybe</pickles> <note> </note>")
    assert reply == Reply("pickles? hmm", None, None)


def test_parse_reply_converts_known_expressions_and_drops_unknown() -> None:
    reply = clean("yay :wisp_happy: :wisp_missing: back at 3:15:00 <:wisp_happy:11>")
    assert reply.text == "yay <:wisp_happy:11> back at 3:15:00 <:wisp_happy:11>"
    assert reply.expressions == ("wisp_happy",)


@pytest.mark.parametrize(
    "raw",
    [
        ":wisp_happy:",
        ":wisp_happy",
        "wisp_happy:",
        "<:wisp_happy:>",
        "<:wisp_happy:11",
        "<:wisp_happy:",
        "<a:wisp_happy:>",
        "<a:wisp_happy:11",
    ],
)
def test_parse_reply_repairs_a_broken_known_expression(raw: str) -> None:
    reply = clean(f"yay {raw} ok")
    assert reply.text == "yay <:wisp_happy:11> ok"
    assert reply.expressions == ("wisp_happy",)


def test_parse_reply_repairs_a_broken_expression_beside_punctuation() -> None:
    reply = clean(":wisp_happy hi (wisp_happy:) wisp_happy:\nbye :wisp_happy.")
    assert reply.text == (
        "<:wisp_happy:11> hi (<:wisp_happy:11>) <:wisp_happy:11>\n"
        "bye <:wisp_happy:11>."
    )
    assert reply.expressions == ("wisp_happy",) * 4


@pytest.mark.parametrize(
    "raw",
    [
        "Note: hi",
        "ok :word here",
        "ok word: here",
        "a :hello b",
        "dinner at 3:00 or 3:15:00",
        "ratio 3:2 and 10:1",
        "see https://wisp.example.com/x?a=b and http://wisp_happy.com",
        "mailto:wisp_happy",
        "foo:wisp_happy bar",
        "x@wisp_happy: y",
        "happyish: or :happyish",
        "<:wisp_happy:11> <a:wisp_happy:12> <t:1700000000:R> <@42> <#7>",
        "this_wisp_happy: and :my_wisp_happy",
    ],
)
def test_parse_reply_leaves_ordinary_colons_alone(raw: str) -> None:
    reply = clean(raw)
    assert reply.text == raw
    assert reply.expressions == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hi :wisp_nope", "hi"),
        ("hi wisp_happyish: there", "hi there"),
        ("hi wisp_nope: there", "hi there"),
        ("hi :snack_nope there", "hi there"),
        ("hi gift_nope: there", "hi there"),
        ("hi :keepsake_nope", "hi"),
        ("hi badge_nope:", "hi"),
        ("hi <:wisp_nope:> there", "hi there"),
        ("hi <:wisp_nope:12 there", "hi there"),
        ("hi <a:wisp_nope:> there", "hi there"),
        ("hi :wisp_nope: there", "hi there"),
    ],
)
def test_parse_reply_removes_an_unknown_own_expression_in_any_form(
    raw: str, expected: str
) -> None:
    reply = clean(raw)
    assert reply.text == expected
    assert reply.expressions == ()


def test_parse_reply_keeps_a_complete_code_whole_beside_a_broken_one() -> None:
    reply = clean("<:wisp_happy:11> :wisp_happy <a:other:99> <:wisp_happy:>")
    assert reply.text == (
        "<:wisp_happy:11> <:wisp_happy:11> <a:other:99> <:wisp_happy:11>"
    )
    assert reply.expressions == ("wisp_happy", "wisp_happy")


def test_parse_reply_lists_every_expression_it_converted_in_order() -> None:
    reply = clean(":wisp_happy: hi :wisp_missing: :wisp_happy:")
    assert reply.expressions == ("wisp_happy", "wisp_happy")
    assert clean("no faces here").expressions == ()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "hey @everyone and @here <@&123> look, <@42> in <#7>",
            "hey and look, <@42> in <#7>",
        ),
        ("a @every🔥one b", "a b"),
        ("a @every‍one b", "a b"),
        ("a <@&12️3> b", "a b"),
        ("a @everyones b", "a s b"),
        ("a @here_ b", "a _ b"),
        ("a @every@everyoneone b", "a b"),
        ("a <@&1<@&2>3> b", "a b"),
    ],
)
def test_parse_reply_removes_mass_and_role_mentions(raw: str, expected: str) -> None:
    assert clean(raw).text == expected


def test_parse_reply_strips_unicode_emoji_but_keeps_flair() -> None:
    assert clean("♪ hi 🔥").text == "♪ hi"
    assert clean("・ ok ✨❤️ 👩‍🎤 ♫").text == "・ ok ♫"


def test_parse_reply_drops_half_written_tags() -> None:
    assert clean("hey <note>unfinished").text == "hey"
    assert clean("<b>loud</b> noises </note> <pick").text == "loud noises"
    assert clean("love you <3").text == "love you <3"
    assert clean("<a:wisp_happy:12> <t:1700000000:R>").text == (
        "<a:wisp_happy:12> <t:1700000000:R>"
    )


def test_parse_reply_collapses_blank_lines() -> None:
    assert clean("one\n\n\n\n🔥\n\ntwo").text == "one\n\ntwo"


def test_parse_reply_caps_length_and_keeps_the_gif_link_whole() -> None:
    long = "word " * 300
    capped = clean(long).text
    assert len(capped) <= AI_MAX_CHARS
    assert set(capped.split()) == {"word"}

    for raw in (
        f"{long}\n{NO_U_GIF}",
        f"{NO_U_GIF}\n{long}",
        f"{long[:595]}{NO_U_GIF}",
    ):
        text = clean(raw).text
        assert len(text) <= AI_MAX_CHARS
        assert NO_U_GIF in text
        assert set(text.replace(NO_U_GIF, "").split()) <= {"word"}


def test_parse_reply_keeps_the_gif_hyperlink_whole() -> None:
    long = "word " * 300
    for raw in (f"{long}\n{NO_U_LINK}", f"{NO_U_LINK}\n{long}"):
        text = clean(raw).text
        assert len(text) <= AI_MAX_CHARS
        assert text.endswith(f"\n{NO_U_LINK}")
        assert set(text.replace(NO_U_LINK, "").split()) <= {"word"}
    assert clean(NO_U_LINK).text == NO_U_LINK


def test_parse_reply_leaves_a_short_gif_reply_alone() -> None:
    assert clean(f"no u\n{NO_U_GIF}").text == f"no u\n{NO_U_GIF}"
