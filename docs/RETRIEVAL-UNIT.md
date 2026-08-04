# What is the retrieval unit?

Written 2026-08-04, after building the passage layer and starting to build the
wrong thing on top of it. Recorded so the reasoning survives the decision.

## The mistake I nearly made

The passage layer indexes **41,501,325 paragraphs** across 77,540 books. The
obvious next step looked like: embed all of them, get semantic search.

Measured cost on the mini (Apple M4, ollama, nomic-embed-text, 768 dims):
**55.5 passages/sec**. So 41.5M passages is roughly **8 days of continuous
compute** to produce ~60 GB of vectors, after which every query is a
brute-force similarity scan over 41 million items.

That does not scale to "millions of books" — it makes the problem bigger. And
the same objection kills the other proposal I floated, full-text FTS over every
passage body: both are *index everything in case*, which is exactly what the
mission charter warns against with **"questions before corpora"** and
**"do not read at random; read to change an answer."**

## The actual question

A paragraph is a chunk of text. It is not a thing you can agree or disagree with.

The questions that matter here are about **positions people hold**:
- what does Plato argue about justice
- what does this book say about scaling, applied to my business
- everything Socrates said

Those are questions about **claims**, and a claim is a different object:
> "Plato argues justice is intrinsic rather than conventional"
> — with the passages that support it as evidence.

A serious book yields dozens of claims, not 535 paragraphs. Across the 932-book
philosophy shelf that is tens of thousands of claims rather than ~500,000
passages: **two orders of magnitude smaller, and far more answerable**, because
a claim is something an argument can be built on or against.

## Why this composes with what already exists

SISO Evidence Engines' `ingest-knowledge` contract already takes exactly this
shape: a `source`, a `source_text`, and `items[]` where each item carries a
`claim`, a verbatim `quote` grounding it, a `confidence`, and a `type`
distinguishing wisdom from opinion.

That is not a coincidence. The estate already decided the unit; the books work
had drifted away from it.

Foundry's own four-layer model says the same thing: L1 content, L2 people,
L3 watch, **L4 research over the curated result**. Claims are L4. The expensive
step was never embedding — it is **extraction**, and that layer is the one that
does not exist yet.

## The layering, corrected

| Layer | Unit | Count | State |
| --- | --- | --- | --- |
| payload | book | 79,071 | published, byte-addressable |
| passage | paragraph | 41,501,325 | built; the EVIDENCE layer, fetched by id |
| claim | position | ~tens of thousands per domain | **not built** |
| vector | claim, not paragraph | same order as claims | **not built** |

Passages stay exactly as they are. They are cheap, already built, and correct as
an evidence substrate — you retrieve one once you know what you want. What was
wrong was treating them as the *search* surface.

## On storage, and a correction

I kept insisting vectors must live on the internal SSD rather than the 5 TB
vault. That was over-general.

The real failure was specific: **SQLite doing thousands of small synchronous
writes over USB 2.0 while another job hammered the same drive** produced a disk
I/O error at 500 books during the passage build. That is a transactional write
workload on a slow bus — not evidence that the vault cannot hold data.

Vectors are written once in bulk and read sequentially. A flat float32 file on
the vault is fine, and 3.8 TB free means size stops being a consideration. The
mini is always on with a tunnel already running, so it can serve queries rather
than every machine holding a copy.

Rule, stated properly: **transactional writes on internal storage; bulk
sequential artifacts on the vault.** Not "SQLite never touches the vault."

## Open question

Should claims be extracted **per-book** or **per-question**?

- Per-book is comprehensive but speculative: extract everything, hope it is
  useful. It is also how you end up with 41M paragraphs again, one level up.
- Per-question is the doctrine — read to change an answer. Cheaper and always
  relevant, but you only ever get what you asked for, and the corpus stays dark
  until someone asks.

Unresolved. Probably a hybrid: extract per-question, but cache claims so the
second question about the same book is free.
