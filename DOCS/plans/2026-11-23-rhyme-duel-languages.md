# Rhyme Duel Languages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Rhyme Duel playable in English, Spanish and French. The member picks the language once, with three buttons in their room, and can change it later with an option on `/wisp play rhyme`.

**Architecture:**
- A small `wisp/language.py` holds the `Language` StrEnum.
- A leaf module, `wisp/rhyme_keys.py`, holds `RhymeKind`, `WordKeys`, `fold` and `compare`. It imports only `wisp.language`, so `rhymes`, `rhymes_es`, `rhymes_fr` and the builder can all import it without a cycle.
- `wisp/rhymes.py` becomes a language-aware facade. Each language turns a word into `WordKeys(whole, perfect, slant)`:
  - English from CMU, exactly as today;
  - Spanish in `wisp/rhymes_es.py`;
  - French in `wisp/rhymes_fr.py`.
- One shared `compare` turns two sets of keys into a `RhymeKind`.
- Word lists and accent maps are built offline by `tools/build_common_words.py` and committed.
- The duel takes its language from `players.rhyme_language`, takes its words from a `DuelText` table and takes its lines from per-language Moments.
- The language picker is a persistent `DynamicItem` button posted in the member's room.

**Tech Stack:** Python 3.13, discord.py 2.x (`DynamicItem`, `app_commands.choices`), aiomysql on MariaDB, `pronouncing`/`cmudict` at runtime, `wordfreq==3.1.1` at build time only, and pytest with real `wisptest_` tables.

**Spec:** `DOCS/specs/2026-11-23-rhyme-duel-languages-design.md`

## Global Constraints

- **Storage:** Wisp is live, so the only storage change is the additive column `players.rhyme_language VARCHAR(2) NULL`, migrated at startup (`db/schema.py`).
- **No new runtime dependency:**
  - `wordfreq` is imported only by `tools/build_common_words.py` and never by `wisp/` or `cogs/`;
  - nothing is downloaded;
  - the bot reads only the committed files in `wisp/data/`.
- **Numbers:** every tunable number lives only in `wisp/rules.py`. The builder's own list sizes and zipf margins stay in the tool, as the English ones do today.
- **Members:** identified by Discord ID everywhere, including the picker's custom id and its owner check.
- **Bot text:**
  - `・` bullets and `♪` flair;
  - no Unicode emoji in canned lines;
  - no `—` or `–`;
  - no embeds and no DMs;
  - a plain space (never NBSP) before French `! ? :`;
  - any frame heading spells `WiSP`.
- **Errors:** posted as `Error in <context>: <Type>: <message>` through `bot.report_error`.
- **Quality:**
  - `PYTHONUTF8=1 .venv/Scripts/python -m black/isort/flake8/mypy --strict` pass on every touched file;
  - section headers are `# ---` rules;
  - no narrating comments, no dead code, no blanket `except Exception`;
  - PEP 8 names: functions are snake_case (`language_picker`, not `LanguagePicker`).
- **Builder commands** run as modules from the repo root, so `wisp` imports: `PYTHONUTF8=1 .venv/Scripts/python -m tools.build_common_words <en|es|fr>`. The module docstring says so.
- **Tests:**
  - use the real database (`db` fixture, `wisptest_` prefix) and fake Discord objects;
  - never run two pytest processes at once;
  - never mock the database;
  - tests never import `tools/build_common_words.py` (it imports `wordfreq` at module top). Word-list hygiene tests check literal sample sets, as `tests/test_rhymes.py:221` does for English.
- **English must not change.** The only intended English change is the wider edge-strip and NFC in `clean_word`. Rebuilding `common_words.txt` must leave it byte-identical.
- **Message length:** messages stay under 2,000 characters (`text_length`).
- **Repo hygiene:**
  - commit by explicit paths;
  - never commit `CLAUDE.md`, `.claude/` or `.superpowers/`;
  - Wisp is main-only, and a push auto-deploys.

## Review Focus

1. **English is unchanged:**
   - every existing `tests/test_rhymes.py` and `tests/test_rhyme_duel.py` case passes with only the added `language=Language.EN` argument, including `("don’t", "don't")`;
   - Task 1 test `test_english_keys_match_the_old_rhyme_kind` checks the new `compare(keys(...))` against the old functions over 2,000 seeded COMMON pairs;
   - `git diff --exit-code wisp/data/common_words.txt` passes after rebuilding.
2. **Nonsense is rejected and unaccented words are accepted:**
   - `rhyme_kind("fuego", "xuego", language=Language.ES) is None`;
   - `rhyme_kind("canción", "corazon", language=Language.ES) is RhymeKind.PERFECT`;
   - `rhyme_kind("maison", "blorp'aison", language=Language.FR) is None`;
   - Task 2 tests `test_unknown_spanish_word_rejected` and `test_unaccented_spanish_word_reads_as_accented`; Task 3 test `test_elision_needs_a_real_prefix`.
3. **The picker never holds the room, never saves on a refusal, and is closed before the duel:**
   - Task 5 test `test_a_first_duel_posts_the_picker_and_frees_the_room`;
   - Task 5 test `test_a_refused_start_saves_no_language`;
   - Task 5 test `test_picking_a_language_saves_it_and_starts_the_duel_in_it` (the picker is edited before the first duel post).
