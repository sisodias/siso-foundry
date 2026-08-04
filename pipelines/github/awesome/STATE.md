# awesome harvest — resume note

Written 2026-08-03. Read this before touching the module again.

## Current state

**HARVEST COMPLETE 2026-08-04.** All 11,012 queued lists fetched
(10,797 succeeded, 200 404'd — 98.2%). `.cache/` holds 12,697 READMEs.

`catalog_full.sqlite`, two parallel populations:

| | GitHub side | Web side |
|---|---|---|
| lists | 4,026 | 2,030 |
| entries / links | 652,851 | 199,491 |
| unique targets | 307,180 repos | 68,335 domains |
| peer-validated | **89,857 repos** | 14,495 domains |

Export feeds in `export/` (verified 2026-08-04):
**181,929 candidates** (repos identity lacks) · **121,958 enrichment** rows
(existing identity repos gaining curated categories) · **2,249,906 substitute
edges**.

Seed-only crawl for comparison: 616 lists / 70,832 entries / 5,392
peer-validated. Widening discovery multiplied the peer-validated repo set —
the most valuable slice — by **16.7×**.

Web side (`weblist`/`weblink`) captures what a repo catalog structurally
cannot: hosted SaaS with no repo (Notion cited by 37 lists, VS Code 32,
Figma 30, Vercel 29, Grafana 25, Prometheus 24), papers (arxiv across 219
lists), and courses. Deliberately separate tables — `entry.target_repo` is the
join key into the identity corpus and must stay repo-only.

**The catalog is a projection of `.cache/`.** Fetchers were still running at
close. To pick up whatever landed since:

```bash
python3 ingest_cache.py --db catalog_full.sqlite --cache .cache
python3 load_enrichment.py --db catalog_full.sqlite --jsonl data/enriched_full.jsonl
```

Both are idempotent — re-run freely, they rebuild rollups from scratch.

## Discovery sources used (all feed the same cache)

| source | what it found |
|---|---|
| seed crawl from `sindresorhus/awesome` | 616 lists |
| depth-3 (lists cited *by* those lists) | 510 more READMEs |
| `topic:awesome` / `topic:awesome-list` search | ~9,978 repos enumerated to `data/topic_enumeration.jsonl`, top ~807 by stars fetched |

## The one thing not to repeat

The first build crawled only from the seed and I reported ecosystem-wide
conclusions from it — including "the corpus is stale on AI", which was false.
**73% of `topic:awesome` repos are unreachable from that seed.** The seed is
maintained but closed: its entries stay fresh (75% pushed <1y vs 60% for
seed-missed lists) while new categories are not admitted.

Retracted from that phase and NOT to be reused: the "6.5% created post-2023"
figure, and any claim about what the ecosystem covers or when it stopped.
Both described one neighbourhood.

## Disk

The substitutes export needs several GB of SQLite temp space. It died once with
`database or disk is full` (volume was at 98%, 8.8Gi free) and wrote a
zero-row `substitutes.jsonl` while still exiting 0 — check the row count, not
the exit code. The query is now bounded (multi-list repos only, sections
capped at 400 entries), which cut its temp footprint by roughly 75%.

Module footprint: `.cache/` 424M, `catalog_full.sqlite` 217M, `export/` 221M,
`_scratch/` 149M. Session test DBs are parked in
`/tmp/awesome_scratch_20260804/` (638M, disposable).

## The non-GitHub blind spot (measured 2026-08-04)

`LINK_RE` matches `github.com` URLs only, so a list curating **websites,
papers, videos, or hosted tools** parses as ~0 links and gets rejected as
"not a list". This is by construction — it is a *repo* catalog — but the size
is worth knowing:

    8,435 cached READMEs rejected by is_list_readme()
      2,535 (30%) have 20+ markdown bullet links to NON-github URLs
                  -> genuine curated lists this module structurally cannot see
      5,900 (70%) genuinely sparse

Confirmed by sampling: `awesome-amsterdam`, `awesome-brazilian-youtubers`,
`awesome-omnigraffle`, `awesome-agent-economy` are all real curated lists that
this pipeline drops. Fixing it means widening `LINK_RE` to all URLs and adding
a `target_url` column alongside `target_repo` — a schema change, not a tweak.

## Enrichment — DONE 2026-08-04

**75,673 repos enriched (84% of the peer-validated set)**, up from 975.
Done with `enrich_graphql.py`: GraphQL aliases 100 repos per request at cost 1
point, so 87,710 repos = **878 requests in 25.6 min**, versus 87,710 REST calls
over ~17h. Six concurrent workers; the limit is latency, not quota.

Three traps it handles, all of which look like success:
  * >100 aliases per query returns HTTP 200, `cost: 1`, and NO data
  * one deleted repo makes `gh` exit non-zero while 99 records sit in stdout
  * concurrent throttling returns empty `data`, not an error

Liveness across the peer-validated corpus: **50.6% active · 21.2% stale ·
28.1% DEAD (>3y)**, 4,854 archived. The earlier 5.8%-dead figure came from the
top-1,200 by citation and badly understated it.

## Known gaps, in priority order

1. **Free-text search is weak.** Blind A/B (EVALUATION.md): LIKE scores 31/75,
   FTS5 15/75. `bank_check.py --alts` and the liveness flags are the strong
   paths; keyword search needs eyeballing. Best fix is embeddings over the
   curated descriptions, not more bm25 tuning.
2. **Cross-language contamination** in the substitutes graph was largely fixed
   as a side effect of restricting the join to multi-list repos (`zod` no
   longer returns Go validators). Residual cases need (1) to filter by stack.
3. **Descriptions carry raw markdown/badges** (shields.io images inline).
   Cosmetic until something renders them.
4. **Web-side domains are coarse.** `youtube.com` as one "resource" is
   useless; the per-URL rollup is the useful grain and is already stored.
   Aggregate on `url`, not `domain`, for anything user-facing.

## Files

| file | role |
|---|---|
| `build_awesome_catalog.py` | seed crawl; read-based list classification (`is_list_readme`) |
| `ingest_cache.py` | **discovery-agnostic ingestion** — anything in `.cache/` becomes catalog input |
| `ingest_nongithub.py` | recovers lists curating websites/papers/SaaS -> `weblist`/`weblink` |
| `export_for_identity.py` | three JSONL feeds for the identity corpus |
| `FINDINGS-agent-tooling.md` | peer-validated agent/LLM tooling shortlists |
| `load_enrichment.py` | folds worker-fetched JSONL metadata into `repo` |
| `query_awesome.py` | `top`/`owners`/`sections`/`repo`/`stats`/`alternatives`/`stale` |
| `enrich_graphql.py` | bulk metadata, 100 repos/request (~100x fewer calls than REST) |
| `bank_check.py` | **the query entry point** — "what should I use for X" + liveness |
| `EVALUATION.md` | blind A/B vs model recall; what this does and does not beat |
| `README.md` | findings, with runnable SQL for each claim |

## Data (all durable, none in /tmp)

| path | what |
|---|---|
| `data/enriched_full.jsonl` | 82,951 GraphQL metadata records (31MB) |
| `data/topic_enumeration.jsonl` | 12,398 repos found via `topic:awesome` search |
| `data/fetch_queue.txt` | the 11,012-list queue that was worked through |
| `data/eval_*.txt` | frozen A/B baseline — do not regenerate, it is the control |
| `export/*.jsonl` | four feeds for the identity corpus |

`core/paths.py` exposes `github_awesome_db()` -> `catalog_full.sqlite`.
