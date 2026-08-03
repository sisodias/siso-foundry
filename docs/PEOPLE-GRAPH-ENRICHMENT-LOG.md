# People Graph — Enrichment Log

Running log of every idea for making the people graph richer from data we
**already have**, implemented or not, with measured numbers and receipts.

Working copy: `/tmp/people_v2_gh.sqlite` on the mini (584 MB).
Canonical DB `~/foundry-data/domains/people/people.sqlite` is never written
(single-writer law). Backup before first change:
`/tmp/people_v2_gh.PRE-ENRICH-20260803-174831.sqlite`.

---

## Round 1 — 2026-08-03

### Baseline (measured, not assumed)

```
$ sqlite3 /tmp/people_v2_gh.sqlite 'select "person",count(*) from person
    union all select "person_content",count(*) from person_content
    union all select "external_ids",count(*) from external_ids
    union all select "person_topic",count(*) from person_topic
    union all select "identity_claim",count(*) from identity_claim;'
person|280708
person_content|564486
external_ids|245628
person_topic|1661361
identity_claim|0
```

Edges by domain/role/source:

```
github|owner|github_identity|462930|245167
book|author|gutenberg|72137|26084
book|illustrator|gutenberg|9692|3130
book|translator|gutenberg|7179|3292
book|editor|gutenberg|7005|2728
... (24 more book roles)
github|author|v1_migration|300|300
youtube_video|author|v1_migration|97|24
youtube_channel|author|v1_migration|35|35
```

Cross-domain reach — **the core problem**:

```
$ sqlite3 /tmp/people_v2_gh.sqlite 'select domain_count, count(*) from v_person_layers group by 1 order by 1;'
0|113
1|280592
2|3
```

Three people out of 280,708 span more than one domain: Andrej Karpathy,
Jensen Huang, Simon Willison. Everything else is single-layer.

### Premise corrections (verified against the machine, contradicting the brief)

**F5 is wrong — there is no YouTube domain DB to mine.** The brief said "there
is a whole youtube domain DB barely represented". There is not.

```
$ ls ~/foundry-data/domains/
github
people
```

No `youtube/`, no `podcasts/`. A bounded search of the vault
(`find /Volumes/SISO-STORAGE-VAULT -maxdepth 4 -name '*.sqlite' -o -name '*.db'`)
returned 24 databases, none of them YouTube or podcast corpora — they are
bifrost log archives, brain backups, house-search, and `library/gutenberg/locator.sqlite`.

The entire YouTube corpus on this machine is:

```
$ sqlite3 ~/foundry-data/domains/people/_inputs/people_video_queue.sqlite \
    'select count(*) from people_video_queue;'
97
```

97 rows — and the graph already has 97 `youtube_video` edges. **YouTube is not
under-loaded; it is fully loaded.** The weakness is real but the cause is
absence of data, not a missing loader. Chasing a YouTube loader would have been
wasted work.

**A4 is partly wrong.** `bank_adoption` exists (714 rows) but the richer table
is `bank_adoption_v2` (1,026 rows, with `downloads`, `dependent_repos`,
`real_value`, `verdict`, `fame_gap`). Use v2.

### The seam that actually matters

`score` on all 463,230 github edges is **stars**:

```
$ sqlite3 /tmp/people_v2_gh.sqlite "select count(*), sum(score is not null) from person_content where domain='github';"
463230|463230
```

Stars measure fame. Meanwhile the identity DB holds a *rated* judgement of
303,116 repos that has never reached the graph:

```
$ sqlite3 identity.sqlite 'select count(*) total, sum(overall_value is not null) has_overall,
    sum(reuse_value is not null) has_reuse, sum(info_value is not null) has_info,
    sum(saucy=1) saucy, sum(liftability is not null) has_lift from repo_category;'
385964|385959|385959|385959|44967|16082

$ sqlite3 identity.sqlite 'select count(distinct full_name) from repo_category where overall_value is not null;'
303116

$ sqlite3 identity.sqlite "select count(distinct substr(full_name,1,instr(full_name,'/')-1))
    from repo_category where overall_value is not null and instr(full_name,'/')>0;"
170237
```

**170,237 distinct owners have rated work.** Those owners join to the graph's
245,174 github logins on exactly the key the graph already indexes.

---

## The ten ideas

Ranked by (edges unlocked) × (questions made answerable). Estimates marked
UNVERIFIED until the loader measures them.

