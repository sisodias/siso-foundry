<p align="center">
  <img src="docs/assets/repository-header.png" width="100%" alt="Source fragments refined into reusable research knowledge">
</p>

# SISO Foundry

**Turn a named research or business need into a traceable, qualified source decision.**

Foundry discovers useful source material and software, establishes identity and
provenance, compares alternatives, and supplies evidence to the existing question
or product owner. Success is a better-supported decision with less repeated work,
not a larger pile of links or a higher repository-star count.

Foundry is an independent **Research Work**. Agents operate it; that does not make
it an agent runtime, a product control plane, or the owner of every system it feeds.
The [business-application mission](docs/AGENCY_OS_APPLICATION_MISSION.md) remains
the detailed demand, adoption-route and product-evaluation contract.

## Start here

| Need | Source |
|---|---|
| Understand the purpose, ownership and evidence flow | [Foundation and operating model](docs/FOUNDATION.md) |
| Inspect what the September source audit actually found | [Source audit and repair boundaries](docs/SOURCE-AUDIT-2026-09-07.md) |
| Plan a substantial, measurable research/reasoning run | [Research-run playbook](docs/RESEARCH-RUN.md) |
| Work on the repository | [Agent guide](AGENTS.md), [architecture](ARCHITECTURE.md), [provenance](PROVENANCE.md) |
| Understand the external data boundary | [Datasets](DATASETS.md), [dated manifest](datasets/manifest.json) |
| Use existing business research | [Research index](intelligence/agency/RESEARCH-INDEX.md), [Agency intelligence](intelligence/agency/README.md) |

## Keep the systems separate

| System | Responsibility | Boundary |
|---|---|---|
| **Foundry** | Discovery, source/repository intelligence, qualification and evidence-supply coordination | Not client operations, automatic code adoption or a runtime |
| **SISO Knowledge / Knowledge Graph** | Durable corpus, provenance, indexes, graphs and retrieval under their existing owners | Not absorbed or reorganised by Foundry |
| **People Graph** | Its own identity/relationship system and ownership | People-related adapters in this checkout do not confer canonical Graph ownership |
| **Evidence Engines** | Explicit source-grounded transformations, claims and evaluation inputs | Not source discovery or product execution |
| **Question and product owners** | Reasoning, accepted decisions, implementation and authorised operational proof | A Foundry recommendation does not transfer their authority |
| **Great Library** | Public identity, lineage, selection, accepted research and release history | Not raw private evidence, a deployment engine or proof of installability |

These boundaries follow the [application mission](docs/AGENCY_OS_APPLICATION_MISSION.md)
and the public source references in the [audit](docs/SOURCE-AUDIT-2026-09-07.md).

## Repository versus data

```text
Foundry source (this Git repository)
  core/                  path, identity, ranking and DB helpers
  pipelines/             acquisition/enrichment software and contracts
  packages/              bank query, topic and business-application modules
  intelligence/agency/   reviewed public research metadata and source links
  datasets/              manifests, not the external warehouse
  scripts/ + tests/      source checks and synthetic regression tests

External data plane (not supplied by cloning this repository)
  incoming -> raw observations -> identity -> staging -> curated
                                      \-> generated artifacts
```

The public source still contains historical people-ingestion and graph-related
code. It is preserved, not reclassified as ownership of the canonical Knowledge
Graph or People Graph. Legacy infrastructure documents and machine-specific
comments are historical design evidence, not live-host receipts.

Code, contracts, small fixtures and reviewed provenance belong in Git. Raw
observations, large databases, transcripts, private handoffs, credentials, caches
and generated run artifacts do not. Upstream source ownership and licenses remain
asset-specific; Foundry's MIT code license does not relicense a dataset.

### Existing source capabilities, not runtime promises

| Surface | What the public source supplies | Remaining distinction |
|---|---|---|
| `core` | Path and SQLite helpers | Does not elect a writer or verify a machine |
| `pipelines/github` | Discovery campaigns, identity/enrichment and ranking code | Real runs need data, access and a bounded acquisition decision |
| `pipelines/youtube`, `pipelines/podcasts` | Acquisition software or routing contracts | Source presence is not a complete, available corpus |
| `packages/bank-api` | Experimental reuse-query and verification surface | Query access and behavioral proof remain separate |
| `packages/research-topics` | Experimental topic registry with provenance | Not a replacement for a question owner's records |
| `intelligence/agency` | Industry hypotheses, capability/coverage records and value models | Research-only claims are not measured client outcomes |

