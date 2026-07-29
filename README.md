# SISO Foundry

Foundry turns large source corpora into traceable, ranked, reusable research knowledge.

It lives under the **Research** section of the Great Library of SISO. Agents can operate it and consume its results, but that does not make it agent infrastructure: its durable outcome is a research asset—the identity graph, observations, evidence, rankings, and verified reuse knowledge.

## The boundary

```text
Research
└── Foundry
    ├── core/                  shared identity, ranking, storage, and DB contracts
    ├── pipelines/             domain ingestion and enrichment software
    │   ├── github/            repository catalog and value-mining pipeline
    │   ├── people/            cross-domain people graph
    │   ├── youtube/           channel and transcript acquisition
    │   └── podcasts/          podcast acquisition contract
    ├── packages/
    │   ├── bank-api/          query and verification surface for reuse knowledge
    │   └── research-topics/   append-only topic registry and artifact links
    └── data plane             external, append-only, and deliberately not stored in Git
```

Code, contracts, schemas, small fixtures, and provenance belong in this repository. Multi-gigabyte databases, raw observations, transcripts, generated browsers, caches, and run artifacts live in the external data plane described by [`DATASETS.md`](DATASETS.md).

That boundary is what lets Foundry scale from gigabytes to petabytes without turning GitHub into a database or making the source impossible to fork.

## Current modules

| Module | Outcome | State |
|---|---|---|
| `core` | One data-root indirection, read-only/default SQLite access, shared identity and ranking contracts | Extracted |
| `pipelines/github` | Append-only repository observations → canonical identity → enrichment → value ranking | Extracted, requires an external database |
| `pipelines/people` | Cross-domain creator and maintainer identity graph | Extracted |
| `pipelines/youtube` | Resumable channel acquisition and transcription | Extracted |
| `pipelines/podcasts` | Podcast corpus routing contract | Early |
| `packages/bank-api` | Capability query surface and behavioral verification harness | Experimental |
| `packages/research-topics` | Fuzzy add-or-match topic registry with provenance-preserving merges | Experimental |

## Data layout

Foundry resolves data through `FOUNDRY_DATA`. When it is unset, the portable default is:

```text
~/.local/share/siso-foundry/
├── domains/
│   ├── github/
│   │   ├── raw/               append-only observations
│   │   ├── identity/          canonical identity database
│   │   ├── staging/           reproducible intermediate products
│   │   └── curated/           promotion-gated research assets
│   └── <future-domain>/
├── incoming/                  resumable harvest shards
└── artifacts/                 generated reports and offline browsers
```

Override the GitHub database alone with `FOUNDRY_GITHUB_DB`. Other explicit paths are documented in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Verify

```bash
npm test
```

The check compiles every Python source file, syntax-checks JavaScript and shell entrypoints, exercises the research-topic registry against a disposable SQLite database, validates the dataset manifest, and scans the public surface for personal absolute paths and common credential forms.

## Great Library identity

- Work: `gls:work:ec664d93-df93-48c5-be40-5d0165886c01`
- Section: Research
- Catalog: <https://great-library-of-siso.vercel.app/works/siso-foundry/>

The software is MIT licensed. Dataset and upstream-source rights remain asset-specific; inclusion in a Foundry catalog never changes the original source's ownership or license.
