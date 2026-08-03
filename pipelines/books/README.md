# Foundry Books Domain

Books intelligence is a Foundry domain — the fifth instance of the same
four-layer loop, not a new architecture. Per FOUNDRY-NORTH-STAR: *"build the
loop once in core/, and every new domain is an adapter, not a rewrite."*

The domain's distinguishing property: **books arrive pre-classified.** Unlike
GitHub repos or YouTube videos, the world's librarians have already assigned
Library of Congress Classification and subject headings. We inherit a
century-old taxonomy instead of inventing or model-guessing one.

## Layer state

| Layer | What it does here | State |
| --- | --- | --- |
| L1 content | Catalog every work, inherit LoCC + LCSH classification | **built** |
| L2 people | Every author/editor/translator, linked to their works | **built** |
| L3 watch | Gutenberg publishes new books continuously; diff the catalog | not started |
| L4 research | Extract claims from text, tied to person and work | not started |

## Measured state (2026-08-03)

L1 — from the official bulk catalog
(`https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv`, 21 MB, 5 s):

- **79,071 works** (77,820 Text; the rest audio/dataset/image, retained)
- 184,624 work↔subject edges, 206,269 work↔shelf edges
- 82,405 LoCC classification edges covering **99.98%** of Text works
- 42,335 distinct subjects
- Lossless: all nine upstream columns present, 5/5 sampled rows round-tripped
  exactly. The whole raw row is stored as JSON per work, so an upstream schema
  change loses nothing and the module rebuilds without re-fetching.

L2 — parsed from author strings, no scraping, 3.28 s build:

- **36,456 people**, 107,987 person→work edges, 0 unparsed
- 27,771 with life dates; 870 flagged corporate (institutions, not humans)
- Roles kept as distinct edges: author, editor, translator, illustrator,
  commentator, compiler, composer, annotator, adapter, arranger, artist,
  collaborator. "Wrote" and "translated" are different claims; merging them
  corrupts attribution. Filtering `role='author'` drops a Gutenberg volunteer
  editor who would otherwise rank as the second most prolific writer in history.
- BCE years stored negative (`Plato, 428? BCE-348? BCE` → −428/−348) so
  chronological range queries span antiquity instead of silently dropping it.

Verified: Plato 48 philosophy works, Nietzsche 35, Schopenhauer 21, Kant 17,
Voltaire 14, Spinoza 13, Hegel 9.

## Files

| File | Role |
| --- | --- |
| `build_books_module.py` | L1 — bulk catalog → `books.sqlite` |
| `build_people_graph.py` | L2 — author strings → `people` + `person_work` |
| `probe_text_layer.py` | ingest gate — does a PDF have usable text? |

## The text-layer gate

PDF is a print format, not a text format. Roughly half of scanned material has
no text layer, and extraction silently returns a fraction of the book.

Measured: Talbot's *Holographic Universe* (342 pp) yielded **3,707 words** via
pdftotext — 1 of 12 sampled pages carried text, because the body is page images.
The Internet Archive `_djvu.txt` sidecar for the same book yielded **131,713
words**, 35× more. IA pre-OCRs everything (12/12 sampled items carry a `DjVuTXT`
file), but IA's own docs warn output can be "sub-optimal to unusable" for some
scripts — so quality is gated at ingest, never assumed.

`probe_text_layer.py` samples 12 pages across the body, deliberately skipping
the first 5% because front matter is exactly where a scanned book fakes having
text. Returns TEXT / PARTIAL / OCR_REQUIRED plus a shell exit code.

Prefer text-native sources: Gutenberg, Standard Ebooks, arXiv LaTeX source,
PMC JATS XML, university OAI-PMH repositories.

## Data plane

Code here; data external, per the Foundry law. `core/paths.py` resolves
`domain_db("books")` → `<FOUNDRY_DATA>/domains/books/books.sqlite`.

Payload (11,244,765,936 bytes of plaintext, refreshed weekly upstream) lives on
the vault at `library/gutenberg/`, never in Git.

## Rights

Gutenberg is public-domain-US **by construction** — recorded as
`public_domain_us`, never a blanket public-domain claim; non-US law differs.
In-copyright works enter as extracted claims plus short quotes with rights
recorded, never as full text. Unknown rights block promotion; `pending` is a
valid and safer answer than a guess.

## Feeding the people graph

`core/people_schema.sql` is the canonical cross-domain model. Books is a fourth
`person_content.domain` value — `domain='book'`, `content_ref=<gutenberg gid>`.
No schema change required; the edge table was built generic for exactly this.

Scale note: the canonical graph currently holds 471 people with 3 humans
stitched across all three existing domains. The books leg is 36,456 people —
77× the whole graph. The definition adopted is **"people who produced
something"**, so book authors are first-class members alongside GitHub and
YouTube creators, and overlaps (an author who also has repos and posts) become
the high-value multi-source cases.

The identity matcher that would populate `external_ids` across domains does not
exist yet. That, not schema, is why cross-domain stitch is 3.