4. **Only the owner can press their language buttons:** Task 5 test `test_only_the_member_can_press_their_language_buttons`.
5. **Repeats use the same-word key, for the player and for Wisp:**
   - `corazon` after `corazón` ends the duel with the "already used" verdict (Task 5 test `test_an_unaccented_repeat_counts_as_used`);
   - `l'été` after `été` is a repeat (Task 3 test `test_same_word_key_folds_and_drops_elision`);
   - Wisp never answers with a spelling of a used word (Task 2 test `test_wisp_never_answers_a_used_word_in_another_spelling`).
6. **The language reaches every step of the duel:** the opener, the check, Wisp's reply and the ending Moment all receive the same language (Task 5 test `test_a_spanish_duel_runs_entirely_in_spanish`).

## Rulings made while planning

- **The receipt and private replies stay English**, because their reasons are shared with feeding and the Craving. The spec marks this my call, to raise with Myra.
- **The language is saved only after the checks pass.** The picker buttons and the command option go through the same `start_duel(interaction, language=..., picker=...)`.
- **The picker is edited to a one-line note** inside `_host`, right after `set_rhyme_language` succeeds and before the duel starts. A refused press leaves it alone.
- **`language` is a required keyword-only argument** on every rhyme function, so mypy catches a missed call site. There are no defaults that could hide English.
- **`same_word_key` drops elision only in French.** English keeps `fold(word)`, because `tail("don't")` would be `t`.
- **`RhymeKind` moves to `wisp/rhyme_keys.py`** and is re-exported from `wisp/rhymes.py`, so existing imports keep working.
- **The English file keeps its name**, `common_words.txt`, so the English rebuild can be compared byte for byte.
- **The test fixtures `configured`/`lay`** set `Language.EN` for the test players, so the existing duel tests skip the picker.
- **The Spanish/French accent map is a committed file**, not derived at runtime, so the zipf margin for known unaccented words can be applied offline.

---

### Task 1: Language storage and the per-language rhyme interface (English identical)

**Files:**
- Create: `wisp/language.py`, `wisp/rhyme_keys.py`
- Modify: `wisp/rhymes.py`, `db/schema.py`, `db/players.py`, `cogs/rhyme_duel.py` (call sites pass `Language.EN` for now)
- Test: `tests/test_rhymes.py`, `tests/test_schema.py`, `tests/test_repos.py`, `tests/test_rhyme_duel.py` (the `opener`/`wisp_says` fixtures)

**Interfaces:**
- `wisp/language.py`:
  - `class Language(StrEnum): EN = "en"; ES = "es"; FR = "fr"`
  - `LANGUAGE_NAMES: Final[dict[Language, str]] = {EN: "English", ES: "Español", FR: "Français"}`
- `wisp/rhyme_keys.py` (leaf module; imports only `wisp.language` and the standard library):
  - `class RhymeKind` (moved unchanged from `wisp/rhymes.py`)
  - `class WordKeys(NamedTuple): whole: frozenset[str]; perfect: frozenset[str]; slant: frozenset[str]`
  - `def fold(word: str, *, language: Language) -> str`: NFC, then removes acute, grave, circumflex and diaeresis accents in every language. French also maps `ç → c`, `œ → oe`, `æ → ae`. Spanish keeps `ñ`.
  - `def compare(first: WordKeys | None, second: WordKeys | None) -> RhymeKind | None`
- `db/players.py`:
  - `Player.rhyme_language: Language | None = None`
  - `_from_row` converts it the way `pickle_stance` is converted
  - `PlayerRepo.set_rhyme_language(guild_id: int, user_id: int, language: Language) -> None`, through `_update`
- `db/schema.py`: `rhyme_language VARCHAR(2) NULL` in the `players` definition and in `_ADDED_COLUMNS["players"]`.
- `wisp/rhymes.py`:
  - re-exports `RhymeKind`, `WordKeys`, `fold` and `compare` from `wisp.rhyme_keys`.
  - `EDGE: Final = string.punctuation + "¡¿«»“”‘’…"`
  - `def clean_word(text: str, *, language: Language) -> str | None`: NFC → lowercase → `replace("’", "'")` → one regex strip of whitespace and `EDGE` from both ends together, `re.sub(rf"^[\s{re.escape(EDGE)}]+|[\s{re.escape(EDGE)}]+$", "", text)` → the language's word regex.
  - `def same_word_key(word: str, *, language: Language) -> str`: `fold(rhymes_fr.tail(word), language=FR)` for French, `fold(word, language=language)` otherwise. In this task French is not wired yet, so only the non-French branch exists; Task 3 adds the French branch.
  - `def keys(word: str, *, language: Language) -> WordKeys | None`. English: whole = the CMU phone strings, perfect = `_rhyme_part`, slant = the first phone of each rhyme part, None when CMU does not know the word.
  - `def rhyme_kind(first: str, second: str, *, language: Language) -> RhymeKind | None`: None when `same_word_key` is equal, else `compare(keys(...), keys(...))`.
  - `_common(language) -> tuple[str, ...]`, `_common_by_perfect(language) -> dict[str, frozenset[str]]`, `_common_rhymes(word, used, language)` and `_openers(language)`: each `@cache`d except `_common_rhymes`, which filters out every candidate whose `same_word_key` is in `{same_word_key(w) for w in used}`.
  - `def opening_word(rng: random.Random, *, language: Language) -> str`
  - `def wisp_reply(word: str, used: set[str], stage: Stage, turn: int, rng: random.Random, *, language: Language) -> str | None`: compares `used` by `same_word_key`, never by raw spelling.
  - `_WORD_FILES: Final[dict[Language, Path]]`. Only EN is filled in this task; ES and FR come in Tasks 2 and 3.
