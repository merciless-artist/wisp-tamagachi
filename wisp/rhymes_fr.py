"""French rhyme keys, read from the spelling.

French spelling is regular enough to read aloud by rule: drop the silent
letters at the end, then read the rest left to right with an ordered table of
letter patterns, the first match winning. A short table of whole words covers
the ones the rules get wrong. Each phone is one character, so readings are
plain strings:

    vowels      a e (é) E (è) i o u (ou) y (u) 2 (eu, a final schwa)
                @ (inner schwa) A (an) I (in, un) O (on)
    glides      j w H
    consonants  p b t d k g f v s z m n l S (ch) Z (j) N (gn) R

A player's word only counts when it is a known word, or reaches one through
the accent map in `data/`, so `ete` reads as `été` while a made-up word like
`blorpaison` is rejected. The known words are the frequent-word list in
`data/` and every word form of Lexique 3.83 (New, Pallier et al., CC BY-SA
4.0). A Lexique word is heard as Lexique says (its `phon`, in these phones),
plus any reading the whole-word table gives it; every other word is read by
the rules. Whether a final -ent is silent (ils parlent) or not (un moment)
comes from a list in `data/`.
"""

import re
import unicodedata
from functools import cache
from pathlib import Path
from typing import Final

from wisp.language import Language
from wisp.rhyme_keys import WordKeys, known_spellings, merge, read_accents

__all__ = [
    "ELIDED",
    "RHYME_VOWELS",
    "WORD",
    "keys",
    "keys_of",
    "phones_of",
    "readings",
    "tail",
]

_LETTERS: Final = "a-zàâäéèêëîïôöùûüÿœæç"
WORD: Final = re.compile(rf"[{_LETTERS}]+(?:['-][{_LETTERS}]+)*")
ELIDED: Final = frozenset(
    {"l", "d", "j", "m", "n", "s", "t", "c", "qu", "jusqu", "lorsqu", "puisqu"}
)

_DATA: Final = Path(__file__).resolve().parent / "data"
_KNOWN_FILE: Final = _DATA / "known_words_fr.txt"
_ACCENTS_FILE: Final = _DATA / "accents_fr.txt"
_SILENT_ENT_FILE: Final = _DATA / "silent_ent_fr.txt"
_LEXIQUE_FILE: Final = _DATA / "lexique_fr.txt"

_TAIL: Final = re.compile(rf"[{_LETTERS}]+")
_PARTS: Final = re.compile(r"['-]")
_MUTE: Final = "ə"
_V: Final = "aàâäeéèêëiîïoôöuùûüyÿœæ"
_VOWEL_GROUP: Final = re.compile(f"[{_V}]+")
_PHONE_VOWELS: Final = frozenset("aeEiouy2@AIO")
RHYME_VOWELS: Final = _PHONE_VOWELS - {"@"}
_GLIDES: Final = {"i": "j", "u": "w", "y": "H"}
_SLANT: Final = {"E": "e", "@": "2"}

# ---
# Listed words
# ---

WHOLE: Final[dict[str, frozenset[str]]] = {
    word: frozenset(reads.split())
    for word, reads in {
        "est": "E Est", "es": "E", "et": "e", "les": "le", "des": "de", "mes": "me",
        "tes": "te", "ses": "se", "ces": "se", "eu": "y", "eus": "y", "eut": "y",
        "oignon": "oNO", "femme": "fam", "monsieur": "m@sj2", "pays": "pei",
        "fils": "fis", "plus": "ply plys", "tous": "tu tus", "os": "os o",
        "six": "sis", "dix": "dis", "huit": "Hit", "sept": "sEt", "août": "u ut",
        "œil": "2j", "second": "s@gO", "seconde": "s@gOd", "ville": "vil",
        "mille": "mil", "tranquille": "tRAkil", "village": "vilaZ",
        "million": "miljO", "client": "klijA", "parfum": "paRfI", "aux": "o",
        "écho": "eko", "chorale": "koRal", "orchestre": "oRkEstR",
        "technique": "tEknik", "chœur": "k2R", "œuf": "2f", "bœuf": "b2f",
        "œufs": "2", "bœufs": "b2", "hier": "jER", "fier": "fjER", "dessus": "d@sy",
        "dessous": "d@su", "clef": "kle",
    }.items()
}  # fmt: skip
"""Whole-word readings the rules get wrong."""

