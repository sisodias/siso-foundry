# Dataset boundary

Foundry's large assets are not missing from this repository; they are intentionally represented by manifests rather than committed as Git blobs.

At extraction time, the source warehouse held a 1.88 GB SQLite identity database, 681 MB of append-only raw observations, and 253 MB of staging artifacts. The database contained 1,358,200 repository cards, 226,968 category placements, 264 categories, 23,778 bank candidates, and 70 deep ContractCards. These figures are an observed checkpoint, not a promise that a live data plane will remain frozen.

The machine-readable record is [`datasets/manifest.json`](datasets/manifest.json).

## Storage policy

| Asset class | GitHub | Durable storage | Public distribution |
|---|---|---|---|
| Source code, schemas, contracts | Yes | Git + mirrors | Release archives |
| Small synthetic fixtures | Yes | Git + mirrors | Release archives |
| Raw observations and corpora | No | Object/data storage with content manifests | Per-source rights and privacy gate |
| SQLite snapshots | No | Versioned snapshot storage | Explicit snapshot release and checksum |
| Generated HTML, logs, caches | No | Regenerable artifact storage | Optional build artifact |
| Third-party repositories | Never flattened | URL + commit + license + evidence receipt | Original source or permitted mirror |

The next data-plane milestone is a versioned snapshot receipt with a content hash, schema version, public/private classification, and at least two independent durable copies. Until that receipt exists, the Library truthfully reports the corpus as locally preserved but not publicly downloadable.