- `cogs/rhyme_duel.py` passes `language=Language.EN` everywhere for now. The repeat check becomes `same_word_key(answer, language=...) in {same_word_key(word, language=...) for word in chain}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rhymes.py: existing parametrized tests gain language=Language.EN,
# including the existing ("don’t", "don't") case, which must still pass.
@pytest.mark.parametrize(("text", "word"), [
    ("«hat»", "hat"), ("hat !", "hat"), ("hat\u202f!", "hat"),
    ("\u00a0hat\u00a0", "hat"), ("don’t", "don't"),
    ("he\u0301llo", None),        # NFC keeps English ASCII-only
])
def test_clean_word_strips_unicode_edges(text, word):
    assert clean_word(text, language=Language.EN) == word

def test_english_keys_match_the_old_rhyme_kind():
    rng = random.Random(7)
    for _ in range(2000):
        a, b = rng.choice(COMMON), rng.choice(COMMON)
        assert rhyme_kind(a, b, language=Language.EN) is _old_rhyme_kind(a, b)
    # _old_rhyme_kind: test-local copy of today's rule via pronouncing

@pytest.mark.parametrize(("word", "language", "folded"), [
    ("corazón", Language.ES, "corazon"),
    ("año", Language.ES, "año"),
    ("ça", Language.FR, "ca"),
    ("garçon", Language.FR, "garcon"),
    ("cœur", Language.FR, "coeur"),
    ("maïs", Language.FR, "mais"),
])
def test_fold_per_language(word, language, folded):
    assert fold(word, language=language) == folded

def test_rhyme_keys_is_a_leaf_module():
    source = Path("wisp/rhyme_keys.py").read_text(encoding="utf-8")
    assert not re.search(r"^\s*(from|import)\s+wisp\.rhymes", source, re.MULTILINE)

# tests/test_schema.py
async def test_create_tables_adds_rhyme_language_to_a_live_players_table(db): ...
    # drop rhyme_language, create_tables, column back and NULL

# tests/test_repos.py
async def test_rhyme_language_starts_unset_and_is_saved(db):
    repo = PlayerRepo(db)
    assert (await repo.get(GUILD, USER)).rhyme_language is None
    await repo.set_rhyme_language(GUILD, USER, Language.FR)
    assert (await repo.get(GUILD, USER)).rhyme_language is Language.FR

# tests/test_rhyme_duel.py: the opener fixture becomes
#   lambda _rng, *, language: "fire"
# and wisp_says records (word, used, stage, turn, language).
```

- [ ] **Step 2: Run them and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhymes.py tests/test_schema.py tests/test_repos.py -q -p no:cacheprovider -k "rhyme or clean or fold or language or leaf"`
Expected: FAIL (`wisp.language` import error, missing column).

- [ ] **Step 3: Implement the interface above**

Move `RhymeKind` into `wisp/rhyme_keys.py` and re-export it from `wisp/rhymes.py`. Write English `keys` from the existing `_rhyme_part`/`_sounds_of`, then delete the old bodies with no duplicate helpers left. Keep `score` and `rhyme_chance` as they are.

- [ ] **Step 4: Run them and see them pass**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhymes.py tests/test_schema.py tests/test_repos.py tests/test_rhyme_duel.py -q -p no:cacheprovider` (in the background).
Expected: PASS, with the existing tests unchanged apart from the added argument.

- [ ] **Step 5: Commit**

`git add wisp/language.py wisp/rhyme_keys.py wisp/rhymes.py db/schema.py db/players.py cogs/rhyme_duel.py tests/test_rhymes.py tests/test_schema.py tests/test_repos.py tests/test_rhyme_duel.py` and commit "Store a rhyme language and key rhymes by language".

---

### Task 2: Spanish rhymes and word lists

**Files:**
- Create: `wisp/rhymes_es.py`, `wisp/data/common_words_es.txt`, `wisp/data/known_words_es.txt`, `wisp/data/accents_es.txt` (all three generated)
- Modify: `wisp/rhymes.py` (ES dispatch, regex, files), `wisp/rules.py`, `tools/build_common_words.py`
- Test: `tests/test_rhymes_es.py` (new)