| # | Source | Target | Est. rows | Question it unlocks |
|---|---|---|---|---|
| 1 | `repo_category.overall_value/reuse_value/info_value/saucy` (385,959 rated rows, 303,116 repos, 170,237 owners) | `person_content.meta_json` + new `quality_score` | ~300k edges enriched | "Who does the most *valuable* work?" — today only "who has the most stars" is answerable. Separates 100-star gems from 100k-star toys. |
| 2 | `category` + `repo_category` (264 categories, 385,964 assignments) | `person_topic` scheme=`gh_category` | ~380k | "Who works on databases?" — curated taxonomy, unlike raw github_topic noise. Also the join key for idea #5. |
| 3 | `owner_signal` (86,475 owners, editorially cited) + `repo.list_count` | `person_topic` scheme=`curated` + person.rank_score | ~86k | "Who does the community actually cite?" Peer-validated inclusion is an editorial quality signal independent of stars. |
| 4 | LCSH ↔ github topic/category crosswalk | `person_topic` scheme=`bridge` | ~50–150k UNVERIFIED | "Who works on X?" reaching BOTH the 35k book population and the 245k github population from one query. Currently a topic query hits one population only. |
| 5 | Shared-category co-membership | new `person_person` table | UNVERIFIED, large | "Who else works on what this person works on?" The graph has **no person↔person representation at all** today. |
| 6 | `bank_adoption_v2` (1,026 rows: downloads, dependent_repos, real_value, verdict, fame_gap) | `person_content.meta_json` | ~1k edges, high value | "Whose code is genuinely *depended on*?" 467 `confirm` / 152 `promote` / 95 `demote` verdicts. Small but the strongest possible quality signal. |
| 7 | `enrich_owners.py` at scale (149/245,166 done; 5,000 req/hr budget) | `person.kind`, `external_ids` real_name/x_handle/website | ~245k over ~50 hrs | Resolves `kind='unknown'` for 239,497 people AND produces the real names that idea #8 needs. |
| 8 | Resolved real_name ↔ book author name matching | `identity_claim` | UNVERIFIED, likely 100s–1000s | **The cross-domain stitch.** This is the actual fix for "stitch is 3". Blocked on #7 — needs real names, which 245k logins do not have. |
| 9 | `repo_card.created_at/pushed_at/archived` (1.36M rows, 106,994 archived) | `person_content.observed_at` + meta | ~1.36M | "Who is *currently* active?" Today the graph cannot distinguish a 2011 abandoned repo from last week's work. |
| 10 | `work_top10k/50k/100k` rank + `bank_liftable_ranked` (32,137 with liftability) | `person_content.meta_json` | ~32k–100k | "Whose work can I actually lift into my own system?" — the Foundry's core question. |

Ideas 1, 2, 3 are implemented this round. Idea 8 turned out to be **structurally
impossible via github↔book** — see the negative result below, which is the most
important finding of this round.

---

## Implemented — round 1

### #1 + #2 — rated value and curated categories (`pipelines/github/load_repo_value.py`)

One pass over `repo_category`, writing value into `person_content.meta_json`
(NOT over `score` — overwriting would destroy the star signal, and fame-vs-value
is the comparison that makes this interesting) and categories into `person_topic`
under a new `gh_category` scheme.

```
$ python3 load_repo_value.py --identity identity.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "repos_rated": 303116,
  "edges_matched": 303114,
  "owner_not_in_graph": 2,
  "distinct_owners_enriched": 170236,
  "before": {"github_edges_with_value": 0, "person_topic_total": 1661361, "gh_category_topics": 0},
  "after":  {"github_edges_with_value": 303403, "person_topic_total": 1971077, "gh_category_topics": 309716},
  "elapsed_s": 12.68
}
```

99.9993% of rated repos matched an owner already in the graph (303,114 / 303,116).

Independent re-derivation (not the loader's own count):

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from person_content where domain='github'
    and json_extract(meta_json,'$.value') is not null;"
303403
$ sqlite3 people_v2_gh.sqlite "select count(*), count(distinct person_id), count(distinct topic)
    from person_topic where scheme='gh_category';"
309716|170236|264
```

All 264 categories are represented.

**Question now answerable that was not before** — rank people by rated quality
rather than by fame:

```
$ sqlite3 people_v2_gh.sqlite "select p.name, count(*) n_rated,
    round(avg(json_extract(c.meta_json,'$.value')),1) avg_val, sum(c.score) stars
    from person_content c join person p using(person_id)
    where c.domain='github' and json_extract(c.meta_json,'$.value')>=90
    group by 1 having n_rated>=3 order by n_rated desc limit 12;"
microsoft|33|91.7|1227062.0
apache|31|91.7|374329.0
rust-lang|21|92.7|325853.0
google|21|91.4|340681.0
huggingface|17|93.0|586175.0
dotnet|14|91.4|117412.0
boostorg|12|91.2|21649.0
aws|12|90.8|89204.0
Jensen Huang|12|92.2|83309.0
dtolnay|10|91.9|30910.0
facebook|9|94.8|801473.0
symfony|8|90.0|101713.0
```

`dtolnay` — 10 repos rated ≥90 on 30,910 stars — ranks above `facebook` at
801,473 stars. That inversion is the entire point: it is invisible to a
star-ranked graph.

### #3 — awesome-list editorial signal (`pipelines/github/load_awesome_signal.py`)

Source: `pipelines/github/awesome/catalog_full.sqlite` (1,077 lists / 204,186
entries / 135,784 repos / 86,475 owner rollups), built 2026-08-03.

```
$ python3 load_awesome_signal.py --catalog awesome_catalog_full.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "owner_signal_rows": 85608, "matched_owners": 53072, "unmatched_owners": 32536,
  "edges_matched": 64230, "edges_owner_missing": 71554,
  "before": {"person_topic_total": 1971077, "curated_awesome": 0, "edges_with_list_count": 0},
  "after":  {"person_topic_total": 2024149, "curated_awesome": 53072, "edges_with_list_count": 64411},
  "elapsed_s": 4.14
}
```

62% of cited owners (53,072 / 85,608) were already in the graph. Weight is
`log1p(n_lists)/log1p(300)` — using **distinct lists**, not total citations,
because one list citing an owner forty times is one editor's opinion, not forty.

Independent verification: `curated_awesome` = 53,072, edges with `list_count` = 64,411.

**Caveat recorded on the loader, not hidden:** the top of this signal is
`microsoft`, `google`, `apache`. Editorial citation tracks organisational output
as much as individual craft, so it is stored as *cited-ness*, never as a
"great engineer" score.

### Round 1 totals — before → after

| table | before | after | delta |
|---|---|---|---|
| person | 280,708 | 280,708 | 0 (no people created — by design) |
| person_content | 564,486 | 564,486 | 0 rows; **367,814 edges enriched in place** |
| external_ids | 245,628 | 249,041 | +3,413 (from the concurrent enrich grind) |
| person_topic | 1,661,361 | 2,024,149 | **+362,788** |

---

## NEGATIVE RESULT — idea #8 (the cross-domain stitch) is structurally near-empty

This is the most valuable finding of the round, because it stops an expensive
wrong plan. The brief called the stitch-of-3 "the single biggest problem" (F3)
and implied resolving real names would fix it. **It will not.**

First attempt — join resolved GitHub `real_name` against book author names:

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from external_ids e
    join person bp on lower(bp.name)=lower(e.value)
    where e.platform='real_name' and bp.person_id like 'bk:%';"
2
```

