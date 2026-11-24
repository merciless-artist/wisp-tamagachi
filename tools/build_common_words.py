"""Build the word lists in wisp/data/ that the Rhyme Duel reads.

Run from the repo root with the dev requirements installed, as a module so
`wisp` imports:

    PYTHONUTF8=1 .venv/Scripts/python -m tools.build_common_words <en|es|fr>

Every language gets a common word list, the words Wisp himself may open with
and answer with: the most frequent words from wordfreq that pass the
language's filters, WORD_COUNT of them in frequency order, one per line.

English keeps lowercase alphabetic words of three or more letters (and a few
real two-letter words) that the CMU Pronouncing Dictionary knows, and drops
abbreviations said letter by letter (tv, dna), other abbreviations and foreign
fragments, profanity and slurs. CMU also decides which words a player may use.

Spanish and French have no dictionary, so they also get a known word list
(every word a player may use) and an accent map (the accented known words an
unaccented spelling stands for). Both come from the top KNOWN_SCAN words,
without English words and without unaccented misspellings of a more frequent
accented word. French also gets the -ent verb forms whose ending is silent
(ils parlent), worked out from how frequent each form is next to its stem.

The tool prints every common word it keeps (and, for French, the silent -ent
forms), so a person can look for names, places and misread nouns to add to
the lists here, then rebuild.
"""

import argparse
import re
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from textwrap import fill
from typing import Final

import pronouncing
from wordfreq import top_n_list, zipf_frequency

from wisp import rhymes_es, rhymes_fr
from wisp.language import Language
from wisp.rhyme_keys import fold

DATA: Final = Path(__file__).resolve().parent.parent / "wisp/data"
WORD_COUNT: Final = 5000
KNOWN_SCAN: Final = 50000
ENGLISH_MARGIN: Final = 1.0
ACCENT_MARGIN: Final = 0.7

# ---
# English
# ---

SCAN: Final = 30000
_WORD: Final = re.compile(r"[a-z]{3,}")

TWO_LETTER_WORDS: Final = frozenset(
    "go no so me we my by hi oh yo up us is it at an as be do he if in of on or to"
    .split()
)  # fmt: skip
STOPLIST: Final = frozenset(
    {
        "aka", "apr", "aug", "ave", "com", "corp", "dec", "del", "dept", "der", "des",
        "est", "feb", "fifa", "gen", "hong", "inc", "jan", "jun", "kong", "las", "les",
        "lol", "los", "mar", "mrs", "nasa", "non", "nov", "oct", "pre", "san", "sec",
        "sep", "sept", "und", "von",
    }
)  # fmt: skip

BLOCKLIST: Final = frozenset(
    {
        "abortion", "anal", "arse", "ass", "asses", "asshole", "bastard", "bitch",
        "bitches", "bitchy", "bloody", "blowjob", "bollocks", "boob", "boobs", "breast",
        "bullshit", "butt", "chink", "clinton", "clit", "cock", "cocks", "coon", "crap",
        "cum", "cunt", "damn", "dick", "dicks", "dildo", "drug", "drugs", "dumb",
        "dyke", "fag", "faggot", "fags", "fuck", "fucked", "fucker", "fuckin",
        "fucking", "fucks", "gay", "goddamn", "hell", "hillary", "hitler", "ho", "hoe",
        "hoes", "homo", "horny", "idiot", "isis", "islam", "islamic", "jewish", "jews",
        "jizz", "kike", "marijuana", "milf", "murder", "murdered", "muslim", "muslims",
        "naked", "nazi", "nazis", "nigga", "niggas", "nigger", "niggers", "nipple",
        "nipples", "nude", "nudes", "obama", "orgasm", "penis", "piss", "pissed",
        "porn", "porno", "prick", "pussy", "racism", "racist", "rape", "raped",
        "rapist", "retard", "retarded", "screw", "sex", "sexual", "sexy", "shit",
        "shits", "shitty", "slave", "slavery", "slaves", "slut", "sluts", "spic",
        "stupid", "suck", "sucks", "suicide", "terror", "terrorism", "terrorist",
        "terrorists", "tit", "tits", "titties", "tranny", "trump", "twat", "ugly",
        "vagina", "virgin", "wank", "wanker", "weed", "wetback", "whore", "whores",
    }
)  # fmt: skip


