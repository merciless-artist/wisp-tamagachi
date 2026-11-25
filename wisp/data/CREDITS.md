# Credits for the Rhyme Duel word data

The Rhyme Duel reads these sources. The files in this folder are compact
derived lists (a word and its phones, one per line), rebuilt offline by
`tools/build_pronunciations.py` and `tools/build_common_words.py`.

## Lexique 3.83 (French)

- Boris New, Christophe Pallier et al., Lexique 3.83, http://www.lexique.org
  (New, B., Pallier, C., Brysbaert, M. and Ferrand, L. (2004). Lexique 2: A
  new French lexical database. Behavior Research Methods, Instruments, and
  Computers, 36(3), 516-524).
- License: Creative Commons Attribution-ShareAlike 4.0 International
  (CC BY-SA 4.0), https://creativecommons.org/licenses/by-sa/4.0/
- Derived file: `lexique_fr.txt` (each word form with its `phon` readings,
  mapped to Wisp's French phones). It stays under CC BY-SA 4.0, and so do the
  parts of `accents_fr.txt` that come from it.

## WikiPron (English and Spanish, from Wiktionary)

- Lee, J. L., Ashby, L. F. E., Garza, M. E., Lee-Sikka, Y., Miller, S.,
  Wong, A., McCarthy, A. D. and Gorman, K. (2020). Massively multilingual
  pronunciation mining with WikiPron. Proceedings of LREC 2020, 4223-4228.
  https://github.com/CUNY-CL/wikipron
- The pronunciations are scraped from Wiktionary, https://www.wiktionary.org,
  whose text is licensed under Creative Commons Attribution-ShareAlike 4.0
  International (CC BY-SA 4.0).
- Lists used: `eng_latn_us_broad.tsv` and `spa_latn_la_broad.tsv`.
- Derived files: `wikipron_en.txt` (English words the CMU dictionary lacks,
  with ARPAbet readings) and `wikipron_es.txt` (Spanish words). They stay
  under CC BY-SA 4.0, and so do the parts of `accents_es.txt` that come from
  `wikipron_es.txt`.

## CMU Pronouncing Dictionary (English)

- Carnegie Mellon University, The CMU Pronouncing Dictionary,
  http://www.speech.cs.cmu.edu/cgi-bin/cmudict, read through the
  `pronouncing` package. BSD-style license (copyright Carnegie Mellon
  University). Nothing from it is stored here.

## wordfreq

- Robyn Speer, wordfreq, https://github.com/rspeer/wordfreq (code under the
  Apache License 2.0; data under CC BY-SA 4.0), used offline to pick the
  common and frequent word lists (`common_words*.txt`, `known_words_*.txt`).
