# Rhyme Duel in three languages: design

Agreed with Myra on 2026-11-23, during the beta. She said: "we have french and spanish speakers in the server. Wisp should play the rhyme game in spanish and french too, so offer three buttons at the beginning of the game the first time they play". Wisp is live with real data, so every storage change is additive and migrates the live database safely. Anything marked **my call** was chosen by Claude, and Myra has not weighed in on it yet.

## Why

The server has Spanish and French speakers. Today the Rhyme Duel only works in English: the CMU dictionary checks the rhymes, Wisp picks his words from one English list, and every line the duel posts is an English constant. A Spanish or French speaker cannot play in their own language at all.

## Goals

- A Rhyme Duel can be played in English, Español or Français.
- The first time a member plays, Wisp asks which language with three buttons in the member's room, before the duel starts.
- The choice is remembered per member, by Discord ID, and used for every duel after that.
- A member can change it later with a `language` option on `/wisp play rhyme`.
- In the chosen language:
  - rhymes are checked, both perfect and slant;
  - Wisp's own words (the opener and his answers) are in it;
  - Wisp's duel lines are in it (the start, "I'm stuck" and "you're stuck");
  - the duel's verdicts are in it (time ran out, not one word, already used, doesn't rhyme);
  - the end-of-duel summary is in it.
- English plays exactly as it does today.

## Non-goals

- The rest of Wisp does not get translated: the status card, the Vault, the Snack Pack, the Craving, chat and the FAQ stay English.
- No separate leaderboards per language.
- No new runtime dependency and no dictionary download. `wordfreq` stays dev-only (`DOCS/BuildRulings.md:53`).
- No dialect choice (Spain vs Latin America, France vs Québec).

## Anti-goals

- Never two languages in one duel. The language is fixed when the duel starts.
- Never a nonsense word accepted as a rhyme (`xuego` for `fuego`, `blorp'été`). English rejects them through CMU, and Spanish and French must reject them too.
- Never a room held open while a member is deciding which language to pick.
- Never a new public thread. The picker and the duel both live in the member's room.

## Decisions

