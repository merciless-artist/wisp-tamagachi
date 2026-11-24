"""The Rhyme Duel's own words in each language, and the language picker post."""

from dataclasses import dataclass
from typing import Final

from wisp.language import Language

# ---
# Duel text
# ---


@dataclass(frozen=True)
class DuelText:
    """What a duel says around Wisp's lines, in one language.

    `word_line` takes `{word}`, `already_used` takes `{answer}`,
    `no_rhyme_with` takes `{answer}` and `{word}`, and `score_line` takes
    `{points}`, as `points` writes it. `picked` is the note the language
    picker becomes once this language is chosen.
    """

    word_line: str
    timed_out: str
    not_one_word: str
    already_used: str
    no_rhyme_with: str
    score_line: str
    point: str
    points_noun: str
    zero_is_singular: bool
    picked: str

    def points(self, amount: int) -> str:
        """`amount` with the singular noun for one (and zero, when the language
        says so) and the plural noun otherwise."""
        singular = amount == 1 or (amount == 0 and self.zero_is_singular)
        return f"{amount} {self.point if singular else self.points_noun}"


DUEL_TEXT: Final[dict[Language, DuelText]] = {
    Language.EN: DuelText(
        word_line="・The word to rhyme is: {word}",
        timed_out="Time ran out",
        not_one_word="That wasn't one word",
        already_used="{answer} was already used",
        no_rhyme_with="{answer} doesn't rhyme with {word}",
        score_line="・Score: {points}",
        point="point",
        points_noun="points",
        zero_is_singular=False,
        picked="♪ We rhyme in English.",
    ),
    Language.ES: DuelText(
        word_line="・La palabra para rimar es: {word}",
        timed_out="Se acabó el tiempo",
        not_one_word="Eso no era una sola palabra",
        already_used="{answer} ya se usó",
        no_rhyme_with="{answer} no rima con {word}",
        score_line="・Puntuación: {points}",
        point="punto",
        points_noun="puntos",
        zero_is_singular=False,
        picked="♪ Rimamos en español.",
    ),
    Language.FR: DuelText(
        word_line="・Le mot à faire rimer, c'est {word}",
        timed_out="Le temps est écoulé",
        not_one_word="Ce n'était pas un seul mot",
        already_used="{answer} a déjà été dit",
        no_rhyme_with="{answer} ne rime pas avec {word}",
        score_line="・Score : {points}",
        point="point",
        points_noun="points",
        zero_is_singular=True,
        picked="♪ On rime en français.",
    ),
}

# ---
# Language picker
# ---

LANGUAGE_PICKER: Final = (
    "♪ Which language should we rhyme in?\n"
    "・¿En qué idioma rimamos?\n"
    "・On rime en quelle langue ?\n"
    "・Change it any time with /wisp play rhyme."
)
"""The post that asks a member which language their Rhyme Duels are in."""