def _spoken_as_a_word(word: str) -> bool:
    """Whether the dictionary knows the word and never spells it out."""
    phones: list[str] = pronouncing.phones_for_word(word)
    return bool(phones) and all(
        pronouncing.syllable_count(pronunciation) < len(word)
        for pronunciation in phones
    )


def _keep_english(word: str) -> bool:
    """Whether an English word may be one of Wisp's own."""
    return bool(
        (_WORD.fullmatch(word) or word in TWO_LETTER_WORDS)
        and word not in STOPLIST
        and word not in BLOCKLIST
        and _spoken_as_a_word(word)
    )


# ---
# Spanish
# ---

SCAN_ES: Final = 30000
_SHAPE_ES: Final = re.compile(r"[a-záéíóúüñ]{3,}")
_ENDINGS_ES: Final = frozenset("aeiouáéíóúnsrldzyj")
_ACUTE_ES: Final = frozenset("áéíóú")
_DIAERESIS_ES: Final = re.compile(r"gü[eiéí]")
_DOUBLED_ES: Final = re.compile(r"([^clrneo])\1")

TWO_LETTER_WORDS_ES: Final = frozenset("yo tu tú mi fe va ve da ir ya no sé sí".split())
STOPLIST_ES: Final = frozenset(
    {
        "madrid", "méxico", "maría", "maria", "españa", "argentina", "colombia",
        "chile", "perú", "venezuela", "barcelona", "francia", "josé", "juan", "carlos",
        "luis", "antonio", "manuel", "jesús", "pedro", "miguel", "san", "europa",
        "américa", "brasil", "china", "francisco", "cuba", "santiago", "john", "david",
        "garcía", "lópez", "japón", "rusia", "alemania", "ecuador", "londres", "parís",
        "fernando", "jorge", "uruguay", "sánchez", "valencia", "india", "rodríguez",
        "diego", "gonzález", "italia", "bolivia", "lima", "sevilla", "alberto",
        "felipe", "roma", "martín", "martin", "michael", "pérez", "castro", "daniel",
        "fernández", "inglaterra", "córdoba", "panamá", "caracas", "ana", "enrique",
        "pablo", "guatemala", "james", "cataluña", "paul", "rafael", "áfrica", "africa",
        "israel", "martínez", "peña", "mario", "washington", "bogotá", "díaz", "george",
        "andrés", "asia", "eduardo", "harry", "corea", "javier", "australia",
        "california", "peter", "ricardo", "castilla", "cristina", "gómez", "alejandro",
        "canadá", "grecia", "rosario", "lucas", "nicolás", "andalucía", "chávez",
        "paraguay", "portugal", "rivera", "vicente", "ben", "laura", "oscar", "ramón",
        "caribe", "gabriel", "hugo", "mendoza", "river", "roberto", "macri", "alfonso",
        "carmen", "egipto", "hernández", "honduras", "bolívar", "obama", "isabel",
        "louis", "richard", "puebla", "guillermo", "miami", "sergio", "teresa",
        "charles", "habana", "siria", "alonso", "césar", "jean", "toledo", "zaragoza",
        "montevideo", "moscú", "málaga", "henry", "ignacio", "nicaragua", "suiza",
        "mariano", "raúl", "thomas", "lorenzo", "sebastián", "veracruz", "calderón",
        "guadalajara", "gil", "romero", "víctor", "jaime", "rodrigo", "santander",
        "tomás", "mauricio", "silva", "vargas", "gustavo", "julia", "kevin", "murcia",
        "florida", "herrera", "mercedes", "paulo", "turquía", "vega", "chris", "elena",
        "medina", "miranda", "rajoy", "anna", "aragón", "chicago", "galicia", "joaquín",
        "mary", "ortega", "berlín", "medellín", "monterrey", "steve", "texas",
        "agustín", "eva", "federico", "oaxaca", "ramírez", "suárez", "tony", "alan",
        "filipinas", "jiménez", "joe", "walter", "alfredo", "asturias", "gutiérrez",
        "navarra", "valladolid", "alexander", "canarias", "cristo", "google", "youtube",
        "online", "software", "iphone", "windows", "ios", "android", "disney", "fifa",
        "mail", "hey", "info", "tour", "jaja", "jajaja", "jajajaja", "min", "xvi",
        "adn", "cia", "onu", "psoe", "pri", "arturo", "bretaña", "brown", "colón",
        "cádiz", "diana", "gonzalo", "jackson", "jesucristo", "jones", "juárez",
        "lucía", "marruecos", "marta", "mike", "navarro", "polonia", "salamanca",
        "sudáfrica", "maya", "andes", "trinidad", "ucrania",
    }
)  # fmt: skip
BLOCKLIST_ES: Final = frozenset(
    {
        "puta", "putas", "puto", "putos", "mierda", "mierdas", "coño", "joder", "joda",
        "jodido", "jodida", "cabrón", "cabrones", "pendejo", "pendeja", "pendejos",
        "verga", "vergas", "chingar", "chingada", "chingado", "pinche", "culo", "culos",
        "polla", "pollas", "follar", "coger", "concha", "orto", "pedo", "carajo",
        "maldito", "maldita", "marica", "maricón", "maricones", "zorra", "zorras",
        "perra", "perras", "idiota", "idiotas", "estúpido", "estúpida", "imbécil",
        "gilipollas", "tonto", "tonta", "feo", "fea", "mamada", "pene", "vagina",
        "sexo", "sexual", "sexuales", "sexy", "porno", "violación", "violar", "nazi",
        "nazis", "hitler", "droga", "drogas", "marihuana", "suicidio", "asesinato",
        "asesinatos", "asesino", "asesinos", "asesinado", "terror", "terrorismo",
        "terrorista", "terroristas", "esclavos", "esclavo", "aborto", "gay", "negro",
        "negra", "negros", "negras", "teta", "tetas", "desnuda", "desnudo", "orgasmo",
        "pelotudo", "pelotudos", "musulmanes", "musulmán",
    }
)  # fmt: skip