**Interfaces:**
- `wisp/rules.py`: `RHYME_OPENER_MIN_LETTERS = 4` and `RHYME_OPENER_SKIP_TOP = 150`, written next to `RHYME_OPENER_RHYMES` with no `Final` (matching `wisp/rules.py:327-331`). `_openers` applies them to ES and FR only, where "skip top" means the first 150 lines of `common_words_<lang>.txt`.
- `wisp/rhymes_es.py` (imports `WordKeys`, `fold` from `wisp.rhyme_keys`):
  - `WORD: Final = re.compile(r"[a-záéíóúüñ]+")`
  - `def stressed_vowel(spelling: str) -> str | None`: pure; spec steps 1 to 3, returning the normalised stressed vowel (accent removed), or None when the spelling cannot be read.
  - `def keys_of(spelling: str) -> WordKeys | None`: pure; spec steps 1 to 5 on a single spelling, using `stressed_vowel`.
  - `def readings(word: str) -> tuple[str, ...]`: when `fold(word, language=ES) != word`, `(word,)` if known, else `()`. Otherwise the word itself if known, plus `_accents().get(word, ())`.
  - `def keys(word: str) -> WordKeys | None`: the union of `keys_of` over `readings`, None when there are none.
  - `_known() -> frozenset[str]` read from `known_words_es.txt`, and `_accents() -> dict[str, tuple[str, ...]]` read from `accents_es.txt` (`unaccented<TAB>accented accented ...`). Both `@cache`d.
- `tools/build_common_words.py`:
  - module docstring: run as `PYTHONUTF8=1 .venv/Scripts/python -m tools.build_common_words <en|es|fr>` from the repo root;
  - `@dataclass(frozen=True) class Profile` with fields `language`, `scan`, `word_count`, `keep: Callable[[str], bool]`, `output`, `known_output`, `accents_output`;
  - `PROFILES: Final[dict[Language, Profile]]`;
  - `def main(argv: list[str]) -> None` takes `en|es|fr`;
  - Spanish constants: `TWO_LETTER_WORDS_ES`, `STOPLIST_ES`, `BLOCKLIST_ES`, `ENGLISH_MARGIN = 1.0`, `ACCENT_MARGIN = 0.7`, `KNOWN_SCAN = 50000`;
  - known words also drop English (`zipf_en - zipf_es >= 1.0`);
  - `def accent_map(known: list[str], language: Language) -> dict[str, tuple[str, ...]]`: keyed by `fold`; a known unaccented key keeps only twins with `zipf >= zipf(key) - ACCENT_MARGIN`, and is left out when none qualify;
  - English output stays byte-identical.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rhymes_es.py
PERFECT = [("canción","corazón"), ("amor","dolor"), ... ]   # all 36 spec pairs
SLANT   = [("casa","cama"), ("casa","casas"), ... ]         # all 17
HOMOPHONES = [("casa","caza"), ("hola","ola"), ("vaca","baca"), ("gente","jente")]
NONE    = [("árbol","cielo"), ("sol","mar"), ("joven","examen"), ("útil","fácil"), ("régimen","imagen")]

@pytest.mark.parametrize(("a","b"), PERFECT)
def test_spanish_perfect_rhymes(a, b):
    assert compare(keys_of(a), keys_of(b)) is RhymeKind.PERFECT
# same shape: test_spanish_slant_rhymes, test_spanish_homophones_are_not_rhymes,
# test_spanish_non_rhymes

@pytest.mark.parametrize(("word","stressed"), [
    ("guion","o"), ("ciudad","a"), ("fui","i"), ("rápidamente","e"), ("estoy","o"),
])
def test_spanish_stressed_vowel(word, stressed):
    assert stressed_vowel(word) == stressed

def test_unknown_spanish_word_rejected():
    assert rhyme_kind("fuego", "xuego", language=Language.ES) is None
def test_unaccented_spanish_word_reads_as_accented():
    assert rhyme_kind("canción", "corazon", language=Language.ES) is RhymeKind.PERFECT
def test_esta_reads_both_ways():
    assert set(readings("esta")) == {"esta", "está"}
def test_an_accented_word_is_never_expanded():
    assert readings("público") == ("público",)

def test_wisp_never_answers_a_used_word_in_another_spelling():
    rng = random.Random(3)
    for turn in range(200):
        reply = wisp_reply("corazón", {"cancion"}, Stage.ADULT, turn, rng,
                           language=Language.ES)
        assert reply != "canción"

@pytest.mark.parametrize(("text","word"), [
    ("¡fuego!", "fuego"), ("¿qué?", "qué"), ("**Fuego**", "fuego"),
    ("cancio\u0301n", "canción"), ("dos palabras", None), ("fuego2", None),
])
def test_clean_spanish_word(text, word):
    assert clean_word(text, language=Language.ES) == word

def test_spanish_common_list_hygiene():
    common = rhymes._common(Language.ES)
    assert 4500 <= len(common) <= 5500 and len(set(common)) == len(common)
    assert all(keys_of(word) for word in common)
    assert set(common) <= rhymes_es._known()
    # literal samples, as tests/test_rhymes.py:221 does for English
    assert not {"madrid", "méxico", "maría", "puta", "mierda"} & set(common)
    assert not {"love", "game", "the"} & rhymes_es._known()

def test_spanish_openers_have_rhymes_and_skip_function_words():
    # each opener: >= RHYME_OPENER_RHYMES rhymes, >= RHYME_OPENER_MIN_LETTERS
    # letters, not in the first RHYME_OPENER_SKIP_TOP lines of common_words_es.txt;
    # 50 seeded picks give > 1 distinct opener
    ...
def test_wisp_answers_spanish_with_perfect_common_rhymes_only(): ...
    # seeded 200 replies to "fuego": each in COMMON_ES, PERFECT, never used,
    # never a homophone

def test_no_wordfreq_at_runtime():
    sources = [*Path("wisp").rglob("*.py"), *Path("cogs").rglob("*.py")]
    assert not [path for path in sources
                if "wordfreq" in path.read_text(encoding="utf-8")]
