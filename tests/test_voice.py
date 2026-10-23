"""Tests for Wisp's voice: who talks how, his prompts and reply cleaning."""

import re
from datetime import UTC, datetime

import pytest

from ai.prompt import Prompt
from wisp.bond import PickleStance
from wisp.life import Life, Mood, Phase, new_egg
from wisp.rules import AI_MAX_CHARS, Stage
from wisp.voice import (
    NO_U_GIF,
    ChatLine,
    Reply,
    Speaker,
    Talk,
    build_prompt,
    chimes_in,
    goodbye_prompt,
    keeps_notes,
    parse_reply,
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
        (Phase.EGG, Stage.EGG, Talk.POKE),
        (Phase.HATCHING, Stage.EGG, Talk.POKE),
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
    for persona in ("Wisp", "ViiBR", "headphones", "3 AM", "never cruel"):
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
    assert len(gif_lines) == 1
    assert "compliment" in gif_lines[0] and "on its own line" in gif_lines[0]
    assert ":wisp_happy:" in system and ":wisp_sad:" in system


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


def test_baby_and_egg_have_no_ai_prompt() -> None:
    for stage in (Stage.EGG, Stage.BABY):
        with pytest.raises(ValueError, match=stage.label):
            prompt_for(stage)


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


def test_parse_reply_leaves_a_short_gif_reply_alone() -> None:
    assert clean(f"no u\n{NO_U_GIF}").text == f"no u\n{NO_U_GIF}"
