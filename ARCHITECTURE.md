# Architecture

Foundry follows four first-principles rules.

## 1. Identity is not location

A source, person, topic, observation, or derived asset keeps a stable identity even when its storage device, repository, URL, or category changes. Locations are mutable provenance records; they are never the identity key.

## 2. Observations are append-only

Raw sightings are evidence. Deduplication links observations to a canonical identity rather than overwriting history. Derived views may be rebuilt; provenance is retained.

## 3. Software and data have different lifecycles

Git holds reviewable software, schemas, contracts, small fixtures, and manifests. The data plane holds large or fast-changing payloads. A dataset can move from laptop to object storage to a distributed archive while the repository and Great Library Work identity remain stable.

## 4. One writer, many readers

Each SQLite database has one local writer. Readers use read-only connections. Network filesystems must not become concurrent SQLite writers; publish snapshots or query services instead.

## Data states

```text
incoming → raw observations → canonical identity → staging → curated assets
                              │                         │
                              └──── evidence links ─────┘
```

- `incoming`: resumable transport shards; safe to replay.
- `raw`: immutable observations from named sources.
- `identity`: canonical units plus links to every observation.
- `staging`: reproducible classifications, extracts, and candidate promotions.
- `curated`: evidence-gated assets intended for reuse.
- `artifacts`: generated human views; never a source of truth.

## Repository promotion rule

A directory does not become a repository merely because it has a name. Promote a module only when people need to adopt, fork, version, release, or govern it independently. Until then, packages remain visible modules inside this coherent Foundry release boundary.

The current package boundaries are deliberately revisable. Great Library snapshots record how they were projected at a point in time without baking today’s taxonomy into stable Work identity.