```

- [ ] **Step 2: Run them and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhymes_es.py -q -p no:cacheprovider`
Expected: FAIL (`wisp.rhymes_es` import error).

- [ ] **Step 3: Implement the rules, then build the lists**

Port the spec's algorithm, using the scratchpad prototype `es_rhyme.py` as a reference for behaviour only. Then build the lists:

```
PYTHONUTF8=1 .venv/Scripts/python -m tools.build_common_words es
PYTHONUTF8=1 .venv/Scripts/python -m tools.build_common_words en
git diff --exit-code wisp/data/common_words.txt
```

Review the printed kept list for names, add them to `STOPLIST_ES`, and rebuild.

- [ ] **Step 4: Run them and see them pass**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhymes_es.py tests/test_rhymes.py tests/test_rules.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add wisp/rhymes_es.py wisp/rhymes.py wisp/rules.py tools/build_common_words.py wisp/data/common_words_es.txt wisp/data/known_words_es.txt wisp/data/accents_es.txt tests/test_rhymes_es.py` and commit "Add Spanish rhymes and word lists".

---

### Task 3: French rhymes and word lists

**Files:**
- Create: `wisp/rhymes_fr.py`, `wisp/data/common_words_fr.txt`, `wisp/data/known_words_fr.txt`, `wisp/data/accents_fr.txt`, `wisp/data/silent_ent_fr.txt` (all four generated)
- Modify: `wisp/rhymes.py` (FR dispatch, regex with elision, the French branch of `same_word_key`), `tools/build_common_words.py`
- Test: `tests/test_rhymes_fr.py` (new)

**Interfaces:**
- `wisp/rhymes_fr.py` (imports `WordKeys`, `fold` from `wisp.rhyme_keys`):
  - `WORD: Final = re.compile(r"[a-zàâäéèêëîïôöùûüÿœæç]+(?:['-][a-zàâäéèêëîïôöùûüÿœæç]+)*")`
  - `ELIDED: Final = frozenset({"l", "d", "j", "m", "n", "s", "t", "c", "qu", "jusqu", "lorsqu", "puisqu"})`
  - `def tail(word: str) -> str`: the part after the last `'` or `-`.
  - `def phones_of(spelling: str, silent_ent: frozenset[str]) -> frozenset[str]`: pure; spec steps 1 to 4 on a single tail, one or two readings. Step 4 (`-ent`) runs before step 2.
  - `def keys_of(spelling: str, silent_ent: frozenset[str]) -> WordKeys | None`: pure; spec step 5, with glides `j w H` counted as consonants.
  - `def readings(word: str) -> tuple[str, ...]`: returns `()` unless every part before the tail is in `ELIDED` or known; then the Spanish rule applied to `tail(word)` with `_accents()`.
  - `def keys(word: str) -> WordKeys | None`, as in Spanish.
  - `WHOLE: Final[dict[str, frozenset[str]]]` (including `"clef": frozenset({"kle"})`), plus the listed-word sets: `KEEP_FINAL_S`, `ET_SOUNDED`, `ER_OPEN`, `KEEP_FINAL_C`, `SILENT_FINAL_C`, `ENT_SILENT`, `ENT_BOTH`, `ENT_NASAL`.
  - `_known()`, `_accents()` and `_silent_ent()`: `@cache`d, read from `known_words_fr.txt`, `accents_fr.txt` and `silent_ent_fr.txt`.
- `tools/build_common_words.py`:
  - French profile constants: `NAMES_FR`, `BLOCKLIST_FR`, scan of 40,000, `word_count` 5,000;
  - known words also drop English (`zipf_en > zipf_fr + 1.0`);
  - `def silent_ent(scan: list[str]) -> frozenset[str]`: the zipf rule, worked out before the list is filtered and passed to `keys_of`; the builder prints the resulting set for review.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_rhymes_fr.py
SILENT = rhymes_fr._silent_ent()
PERFECT = [("parler","aller"), ("été","côté"), ... ]       # all spec pairs
SLANT   = [("chanter","parler"), ("été","café"), ... ]
HOMOPHONES = [("aller","allée"), ("vert","verre"), ("eau","haut"),
              ("cou","coup"), ("sang","cent"), ("brun","brin"), ("sept","cette")]
NONE    = [("parlent","chantent"), ("parlent","lent")]

@pytest.mark.parametrize(("a","b"), PERFECT)
def test_french_perfect_rhymes(a, b):
    assert compare(keys_of(tail(a), SILENT), keys_of(tail(b), SILENT)) is RhymeKind.PERFECT
# test_french_slant_rhymes, test_french_homophones_are_not_rhymes, test_french_non_rhymes

@pytest.mark.parametrize(("word","reads"), [
    ("parlent", {"paRl"}), ("moment", {"momA"}), ("content", {"kOtA", "kOt"}),
    ("tient", {"tjI"}), ("client", {"klijA"}),
])
def test_french_ent_endings(word, reads):
    assert phones_of(word, SILENT) == frozenset(reads)