Both are **false positives**:

```
gh:gildas-lormeau | Gildas   | bk:gildas|516-570   | Gildas
gh:parallax       | Parallax | bk:parallax|1816-1884 | Parallax
```

A modern developer matched to a 6th-century monk, and a handle matched to a
19th-century pseudonym. Restricting to plausible human names (two words, no
punctuation) gives:

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from external_ids where platform='real_name'
    and value like '% %' and value not like '%.%' and value not like '%/%' and length(value)<40;"
851
$ sqlite3 people_v2_gh.sqlite "select count(*) from external_ids e
    join person bp on lower(bp.name)=lower(e.value)
    where e.platform='real_name' and e.value like '% %' and bp.person_id like 'bk:%';"
0
```

**Zero.** Two independent structural reasons, both measured:

**1. Gutenberg is a public-domain corpus. The populations do not overlap in time.**

```
$ sqlite3 people_v2_gh.sqlite "select case when death_year is null then 'no_death_year'
    when death_year<1950 then 'died_pre_1950' when death_year<2000 then 'died_1950_1999'
    else 'died_2000+' end band, count(*) from person where person_id like 'bk:%' group by 1;"
died_pre_1950|20246
no_death_year|9695
died_1950_1999|5088
died_2000+|334
```

The plausible-overlap population is the ceiling on this entire idea:

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from person where person_id like 'bk:%'
    and (death_year>=2000 or (death_year is null and birth_year>=1940));"
419
```

**419 people is the theoretical maximum**, not the thousands implied.

**2. GitHub `real_name` is mostly not a person's name.** It is the free-text
profile field, and orgs fill it with anything:

```
.Monks / .NET Application Architecture - Reference Apps / .NET Core Community
/r/freemediaheckyeah / 0voice / 1024xiaoshen / 1Panel-dev / 37signals
AFNetworking / AI4Finance Foundation / AMAI GmbH / ASP.NET
```

**Conclusion:** completing the 50-hour `enrich_owners` grind for the *purpose of*
github↔book stitching would buy at most ~419 candidate people and realistically
far fewer. The grind is still worth finishing — it resolves `kind` for 238,017
`unknown` people, which is independently valuable — but it must not be sold as
the stitch fix. **Cross-domain reach needs a contemporary corpus (YouTube,
podcasts, conference talks), which does not currently exist on this machine.**
That, not name resolution, is the real blocker.

---

## Round 2 — 2026-08-03/04

### #9 + #10 — recency, lifecycle, liftability (`pipelines/github/load_activity_signal.py`)

Before this the graph could not distinguish a 2011 abandoned repo from last
week's work — no temporal signal existed on any edge. Source coverage:

```
$ sqlite3 identity.sqlite "select case when pushed_at is null or pushed_at='' then 'none'
    when pushed_at>='2025' then 'pushed_2025+' when pushed_at>='2023' then 'pushed_2023_24'
    when pushed_at>='2020' then 'pushed_2020_22' else 'pushed_pre2020' end b,
    count(*) from repo_card group by 1 order by 2 desc;"
pushed_2025+|494167
pushed_2023_24|295281
pushed_pre2020|294085
pushed_2020_22|272370
none|2297

$ sqlite3 identity.sqlite 'select sum(archived=1), sum(archived=0), sum(archived is null) from repo_card;'
106994|1248825|2381
```

Applied:

```
$ python3 load_activity_signal.py --identity identity.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "rows_scanned": 1358200, "edges_matched": 462929, "owner_missing": 895264,
  "with_pushed": 462929, "with_archived": 38510, "with_lift": 32070,
  "before": {"edges_with_pushed_at": 0, "edges_with_liftability": 16115, "edges_archived": 23},
  "after":  {"edges_with_pushed_at": 463221, "edges_with_liftability": 36516, "edges_archived": 38552},
  "elapsed_s": 26.65
}
```