The dataset manifest is dated **2026-07-30**. Its recorded counts are a checkpoint,
not a count obtained by opening the live database today. Read [DATASETS.md](DATASETS.md)
before describing anything as downloadable, replicated, released or operational.

## Verify without pretending the data is present

Use a Git checkout, Python 3.10 or newer, Node.js, npm and Bash. The source checks
use the standard library and existing code; no package installation is required
for these commands. Git identifies tracked and nonignored publication candidates
so the source scanner does not recursively crawl ignored datasets.

```sh
# Public code, manifests, existing source invariants and synthetic fixtures.
npm run test:source

# Focused new regression tests, with disposable synthetic databases only.
npm run test:foundation

# Heuristic publication scan; prints rule IDs, never matched secret values.
npm run check:publication
```

`test:source` prints `external_data=NOT_CHECKED` and
`execution=NOT_ESTABLISHED`. The public CI runs this source-only gate with
read-only GitHub permissions; it does not claim a deployment or dataset test.

The original full entry point remains strict:

```sh
# Set this deliberately to an existing, authorised local atlas file.
export FOUNDRY_CAPABILITY_ATLAS="/approved/local/atlas.jsonl"
npm test

# Or run only its explicit external-atlas consistency component.
npm run test:external
```

Without that explicit file, the external gate reports **blocked** and exits 2.
Malformed, duplicate or mismatched capability records fail with exit 1. A match
returns 0 and a content hash, but still does not prove broader corpus completeness,
rights, backups, product fit or runtime readiness. External receipts are private
operational metadata; do not upload them automatically.

The old ancestor-directory atlas lookup has been removed. Missing external data
is not silently replaced by a fixture and is not counted as a passing full test.

## Existing discovery and business research

[Agent-systems campaign](pipelines/github/campaigns/agent-systems-v1.json) and
[business-software campaign](pipelines/github/campaigns/agency-business-software-v1.json)
are reproducible query definitions, not complete or rights-cleared universes.
Inspect a campaign without collection:

```sh
python3 pipelines/github/run_campaign.py --dry-run
```

Real acquisition uses the operator's existing GitHub access, an explicit scope
and the external data plane. Query existing supply before collecting again.
The public [Repo Bank](https://github.com/sisodias/siso-repo-bank) is a separately
maintained derived index, not proof that its parent database is accessible.

Existing Agency research includes the [value matrix](intelligence/agency/VALUE-MATRIX.md),
[coverage inventory](intelligence/agency/COVERAGE.md),
[economic valuation specification](intelligence/agency/ECONOMIC-VALUATION.md),
[industry dossiers](intelligence/agency/industries/) and
[value examples](intelligence/agency/economics/).

**Unresolved evidence debt remains:** the baseline README documented four
value-matrix projects missing from coverage and sixteen stronger records reduced
to `inferred`. This foundation repair does not reconcile those records or turn
provisional valuations into measured savings. The exact baseline and remaining
work are in the [audit](docs/SOURCE-AUDIT-2026-09-07.md).

## Data configuration

`FOUNDRY_DATA` selects the external data root; its portable default is
`~/.local/share/siso-foundry`. The usual identity location is
`domains/github/identity/identity.sqlite` beneath that root.

**Known divergence:** `pipelines/github/config.py` supports
`FOUNDRY_GITHUB_DB`, while `core/paths.py` and some bank callers resolve defaults
differently. This repair does not silently migrate every caller. Check the actual
consumer before assuming that an environment setting selects the same database
throughout the repository. No machine placement is inferred from a path.

## Great Library identity

- Work: `gls:work:ec664d93-df93-48c5-be40-5d0165886c01`
- Section: Research
- [Public Foundry reading surface](https://great-library-of-siso.pages.dev/works/siso-foundry/)

Registered, selected, pinned, published and deployed are different observations.
A source branch or pull request does not update a Library Release or Snapshot.
Keep those decisions with the existing Library owner.