@pytest.mark.parametrize(("word","reads"), [
    ("long", {"lO"}), ("blanc", {"blA"}), ("plomb", {"plO"}),
    ("vie", {"vi"}), ("rue", {"Ry"}), ("pluie", {"plHi"}),
    ("dur", {"dyR"}), ("respect", {"REspE"}), ("clef", {"kle"}),
])
def test_french_readings_from_the_review(word, reads):
    assert phones_of(word, SILENT) == frozenset(reads)

def test_elision_rhymes_on_the_word_after_it():
    assert rhyme_kind("l'été", "côté", language=Language.FR) is RhymeKind.PERFECT
@pytest.mark.parametrize("word", ["blorp'été", "xyz-côté"])
def test_elision_needs_a_real_prefix(word):
    assert rhyme_kind(word, "côté", language=Language.FR) is None
def test_same_word_key_folds_and_drops_elision():
    key = partial(same_word_key, language=Language.FR)
    assert key("l'été") == key("été")
    assert key("coeur") == key("cœur")
def test_unknown_french_word_rejected():
    assert rhyme_kind("maison", "blorpaison", language=Language.FR) is None
def test_unaccented_french_word_reads_as_accented():
    assert rhyme_kind("ete", "côté", language=Language.FR) is RhymeKind.PERFECT
    assert "garçon" in readings("garcon")
def test_known_words_are_not_expanded_to_rare_twins():
    assert readings("mais") == ("mais",)

@pytest.mark.parametrize(("text","word"), [
    ("«cœur»", "cœur"), ("mot\u00a0!", "mot"), ("mot\u202f?", "mot"),
    ("aujourd’hui", "aujourd'hui"), ("arc-en-ciel", "arc-en-ciel"), ("deux mots", None),
])
def test_clean_french_word(text, word):
    assert clean_word(text, language=Language.FR) == word

def test_french_common_list_hygiene():
    common = rhymes._common(Language.FR)
    assert 4500 <= len(common) <= 5500 and len(set(common)) == len(common)
    wholes = [keys_of(word, SILENT).whole for word in common]
    assert len({w for whole in wholes for w in whole}) >= len(common)  # no shared whole key
    assert set(common) <= rhymes_fr._known()
    # literal samples
    assert not {"paris", "marie", "jésus", "merde"} & set(common)
    assert not {"love", "game", "the"} & rhymes_fr._known()
def test_french_openers_have_rhymes_and_skip_function_words(): ...
def test_wisp_answers_french_with_perfect_common_rhymes_only(): ...
```

- [ ] **Step 2: Run them and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhymes_fr.py -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Implement the rules, then build the lists**

Port the spec's ordered rule table, using the scratchpad prototype `fr_rhyme_proto.py` as a reference for behaviour only. Then:

```
PYTHONUTF8=1 .venv/Scripts/python -m tools.build_common_words fr
```

Review the printed kept list for names and the printed `silent_ent_fr.txt` for nouns read as silent (`ciment`), then rebuild. Then rebuild `en` and run `git diff --exit-code wisp/data/common_words.txt`.

- [ ] **Step 4: Run them and see them pass**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhymes_fr.py tests/test_rhymes_es.py tests/test_rhymes.py -q -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

`git add wisp/rhymes_fr.py wisp/rhymes.py tools/build_common_words.py wisp/data/common_words_fr.txt wisp/data/known_words_fr.txt wisp/data/accents_fr.txt wisp/data/silent_ent_fr.txt tests/test_rhymes_fr.py` and commit "Add French rhymes and word lists".

---

### Task 4: Spanish and French duel lines and duel text

**Files:**
- Create: `wisp/duel_text.py`
- Modify: `wisp/lines.py`
- Test: `tests/test_lines.py`, `tests/test_duel_text.py` (new)

**Interfaces:**
- `wisp/lines.py`:
  - six new Moments: `RHYME_START_ES`, `RHYME_START_FR`, `RHYME_WISP_STUCK_ES`, `RHYME_WISP_STUCK_FR`, `RHYME_PLAYER_STUCK_ES`, `RHYME_PLAYER_STUCK_FR`;
  - `FIELDS` entries for all six: `frozenset({"word"})` for the two starts, `_NONE` for the four stuck ones (otherwise `test_fields_cover_every_moment` fails);
  - happy and hangry sets for each, at least 4 lines per mood;
  - `class RhymeMoments(NamedTuple): start: Moment; wisp_stuck: Moment; player_stuck: Moment`;
  - `RHYME_MOMENTS: Final[dict[Language, RhymeMoments]]`.
- `wisp/duel_text.py`:
  - `@dataclass(frozen=True) class DuelText` with fields `word_line: str` (`{word}`), `timed_out: str`, `not_one_word: str`, `already_used: str` (`{answer}`), `no_rhyme_with: str` (`{answer}`, `{word}`), `score_line: str` (`{points}`), `point: str`, `points_noun: str`, `zero_is_singular: bool`, `picked: str` (the picker's after-press note);
  - `def points(self, amount: int) -> str`;
  - `DUEL_TEXT: Final[dict[Language, DuelText]]`, with the spec table's strings. EN is exactly today's strings.
  - `LANGUAGE_PICKER: Final[str]`: the spec's four-line post.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_lines.py: the global moment tests cover the new Moments automatically
# (>= 4 per mood, happy and hangry written, own sets, no duplicates, no emoji,
# no dashes, fits a message, fields).
def test_rhyme_start_lines_say_the_word() -> None:          # widened, still every Mood
    for moments in RHYME_MOMENTS.values():
        for mood in Mood:
            for line in lines_for(moments.start, mood):
                assert placeholders(line) == {"word"}, line

def test_every_language_has_rhyme_moments():
    assert set(RHYME_MOMENTS) == set(Language)
    assert RHYME_MOMENTS[Language.EN] == RhymeMoments(
        Moment.RHYME_START, Moment.RHYME_WISP_STUCK, Moment.RHYME_PLAYER_STUCK)

def test_french_lines_use_plain_spaces():
    for line in _all_fr_rhyme_lines():
        assert "\u00a0" not in line and "\u202f" not in line

# tests/test_duel_text.py
def test_english_duel_text_is_unchanged():
    en = DUEL_TEXT[Language.EN]
    assert en.word_line.format(word="**fire**") == "・The word to rhyme is: **fire**"
    assert (en.timed_out, en.not_one_word) == ("Time ran out", "That wasn't one word")
    assert en.points(1) == "1 point" and en.points(0) == "0 points"

@pytest.mark.parametrize(("language","zero","two"), [
    (Language.ES, "0 puntos", "2 puntos"), (Language.FR, "0 point", "2 points")])
def test_points_pluralise_per_language(language, zero, two): ...

def test_duel_text_follows_the_line_rules(): ...
    # every field: no Unicode emoji (allows ♪), no em/en dash, no NBSP

def test_language_picker_text():
    assert "/wisp play rhyme" in LANGUAGE_PICKER
```