462,929 edges enriched — essentially every github edge in the graph (463,230).
The 895,264 `owner_missing` rows are repo_cards whose owner was never loaded as
a person (the owner loader ran with a star floor); they are not losses.

Independent verification using `json_extract` rather than the loader's `LIKE`:

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from person_content where domain='github'
    and json_extract(meta_json,'$.pushed_at') is not null;"
463221
```

**`observed_at` semantics fixed.** The column's schema comment says "when it was
true", but it held the load timestamp — when *we looked*. It now carries the
repo's `pushed_at`:

```
$ sqlite3 people_v2_gh.sqlite "select substr(observed_at,1,4) yr, count(*) from person_content
    where domain='github' group by 1 order by 2 desc limit 8;"
2026|149393
2025|57945
2024|55863
2023|49179
2022|34406
2021|25101
2020|22095
2019|18160
```

Previously every row carried a single load date.

**Questions now answerable:**

Active *and* high-value (neither axis existed before round 1):

```
microsoft|99|87.4|2026-06-23   apache|83|87.8   google|66|87.3
huggingface|32|89.6            rust-lang|30|90.7  Jensen Huang|26|88.2
```

Abandoned work — sanity-checks correctly, the archive orgs surface at the top:

```
microsoft|534  google|524  facebookresearch|368
facebookarchive|214  googlearchive|204  GoogleCloudPlatform|113
```

Liftable *and* still maintained — the Foundry's core question:

```
google|component|87  microsoft|component|77  sindresorhus|component|60
apache|component|44  symfony|component|37    spatie|component|36
```

### Idempotency — verified for all three loaders

Every loader was re-run with `--apply` after its first successful run. All
counters identical before/after, i.e. no double-writes:

```
load_repo_value.py      303403 / 2024149 / 309716  ->  303403 / 2024149 / 309716
load_awesome_signal.py  2024149 / 53072 / 64411    ->  2024149 / 53072 / 64411
load_activity_signal.py 463221 / 36516 / 38552     ->  463221 / 36516 / 38552
```

### Note on overlapping sources

`edges_with_liftability` was already 16,115 before this loader ran —
`load_repo_value.py` writes `liftability` from `repo_category`, while this one
writes it from `bank_liftable_ranked` (32,071 repos, plus `unit_class`). The two
sources agree on the field name and do not conflict; the ranked table is richer
and wins where both exist. Final: 36,516 edges.

### #5 — person↔person co-membership: MEASURED AND REJECTED for now

The graph has no person↔person representation at all, so this looked like the
obvious next build. It is not tractable as a naive co-membership table:

```
$ sqlite3 people_v2_gh.sqlite "select sum(n*(n-1)/2) from
    (select count(distinct person_id) n from person_topic where scheme='gh_category' group by topic);"
720107620
```

**720 million pairs.** The largest categories:

```
self-hosted-application|15799
client-library-sdk|14479
cli-utility|10900
```

15,799 owners in one category is 124.8M pairs from that category alone, and a
co-membership edge at this granularity carries almost no information — "both
wrote a CLI utility" is not a relationship. Deferred pending a design that gates
on something scarcer (shared *rare* category, co-citation within the same
awesome-list section, or genuine co-contribution, which this data does not have).
Recorded here so it is not re-attempted naively.

### Round 2 totals

| metric | before | after |
|---|---|---|
| edges with `pushed_at` | 0 | 463,221 |
| edges with `liftability` | 16,115 | 36,516 |
| edges with `archived` | 23 | 38,552 |
| `observed_at` = truth-time | no | yes (2019–2026 spread) |

---

## Round 3 — 2026-08-04

### #6 — real-world adoption (`pipelines/github/load_adoption_signal.py`)

Stars are a vote and ratings are an opinion. Download counts and dependent-repo
counts are a *measurement* of how much other software actually depends on the
work — the strongest quality signal in the corpus, and it had never reached the
graph.

```
$ python3 load_adoption_signal.py --identity identity.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "source_rows": 1026, "edges_matched": 1026, "owner_missing": 0,
  "no_payload": 0, "with_fame_gap": 748,
  "before": {"edges_with_downloads": 36, "edges_with_fame_gap": 0},
  "after":  {"edges_with_downloads": 898, "edges_with_fame_gap": 760},
  "elapsed_s": 14.58
}
```

**100% owner match** — all 1,026 adoption rows resolved to people already in the
graph. Only ~1k edges, but this is the difference between "looks popular" and
"four million repos break without this".

Independent verification (`json_extract`, not the loader's `LIKE`):

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from person_content
    where json_extract(meta_json,'$.dependent_repos') is not null;"
867
```

**The question this unlocks — who is UNDERRATED?** High adoption, low fame.
Structurally invisible to a star-ranked graph:

```
$ sqlite3 people_v2_gh.sqlite "select p.name, c.content_ref, cast(c.score as int) stars,
    json_extract(c.meta_json,'$.dependent_repos') deps,
    round(json_extract(c.meta_json,'$.fame_gap'),1) gap
    from person_content c join person p using(person_id)
    where json_extract(c.meta_json,'$.fame_gap')>=40
    order by json_extract(c.meta_json,'$.dependent_repos') desc limit 10;"
yargs|yargs/yargs-parser|517|4384968|46.6
Mathias Bynens|mathiasbynens/emoji-regex|1909|4193583|42.4
sindresorhus|sindresorhus/p-map|1499|3047734|44.6
follow-redirects|follow-redirects/follow-redirects|582|2023308|53.3
jshttp|jshttp/on-finished|404|1780334|53.3
kentcdodds|kentcdodds/babel-plugin-macros|2635|1650407|49.3
jsdom|jsdom/whatwg-url|414|1350571|46.6
Socket.IO|socketio/socket.io|63195|1259292|45.6
slevithan|slevithan/xregexp|3326|962216|52.0
Immutable.js|immutable-js/immutable-js|33059|878497|41.6
```

`yargs/yargs-parser`: **517 stars, 4,384,968 dependent repos.** A star-ranked
graph would place it below a toy with 600 stars.

The rating pass's own conclusion is stored as `adoption_verdict` (promote 152 /
confirm 467 / demote 95 / unresolved 312), deliberately NOT as `verdict`, so it
can never be confused with the `value` that `load_repo_value.py` writes — they
are different claims from different passes.

Idempotent: re-run `--apply` gives `898 / 760` → `898 / 760`, unchanged.


### #4 — the topic bridge (`pipelines/build_topic_bridge.py`)

Identity stitching is dead (see the negative result above). But the two
populations are not different SUBJECTS, only different people. 819 topic strings
appear verbatim in both the LCSH and github-topic vocabularies:

```
$ sqlite3 people_v2_gh.sqlite "select count(*) from (
    select distinct lower(topic) from person_topic where scheme='lcsh'
    intersect
    select distinct lower(topic) from person_topic where scheme='github_topic');"
819

$ sqlite3 people_v2_gh.sqlite "select scheme, count(distinct topic) from person_topic group by 1;"
curated|1
gh_category|264
github_lang|463
github_topic|189739
lcsh|40622
```

Applied:

```
$ python3 build_topic_bridge.py --graph /tmp/people_v2_gh.sqlite --apply
{
  "shared_terms": 819, "dropped_stopword": 57, "dropped_too_broad": 0,
  "bridge_terms": 762, "bridge_rows": 26480,
  "distinct_people": 22466, "book_people": 5281,
  "before": {"bridge_rows": 0, "person_topic_total": 2024149},
  "after":  {"bridge_rows": 26480, "person_topic_total": 2050629},
  "elapsed_s": 3.12
}
```

**22,466 people** (5,281 book + 17,185 github) are now reachable from a single
predicate instead of requiring the caller to know which namespace to ask.

**The payoff — one query, both populations:**

```
$ -- scheme='bridge' AND topic='cryptography'
BOOK:   Hitt, Parker | Jacob, P. L. | Simonetta, Cicco | Ball, W. W. Rouse
GITHUB: Bitcoin | Filippo Valsorda | Autumn (Bee) | Zama

$ -- scheme='bridge' AND topic='astronomy'
BOOK:   Dolmage, Cecil | Maunder, E. Walter | Langley, S. P. | Rolfe, W. J.
GITHUB: Stellarium | PWhiddy | astropy | dfm
```

Parker Hitt (author of the 1916 *Manual for the Solution of Military Ciphers*)
now returns alongside Filippo Valsorda (Go cryptography) from one query. Per-term
population split:

```
algorithms|4|630   astronomy|51|102   cryptography|7|588   economics|64|60
```

**Design constraints, stated because they are what keep this honest:**

- **Exact match only.** No stemming, no fuzzy matching, no embeddings. LCSH is a
  controlled vocabulary ("Science fiction, American"); github topics are
  free-text. Fuzzy matching across those generates plausible-looking garbage —
  precisely the failure mode the name-stitch attempt already demonstrated.
- **Stopword gate:** 57 of 819 shared strings dropped ('air', 'ability',
  'actors') — shared strings, not shared subjects.
- **Breadth gate** at 10% of either population. Nothing tripped it this run
  (`dropped_too_broad: 0`), but it stays as a guard.

Idempotent: re-run `--apply` gives `26480 / 2050629` → unchanged.

**PERFORMANCE NOTE — a real bug, fixed.** The first implementation ran two
`COUNT(DISTINCT ...)` queries per term. The existing index is
`person_topic(topic, scheme)`, which **cannot serve `lower(topic)`**, so each of
1,638 queries was a full scan of ~2M rows (~0.25 s each). Measured:

```
$ time sqlite3 people_v2_gh.sqlite "select count(distinct person_id) from person_topic
    where scheme='github_topic' and lower(topic)='algorithms';"
630
0.246 total
```

It was still running after ~15 minutes. Rewritten as a single set-based sweep
that buckets by `lower(topic)` in one pass: **1.33 s**, a >600× speedup for
identical output. Worth recording as a general trap: an index on `col` does not
serve `lower(col)`.

### Round 3 totals

| metric | before | after |
|---|---|---|
| person_topic | 2,024,149 | 2,050,629 |
| bridge rows | 0 | 26,480 |
| edges with `downloads` | 36 | 898 |
| edges with `fame_gap` | 0 | 760 |
| people reachable cross-population by topic | 0 | 22,466 |

---