KEEP_FINAL_S: Final = frozenset(
    {
        "as", "hélas", "mars", "ours", "sens", "maïs", "jadis", "oasis", "tennis",
        "iris", "lys", "virus", "bonus", "campus", "cactus", "terminus", "bus",
        "autobus", "rébus", "consensus", "processus", "atlas", "ananas", "albatros",
        "cosmos", "bis", "gratis", "humus", "lotus", "papyrus", "index", "lynx",
        "sphinx", "thorax", "larynx", "silex", "fax", "box", "relax", "latex",
        "phénix", "onyx", "codex", "vortex",
    }
)  # fmt: skip
"""Words whose final s or x is heard."""

ET_SOUNDED: Final = frozenset(
    {
        "net", "ouest", "test", "zest", "internet", "toast", "but", "brut", "chut",
        "kit", "granit", "transit", "déficit", "mat", "dot", "set", "jet", "budget",
    }
)  # fmt: skip
"""Words whose final t is heard, -et words among them."""

KEEP_FINAL_C: Final = frozenset(
    {"sud", "raid", "cap", "stop", "top", "rap", "clip", "slip", "gaz", "quiz", "fez"}
)
"""Words whose final d, p or z is heard."""

ER_OPEN: Final = frozenset(
    {
        "mer", "hiver", "enfer", "amer", "super", "cancer", "laser", "hamster",
        "poster", "master", "leader", "joker", "revolver", "éther", "cuiller",
    }
)  # fmt: skip
"""Words whose final -er is heard as in mer, not as é."""

SILENT_FINAL_C: Final = frozenset(
    {
        "tabac", "estomac", "porc", "caoutchouc", "croc", "escroc", "clerc", "nerf",
        "cerf", "gentil", "outil", "fusil", "persil", "sourcil", "nombril", "chenil",
        "fournil", "saoul", "soûl", "pouls", "respect", "aspect", "instinct",
        "distinct",
    }
)  # fmt: skip
"""Words whose final c, f, l or -ct is silent."""

ENT_SILENT: Final = frozenset(
    {"rient", "lient", "nient", "fient", "peuvent", "savent", "veulent", "doivent"}
)
ENT_BOTH: Final = frozenset(
    {
        "content", "couvent", "président", "résident", "parent", "violent", "ferment",
        "excellent", "différent", "convergent", "divergent", "émergent", "influent",
        "affluent", "négligent", "précédent", "adhérent", "équivalent", "somnolent",
        "expédient", "coïncident",
    }
)  # fmt: skip
"""-ent words read both as a verb (silent) and as a noun or adjective."""

ENT_NASAL: Final = frozenset(
    {"comment", "urgent", "évident", "souvent", "moment", "argent", "torrent"}
)

# ---
# The body table
# ---

_VM: Final = f"[{_V}{_MUTE}]"
_OPEN: Final = f"(?![{_V}{_MUTE}mnh])"
_FRONT: Final = f"[eéèêëiîïy{_MUTE}]"
_CONSONANT: Final = f"[^{_V}{_MUTE}]"

