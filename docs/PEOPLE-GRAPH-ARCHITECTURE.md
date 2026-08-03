# The People Graph — the layer above every domain

Written 2026-08-03. Every number measured, with the command that produced it.

## The thesis

Domains scrape *content*. But content is made by *people*, and the same human
shows up across every domain: a GitHub login, a YouTube channel, a Twitter
handle, a Reddit account, an author name on a book. The people graph is the
layer **above** all of them — the only place where "everything this human has
ever produced, across every medium" is answerable.

That is why it is canonical and the domains are satellites. A domain answers
"what exists here". The people graph answers "who, and what else did they do".

## What already exists (and it is the right shape)

`foundry/core/people_schema.sql` — the canonical model, already built:

```
person          canonical entity, stable person_id
external_ids    one row per (person, platform) -- the JOIN KEY across domains
person_content  edges: person -> (domain, content_ref)
v_person_layers view: how many domains each person appears in
```

Its own design law, quoted from the file:

> one canonical entity table + a thin external_ids model (one row per platform
> identity) + a generic person_content edge table. We do NOT duplicate the
> satellites; we reference them (content ref = repo full_name OR video_id).

`external_ids.platform` already anticipates `youtube_channel_id`, `github_login`,
`x_handle`, `website`. Twitter and Reddit need no schema change — they need rows.

## Measured state of the canonical graph

Live DB: `~/foundry-data/domains/people/people.sqlite` (28.5 MB, built 26 Jun).
Read-only query receipts:

| Metric | Count |
| --- | --- |
| person | **471** |
| external_ids | 419 |
| person_content edges | 432 |
| — github | 300 |
| — youtube_video | 97 |
| — youtube_channel | 35 |
| origin: github | 297 |
| origin: registry | 140 |
| origin: youtube | 34 |

Cross-domain stitch (`v_person_layers`):

| layers | people |
| --- | --- |
| 3 (registry + github + youtube) | **3** |
| 2 | 21 |
| 1 | 447 |

**The honest read: the schema is excellent and the graph is nearly empty.**
471 people, and only 3 humans stitched across all three domains. The design
anticipated Karpathy-style full stitches; it has three of them.

## What the books leg adds

Built today from Gutenberg catalog metadata alone — no scraping, no model calls:

| Metric | Count |
| --- | --- |
| people | **36,456** |
| person→work edges | **107,987** |
| with life dates | 27,771 |
| flagged corporate (not humans) | 870 |
| unparsed author strings | 0 |

That is **77× the entire canonical graph**, from one domain, in 3.28 seconds of
build time. Philosophy alone: Plato 48 works, Nietzsche 35, Schopenhauer 21,
Kant 17, Voltaire 14, Spinoza 13, Hegel 9.

## How the layers actually tie together

```
                    ┌─────────────────────────────┐
                    │       PEOPLE GRAPH          │  ← canonical, cross-domain
                    │  person + external_ids      │
                    │  + person_content edges     │
                    └──────────────┬──────────────┘
        ┌──────────┬───────────┬───┴───────┬───────────┬──────────┐
     GitHub     YouTube      Books      Twitter     Reddit    Podcasts
     (live)      (live)   (built today)  (none)     (none)   (scaffold)
     repos      channels    79,071      handles    accounts
                +videos      works
        └──────────┴───────────┴───────────┴───────────┴──────────┘
                         domain satellites
                    each owns its own content store
```

**The join key is `external_ids`.** A human with a GitHub login, a YouTube
channel and a book authorship collapses to ONE `person_id` with three identity
rows and N content edges. That is what makes "everything X ever produced"
a single query instead of five.

**Satellites are referenced, never duplicated.** `person_content.content_ref`
holds a repo full_name, a video_id, or a Gutenberg gid. The bytes stay in the
domain that owns them.

## Adding books as a domain — no schema change needed

`person_content.domain` currently takes `github` | `youtube_video` |
`youtube_channel`. Books is a fourth value: `domain='book'`,
`content_ref=<gutenberg gid>`. The table was built generic for exactly this.

Two real design questions before merging, which are NOT yet settled:

1. **Absorb or federate?** Adding 36,456 people to a 471-person entity table is
   a 77× expansion. Either the canonical `person` table grows to hold every book
   author, or books stays a satellite whose people are referenced but not
   promoted into `person` until they matter (e.g. they stitch to another domain).
   Federating keeps the canonical table meaningful; absorbing makes one query
   answer everything. **Unresolved.**

2. **Identity resolution across domains is unsolved.** Matching
   `Nietzsche, Friedrich Wilhelm, 1844-1900` to a GitHub login is trivial
   (they will never collide). Matching a modern author to their Twitter handle
   is not. `external_ids` is the right mechanism; the *matcher* does not exist.
   Without it, cross-domain stitch stays at 3.

## Why this is the highest-leverage layer

Everything downstream composes on it:

- "Everything Socrates ever said" → person → works → passages
- "What does this founder actually believe" → one person, their repos, their
  talks, their threads, their book — reasoned together
- "Who else was working on this in the same decade" → life dates + subject edges
- Training-data curation by *person* rather than by document

The domains are supply. The people graph is the index that makes supply
addressable as *positions held by humans*, which is the unit reasoning actually
operates on.

## Immediate next actions (in dependency order)

1. Decide absorb-vs-federate for the books people. Everything else waits on it.
2. Write the books leg into `person_content` with `domain='book'`.
3. Build the identity matcher — the thing that turns 3 stitches into thousands.
4. Then Twitter/Reddit legs, which are pure `external_ids` + edges once the
   matcher exists.