## Round 4 — 2026-08-04

### #11 (new) — momentum / star velocity (`pipelines/github/load_momentum_signal.py`)

After round 2 the graph knows WHEN work was last touched. It still did not know
whether that work is RISING or FADING — a different question from "who is
active" and from "who is famous", and the one that finds people before they are
obvious.

`~/foundry-data/domains/github/momentum.sqlite` had carried it all along:

```
$ sqlite3 momentum.sqlite "select count(distinct full_name), count(*) from repo_snapshot;"
56688|170062
$ sqlite3 momentum.sqlite "select day, count(*) from repo_snapshot group by 1 order by 1;"
2026-07-09|56687
2026-07-10|56687
2026-07-11|56688
```

Applied:

```
$ python3 load_momentum_signal.py --momentum momentum.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "repos_in_series": 56688, "edges_matched": 56679, "owner_missing": 9,
  "before": {"edges_with_velocity": 0},
  "after":  {"edges_with_velocity": 56933},
  "elapsed_s": 1.98
}
```

**Question unlocked — who is RISING?** High velocity against modest stars:

```
DeusData|DeusData/codebase-memory-mcp|11976 stars|547/day|value 85
microsoft|microsoft/Webwright|5543|157/day|85
Xiaomi MiMo|XiaomiMiMo/MiMo-Code|10391|138/day|80
```

**HONEST SCOPE, stated on the loader and repeated here.** The window is three
consecutive days in July 2026. That is a momentary reading, not a trend — a repo
that launched on 2026-07-10 shows enormous velocity while a steady long-term
grower shows little. `momentum_day` is written alongside every value so a
consumer can see how narrow and how stale the reading is, and it is deliberately
NOT folded into `person.rank_score`.

Idempotent: re-run gives `56933` → `56933`.

### A measurement bug caught by the classify-by-reading guard

The first draft of this loader asserted momentum was "unused by any loader" and
counted coverage with `meta_json LIKE '%star_velocity%'`. Both were sloppy.
Verified by content instead:

```
$ grep -rn "momentum" --include="*.py" --include="*.md" --include="*.sql" .
(no loader references it)
$ sqlite3 people_v2_gh.sqlite "select source, count(*) from person_content group by 1;"
github_identity|462930
gutenberg|101124
v1_migration|432
```

No momentum source exists, so the claim was right — but the `LIKE` counter was
not. It matched **35 pre-existing edges** that were repos *named* velocity:

```
gh:julianshapiro | julianshapiro/velocity   | github_identity
gh:iampawan      | iampawan/VelocityX       | github_identity
gh:mind-protocol | mind-protocol/terminal-velocity | github_identity
```

A `LIKE`-based before/after would have reported a baseline of 35 instead of 0
and silently understated the load by that much. Counters now use
`json_extract(meta_json,'$.star_velocity')`, which confirmed `before: 0`.

Worth generalising: **`meta_json LIKE '%key%'` matches values as well as keys.**
The earlier loaders in this log used LIKE for their coverage counters; their
headline numbers were all independently re-derived with `json_extract`, which is
why the discrepancies (e.g. 303,403 vs 303,114) are visible above rather than
hidden.

### Round 4 totals

| metric | before | after |
|---|---|---|
| edges with `star_velocity` | 0 | 56,933 |
| person_topic | 2,050,629 | 2,050,629 (unchanged — this round is edge-only) |


---

## Verified state after rounds 1–4

Every number below re-derived with `json_extract` (NOT the `LIKE` counters the
loaders print), 2026-08-04:

```
$ for K in value reuse_value info_value liftability unit_class list_count \
      pushed_at created_at archived downloads dependent_repos fame_gap \
      adoption_verdict star_velocity momentum_day; do
    printf '%-18s ' $K
    sqlite3 people_v2_gh.sqlite "select count(*) from person_content
      where json_extract(meta_json,'\$.$K') is not null;"
  done
value              303403      pushed_at          463221
reuse_value        303403      created_at         463122
info_value         303403      archived            38532
liftability         36516      downloads             856
unit_class          32189      dependent_repos       867
list_count          64411      fame_gap              760
adoption_verdict     1039      star_velocity       56933
                               momentum_day        56933
```

Tables:

```
person|280708          person_content|564486
external_ids|253815    person_topic|2050629
```

Topic schemes:

```
github_topic|1206260|136024     gh_category|309716|170236
github_lang|287516|228970       lcsh|167585|35347
curated|53072|53072             bridge|26480|22466
```

### The compounding effect — signals per edge

Before round 1, every github edge carried exactly one signal (stars). Now:

```
$ sqlite3 people_v2_gh.sqlite "select n_signals, count(*) from (
    select (json_extract(meta_json,'$.value') is not null)
         + (json_extract(meta_json,'$.list_count') is not null)
         + (json_extract(meta_json,'$.dependent_repos') is not null)
         + (json_extract(meta_json,'$.star_velocity') is not null)
         + (json_extract(meta_json,'$.pushed_at') is not null) n_signals
    from person_content where domain='github') group by 1 order by 1;"
0|3
1|149382
2|224435
3|67335
4|21797
5|278
```

**313,845 edges carry two or more independent quality signals**, up from zero.
170,233 people now have both a rated value and a recency date, so questions can
be compound ("actively maintained AND highly rated AND widely depended upon")
rather than single-axis.