_RULES: Final[tuple[tuple[re.Pattern[str], str], ...]] = tuple(
    (re.compile(pattern), phones)
    for pattern, phones in (
        (r"eaux?", "o"),
        (r"œu|oeu|œ", "2"),
        (r"ouill", "uj"),
        (r"ouil$", "uj"),
        (f"ou(?=[{_V}])", "w"),
        (r"o[uùû]", "u"),
        (f"oin(?!{_VM}|n)", "wI"),
        (f"o(?=y{_VM})", "wa"),
        (r"o[iî]", "wa"),
        (f"[ae]in(?!{_VM}|n)|aim(?![{_V}{_MUTE}m])", "I"),
        (r"aill", "aj"),
        (r"eill", "Ej"),
        (r"euill|ueill", "2j"),
        (r"ail$", "aj"),
        (r"eil$", "Ej"),
        (r"euil$", "2j"),
        (f"a(?=y{_VM})", "E"),
        (r"a[iîy]|ei", "E"),
        (r"au", "o"),
        (r"e[uû]", "2"),
        (r"ienc", "jAs"),
        (f"ien(?!{_VM}|n)", "jI"),
        (r"éen$", "eI"),
        (r"yen$", "jI"),
        (r"emm", "am"),
        (f"^ex(?={_VM}|h)", "Egz"),
        (f"[ae][mn]{_OPEN}", "A"),
        (r"um$", "om"),
        (f"[iyu][mn]{_OPEN}", "I"),
        (f"o[mn]{_OPEN}", "O"),
        (f"(?<={_CONSONANT})ill", "ij"),
        (r"^ill", "il"),
        (f"uin(?!{_VM}|n)", "HI"),
        (r"ui", "Hi"),
        (f"u(?=[{_V}])", "H"),
        (f"i(?=[{_V}])", "j"),
        (f"y(?={_VM})", "j"),
        (r"[éëæ]", "e"),
        (r"[èê]", "E"),
        (r"[aàâä]", "a"),
        (r"[iîïyÿ]", "i"),
        (r"[oôö]", "o"),
        (r"[uûü]", "y"),
        (r"ù", "u"),
        (r"e(?=x)", "E"),
        (
            f"e(?!ch|ph|th|gn|[bcdfgkptv][lr])(?={_CONSONANT}{_CONSONANT})",
            "E",
        ),
        (f"e(?={_CONSONANT}$)", "E"),
        (r"e", "@"),
        (r"sch|ch(?![rln])|sh", "S"),
        (r"ch", "k"),
        (r"ph", "f"),
        (r"th", "t"),
        (r"gn", "N"),
        (f"cc(?={_FRONT})", "ks"),
        (f"c(?={_FRONT})|ç", "s"),
        (r"cqu|qu|q|ck|cc|c", "k"),
        (f"gu(?={_FRONT})", "g"),
        (r"ge(?=[aoâôu])", "Z"),
        (f"g(?={_FRONT})", "Z"),
        (r"(?<=n)g(?=t)", ""),
        (r"gg|g", "g"),
        (f"(?<=[st])tio(?=n(?:{_VM}|n))", "tjo"),
        (f"tio(?=n(?:{_VM}|n))", "sjo"),
        (r"(?<=[st])tion", "tjO"),
        (r"tion", "sjO"),
        (r"ti(?=el|al|eu)", "sj"),
        (f"(?<=[{_V}])s(?={_VM})", "z"),
        (r"ss|sc(?=[eéèêiîy])|s", "s"),
        (r"x(?=ième)", "z"),
        (r"x", "ks"),
        (f"h|{_MUTE}", ""),
        (r"jj?", "Z"),
        (r"rr?", "R"),
        (r"([bdfklmnptvwz])\1?", r"\1"),
    )
)


def _body(body: str) -> str:
    """The phones of a spelling whose silent ending is already gone."""
    phones: list[str] = []
    position = 0
    while position < len(body):
        for pattern, replacement in _RULES:
            match = pattern.match(body, position)
            if match and match.end() > position:
                phones.append(match.expand(replacement))
                position = match.end()
                break
        else:
            position += 1
    return "".join(phones)


# ---
# Silent endings
# ---