def _english(word: str, language: Language) -> bool:
    """Whether a word in another language's list is really English.

    Spanish counts a word as English at exactly ENGLISH_MARGIN more frequent
    in English; French only beyond it.
    """
    margin = zipf_frequency(word, "en") - _zipf(word, language)
    if language is Language.FR:
        return margin > ENGLISH_MARGIN
    return margin >= ENGLISH_MARGIN


def _known_spanish(word: str) -> bool:
    """Whether a frequent Spanish word may be used by a player."""
    return bool(
        rhymes_es.WORD.fullmatch(word)
        and rhymes_es.keys_of(word) is not None
        and not _english(word, Language.ES)
    )


def _keep_spanish(word: str) -> bool:
    """Whether a Spanish word may be one of Wisp's own."""
    return bool(
        (_SHAPE_ES.fullmatch(word) or word in TWO_LETTER_WORDS_ES)
        and word[-1] in _ENDINGS_ES
        and sum(char in _ACUTE_ES for char in word) <= 1
        and "ü" not in _DIAERESIS_ES.sub("", word)
        and not _DOUBLED_ES.search(word)
        and word in known_words(Language.ES)
        and word not in STOPLIST_ES
        and word not in BLOCKLIST_ES
    )


# ---
# French
# ---

SCAN_FR: Final = 40000
STEM_LETTERS: Final = 4
STEM_ZIPF: Final = 2.5
VERB_MARGIN: Final = 1.0
_SHAPE_FR: Final = re.compile(r"[a-zàâäéèêëîïôöùûüÿœæç]{3,}")
_HEARD_VOWEL_FR: Final = re.compile(r"[aàâäeéèêëiîïoôöuùûüœæ]")
_FOREIGN_FR: Final = re.compile(r"[wk]")

