"""Build wisp/data/common_words.txt, the words Wisp himself may rhyme with.

Run once from the project root with the dev requirements installed:

    python tools/build_common_words.py

It takes the most frequent English words from wordfreq, keeps lowercase
alphabetic words of two or more letters that the CMU Pronouncing Dictionary
knows, drops abbreviations said letter by letter (tv, dna), profanity and
slurs, and writes the first WORD_COUNT of them in frequency order, one per
line.
"""

import re
from pathlib import Path
from typing import Final

import pronouncing
from wordfreq import top_n_list

WORD_COUNT: Final = 5000
SCAN: Final = 30000
OUTPUT: Final = Path(__file__).resolve().parent.parent / "wisp/data/common_words.txt"
_WORD: Final = re.compile(r"[a-z]{2,}")

BLOCKLIST: Final = frozenset(
    {
        "abortion", "anal", "arse", "ass", "asses", "asshole", "bastard", "bitch",
        "bitches", "bitchy", "bloody", "blowjob", "bollocks", "boob", "boobs", "breast",
        "bullshit", "butt", "chink", "clinton", "clit", "cock", "cocks", "coon", "crap",
        "cum", "cunt", "damn", "dick", "dicks", "dildo", "drug", "drugs", "dumb",
        "dyke", "fag", "faggot", "fags", "fuck", "fucked", "fucker", "fuckin",
        "fucking", "fucks", "gay", "goddamn", "hell", "hillary", "hitler", "hoe",
        "hoes", "homo", "horny", "idiot", "isis", "islam", "islamic", "jewish", "jews",
        "jizz", "kike", "marijuana", "milf", "murder", "murdered", "muslim", "muslims",
        "naked", "nazi", "nazis", "nigga", "niggas", "nigger", "niggers", "nipple",
        "nipples", "nude", "nudes", "obama", "orgasm", "penis", "piss", "pissed",
        "porn", "porno", "prick", "pussy", "racism", "racist", "rape", "raped",
        "rapist", "retard", "retarded", "screw", "sex", "sexual", "sexy", "shit",
        "shits", "shitty", "slave", "slavery", "slut", "sluts", "spic", "stupid",
        "suck", "sucks", "suicide", "terror", "terrorism", "terrorist", "terrorists",
        "tit", "tits", "titties", "tranny", "trump", "twat", "ugly", "vagina", "virgin",
        "wank", "wanker", "weed", "wetback", "whore", "whores",
    }
)  # fmt: skip


def _spoken_as_a_word(word: str) -> bool:
    """Whether the dictionary knows the word and never spells it out."""
    phones: list[str] = pronouncing.phones_for_word(word)
    return bool(phones) and all(
        pronouncing.syllable_count(pronunciation) < len(word)
        for pronunciation in phones
    )


def common_words() -> list[str]:
    """The first WORD_COUNT frequent words that pass every filter, in order."""
    kept: list[str] = []
    for word in top_n_list("en", SCAN):
        if _WORD.fullmatch(word) and word not in BLOCKLIST and _spoken_as_a_word(word):
            kept.append(word)
            if len(kept) == WORD_COUNT:
                return kept
    raise RuntimeError(f"Only {len(kept)} words passed; scan more than {SCAN}.")


def main() -> None:
    """Write the word list and say how many words it holds."""
    words = common_words()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(words) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {len(words)} words to {OUTPUT}")


if __name__ == "__main__":
    main()