### Cumulative before → after (rounds 1–4)

| metric | before | after |
|---|---|---|
| person | 280,708 | 280,708 (no people created — by design) |
| person_content rows | 564,486 | 564,486 (no rows added; enriched in place) |
| person_topic | 1,661,361 | **2,050,629** (+389,268) |
| topic schemes | 3 | 6 (+gh_category, +curated, +bridge) |
| edges with any quality signal beyond stars | 0 | **313,845 with ≥2** |
| cross-population topic reach | 0 people | **22,466 people** |

### Safety record

- Nothing deleted. No `rm`, no `git clean`, no `DROP`. (C1)
- No pattern-kills. One process stopped, by exact PID, and it was my own
  superseded read-only dry run. (C2)
- All writes to `/tmp/people_v2_gh.sqlite`; the canonical
  `~/foundry-data/domains/people/people.sqlite` was never opened for write. (C3)
- Backup taken before the first change:
  `/tmp/people_v2_gh.PRE-ENRICH-20260803-174831.sqlite`.
- No git push; local commits only. (C4)
- The vault was never written to or unmounted. (C5)
- A concurrent `enrich_owners.py` API grind was left running throughout rather
  than killed; loaders wait on the lock with `busy_timeout=600000` instead.

### Ideas still open

| # | Idea | Status |
|---|---|---|
| 5 | person↔person edges | REJECTED as designed — 720M naive pairs; needs a scarcity gate |
| 7 | `enrich_owners` at full scale | IN PROGRESS — real_name 172 → 3,601; still ~240k owners to go |
| 8 | github↔book identity stitch | DEAD — ceiling ~419 people, zero plausible matches |
| 12 | `bank_gold.why` (29,937 human-written rationales incl. license lane) | NOT STARTED |
| 13 | `bank_capability.capability_tag` | LOW VALUE — only 4,063 of 23,778 tagged, 1,921 in one bucket |
| 14 | `repo_observation` (602,565 rows — provenance/source diversity per repo) | NOT SURVEYED |


## Round 5 — 2026-08-04

### #15 (new) — retrievable full text (`pipelines/books/load_passage_signal.py`)

Every enrichment so far describes work from the OUTSIDE — stars, ratings,
adoption, recency, momentum. None answers the question a people graph most
obviously ought to answer: **"what did this person actually write?"**

`passages.sqlite` on the vault holds segmented, searchable book text, and `gid`
is the same namespace the graph already uses as `content_ref` for book edges —
an exact join, no name matching:

```
$ sqlite3 'file:passages.sqlite?mode=ro' 'select count(*), count(distinct gid) from passage;'
295646|500
$ -- graph book content_refs are bare gids
25516|The Crown of Success
26094|Hebrew Heroes: A Tale Founded on Jewish History
```

Applied:

```
$ python3 load_passage_signal.py --passages passages.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "passage_books": 500, "matched_gids": 453,
  "edges_to_update": 606, "distinct_people": 442,
  "before": {"book_edges_with_text": 0, "book_edges_total": 101124},
  "after":  {"book_edges_with_text": 606},
  "elapsed_s": 14.47
}
```

**Question unlocked — whose work can I actually read?**

```
Shakespeare, William|4 works|1,075,839 words
Cooper, James Fenimore|5|778,473
Horne, Charles F.|5|774,601
Dante Alighieri|11|715,920
Johnson, Samuel|3|560,849
```

**The layers compose.** Readable authors joined against the round-4 topic bridge:

```
Addison, Joseph  | fiction, friendship
Alcott, Louisa May | fiction
Aho, Juhani      | essays, fiction
Aaronsohn, Alexander | palestine
```

So "find someone on topic X whose work I can actually read" now works end to
end — a question that needed both this round and the bridge to exist.

**Design: a flag, not the text.** The corpus is 174 MB and lives under a
single-writer build job. Copying it into the graph would duplicate a large body
of text into what is meant to be an index of people, and it would go stale the
moment the builder advances. The flag plus counts makes the graph able to
*answer* "can I read this person?"; retrieval then goes to passages.sqlite by
gid, which is what that database is for.

**Headroom, measured rather than estimated.** The graph holds 72,744 distinct
books; 51,026 have a locator entry (text addressable); `passage` currently
covers 500. The builder is still running, so re-running this loader picks up new
books — it is idempotent by value, not by "already done".

```
$ sqlite3 people_v2_gh.sqlite "select count(distinct content_ref) from person_content where domain='book';"
72744
$ sqlite3 'file:locator.sqlite?mode=ro' 'select count(distinct gid) from location;'
51026
```

Vault safety: `passages.sqlite` and `locator.sqlite` were opened `mode=ro` only.
Nothing under /Volumes was written, moved, or unmounted (C5).

Idempotent: re-run gives `606` → `606`.

### Note on the three idle recon workers

`awesome-recon`, `books-recon` and `bridge-recon` all signalled idle without
transmitting a payload, and no findings were recoverable from the session
transcripts. They were NOT re-dispatched — that pays twice for the same work.
All three questions were answered directly instead: the awesome catalog profile
(round 1), the LCSH/github overlap (round 4), and the books source survey (this
round, which is what surfaced passages.sqlite).