def _strip_consonants(word: str, spelling: str) -> str:
    """`word` without its silent final consonants, two at most.

    `spelling` is the whole word, for the listed exceptions. An e left at the
    end by the strip is heard as è (respect).
    """
    for _ in range(2):
        last = word[-1]
        if word.endswith(("mpt", "gt")):
            stripped = word[:-2]
        elif word.endswith("ct"):
            if spelling not in SILENT_FINAL_C:
                break
            stripped = word[:-2]
        elif word.endswith("pt"):
            break
        elif last == "t" and spelling not in ET_SOUNDED:
            stripped = word[:-1]
        elif last in "dpz" and spelling not in KEEP_FINAL_C:
            stripped = word[:-1]
        elif word.endswith(("ng", "nc", "mb")):
            stripped = word[:-1]
        elif last in "cflb" and spelling in SILENT_FINAL_C:
            stripped = word[:-1]
        else:
            break
        if not _VOWEL_GROUP.search(stripped):
            break
        word = stripped[:-1] + "è" if stripped.endswith("e") else stripped
    return word


def _split_tail(spelling: str) -> tuple[str, str]:
    """A spelling as a body to read and the phones its ending adds.

    A mute final e becomes the marker ə, which is never heard but keeps the
    letters before it as they sound (porte, chose, une).
    """
    if re.search(f"(?<![qg])[{_V}]es?$", spelling):
        return re.sub("es?$", _MUTE, spelling), ""
    if len(_VOWEL_GROUP.findall(spelling)) >= 2 and re.search("es?$", spelling):
        return re.sub("es?$", _MUTE, spelling), ""
    word = spelling
    if word[-1] in "sx" and spelling not in KEEP_FINAL_S and len(word) > 2:
        word = word[:-1]
    if word.endswith(("ez", "ed")) and len(word) > 2:
        return word[:-2] + _MUTE, "e"
    if word.endswith("et") and len(word) > 2 and spelling not in ET_SOUNDED:
        return word[:-2] + _MUTE, "E"
    if word.endswith("er") and len(word) > 2:
        if (
            spelling in ER_OPEN
            or not _VOWEL_GROUP.search(word[:-2])
            or spelling.endswith("vers")
        ):
            return word[:-2] + _MUTE, "ER"
        return word[:-2] + _MUTE, "e"
    word = _strip_consonants(word, spelling)
    if word.endswith("er") and len(word) > 2:
        return word[:-2] + _MUTE, "ER"
    return word, ""


def _ent_endings(spelling: str, silent_ent: frozenset[str]) -> tuple[bool, ...]:
    """For a spelling ending in -ent, whether each of its readings is silent."""
    if spelling.endswith("aient") or spelling in ENT_SILENT:
        return (True,)
    if spelling in ENT_BOTH:
        return (True, False)
    if spelling in ENT_NASAL or len(spelling) < 5:
        return (False,)
    return (spelling in silent_ent,)


def _reading(spelling: str, silent: bool) -> str:
    """One reading of a spelling, with a final -ent silent or not."""
    if silent:
        body, extra = spelling[:-3] + _MUTE, ""
    elif spelling.endswith("ient"):
        heard = "jI" if re.search("(?<![ao])[tv]ient$", spelling) else "jA"
        body, extra = spelling[:-4], heard
    else:
        body, extra = _split_tail(spelling)
    phones = _body(body)
    if extra[:1] in _PHONE_VOWELS and phones[-1:] in _GLIDES:
        phones = phones[:-1] + _GLIDES[phones[-1]]
    phones = re.sub(r"(.)\1+", r"\1", phones + extra)
    return phones[:-1] + "2" if phones.endswith("@") else phones


def phones_of(spelling: str, silent_ent: frozenset[str]) -> frozenset[str]:
    """Every reading of one spelling (no elision) as phones; empty when unreadable.

    `silent_ent` lists the -ent verb forms whose ending is silent.
    """
    spelling = unicodedata.normalize("NFC", spelling).lower()
    if not _TAIL.fullmatch(spelling):
        return frozenset()
    if spelling in WHOLE:
        return WHOLE[spelling]
    if spelling.endswith("ents"):
        options = [(spelling[:-1], False)]
    elif spelling.endswith("ent"):
        options = [(spelling, silent) for silent in _ent_endings(spelling, silent_ent)]
    else:
        options = [(spelling, False)]
    read = {_reading(option, silent) for option, silent in options}
    return frozenset(phones for phones in read if RHYME_VOWELS & set(phones))


