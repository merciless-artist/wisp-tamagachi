"""The languages a Rhyme Duel can be played in."""

from enum import StrEnum
from typing import Final


class Language(StrEnum):
    """A Rhyme Duel language, stored by its two-letter code."""

    EN = "en"
    ES = "es"
    FR = "fr"


LANGUAGE_NAMES: Final[dict[Language, str]] = {
    Language.EN: "English",
    Language.ES: "Español",
    Language.FR: "Français",
}