NAMES_FR: Final = frozenset(
    {
        "adam", "adn", "afghanistan", "afp", "afrique", "alain", "albert",
        "alberta", "alex", "alexandre", "alexis", "alfred", "alger", "algérie",
        "ali", "alice", "allah", "allemagne", "alpes", "alsace", "amazon",
        "amiens", "amsterdam", "amérique", "andré", "andy", "angela", "angeles",
        "angers", "angleterre", "ann", "anna", "anne", "annie", "anthony",
        "antoine", "antonio", "apple", "aquitaine", "argentine", "arnaud",
        "arthur", "asie", "athènes", "auguste", "augustin", "australie",
        "autriche", "auvergne", "avignon", "baptiste", "barbara", "barcelone",
        "barry", "bastia", "batman", "beach", "belgique", "benjamin", "benoît",
        "berlin", "bernard", "bertrand", "bill", "billy", "bob", "bordeaux",
        "boston", "boulogne", "bourgogne", "boy", "brest", "bretagne", "brian",
        "bruce", "bruno", "bruxelles", "brésil", "bush", "caen", "caire",
        "calais", "californie", "cameron", "cameroun", "camille", "canada",
        "cannes", "caq", "carl", "carlos", "caroline", "carter", "catalogne",
        "catherine", "cdi", "charles", "charlie", "charlotte", "chelsea",
        "chicago", "chili", "chine", "chirac", "chris", "christ", "christian",
        "christine", "christophe", "chu", "cia", "clara", "claude", "clermont",
        "clinton", "cloud", "clément", "coca", "colombie", "com", "congo",
        "coran", "corse", "corée", "costa", "couillard", "cuba", "cécile",
        "céline", "damien", "daniel", "dave", "david", "davis", "del", "denis",
        "der", "diane", "didier", "diego", "dieu", "dijon", "disney",
        "dominique", "donald", "dupont", "dylan", "edf", "edouard", "egypte",
        "elizabeth", "elysée", "emma", "emmanuel", "eric", "espagne", "etc",
        "etienne", "eugène", "europe", "eva", "ferrari", "figaro", "fillon",
        "finlande", "flandre", "florence", "floride", "france", "francfort",
        "francis", "francisco", "françois", "françoise", "fred", "french",
        "frédéric", "félix", "gabriel", "garcia", "garonne", "gary", "gaulle",
        "gaza", "genève", "george", "georges", "gilbert", "gilles", "google",
        "gordon", "grenoble", "grèce", "grégoire", "guadeloupe", "guillaume",
        "guinée", "gérard", "haha", "hamilton", "hamon", "harper", "harry",
        "havre", "haïti", "hello", "henri", "henry", "hervé", "hey", "hill",
        "hip", "hollande", "hongrie", "hubert", "hugo", "hélène", "ian", "ier",
        "iii", "inde", "insee", "instagram", "ipad", "iphone", "iran",
        "irlande", "isabelle", "israël", "italie", "jacob", "jacques", "jai",
        "james", "jane", "japon", "jason", "jay", "jean", "jeanne", "jeff",
        "jennifer", "jersey", "jessica", "jim", "jimmy", "joe", "john",
        "johnny", "johnson", "jonathan", "jordan", "joseph", "josé", "juan",
        "jules", "julia", "julie", "julien", "juliette", "juppé", "justin",
        "jérusalem", "jérôme", "jésus", "lady", "lambert", "languedoc", "larry",
        "las", "laura", "laurent", "lausanne", "laval", "league", "leclerc",
        "lee", "liban", "libye", "lille", "limoges", "linux", "lionel", "lisa",
        "lisbonne", "liverpool", "liège", "loire", "lol", "londres", "lorraine",
        "los", "louis", "louise", "louvre", "luc", "lucas", "lucien",
        "luxembourg", "lyon", "léo", "léon", "mac", "macron", "madagascar",
        "madeleine", "madrid", "mali", "manchester", "marcel", "marco",
        "marguerite", "maria", "marie", "mario", "marion", "marne", "maroc",
        "marseille", "martin", "martine", "martinique", "mathieu", "matt",
        "matthieu", "maurice", "max", "maxime", "mercedes", "mexique", "miami",
        "michael", "michel", "michelle", "microsoft", "milan", "mme", "mohamed",
        "mohammed", "monaco", "montpellier", "montréal", "morgan", "moscou",
        "moselle", "munich", "méditerranée", "mélenchon", "nancy", "nantes",
        "naples", "napoléon", "nasa", "nathalie", "nathan", "nba", "nelson",
        "netflix", "nice", "nicolas", "nicole", "nigeria", "nintendo",
        "normandie", "norvège", "nov", "obama", "oise", "oliver", "olivier",
        "omar", "ontario", "onu", "orléans", "oscar", "palestine", "paris",
        "pascal", "patrice", "paul", "pauline", "peter", "peugeot", "philippe",
        "pib", "pme", "poitiers", "pologne", "porto", "portugal", "potter",
        "poutine", "provence", "pyrénées", "qatar", "queen", "quentin",
        "québec", "raphaël", "ray", "raymond", "red", "reims", "renaud",
        "renault", "rené", "rer", "rez", "rhin", "rhône", "richard", "rio",
        "robert", "robin", "roger", "roland", "rome", "ross", "rouen",
        "roumanie", "rousseau", "roy", "russie", "ryan", "samsung", "samuel",
        "santa", "sarah", "savoie", "scott", "serge", "shirt", "sida", "silva",
        "simon", "singapour", "sir", "smith", "sony", "sophie", "stan",
        "stanley", "stephen", "steven", "strasbourg", "street", "stéphane",
        "suisse", "suède", "sydney", "sylvain", "sylvie", "syrie", "sébastien",
        "sénégal", "taylor", "texas", "thaïlande", "thierry", "thomas",
        "thread", "tim", "tony", "toronto", "toulon", "toulouse", "trump",
        "tunisie", "turquie", "tva", "unesco", "urss", "usa", "valence",
        "valentin", "valérie", "vancouver", "var", "vatican", "vegas",
        "venezuela", "venise", "versailles", "victor", "victoria", "vietnam",
        "vii", "viii", "villeneuve", "vincent", "virginie", "vladimir",
        "xavier", "xbox", "xiii", "xiv", "xixe", "xvi", "xviiie", "xxe",
        "youtube", "yves", "zélande", "écosse",
    }
)  # fmt: skip
BLOCKLIST_FR: Final = frozenset(
    {
        "merde", "putain", "pute", "putes", "salope", "salopes", "connard", "connards",
        "connasse", "con", "conne", "cons", "bite", "bites", "couille", "couilles",
        "enculé", "enculés", "enfoiré", "enfoirés", "niquer", "nique", "bordel",
        "chier", "foutre", "foutu", "salaud", "salauds", "pédé", "pédés", "nègre",
        "nègres", "sexe", "sexuel", "sexuelle", "sexy", "porno", "viol", "violer",
        "nazi", "nazis", "hitler", "drogue", "drogues", "suicide", "meurtre",
        "terroriste", "terroristes", "terrorisme", "esclave", "esclaves",
        "avortement", "gay", "cul", "sein", "seins", "nu", "nue", "nus", "nues",
        "chatte", "branler", "crétin", "idiot", "idiote", "débile", "stupide",
        "imbécile", "abruti", "bâtard", "pétasse", "baiser", "baise", "orgasme",
        "pénis", "vagin", "cocu", "pouffiasse", "négro", "racaille", "homo", "idiots",
        "gays", "prostitution", "emmerde", "emmerder",
    }
)  # fmt: skip
HEARD_ENT_FR: Final = frozenset(
    {
        "ciment", "décadent", "florent", "jacent", "latent", "laurent", "lorient",
        "patent", "régiment", "sergent", "survient",
    }
)  # fmt: skip