# ---
# Keys
# ---


def _rhyme_keys(phones: str) -> tuple[str, str]:
    """The perfect and slant keys of one reading.

    Both start at the last vowel that is not an inner schwa; glides count as
    consonants. The perfect key takes the consonants after that vowel, or the
    phone before it when the reading ends on it.
    """
    last = max(index for index, phone in enumerate(phones) if phone in RHYME_VOWELS)
    vowel = phones[last]
    if last == len(phones) - 1 and last > 0:
        perfect = phones[last - 1 :]
    else:
        perfect = phones[last:]
    return perfect, _SLANT.get(vowel, vowel)


def _keys_of_readings(read: frozenset[str]) -> WordKeys | None:
    """The rhyme keys of a word's readings; None when there are none.

    The perfect key is a rime suffisante or better, the slant key a rime
    pauvre or an assonance.
    """
    if not read:
        return None
    rhymed = [_rhyme_keys(phones) for phones in read]
    return WordKeys(
        whole=read,
        perfect=frozenset(perfect for perfect, _ in rhymed),
        slant=frozenset(slant for _, slant in rhymed),
    )


def keys_of(spelling: str, silent_ent: frozenset[str]) -> WordKeys | None:
    """The rhyme keys of one spelling (no elision) read by the rules, known or not.

    None when the spelling cannot be read.
    """
    return _keys_of_readings(phones_of(spelling, silent_ent))


def _known_keys(spelling: str) -> WordKeys | None:
    """The rhyme keys of one known spelling: Lexique's readings, else the rules'."""
    heard = _lexique().get(spelling)
    if heard is None:
        return keys_of(spelling, _silent_ent())
    return _keys_of_readings(
        frozenset(heard.split("\t")) | WHOLE.get(spelling, frozenset())
    )


# ---
# Known words
# ---


@cache
def _lexique() -> dict[str, str]:
    """Each Lexique word and its tab-separated readings, as phones."""
    lines = _LEXIQUE_FILE.read_text(encoding="utf-8").splitlines()
    return dict(line.split("\t", 1) for line in lines)


@cache
def _known() -> frozenset[str]:
    """Every French word a player may use: the frequent ones and Lexique's."""
    frequent = _KNOWN_FILE.read_text(encoding="utf-8").split()
    return frozenset(frequent).union(_lexique())


@cache
def _accents() -> dict[str, tuple[str, ...]]:
    """Each unaccented spelling and the accented known words it can stand for."""
    return read_accents(_ACCENTS_FILE)


@cache
def _silent_ent() -> frozenset[str]:
    """The -ent verb forms whose ending is silent (ils parlent)."""
    return frozenset(_SILENT_ENT_FILE.read_text(encoding="utf-8").split())


def tail(word: str) -> str:
    """The part of a word after its last apostrophe or hyphen (l'été to été)."""
    return _PARTS.split(word)[-1]


def readings(word: str) -> tuple[str, ...]:
    """The known spellings the tail of `word` can be read as; empty when unknown.

    Every part before the tail must be an elided article or pronoun or a known
    word, so a made-up prefix (blorp'été) makes the whole word unknown.
    """
    *before, last = _PARTS.split(unicodedata.normalize("NFC", word))
    if not all(part in ELIDED or part in _known() for part in before):
        return ()
    return known_spellings(
        last, language=Language.FR, known=_known(), accents=_accents()
    )


def keys(word: str) -> WordKeys | None:
    """The keys of every reading of `word`; None when it is not a known word."""
    return merge(_known_keys(reading) for reading in readings(word))