- [ ] **Step 2: Run them and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_lines.py tests/test_duel_text.py -q -p no:cacheprovider`
Expected: FAIL.

- [ ] **Step 3: Write the lines and the text**

Write Wisp's voice in Spanish and French: lowercase, playful, `¡`/`¿` allowed, and a plain space before French `! ?`.

- [ ] **Step 4: Run them and see them pass**

Same command. Expected: PASS.

- [ ] **Step 5: Commit**

`git add wisp/lines.py wisp/duel_text.py tests/test_lines.py tests/test_duel_text.py` and commit "Write Wisp's Spanish and French duel lines".

---

### Task 5: Picker buttons, command option and threading the language through the duel

**Files:**
- Modify: `cogs/rhyme_duel.py`
- Test: `tests/test_rhyme_duel.py`

**Interfaces:**
- `async def start_duel(interaction: discord.Interaction["WispBot"], language: Language | None = None, picker: discord.Message | None = None) -> None`, which passes both to `_host`.
- `_host(interaction, guild_id, chosen: Language | None, picker: discord.Message | None)`. After `check_game` passes and `enter_room` returns:
  - if `chosen` is set: `set_rhyme_language`; then, if `picker` is set, edit it to `DUEL_TEXT[chosen].picked` with `view=None` (a `discord.HTTPException` is reported through `bot.report_error` as "tidying the Rhyme Duel language picker" and the duel still starts); then play in `chosen`;
  - otherwise, if `player.rhyme_language` is None: post `LANGUAGE_PICKER` in the room with `language_picker(user_id)`, reply privately `♪ Pick a language for your Rhyme Duel in {thread.mention}.`, and return, so the room is freed in `finally`;
  - otherwise: play in the saved language.
- `_duel(bot, thread, user_id, life, rng, language: Language) -> _Outcome`. It uses `RHYME_MOMENTS[language]`, `DUEL_TEXT[language]`, `opening_word(rng, language=...)`, `clean_word(..., language=...)`, `rhyme_kind(..., language=...)`, `wisp_reply(..., set(chain), ..., language=...)` (which compares by `same_word_key`), and a `same_word_key` repeat check.
- `summary_text(line, reason, chain, points, *, divider, text: DuelText) -> str`. The receipt stays English.
- `class RhymeLanguageButton(discord.ui.DynamicItem[discord.ui.Button], template=re.compile(r"wisp:rhyme:lang:(?P<user_id>[0-9]+):(?P<lang>en|es|fr)"))`, matching `NameButton` (`cogs/players.py:479`):
  - `__init__(user_id: int, language: Language)`, with its label taken from `LANGUAGE_NAMES`;
  - `from_custom_id` rebuilds the button from the match;
  - `interaction_check` refuses with `♪ That button is for someone else.`;
  - its callback is `press(interaction, "the Rhyme Duel language button", partial(start_duel, language=self.language, picker=interaction.message))`. It does no editing of its own.
- `def language_picker(user_id: int) -> discord.ui.View`: three buttons in `Language` order, `timeout=None`.
- `play_rhyme` gains `language: app_commands.Choice[str] | None = None`, with `@app_commands.choices(language=[Choice(name="English", value="en"), Choice(name="Español", value="es"), Choice(name="Français", value="fr")])` and `@app_commands.describe(language="The language to rhyme in.")`.
- `setup` registers `bot.add_dynamic_items(PlayButton, RhymeDuelButton, RhymeLanguageButton)`.

- [ ] **Step 1: Write the failing tests**

```python
# fixtures: configured/lay set Language.EN for the test players
async def test_a_first_duel_posts_the_picker_and_frees_the_room(bot, server, turns):
    # player with rhyme_language None runs play_rhyme
    # room posts == [LANGUAGE_PICKER]; view custom ids ==
    #   [f"wisp:rhyme:lang:{USER_ID}:{code}" for code in ("en","es","fr")]
    # private reply mentions the room; bot.room_games == set(); turns.asked == 0
    # rhyme_language still None