def silent_ent(scan: list[str]) -> frozenset[str]:
    """The -ent forms in `scan` read as a verb, with a silent ending (parlent).

    A form is a verb when its stem (the form without nt) has at least
    STEM_LETTERS letters, is frequent enough (STEM_ZIPF), and is not
    VERB_MARGIN or more less frequent than the form: ils parlent is rarer than
    il parle, while a noun like talent is far more frequent than its look-alike
    stem. Forms the rules already decide, and forms found by review to be
    heard (HEARD_ENT_FR: régiment, survient), are left out.
    """
    decided = rhymes_fr.ENT_SILENT | rhymes_fr.ENT_BOTH | rhymes_fr.ENT_NASAL
    return frozenset(
        word
        for word in scan
        if _SHAPE_FR.fullmatch(word)
        and word.endswith("ent")
        and not word.endswith("aient")
        and word not in decided | HEARD_ENT_FR
        and len(stem := word[:-2]) >= STEM_LETTERS
        and _zipf(stem, Language.FR) >= STEM_ZIPF
        and _zipf(word, Language.FR) - _zipf(stem, Language.FR) < VERB_MARGIN
    )


@cache
def _silent_ent_fr() -> frozenset[str]:
    """The silent -ent forms among the top KNOWN_SCAN French words."""
    return silent_ent(top_n_list(Language.FR.value, KNOWN_SCAN))


