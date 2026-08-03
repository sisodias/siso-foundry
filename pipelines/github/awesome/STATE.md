# awesome harvest — resume note

Written 2026-08-03. Read this before touching the module again.

## Current state

`catalog_full.sqlite` — **204,186 entries · 135,784 repos · 28,745
peer-validated** (cited by >1 list). Built by `ingest_cache.py` from `.cache/`,
which held ~1,900 READMEs at close.

For scale: the original seed-only crawl produced 70,832 entries / 59,392 repos
/ 5,392 peer-validated. Widening discovery multiplied the peer-validated set —
the most valuable slice — by **5.3×**.

**The catalog is a projection of `.cache/`.** Fetchers were still running at
close. To pick up whatever landed since:

```bash
python3 ingest_cache.py --db catalog_full.sqlite --cache .cache
python3 load_enrichment.py --db catalog_full.sqlite --jsonl /tmp/enriched.jsonl
```

Both are idempotent — re-run freely, they rebuild rollups from scratch.

## Discovery sources used (all feed the same cache)

| source | what it found |
|---|---|
| seed crawl from `sindresorhus/awesome` | 616 lists |
| depth-3 (lists cited *by* those lists) | 510 more READMEs |
| `topic:awesome` / `topic:awesome-list` search | ~9,978 repos enumerated to `/tmp/awesome_topics.jsonl`, top ~807 by stars fetched |

## The one thing not to repeat

The first build crawled only from the seed and I reported ecosystem-wide
conclusions from it — including "the corpus is stale on AI", which was false.
**73% of `topic:awesome` repos are unreachable from that seed.** The seed is
maintained but closed: its entries stay fresh (75% pushed <1y vs 60% for
seed-missed lists) while new categories are not admitted.

Retracted from that phase and NOT to be reused: the "6.5% created post-2023"
figure, and any claim about what the ecosystem covers or when it stopped.
Both described one neighbourhood.

## Known gaps, in priority order

1. **Enrichment covers 0.77%** (956 of 130,830 repos have `pushed_at`).
   `stale` and `alternatives --language` silently see only that sliver.
   Fix: fetch metadata for the ~27k multi-list repos, load with
   `load_enrichment.py`.
2. **Topic enumeration incomplete** — ~9,978 of ~10,600 enumerated, and only
   lists with >=300 stars were fetched. `/tmp/awesome_topics.jsonl` has the
   full enumeration; queue more from it.
3. **Cross-language contamination** in the substitutes graph — "Validation"
   appears in both TS and Go lists, so `zod` neighbours include Go validators.
   Mitigated by `--language`, which needs (1).
4. **Descriptions carry raw markdown/badges** (e.g. shields.io images inline).
   Cosmetic until something renders them.

## Files

| file | role |
|---|---|
| `build_awesome_catalog.py` | seed crawl; read-based list classification (`is_list_readme`) |
| `ingest_cache.py` | **discovery-agnostic ingestion** — anything in `.cache/` becomes catalog input |
| `load_enrichment.py` | folds worker-fetched JSONL metadata into `repo` |
| `query_awesome.py` | `top`/`owners`/`sections`/`repo`/`stats`/`alternatives`/`stale` |
| `README.md` | findings, with runnable SQL for each claim |

`core/paths.py` exposes `github_awesome_db()` -> `catalog_full.sqlite`.