def test_language_picker_buttons():
    assert [button.label for button in language_picker(USER_ID).children] == [
        "English", "Español", "Français"]

async def test_without_a_pick_the_picker_comes_again(...)   # second start, second picker

@pytest.mark.parametrize("language", [Language.ES, Language.FR])
async def test_picking_a_language_saves_it_and_starts_the_duel_in_it(..., language):
    # await RhymeLanguageButton(USER_ID, language).callback(interaction)
    # saved == language; the picker was edited to DUEL_TEXT[language].picked with
    # view None BEFORE the first duel post (record the order of edits and posts);
    # first post starts with a RHYME_MOMENTS[language].start line and ends with
    # DUEL_TEXT[language].word_line

async def test_a_failed_picker_edit_is_reported_and_the_duel_still_runs(...)
    # picker.edit raises discord.HTTPException -> report_error context
    # "tidying the Rhyme Duel language picker"; the duel posts its opener

async def test_a_saved_language_skips_the_picker(...)
async def test_the_command_option_changes_the_language(...)
    # saved EN, play_rhyme.callback(interaction, language=Choice("Français","fr"))
    # -> saved FR, the duel is in French
async def test_a_refused_start_saves_no_language(...)
    # napping + option es -> nap refusal, rhyme_language unchanged, no picker,
    # a pressed picker is not edited
async def test_only_the_member_can_press_their_language_buttons(...)
    # stranger's interaction_check False, refusal text, nothing saved, no room posts

async def test_a_spanish_duel_runs_entirely_in_spanish(..., opener="fuego"):
    # turns: "juego" (perfect, 2), Wisp's reply, "beso" (slant, 1), timeout
    # wisp_says.asked all carry Language.ES; summary has "・Puntuación: 3 puntos"
    # and the reason "Se acabó el tiempo"

async def test_an_unaccented_repeat_counts_as_used(...)
    # ES chain ["canción", <wisp>], player "cancion" -> "cancion ya se usó"
async def test_an_unknown_spanish_word_does_not_rhyme(...)  # "xuego" -> no_rhyme_with
async def test_the_receipt_stays_english_in_any_language(...)
async def test_language_buttons_survive_a_restart():
    # __discord_ui_compiled_template__.fullmatch + from_custom_id per language
async def test_the_language_ids_never_match_the_play_ids(): ...
async def test_the_play_buttons_are_registered_at_startup():
    # == (PlayButton, RhymeDuelButton, RhymeLanguageButton)
async def test_play_rhyme_has_a_language_option():
    # play_rhyme.parameters[0].name == "language", required False, three choices
```

- [ ] **Step 2: Run them and see them fail**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhyme_duel.py -q -p no:cacheprovider` (in the background).
Expected: the new tests FAIL.

- [ ] **Step 3: Implement the interfaces above**

Follow `NameButton` (`cogs/players.py:477-531`) for the `DynamicItem` and owner check.

- [ ] **Step 4: Run them and see them pass**

Run: `PYTHONUTF8=1 .venv/Scripts/python -m pytest tests/test_rhyme_duel.py tests/test_rhymes.py tests/test_lines.py -q -p no:cacheprovider` (in the background).
Expected: PASS.

- [ ] **Step 5: Commit**

`git add cogs/rhyme_duel.py tests/test_rhyme_duel.py` and commit "Let members pick the Rhyme Duel language".

---

### Task 6: Docs, full suite, ship

**Files:**
- Create: `DOCS/specs/2026-11-23-rhyme-duel-languages-design.md` (the spec above)
- Modify:
  - `README.md`: Rhyme Duel section and commands list (`/wisp play rhyme language:`);
  - `CHANGELOG.md`: a 2026-11-23 (Rhyme Duel languages) entry;
  - `DOCS/BuildRulings.md`: wordfreq is still dev-only and now builds the es/fr lists, accent maps and `silent_ent_fr.txt` (run with `python -m tools.build_common_words`);
  - `DOCS/wisp_faq.html`: a Rhyme Duel languages paragraph. Re-rendering the picture is a follow-up for Myra.

- [ ] **Step 1: Write the docs.** The CHANGELOG entry lists:
  - the picker;
  - the option;
  - rule-based Spanish (consonante/asonante) and French (suffisante/pauvre);
  - the known-word lists and the accent maps;
  - the receipt staying English;
  - the one shared best score;
  - the storage change (`players.rhyme_language`).
- [ ] **Step 2: Run the quality tools** on every touched file:
  - `PYTHONUTF8=1 .venv/Scripts/python -m black --line-length 88 <files>`
  - `isort`, `flake8` and `mypy --strict` the same way.

  Expected: clean.
- [ ] **Step 3: Run the full suite in the background** (it takes about 3 hours): `PYTHONUTF8=1 .venv/Scripts/python -m pytest -q -p no:cacheprovider`. Expected: all pass. Fix and re-run any file that fails.
- [ ] **Step 4: Commit by explicit paths and push to main** (this auto-deploys on fps.ms). Then draft the changelog note and ask Myra before posting it anywhere.