## Round 6 — 2026-08-04

### #12 — legal lane and reuse shape (`pipelines/github/load_legal_signal.py`)

Round 2 put `liftability` on 36,516 edges — "how technically extractable is
this". That is only half the question anyone lifting code has. The other half is
whether they are ALLOWED to, and in what shape. A GPL library and an MIT library
can have identical liftability and opposite answers.

```
$ sqlite3 identity.sqlite "select legal_lane, count(*) from repo_category
    where legal_lane is not null and legal_lane != '' group by 1 order by 2 desc;"
shippable|5730
unknown|2682
blocked|999
reference_only|77

$ sqlite3 identity.sqlite "select value_type, count(*) from repo_category
    where value_type is not null and value_type != '' group by 1 order by 2 desc;"
CODE|4926
BOTH|3125
INFO|928
NEITHER|10
```

Applied:

```
$ python3 load_legal_signal.py --identity identity.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "source_repos": 20794, "edges_matched": 20793, "owner_missing": 1,
  "with_lane": 9488, "shippable": 5730, "blocked": 999,
  "before": {"edges_with_lane": 0, "edges_shippable": 0},
  "after":  {"edges_with_lane": 9605, "edges_shippable": 5801},
  "elapsed_s": 2.5
}
```

**REJECTED the obvious source, and this is the point of the round.** Idea #12 was
originally "`bank_gold.why` — 29,937 human-written rationales". Those rationales
do begin with a bracketed license lane:

```
tavianator/bfs|[COARSE] [CODE|0BSD (permissive)] Breadth-first, friendlier drop-in...
llir/llvm|[CODE|0BSD / public domain (dual-licensed)] Pure-Go library to parse...
```

But the formatting is not consistent enough to parse. The same license appears
at least four ways:

```
MIT (permissive, reusable)] |608
MIT — permissive, fully reus|481
MIT (permissive, fully reusa|246
MIT — permissive, reusable] |184
MIT — permissive, reusable.]| 85
```

A parser over that would silently mis-bucket. `repo_category.legal_lane` is the
*same judgement in a proper column* — use the column, not the prose. Recorded
because "there is 29,937 rows of rich text" is exactly the kind of seam that
looks more valuable than the boring structured column next to it.

**`unknown` is loaded deliberately.** "We looked and could not tell" (2,682) is
a different state from "we never looked", and writing only the confident lanes
would make them indistinguishable — the same honest-null principle that keeps
238k GitHub owners at `kind='unknown'` rather than guessed.

**The payoff — the full Foundry question, four axes at once**, none of which the
graph could express before this session (value: round 1, liftability: round 2,
pushed_at: round 2, legal_lane: this round):

```
$ -- legal_lane='shippable' AND liftability>=88 AND pushed_at>='2025', by value
ajv-validator/ajv                       |95|90|component|2026-05
dart-lang/sdk                           |95|90|component|2026-06
software-mansion/react-native-reanimated|95|90|component|2026-06
google/skia                             |95|90|component|2026-06
e2b-dev/E2B                             |95|90|component|2026-06
redis/jedis                             |95|90|component|2026-06
Kotlin/kotlinx.coroutines               |95|90|component|2026-06
pallets/click                           |95|90|component|2026-06
```

And the inverse, which matters just as much — work to avoid:

```
$ sqlite3 people_v2_gh.sqlite "select count(*), count(distinct person_id) from person_content
    where json_extract(meta_json,'$.legal_lane')='blocked';"
1006|942
```

Idempotent: re-run gives `9605 / 5801` → unchanged.


### #14 — `repo_observation` source diversity: MEASURED AND REJECTED

602,565 rows recording where each repo was observed. The hypothesis was that a
repo seen through many independent sources is a stronger find. The raw
correlation looks compelling:

```
$ -- source count vs quality
n|repos |avg_value|avg_stars
8|     6|     69.5|  72870
6|    59|     75.3|  40410
3| 17543|     64.4|  13022
2|146359|     55.0|   1361
1|382919|     48.7|    226
```

avg_value climbs 48.7 → 69.5 and avg_stars 226 → 72,870. **But the sources are
our own crawl batches, not independent discovery:**

```
.agents/scratch/github-farm/urls_100_499_refresh_2026-06-23.jsonl|343534
.agents/scratch/github-farm/urls_ge5k_refresh_2026-06-23.jsonl|12060
.agents/scratch/github-farm/urls_10k_50k.jsonl|4837
```

The batches are **star-banded by construction** (`urls_ge5k`, `urls_10k_50k`,
`urls_1k_5k`), so a high-star repo appears in more of them mechanically. The
correlation is largely a restatement of stars, which the graph already has.

Controlling for stars (1,000–5,000 band only) mostly collapses it:

```
n|repos |avg_value
1|   104|     54.8
2| 68891|     57.2
3|   428|     65.1
4|   150|     70.7
5|     6|     68.8
6|     5|     66.0
```

A residual effect may exist between n=2 and n=4, but the n≥5 cells hold 5–6
repos — far too few to carry a conclusion. **Rejected:** the signal is weak,
star-confounded, and would import a measurement of our own crawl topology into
a graph about people. Recorded so the compelling-looking raw correlation does
not lure a later pass.