def _sounds_french(word: str) -> frozenset[str]:
    """Every reading of a French word, to keep homophones out of Wisp's words."""
    return rhymes_fr.phones_of(rhymes_fr.tail(word), _silent_ent_fr())


def _known_french(word: str) -> bool:
    """Whether a frequent French word may be used by a player.

    It needs a vowel other than y, which keeps out letter strings like xyz.
    """
    return bool(
        rhymes_fr.WORD.fullmatch(word)
        and _HEARD_VOWEL_FR.search(word)
        and _sounds_french(word)
        and not _english(word, Language.FR)
    )


@cache
def _first_spellings_fr() -> frozenset[str]:
    """The most frequent spelling of each folded French form in the scan."""
    first: dict[str, str] = {}
    for word in top_n_list(Language.FR.value, SCAN_FR):
        first.setdefault(fold(word, language=Language.FR), word)
    return frozenset(first.values())


def _keep_french(word: str) -> bool:
    """Whether a French word may be one of Wisp's own."""
    return bool(
        _SHAPE_FR.fullmatch(word)
        and word in _first_spellings_fr()
        and not _FOREIGN_FR.search(word)
        and word in known_words(Language.FR)
        and word not in NAMES_FR
        and word not in BLOCKLIST_FR
    )


# ---
# Profiles
# ---


@dataclass(frozen=True)
class Profile:
    """How one language's lists are built and where they are written.

    `keep` says whether a word may be one of Wisp's own. `known` says whether a
    frequent word may be used by a player; a language without it (English)
    has a dictionary at runtime instead and no known word or accent files.
    `sounds` gives a word's readings when no two of Wisp's words may sound
    alike, and `silent_ent` the silent -ent forms to write, for French.
    """

    language: Language
    scan: int
    word_count: int
    keep: Callable[[str], bool]
    output: Path
    known: Callable[[str], bool] | None = None
    known_output: Path | None = None
    accents_output: Path | None = None
    sounds: Callable[[str], frozenset[str]] | None = None
    silent_ent: Callable[[], frozenset[str]] | None = None
    silent_ent_output: Path | None = None


PROFILES: Final[dict[Language, Profile]] = {
    Language.EN: Profile(
        language=Language.EN,
        scan=SCAN,
        word_count=WORD_COUNT,
        keep=_keep_english,
        output=DATA / "common_words.txt",
    ),
    Language.ES: Profile(
        language=Language.ES,
        scan=SCAN_ES,
        word_count=WORD_COUNT,
        keep=_keep_spanish,
        output=DATA / "common_words_es.txt",
        known=_known_spanish,
        known_output=DATA / "known_words_es.txt",
        accents_output=DATA / "accents_es.txt",
    ),
    Language.FR: Profile(
        language=Language.FR,
        scan=SCAN_FR,
        word_count=WORD_COUNT,
        keep=_keep_french,
        output=DATA / "common_words_fr.txt",
        known=_known_french,
        known_output=DATA / "known_words_fr.txt",
        accents_output=DATA / "accents_fr.txt",
        sounds=_sounds_french,
        silent_ent=_silent_ent_fr,
        silent_ent_output=DATA / "silent_ent_fr.txt",
    ),
}

