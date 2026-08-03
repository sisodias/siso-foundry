# The SISO Books Module — architecture

Written 2026-08-03. Every number here was measured, not estimated.

## The insight that shapes everything

The use cases are **queries about people and ideas**, not files in folders:

- "Everything Socrates ever said" → an author query spanning many works
- "What does *Exponential Organizations* say about scaling, applied to my business" → one work, fetched by id, extracted against a question
- "A people graph" → relations between persons, works, subjects, claims

None of those care where bytes physically sit. They care that **the index answers
fast**. So the storage layer is deliberately boring, and all design effort goes
into the index. Agents never navigate directories; they query, get an address,
pull bytes.

Corollary: **do not decide the physical batching yet.** If location is just an
address in the index, the corpus can be repacked later without breaking a single
reference. Deciding now, before we know how the collection is actually used,
optimises for a guess.

## Layers

| Layer | Answers | Status |
| --- | --- | --- |
| `person` / `person_work` | who wrote what, when they lived, in what role | **BUILT** |
| `book` + `book_field` | what exists, every upstream column verbatim | **BUILT** |
| `book_subject` / `book_class` / `subject_facet` | what it is about | **BUILT** |
| `passage` | atomic claims extracted from text, tied to person + work | not started |
| payload | the bytes | Gutenberg pulling; layout undecided on purpose |

## What is built and verified

**`books.sqlite` — 182 MB.** 79,071 rows from the official bulk catalog
(`https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv`, 21 MB, 5 s).
Lossless: all nine upstream columns present, 5/5 sampled rows round-tripped
exactly against source. The whole raw row is kept as JSON per book, so an
upstream schema change loses nothing and the module rebuilds without re-fetching.

- 184,624 book↔subject edges
- 206,269 book↔shelf edges
- 82,405 book↔LoCC classification edges, covering 99.98% of Text works
- 42,335 distinct subjects

**`people.sqlite` — the people graph.** Built in 3.28 s from author strings.

- **36,456 people**, 870 flagged corporate (institutions, not humans)
- **27,718 with life years** (76%)
- **107,987 person↔work edges**
- **0 unparsed author chunks**
- Roles captured distinctly: author, editor, translator, illustrator,
  commentator, compiler, composer, annotator, adapter, arranger, artist,
  collaborator, and more — because "wrote" and "translated" are different edges
  and merging them corrupts attribution.

Verified queries: Plato 75 works (*Republic*, *Critias*, *Timaeus*, *Lysis*,
*Charmides*, *Laches*, *Protagoras* …), Nietzsche 40, Aristotle 20, Spinoza 13.
Most prolific: Shakespeare 336, Widger 289, Bulwer-Lytton 226, Twain 204,
Dickens 180, Dumas 177.

### Known flaw, recorded honestly

Ancient authors carry BCE dates *inside the name string* — `Plato, 428? BCE-348?
BCE` parses as display name with `birth_year` NULL. The regex only understands
CE years. Not wrong data, but incomplete: any query filtering by century silently
drops antiquity. Fix before the graph is used for chronological reasoning.

`Widger, David` at 289 works is a Gutenberg *volunteer editor*, not an author —
which is exactly why roles are stored separately. Filter by
`role='author'` for authorship questions.

## Why classification is inherited, not invented

The catalog carries **Library of Congress Classification** on 99.98% of texts,
assigned by professional librarians. That yields 21 sections and their bookcases
with no model call and no curation:

P Language & Literature 45,680 · D World History 8,389 · B Philosophy/Psych/
Religion 4,828 · A General Works 3,235 · Q Science 2,931 · E American History
2,415 · H Social Sciences 2,110 · F Local History 2,019 · T Technology 1,722 ·
G Geography 1,548 · N Fine Arts 1,314 · … · V Naval Science 126

Pure philosophy (B, BC, BD, BJ) = 932 books, including Descartes' *Discourse on
Method* and Spinoza's complete *Ethics*.

## Why membership is a relation, not a folder

Measured: books carry **4.25 subjects each on average, and 199 of 200 belong to
more than one shelf**. Filing each book under one directory would discard most of
what the catalog already knows. So subjects are edge tables; a shelf is a saved
query, not a path. A book appears everywhere it belongs, and re-classifying costs
an UPDATE rather than a move.

This also kills subject-based physical sharding: **356× imbalance** between the
largest section (P, 56% of the corpus, ~8.2 GB gzipped) and the smallest (V, 126
books). Meaning-based location does not distribute.

## Storage, when we get there

Constraints that are real:
- GitHub blocks files >100 MiB; repos are capped at 10 GB on-disk; pushes at 2 GiB.
- **Release assets**: 2 GiB per file, 1000 per release, no documented cap on total
  release size, and *not counted toward repo size* — measured: yt-dlp reports a
  60 MB repo while carrying 1,674 MB of assets across three releases.
- **HTTP Range works**: 206 confirmed on both `raw.githubusercontent.com` and
  release-asset URLs. One request retrieves one book from a large archive.
- GitHub AUP forbids "excessive automated bulk activity" — warehouse, not
  working disk. Cache locally.

Three tiers: **GitHub** = durable distribution and offsite backup (makes the
vault's unreadable SMART status survivable). **5 TB vault** = local mass cache.
**Internal SSD** = hot working set, including all live SQLite.

Prior art: GITenberg (`https://github.com/GITenberg`) runs **50,000 repos, one per
book**, named `Title-slug__<gutenberg_id>` — so their repos join directly to our
`gid`. Proven viable, but one-repo-per-book costs ~200 h just to enumerate a
million repos at 5,000 API req/h. Not Project Gutenberg's own account; it lags
upstream (newest ~75,9xx vs 79,000+).

## Rights

Gutenberg is public-domain-US by construction — recorded as `public_domain_us`,
never a blanket public-domain claim. In-copyright works (*Exponential
Organizations 2.0*, Talbot's *Holographic Universe*) enter as **extracted claims
plus short quotes with rights recorded**, never full text in a public repo. That
is also the more useful artifact: principles to test a business against, not the
book.

`DATA-MANIFEST.json` rule: unknown rights block promotion; "pending" is a valid
and safer answer than a guess.

## Text quality gate

PDFs are print format, not text format. `probe_text_layer.py` samples 12 pages
across the body (skipping front matter, where scanned books fake having text) and
returns TEXT / PARTIAL / OCR_REQUIRED.

Measured: Talbot's *Holographic Universe* (342 pp) yielded **3,707 words** via
pdftotext — verdict PARTIAL, 1/12 pages with text — because the body is page
images. Its Internet Archive `_djvu.txt` sidecar yielded **131,713 words**, 35×
more. IA pre-OCRs everything: 12/12 sampled items carry a `DjVuTXT` file. But IA's
own docs warn OCR can be "sub-optimal to unusable" for some scripts, so quality
must be gated at ingest, not assumed.

Prefer text-native sources: Gutenberg, Standard Ebooks, arXiv LaTeX source, PMC
JATS XML, university OAI-PMH repositories (the LUISS thesis probed TEXT, 12/12,
born-digital from Word).
