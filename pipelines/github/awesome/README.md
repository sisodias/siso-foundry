# awesome — the curated-list catalog

Harvests the awesome-list ecosystem into a queryable SQLite catalog for the
Foundry GitHub domain.

## Why this exists

GitHub already knows every repo, its stars, and its topics. What GitHub does
**not** carry is that a human maintainer decided repo X belongs under the
heading *"Web Crawling"* in a list about Python, wrote a one-line description
of it in their own words, and kept it there through review.

That is an editorial signal, and it is the entire point of this module:

- **Inclusion** is a quality judgement a person made and defends via PRs.
- **The section heading** is an inherited taxonomy — a folksonomy built by
  domain experts, free, already agreed on. We inherit it rather than inventing
  one or asking an LLM to guess.
- **Multi-list membership** is the strongest signal in the dataset. A repo that
  nine independent maintainers each chose to include is doing something one
  with a single citation is not.

This mirrors the reasoning in `pipelines/books/build_books_module.py`, which
inherits the Library of Congress classification instead of inventing shelves.

## What it builds

`awesome_catalog.sqlite`, five tables:

| table | grain | what it carries |
|---|---|---|
| `list` | one curated list repo | title, topic slug, depth, README path that resolved, entry count, fetch status |
| `entry` | one (list → target) citation | **`section`**, `section_path` breadcrumb, editor's `description`, position |
| `repo` | one deduped target repo | owner, name, `list_count`, optional stars/language/topics |
| `owner_signal` | one owner | repos cited, lists citing them, total citations, best repo's list count |

`entry.section` is the load-bearing field. Everything else is context for it.

### Design decisions

- **Nothing stores a verdict.** No score, no tier, no "quality" column.
  `list_count` is a count of observed edges; any ranking is a projection
  computed at read time. This is the same rule the books module follows.
- **Membership is a relation.** A repo appears in every list that cites it;
  adding one is an `INSERT`, never a move.
- **Section path, not just section.** Heading depth is inconsistent across
  lists — `sindresorhus/awesome` uses only `##` while `vinta/awesome-python`
  is mostly `###` — so both the nearest heading and the full `Parent > Child`
  breadcrumb are stored.
- **Zero API cost for the harvest.** READMEs come from
  `raw.githubusercontent.com`, which does not touch the 5,000/hr API quota.
  The GitHub API is used only by the optional `--enrich` pass.
- **Resumable.** Every README is cached to disk and every list carries a fetch
  status, so a re-run skips completed work. Interrupting the script never
  costs you fetches already paid for.

## Usage

```bash
# full harvest (seed -> all discovered lists)
python3 build_awesome_catalog.py --db awesome_catalog.sqlite --cache .cache

# quick slice
python3 build_awesome_catalog.py --limit 10

# optional metadata pass for the top N most-cited repos (uses API quota)
python3 build_awesome_catalog.py --enrich 500
```

Emits a JSON summary to stdout; progress to stderr.

## bank_check.py — the Bank check, with liveness

`foundry repos "<query>"` ranks by STARS. Stars never decay, so it recommends
abandoned projects with full confidence. This adds what stars cannot express:

```
$ bank_check.py --alts ariya/phantomjs
# alternatives to ariya/phantomjs (by independent lists agreeing)
  casperjs/casperjs        7 lists    7,161★  JavaScript   ARCHIVED  ⚠
  microsoft/playwright     6 lists   93,917★  TypeScript   active
  GoogleChrome/puppeteer   6 lists         —  —            unknown
  laurentj/slimerjs        5 lists    2,997★  JavaScript   DEAD 3y   ⚠
```

Query a dead tool, get the live migration target — with the other dead ones
flagged rather than silently recommended.

```bash
bank_check.py "task queue"            # what should I use for X
bank_check.py --alts junegunn/fzf     # what competes with X
bank_check.py "vector database" --json
```

Ranking is by **independent curated lists agreeing**, not stars — so `huey`
[14 lists] outranks `celery` [11] despite 5× fewer stars. That is a different
question than popularity, and deliberately so.

## The substitutes graph (the reason to build this)

When a maintainer files several repos under one heading, they have asserted
those tools are *alternatives to each other*. GitHub has no field for this.
This catalog has ~142k such placements, and co-occurrence weighted by
**distinct lists** recovers a substitutes graph:

```sql
SELECT b.target_repo, COUNT(DISTINCT a.list_repo) AS lists_agreeing
FROM entry a
JOIN entry b ON a.list_repo = b.list_repo
            AND a.section   = b.section
            AND b.target_repo <> a.target_repo
WHERE a.target_repo = :repo
  AND a.section IS NOT NULL
  AND b.target_repo NOT IN (SELECT list_repo FROM list)
GROUP BY b.target_repo
HAVING COUNT(DISTINCT a.list_repo) > 1
ORDER BY lists_agreeing DESC;
```

Measured output:

    langchain-ai/langchain -> llama_index [6], dspy [4], ollama [4],
                              pydantic-ai [3], semantic-kernel [3], langgraph [3]
    BurntSushi/ripgrep     -> fzf [7], fd [5], the_silver_searcher [4], peco [3]
    colinhacks/zod         -> yup [3], govalid [2], go-validator [2]

**Weight by distinct lists, never by raw pair count.** One list
(`unixorn/awesome-zsh-plugins`, 3,242 entries) puts hundreds of repos under a
single heading; unweighted, it swamps everything and returns nonsense
(`fzf`'s top "alternative" came back as `ohmyzsh` with 902 co-occurrences).

**Known weakness — cross-language contamination.** Generic section names
recur across ecosystems, so a heading like "Validation" appears in both a
TypeScript list and a Go list. Measured: `colinhacks/zod`'s neighbours include
`twharmon/govalid`, `tiendc/go-validator` and `lyonnee/hvalid` — correct
*concept*, wrong *language*. Join to `repo.language` and filter when the
caller cares about a specific stack; the raw graph is concept-level, not
stack-level.

## Coverage: what is enriched vs what is only cited

Two different populations, and conflating them will mislead you:

| | count | source |
|---|---|---|
| repos with a curated citation | 123,994 | README parsing, free |
| repos with stars / language | 912 | GitHub API, 1 call each |
| repos with liveness (`pushed_at`) | 955 | GitHub API, 1 call each |

**Enrichment covers 0.77% of the catalog**, chosen by list-count — the densest
signal, but a slice. The substitutes graph and all citation counts work on the
full 123,994. Anything touching `stars`, `language`, or `pushed_at` — the
`stale` command, the `--language` filter on `alternatives` — silently sees
only the enriched sliver. Widen it by running `load_enrichment.py` over a
larger fetch before trusting those for coverage-sensitive questions.

## Liveness: why stars cannot answer this

Stars are a permanent record of past popularity and never decay, so a
star-sorted search recommends abandoned projects with confidence. Cross-
referencing curation against `pushed_at` catches them:

    4 lists  5.9y stale  7,990★  harthur/brain
    3 lists  6.2y stale  5,912★  clvv/fasd
    3 lists  6.0y stale  5,968★  dtao/lazy.js
    3 lists  5.6y stale  3,863★  NervanaSystems/neon

## How it plugs into the GitHub domain

Registered in `core/paths.py` as `github_awesome_db()`, resolving to
`$FOUNDRY_DATA/domains/github/awesome/awesome_catalog.sqlite` — a sibling of
the existing `identity/identity.sqlite` spine.

Two consumers:

1. **Repo intelligence.** `repo.full_name` joins to the GitHub domain's repo
   tables. A repo carrying curated-list membership gains an inherited category
   (`entry.section`) and a human-written description that no metadata scrape
   provides.
2. **The people graph.** `owner_signal` is a *feed table*, deliberately not
   written into the people graph by this module. It answers "how much curated
   attention does this person's work attract" — distinct from follower count,
   because it measures peer editorial judgement rather than popularity.

Both joins are by string key; this module writes nothing outside its own DB.

## The sampling lesson (read this first)

The first version of this module crawled outward from `sindresorhus/awesome`
and reported confident conclusions about "the awesome ecosystem" — including
that it was stale on AI. **That was wrong, and the way it was wrong is the
most useful thing this module learned.**

A seed crawl is a spanning tree rooted at one repo. Measured 2026-08-03,
**73% of repos carrying `topic:awesome` are unreachable from that seed**
(492 of 672 topic-search results absent from the seed crawl). The seed is not
unmaintained — seed-reachable lists are *fresher* than seed-missed ones
(75% vs 60% pushed within a year). It is maintained but **closed**: entries
stay current while new categories are not admitted. The editorial gate that
makes curation valuable is the same gate that makes it lag.

Concretely, counting distinct lists citing each repo:

| repo | seed-only | full catalog |
|---|---|---|
| `langchain-ai/langchain` | 1 | 4 |
| `vllm-project/vllm` | 1 | 5 |
| `ollama/ollama` | 4 | 7 |
| `ggerganov/llama.cpp` | 0 | 1 |

So discovery and ingestion are now **separate**: `build_awesome_catalog.py`
does seed crawling, other tools (topic search, depth-3 expansion) drop READMEs
into the same cache, and `ingest_cache.py` ingests everything found by any
means. Discovery strategy is pluggable; ingestion is one code path.

## Measured results

### Full catalog (all discovery methods), 2026-08-03

| metric | value |
|---|---|
| lists ingested | 945 |
| entries | 183,032 |
| unique repos | 123,994 |
| **repos in >1 list** | **25,344** |
| distinct sections | 12,215 |
| owners | 79,520 |

For scale: the seed-only crawl produced 616 lists / 70,832 entries / 5,392
multi-list repos. Widening discovery multiplied the peer-validated set — the
most valuable slice — by **4.7×**.

Liveness of the enriched top tier (949 repos, reproducible from the DB):
**788 active (<1y) · 107 stale (1-3y) · 54 dead (>3y) · 34 archived.**

### Seed-only harvest (superseded, kept for the comparison above)

| metric | value |
|---|---|
| lists harvested ok | 616 (1 notfound) |
| entries (list → repo citations) | 70,832 |
| unique target repos | 59,392 |
| repos in >1 list | 5,392 (9.08%) |
| distinct section headings | 5,252 |
| entries carrying a section | 96.0% |
| entries carrying a description | 81.5% |
| distinct owners | 39,404 |
| owners cited by >1 list | 6,413 |

Rebuild from the on-disk README cache takes **68.5s**.

### Top curated repos, list-to-list references excluded

`sindresorhus/awesome` itself scores 173 — but 163 of those are the
awesome-list *badge* every list carries in its header, not curation. Excluding
targets that are themselves harvested lists gives the signal worth using:

    11  BayesWitnesses/m2cgen        11  tensorflow/tensorflow
    11  cossacklabs/themis           10  facebook/react-native
    11  ocornut/imgui                 9  facebook/react
     8  Microsoft/vscode              8  hasura/graphql-engine
     7  apache/spark                  7  pytorch/pytorch
     7  babel/babel                   7  mrdoob/three.js
     7  vitejs/vite                   6  BurntSushi/ripgrep

Query it with `query_awesome.py top`, or filter directly:

```sql
SELECT full_name, list_count FROM repo
WHERE list_count > 1 AND full_name NOT IN (SELECT list_repo FROM list)
ORDER BY list_count DESC;
```

## Known limits

- The seed's depth-1 expansion uses a name heuristic (`looks_like_list`) to
  decide which links are themselves lists. Lists not named `awesome-*` are
  missed; genuine repos named `awesome-*` are harvested as lists and simply
  yield few entries.
- Harvest depth is 2 (seed → lists → targets). Lists cited only by other
  leaf lists are not reached.
- `description` is the first non-null seen across citations of a repo, not a
  merge of all of them; the per-citation descriptions remain in `entry`.
  Measured: 8.08% of repos have citations that disagree on the description, so
  `repo.description` can be misleading (e.g. `ocornut/imgui` picks up a Go
  wrapper's blurb). For anything user-facing, read `entry.description`.
- **List-to-list references are not curation.** 1,719 of 70,832 entries point
  at repos that are themselves lists, mostly the awesome badge in each list's
  header. They are retained (removing rows is also information loss) but should
  be filtered out of any ranking — see the SQL above.
- **Owner logins are not case-folded.** `microsoft` and `Microsoft` are
  separate `owner_signal` rows though GitHub treats them as one account. Fold
  on `lower(owner)` when joining to the people graph.
- Section labels are raw heading text and can contain inline HTML (observed:
  `Text-Based User Interfaces <kbd>4 projects</kbd>`). Strip tags before
  displaying.
- The `looks_like_list` name heuristic classifies 617 of the seed's 681 links
  as lists and excludes 64. Reading those 64, most are genuine curated lists
  that simply lack "awesome" in the name (`js-must-watch`,
  `30-seconds-of-code`, `frontend-dev-bookmarks`) — a real ~9% coverage loss
  and the highest-value next improvement.