# ---
# Building
# ---


@cache
def _zipf(word: str, language: Language) -> float:
    """How frequent a word is in `language`, on wordfreq's zipf scale."""
    return zipf_frequency(word, language.value)


@cache
def known_words(language: Language) -> frozenset[str]:
    """Every word a player may use in `language`."""
    return frozenset(_known_in_order(language))


@cache
def _known_in_order(language: Language) -> tuple[str, ...]:
    """The known words of `language`, most frequent first.

    An unaccented spelling is left out when an accented twin is at least
    ACCENT_MARGIN more frequent (corazon, tambien): the accent map reaches the
    twin instead.
    """
    known = PROFILES[language].known
    if known is None:
        raise ValueError(f"{language.value} has no known word list.")
    words = [word for word in top_n_list(language.value, KNOWN_SCAN) if known(word)]
    spellings: defaultdict[str, list[str]] = defaultdict(list)
    for word in words:
        spellings[fold(word, language=language)].append(word)

    def misspelt(word: str) -> bool:
        floor = _zipf(word, language) + ACCENT_MARGIN
        return fold(word, language=language) == word and any(
            _zipf(twin, language) >= floor for twin in spellings[word] if twin != word
        )

    return tuple(word for word in words if not misspelt(word))


def accent_map(known: list[str], language: Language) -> dict[str, tuple[str, ...]]:
    """Each unaccented spelling and the known words it can stand for.

    A spelling that is not itself known stands for every known word that folds
    to it. One that is known stands only for twins nearly as frequent, at most
    ACCENT_MARGIN less, and is left out when there are none.
    """
    known_set = set(known)
    spellings: defaultdict[str, list[str]] = defaultdict(list)
    for word in known:
        folded = fold(word, language=language)
        if folded != word:
            spellings[folded].append(word)
    accents: dict[str, tuple[str, ...]] = {}
    for unaccented, twins in spellings.items():
        if unaccented in known_set:
            floor = _zipf(unaccented, language) - ACCENT_MARGIN
            twins = [twin for twin in twins if _zipf(twin, language) >= floor]
        if twins:
            accents[unaccented] = tuple(twins)
    return accents


def common_words(profile: Profile) -> list[str]:
    """The first `word_count` frequent words that pass `keep`, in order.

    With `sounds`, a word that can sound like one already kept is skipped.
    """
    kept: list[str] = []
    heard: set[str] = set()
    for word in top_n_list(profile.language.value, profile.scan):
        if not profile.keep(word):
            continue
        if profile.sounds is not None:
            sounds = profile.sounds(word)
            if sounds & heard:
                continue
            heard |= sounds
        kept.append(word)
        if len(kept) == profile.word_count:
            return kept
    raise RuntimeError(f"Only {len(kept)} words passed; scan more than {profile.scan}.")


def _write(path: Path, lines: list[str]) -> None:
    """Write `lines` to `path`, one per line, with Unix line endings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {len(lines)} lines to {path}")


def main(argv: list[str]) -> None:
    """Build one language's lists, then print the kept common words."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("language", choices=[language.value for language in PROFILES])
    profile = PROFILES[Language(parser.parse_args(argv).language)]
    if profile.silent_ent is not None and profile.silent_ent_output is not None:
        silent = sorted(profile.silent_ent())
        _write(profile.silent_ent_output, silent)
        print(fill(" ".join(silent), width=88))
    if profile.known_output is not None and profile.accents_output is not None:
        known = list(_known_in_order(profile.language))
        _write(profile.known_output, known)
        accents = accent_map(known, profile.language)
        _write(
            profile.accents_output,
            [f"{key}\t{' '.join(accents[key])}" for key in sorted(accents)],
        )
    words = common_words(profile)
    _write(profile.output, words)
    print(fill(" ".join(words), width=88))


if __name__ == "__main__":
    main(sys.argv[1:])