- **Where the picker appears.** The picker is posted in the member's room, after every normal refusal has passed (banned, not joined, no living Wisp, frozen, napping, room busy) and before the duel starts. The private reply points to the room. Posting the picker does not hold the room: the room is free again as soon as it is posted.
- **What "first time" means (my call).** It means `players.rhyme_language IS NULL`. Until a member picks, every duel start (the command with no option, or the Play menu's Rhyme Duel button) posts the picker again. Nothing is ever guessed for them.
- **Pressing a button (my call).** Pressing a button runs the same start path as `/wisp play rhyme language:<x>`. Every check runs again, then the language is saved. Right after the save, and before the duel starts, the picker is edited to a one-line note of the choice with no buttons left, so it cannot be pressed during the duel. Then the duel starts in the room. The language is saved only once the checks pass, so a refused start changes nothing and leaves the picker as it was.
- **Changing the language later.** `/wisp play rhyme language:` takes the choices English, Español and Français. It saves the language and starts a duel in it. With no option given, the saved language is used.
- **What gets translated (my call).** The duel itself is translated: the opener and its "word to rhyme" line, Wisp's turns, the stuck lines, the verdict reasons and the summary, including the score line. These stay English:
  - the receipt ("Your duel counted..." / "This duel didn't count...");
  - the private replies and refusals;
  - the button labels outside the picker.

  The receipt's reasons are shared with feeding and the Craving (`NOT_ALIVE_REASON`, `FROZEN_REASON`, `blocker_reason`), so translating only part of it would leave a line in two languages. Raise this with Myra after shipping.
- **Best score (my call).** There is still one best score per member across all languages. The scoring is the same in every language (perfect 2, slant 1), so the Vault leaderboard stays as it is.
- **Known words (my call).** Spanish and French accept a player's word only when it is in a committed "known words" list. The list is built offline from wordfreq's top 50,000 words for that language. This is what rejects nonsense, the way CMU does for English.
- **Typing without accents (my call).** A committed accent map (`wisp/data/accents_<es|fr>.txt`) maps an unaccented spelling to its accented forms:
  - `cancion` is read as `canción`;
  - `esta` is read as both `esta` and `está`;
  - `ete` is read as `été`;
  - `garcon` is read as `garçon`, and `ca` as `ça`.

  A word that already carries a removable accent is never expanded (`público` is only `público`, `maïs` is only `maïs`). An unaccented word that is itself known expands only to twins that are nearly as frequent (so `mais` stays `mais`). Every reading is compared and the best result wins, the same way English already tries every CMU pronunciation.
- **Folding (my call).** `fold(word, *, language)` NFC-normalises and removes acute, grave, circumflex and diaeresis accents in every language. French also maps `ç → c`, `œ → oe` and `æ → ae`, because French speakers routinely type without them. Spanish keeps `ñ`, because `año` and `ano` are different words.
- **Repeats (my call).** Two words are the same word when their same-word keys are equal. The key is `fold(tail(word))` in French (the part after the last `'` or `-`) and `fold(word)` otherwise. So `corazon` after `corazón`, `coeur` after `cœur` and `l'été` after `été` all count as already used. The same key is used for Wisp's own answers, so he never answers with a word the player already used in another spelling (`canción` after `cancion`).
- **Cleaning input (my call).** This change also applies to English. The steps run in this order:
  - NFC, then lowercase, then `’` becomes `'`;
  - one strip removes any run of whitespace (including Unicode spaces such as NBSP and U+202F) and edge punctuation (ASCII punctuation plus `¡ ¿ « » “ ” ‘ ’ …`) from both ends at once.

  English only gains from it: `«hat»` and `hat !` now count, and `don’t` still reads `don't`. It is the only change English sees.
- **Wisp's French typing (my call).** In Wisp's French lines there is a plain space before `! ? :`, never a no-break space.
- **Openers (my call).** Spanish and French openers need at least 8 perfect rhymes (`RHYME_OPENER_RHYMES`, as in English). They must also have at least `RHYME_OPENER_MIN_LETTERS = 4` letters, and must not be in the first `RHYME_OPENER_SKIP_TOP = 150` lines of that language's `common_words_<lang>.txt` (its most frequent words). Without this rule, function words like *la*, *que* and *le* would open duels. English openers are unchanged.
- **The French `-ent` ending (my call).** Whether the ending is silent depends on wordfreq frequencies. Those are worked out offline by the builder and committed as `wisp/data/silent_ent_fr.txt`. The builder prints the file's contents for a person to review. At runtime the bot only reads that file.
- **Headings.** The duel draws no frame heading. If one is ever added, it spells him `WiSP`.

## Picker post

The picker is a plain message in the room, with no ping:

```
♪ Which language should we rhyme in?
・¿En qué idioma rimamos?
・On rime en quelle langue ?
・Change it any time with /wisp play rhyme.
```

- **Buttons:** `English`, `Español`, `Français`, in that order.
- **Button ids:** persistent, as `wisp:rhyme:lang:<user_id>:<en|es|fr>`.
- **Anyone else who presses:** gets `♪ That button is for someone else.`
- **After a pick, the picker becomes:**
  - `♪ We rhyme in English.`
  - `♪ Rimamos en español.`
  - `♪ On rime en français.`
- **Private reply on a first play:** `♪ Pick a language for your Rhyme Duel in {room}.`

## Duel text per language

| Piece | English (today) | Español | Français |
|---|---|---|---|
| Word line | `・The word to rhyme is: {word}` | `・La palabra para rimar es: {word}` | `・Le mot à faire rimer, c'est {word}` |
| Timed out | `Time ran out` | `Se acabó el tiempo` | `Le temps est écoulé` |
| Not one word | `That wasn't one word` | `Eso no era una sola palabra` | `Ce n'était pas un seul mot` |
| Repeat | `{answer} was already used` | `{answer} ya se usó` | `{answer} a déjà été dit` |
| Not a rhyme | `{answer} doesn't rhyme with {word}` | `{answer} no rima con {word}` | `{answer} ne rime pas avec {word}` |
| Score | `・Score: N point(s)` | `・Puntuación: N punto(s)` | `・Score : N point(s)` (0 and 1 are singular) |

Wisp's lines are new Moments, with at least 4 lines per mood, written in his lowercase, playful voice:
- `RHYME_START_ES` and `RHYME_START_FR` (field `{word}`);
- `RHYME_WISP_STUCK_ES` and `RHYME_WISP_STUCK_FR`;
- `RHYME_PLAYER_STUCK_ES` and `RHYME_PLAYER_STUCK_FR`.

Examples:
- start: `¡a rimar! empiezo yo con {word}` / `on rime ! je commence avec {word}`
- hangry start: `rápido, tengo hambre. rima con {word}` / `vite, j'ai faim. rime avec {word}`
- Wisp stuck: `uy, me quedé sin rimas. ¡ganaste esta!` / `oh non, je sèche. tu as gagné celle-là !`

Claude writes them. Myra, or native speakers in the server, can edit them.

## Shared key interface

`WordKeys`, `RhymeKind`, `fold` and `compare` live in a leaf module, `wisp/rhyme_keys.py`, which imports nothing from the other rhyme modules. `wisp/rhymes.py`, `wisp/rhymes_es.py`, `wisp/rhymes_fr.py` and the builder all import it, so there is no import cycle.

## Spanish rhyme keys (rule-based, from spelling)

A word yields `WordKeys(whole, perfect, slant)`, each a `frozenset[str]` (one element per reading).

0. **Clean.** NFC, lowercase, then the word must match `[a-záéíóúüñ]+`.
1. **Letter pass**, left to right:
   - `h` is silent unless it is part of `ch`.
   - `u` after `q`/`g` and before `e é i í` is silent. The `q` becomes `k`, and the `g` becomes a hard `G` (`guerra`, `guion`).
   - `ü` is a weak u.
   - `y` is a weak-i vowel when it is the whole word or no vowel follows it (`rey`, `hoy`, `muy`). Otherwise it is a consonant.
2. **Vowel groups.** Strong vowels are `a e o á é ó`. Weak vowels are `i u ü y` (when `y` is a vowel). Consecutive vowels join into one group, except that a new group starts:
   - at `í` or `ú`, or right after one (`día`, `país`, `búho`);
   - at a strong vowel when the group already has one (`poeta`, `leer`, `ahora`).

   Weak+weak and weak+strong+weak stay together (`ciudad`, `fui`, `buey`). `guion` is one syllable (RAE 2010).
3. **Stressed group**, in precedence order:
   1. a word ending in `-mente` with more than 2 groups: the second-to-last group;
   2. a written acute accent: that group;
   3. a word with one group: that group;
   4. a word ending in a vowel, `n` or `s`: the second-to-last group;
   5. anything else, including a final `y`: the last group.

   Inside the group, the stressed vowel is the accented vowel, otherwise the strong vowel, otherwise the last weak vowel.
4. **Sound normalisation:**
   - accents and `ü` become plain vowels;
   - `b`/`v` become `b`;
   - `ll` and consonant `y` become `y`;
   - `z`, `s` and `c`+e/i become `s` (seseo);
   - `c` elsewhere, `qu` and `k` become `k`;
   - `g`+e/i and `j` become `x`;
   - `gu`+e/i becomes `g`;
   - `rr` becomes `R` (kept apart from `r`);
   - `ch` becomes `C`;
   - `x` becomes `ks`;
   - `w` becomes `u`;
   - `ñ` stays.
5. **The three keys:**
   - **Whole:** the normalised whole word. Two words with an equal whole key are homophones, and homophones are not a rhyme.
   - **Perfect (rima consonante):** the normalised sound from the stressed vowel to the end. A glide before that vowel is excluded, so `cielo`, `hielo` and `pelo` all give `elo`.
   - **Slant (rima asonante):** the stressed vowel plus the main vowel of the last unstressed group.
     - Only the strong vowel of a group counts.
     - Middle vowels are ignored.
     - A final unstressed `i` counts as `e`, and a final unstressed `u` as `o`.
     - Words stressed on the last syllable keep only the stressed vowel.
6. **Comparing two words.** Return None when the words have the same same-word key, when any whole keys match, or when a word cannot be read. Otherwise return PERFECT when any perfect keys match, then SLANT when any slant keys match. Otherwise return None.
7. **Readings.**
   - A word that carries a removable accent (`fold(word, language=ES) != word`) has one reading, itself, when it is known.
   - An unaccented word reads as itself when it is known, plus the accented twins the accent map lists for it.
   - The builder writes the map so that, for an unaccented word that is itself known, it lists only twins whose zipf is at least `zipf(word) - 0.7`.
   - If there are no readings, the word is unknown.

**Test pairs**

- **Perfect:**
  - canción/corazón, amor/dolor, cielo/pelo, luna/cuna, casa/masa, única/túnica
  - calle/valle, calle/raye, lava/baba, guerra/tierra, pingüino/camino, quiso/piso
  - guiso/piso, queso/beso, país/maíz, día/tía, poeta/meta, rey/ley, hoy/voy, muy/fui
  - ciudad/verdad, cuidado/olvidado, lentamente/gente, gente/mente, estás/jamás, noche/coche
  - fuego/juego, huevo/nuevo, hielo/cielo, mar/amar, camión/canción, guion/camión
  - leer/creer, construir/vivir, reír/vivir, ahumado/cansado
- **Slant:**
  - casa/cama, casa/casas, música/única, patio/radio, patio/barco, gloria/sombra
  - pálido/llano, rápido/cántaro, venus/beso, tribu/libro, tesis/mece, día/vida
  - rápidamente/siempre, perro/pero, fuego/beso, aire/baile, árbol/mármol
- **None:**
  - homophones: casa/caza, hola/ola, vaca/baca, gente/jente
  - no rhyme: árbol/cielo, sol/mar, joven/examen, útil/fácil, régimen/imagen

## French rhyme keys (rule-based, from spelling)

**Phones.** Each phone is one character:

| Kind | Symbols |
|---|---|
| Vowels | `a` (a/â), `e` (é), `E` (è/ê/ai), `i`, `o` (o and ɔ merged), `u` (ou), `y` (u), `2` (eu/œ, and a final schwa), `@` (inner schwa, never a rhyme vowel), `A` (an/en), `I` (in, with un merged), `O` (on) |
| Glides | `j`, `w`, `H` |
| Consonants | `p b t d k g f v s z m n l`, `S` (ch), `Z` (j), `N` (gn), `R` |

A **vowel group** is a run of consecutive vowel letters (`aàâäeéèêëiîïoôöuùûüyÿœæ`).

1. **Normalise.**
   - NFC, lowercase, `’` becomes `'`, then strip the edges.
   - **Elision.** Split on `'` and `-`. Every part before the tail must be an elided article or pronoun (l d j m n s t c qu jusqu lorsqu puisqu) or a known word. Otherwise the whole word is unknown, so `blorp'été` and `xyz-côté` are rejected.
   - Keep the tail, the part after the last `'` or `-` (`l'été` → `été`).
   - The tail must match `[a-zàâäéèêëîïôöùûüÿœæç]+`.
   - Check the `WHOLE` exception table first, about 50 words: est, et, les/des/mes, eu, femme, monsieur, fils, plus, tous, os, six, dix, huit, sept, août, œil, second, ville, mille, tranquille, comment, client, gentil, outil, parfum, écho, technique, chœur, œuf/œufs, hier, fier, dessus, clef (→ `kle`)…
2. **Silent tail**, in this order. Step 4 runs before this step and decides whether a final `-ent` is silent.
   - a. Final `e`:
     - A final `-e`/`-es` right after a vowel letter is always mute (vie, joie, pluie, rue, vue, amie).
     - Otherwise, in words with 2 or more vowel groups, a final `e`/`es` becomes a mute marker `ə`.
     - A final `-ent` that step 4 marked silent becomes `ə`.
     - `-ée(s)` becomes `é`.
   - b. A final `s`/`x` is dropped unless the word is listed (as, mars, ours, sens, maïs, tennis, virus, bus, fils, index, lynx…).
   - c. `-ez`/`-ed` become `e`. `-et` becomes `E`, except listed words (net, est, ouest, test, internet…). The body gets `ə`.
   - d. `-er` becomes `ER` when the word is listed (mer, hiver, enfer, amer, super…), when no vowel comes before it (cher, ver), or in `-vers` words. Otherwise it becomes `e` and the body gets `ə`.
   - e. Final consonants, up to 2 passes:
     - silent: t, d, p, z;
     - in `-ng`, `-nc` and `-mb`, only the g, c or b is silent, and the n or m stays to nasalise the vowel (long → `lO`, blanc → `blA`, plomb → `plO`);
     - kept: c, r, f, l, b, -ct, -pt, unless listed (tabac, porc, nerf, gentil, outil, respect, aspect…);
     - `-mpt`/`-gt` drop both letters;
     - when a silent final consonant (or `-ct`) is stripped right after `e`, that e reads `E` (respect → `REspE`).
   - f. A word left ending in `er` after the strip becomes `ER`.
   - g. Glide fix: premier → `je`, jouer → `we`, tuer → `He`.
   - h. Collapse doubled phones.
3. **Body.** Read left to right, and at each position the first matching pattern in this ordered table wins. V = vowel letter, Vm = V or `ə`.

| # | Pattern | Phones |
|---|---|---|
| 1 | `eaux?` | o |
| 2 | `œu`, `oeu`, `œ` | 2 |
| 3 | `ou`+V | w |
| 4 | `ou`, `où`, `oû` | u |
| 5 | `oin` (not followed by Vm/n) | wI |
| 6 | `o` before `y`+Vm | wa |
| 7 | `oi`, `oî` | wa |
| 8 | `ain`/`ein` (not followed by Vm/n), `aim` (not followed by V/ə/m) | I |
| 9 | `aill`/`eill`/`euill` and `ueill`/`ouill` | aj/Ej/2j/uj |
| 10 | `ail$`, `eil$`, `euil$`, `ouil$` | aj, Ej, 2j, uj |
| 11 | `a` before `y`+Vm | E |
| 12 | `ai`, `aî`, `ei`, `ay` | E |
| 13 | `au` | o |
| 14 | `eu`, `eû` | 2 |
| 15 | `ienc` | jAs |
| 16 | `ien` (not followed by Vm/n) | jI |
| 17 | `éen$` / `yen$` | eI / jI |
| 18 | `emm` | am |
| 19 | `^ex` + Vm or h | Egz |
| 20 | `[ae][mn]` (not followed by V/ə/m/n/h) | A |
| 21 | `um$` | om |
| 22 | `[iyu][mn]` (not followed by V/ə/m/n/h) | I |
| 23 | `o[mn]` (not followed by V/ə/m/n/h) | O |
| 24 | `ill` after a consonant letter (a lookbehind: the consonant is read on its own) / `^ill` | ij / il |
| 25 | `uin` (not followed by Vm/n), `ui`, `u`+V | HI, Hi, H |
| 26 | `i`+V, `y`+Vm | j |
| 27 | é ë → e, è ê → E, à â ä → a, î ï y ÿ → i, ô → o, u û ü → y, ù → u | |
| 28 | `e` before 2 consonants (except obstruent+l/r, ch, ph, th, gn) | E |
| 29 | `e` before a final consonant | E |
| 30 | any other `e` | @ |
| 31 | sch/ch/sh → S (ch+r/l/n → k), ph → f, th → t, gn → N | |
| 32 | `cc`+e/i/ə → ks, `c`+e/i/y/ə → s, ç → s, cqu/qu/q → k, ck/cc/c → k | |
| 33 | `gu`+e/i/ə → g, `ge`+a/o/u → Z, `g`+e/i/y/ə → Z, n`g`t → silent, otherwise g | |
| 34 | `tio`+n+Vm → tjo after s/t, otherwise sjo; `tion` → tjO after s/t, otherwise sjO; `ti`+el/al/eu → sj | |
| 35 | V`s`Vm → z, ss / sc+e/i → s, otherwise s | |
| 36 | `x`+ième → z, otherwise x → ks; h → silent; ə → silent | |
| 37 | doubled consonants collapse; j → Z, r → R | |

4. **`-ent` verb ending.** This step runs first, before step 2, and decides whether a final `-ent` is silent. Only after that does step 2a turn a silent `-ent` into `ə`. The checks run in this order:
   1. Plural `-ents` always reads as a noun or adjective.
   2. `-aient` is silent, and so are the forced-silent words rient, lient, nient, fient, peuvent, savent, veulent, doivent.
   3. These words return both readings: content, couvent, président, résident, parent, violent, ferment, excellent, différent, convergent, influent, négligent, précédent, adhérent…
   4. These are forced nasal: comment, urgent, évident, souvent, moment, argent, torrent. So is any word under 5 letters.
   5. Any other word is silent when it is in `silent_ent_fr.txt`.

   For the nasal reading, `-ient` reads `jI` after t/v that does not follow a/o. Otherwise it reads `jA`.

   The builder writes `silent_ent_fr.txt` and prints its contents for review. A word goes in when all three hold:
   - its stem (the word minus `nt`) has 4 or more letters;
   - `zipf(stem) >= 2.5`;
   - `zipf(word) - zipf(stem) < 1.0`.
5. **The three keys**, from the last vowel that is not `@`. A final `@` becomes `2`. For the keys, the glides `j`, `w` and `H` count as consonants (`soleil` = `solEj` gives the perfect key `Ej`).
   - **Whole:** the full reading.
   - **Perfect** (rime suffisante or better):
     - when the reading ends in consonants, the last vowel plus those consonants;
     - when it ends in a vowel, the phone before it plus the vowel;
     - a word that is only one vowel uses the vowel alone.
   - **Slant** (rime pauvre or assonance): the last vowel alone, with `e`/`E` and `2`/`@` merged.

   Comparison and readings work as in Spanish, on the tail, with French `fold` and `accents_fr.txt`.

**Test pairs**

- **Perfect:**
  - parler/aller, été/côté, beauté/été, forfait/bienfait, fait/bienfait, mort/sort, porte/sorte, chat/achat
  - moi/toi, roi/loi, mer/fer, mer/amer, hiver/enfer, château/gâteau, temps/content, moment/vraiment
  - aiment/crème, chantent/plantent, raison/maison, nation/passion, nation/camion, fille/famille
  - soleil/pareil, soleil/abeille, travail/détail, yeux/cieux, fleur/cœur, fleur/peur, heure/beurre
  - chose/rose, ville/tranquille, nuit/minuit, nuit/pluie, lui/pluie, vie/envie, ami/parmi
  - dur/sûr, amour/toujours, jour/tour, voix/fois, noir/soir, noir/avoir, cheval/animal, ciel/miel
  - bec/sec, neuf/œuf, prix/gris, gentil/outil, croire/boire, table/câble, sable/diable, l'été/côté
  - lumière/rivière, étoile/voile, tienne/vienne, bien/rien, chien/lien, client/orient, tient/vient
  - respect/aspect, direct/correct, femme/flamme, prudemment/vraiment, question/bastion, monsieur/mieux, long/blond
- **Slant:**
  - chanter/parler, été/café, lait/fait, mort/porte, chat/rat, beau/peau, bateau/chapeau, chaud/faux
  - trop/mot, loup/fou, genou/bijou, hibou/caillou, temps/vent, enfant/temps, enfant/content
  - pain/main, matin/chemin, plein/rein, bon/pont, feu/jeu, ami/souris, rue/vue, plus/jus
  - grand/blanc, nez/assez, chez/parler, patient/souvent, os/dos, deux/eux
- **None:**
  - homophones: aller/allée, vert/verre, eau/haut, cou/coup, sang/cent, brun/brin, sept/cette
  - no rhyme: parlent/chantent, parlent/lent

**Known limits** (accepted):
- `-ent` verbs whose stem is rare can read as nasal.
- Nouns can read as silent under the zipf rule when their stem is a common word (`ciment`, stem `cime`). The review pass over the printed `silent_ent_fr.txt` catches the ones that matter.
- é and è in final `-ai` cannot be told apart from spelling.
- Open and closed o and eu are merged.
- Unlisted Latin words or loanwords with a final t/s.
- Final `-il` outside the list.
- `juillet`.
- `-tie` (démocratie).

## Word lists (built offline, committed)

`python -m tools.build_common_words <en|es|fr>` (run from the repo root, so `wisp` imports) writes these files:

| File | What it holds |
|---|---|
| `wisp/data/common_words.txt` | English, unchanged, byte for byte |
| `wisp/data/common_words_es.txt` / `_fr.txt` | 5,000 words each: Wisp's openers and answers |
| `wisp/data/known_words_es.txt` / `_fr.txt` | every word a player may use |
| `wisp/data/accents_es.txt` / `_fr.txt` | the accent map, one line per entry: `unaccented<TAB>accented accented ...` |
| `wisp/data/silent_ent_fr.txt` | French `-ent` verb forms read as silent |

**Known words** are wordfreq's top 50,000 for the language, kept when:
- the word has the right shape for the language;
- the rules can read it;
- it is not English: Spanish drops it when `zipf_en - zipf_es >= 1.0`, French when `zipf_en > zipf_fr + 1.0`;
- it is not an unaccented spelling whose accented twin is at least 0.7 zipf more frequent (`tambien`, `corazon`, `etat`, `garcon`). Those twins are reached through the accent map instead.

Profanity is not dropped from the known words, because players may rhyme with anything, as in English.

**The accent map** is built from the known words. Its keys are folded spellings (with the language's `fold`). For a key that is not itself a known word, it lists every known spelling with that fold. For a key that is itself known, it lists only the twins whose zipf is at least `zipf(word) - 0.7`, and the entry is left out when none qualify.

**Spanish common words** are scanned from the top 30,000, filtered in this order:
1. Shape: `[a-záéíóúüñ]{3,}`, plus the two-letter words yo, tu, tú, mi, fe, va, ve, da, ir, ya, no, sé, sí.
2. The last letter is in `aeiouáéíóúnsrldzyj`.
3. At most one acute accent, and `ü` only in güe/güi.
4. No doubled letters except cc, ll, rr, nn, ee and oo.
5. Not English: drop the word when `zipf_en - zipf_es >= 1.0`.
6. Not an accent misspelling (the 0.7 margin).
7. The rules can read it.
8. Not on STOPLIST_ES (names and places) or BLOCKLIST_ES (profanity).

The first 5,000 that pass are written in frequency order.

**French common words** are scanned from the top 40,000 and kept when:
- the word matches the French letters with 3 or more letters;
- it is the most frequent spelling of its folded form;
- it has no w or k, and fails the English test `zipf_en > zipf_fr + 1.0`;
- it has a reading;
- it is not a homophone of a word already kept;
- it is not on BLOCKLIST_FR or NAMES_FR.

NAMES_FR covers first names, places, religious names, brands and abbreviations. The 5,000 are written in frequency order.

The tool prints what it keeps (and, for French, `silent_ent_fr.txt`) so a person can review it. Wordfreq lowercases everything, so names cannot be detected automatically.

## Storage (all additive)

- `players.rhyme_language VARCHAR(2) NULL`, which holds `en`, `es` or `fr`. NULL means "not chosen yet", and it is the first-time flag.
- The column goes in the `players` definition and in `_ADDED_COLUMNS["players"]`.
- No other table changes.

## Numbers (`wisp/rules.py`)

- `RHYME_OPENER_MIN_LETTERS = 4` and `RHYME_OPENER_SKIP_TOP = 150`, written next to `RHYME_OPENER_RHYMES` in the same style (no `Final`). They apply to Spanish and French openers only. "The most frequent 150" means the first 150 lines of `common_words_<lang>.txt`.
- Every existing `RHYME_*` number is shared by all three languages.

## Left to the builder

- The exact wording of Wisp's Spanish and French lines, within the voice and rules above.
- The final stoplists and blocklists, after a review pass over the builder's output.
- Tests against real `wisptest_` tables, as the project requires.
