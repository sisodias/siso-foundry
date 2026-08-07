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


## Round 7 — 2026-08-04

### #16 (new) — L1 domain families (`pipelines/github/load_family_topics.py`)

person_topic offered two github vocabularies at opposite extremes and nothing in
between:

```
github_topic  189,739 distinct  -- free-text, whatever the owner typed
gh_category       264 distinct  -- curated, but only where a rater looked
```

Neither answers "who works in AI" well: the first is too granular and noisy
(`ai`, `ai-agent`, `aiagents`, `artificial-intelligence` are four separate
topics), the second is precise but covers rated repos only. `l1_route.family_tags`
sits between them, applied across the whole corpus:

```
$ sqlite3 identity.sqlite "select count(*), sum(family_tags not in ('[]','')) from l1_route;"
465192|271004
```

Applied:

```
$ python3 load_family_topics.py --identity identity.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "source_rows": 271004, "owner_missing": 1111, "bad_json": 0,
  "topic_rows": 328846, "distinct_people": 160056, "distinct_families": 24,
  "before": {"gh_family_rows": 0, "person_topic_total": 2050629},
  "after":  {"gh_family_rows": 328846, "person_topic_total": 2379475},
  "elapsed_s": 4.72
}
```

**160,056 people across 24 families**, under `scheme='gh_family'` so it never
mixes with github_topic or gh_category. A query wanting breadth asks gh_family;
one wanting precision asks gh_category. Both now exist.

**Provenance preserved, not flattened.** `match_source` records how each routing
was decided and the methods are not equally trustworthy:

```
topic|142718   -- matched on declared repo topics
desc |128286   -- matched on description text
none |194188   -- no family assigned
```

A description match is a weaker claim than a topic match, so it is written at a
lower weight rather than asserted as equivalent. Combined with the router's own
`bucket` confidence (clean / ambiguous):

```
(topic, clean) 1.0   (topic, ambiguous) 0.6
(desc,  clean) 0.7   (desc,  ambiguous) 0.4
```

Observed spread confirms the weights differentiate rather than collapsing:

```
Web Frontend|24819|avg weight 0.72       Computer Vision|15511|0.57
Mobile (iOS / Android)|20492|0.72        Media / Audio / Video|13920|0.63
AI / Machine Learning Core|21438|0.68
```

Ambiguous routings ARE loaded (at reduced weight) because "we routed this three
ways and could not choose" is real information — the same honest-null principle
used for `legal_lane='unknown'` and `kind='unknown'`.

**One topic row per person per family, not per repo.** A person with ten repos
in one family gets one row carrying their strongest evidence. person_topic is
about the person; a per-repo tally belongs on the edge.

**Question unlocked** — "who works in AI, with strong evidence AND quality
work" (weight=1.0 means topic-matched and cleanly routed):

```
microsoft|1.0|113 repos|avg value 87     huggingface|1.0|32|90
apache|1.0|83|88                         Jensen Huang|1.0|29|88
google|1.0|72|87                         facebookresearch|1.0|23|87
```

Idempotent: re-run gives `328846 / 2379475` → unchanged.


### CORRECTION — why idea #7 (enrich_owners) had barely moved

Both prior `enrich_owners.py` runs were reported as completing their batches.
They did not. They were **running unauthenticated at 60 requests/hour.**

```
$ cat /tmp/enrich_batch2.out
{
  "considered": 4500, "fetched": 49, "users": 24, "orgs": 25,
  "errors": 1, "rate_limited": true, "elapsed_s": 18.56
}
```

4,500 owners considered, **49 fetched**, then rate-limited after 18 seconds.
The first run showed the same shape (149 of 245,166). Meanwhile the account's
authenticated budget was untouched:

```
$ gh api rate_limit --jq '.resources.core'
{"limit":5000,"remaining":5000,"used":0}
```

Cause, found by reading the script rather than guessing:

```
$ grep -n 'token\|Authorization' /tmp/enrich_owners.py
57:def fetch(login, token):
63:            **({"Authorization": f"Bearer {token}"} if token else {}),
167:  ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
```

The token is optional and defaults to `GITHUB_TOKEN`. Neither prior invocation
passed `--token` or exported that variable, so every request went out
anonymously — 60/hr, not 5,000/hr, an **83× throughput loss**.

Relaunched correctly with `GITHUB_TOKEN=$(gh auth token)` and `--sleep 0.75`
(~4,800/hr, just under the limit). Verified authenticated by watching the budget
actually draw down:

```
$ gh api rate_limit --jq '.resources.core | "remaining=\(.remaining) used=\(.used)"'
remaining=4966 used=34
```

**Lesson recorded:** `rate_limited: true` in a loader's own summary is not proof
of a hard external ceiling — check *which* ceiling. An unauthenticated client
hits a limit 83× lower and reports it identically. Two runs and several hours
were spent before anyone read the auth path.

Revised estimate for #7: at ~4,800/hr against 235,732 unresolved owners, full
`kind` resolution is roughly **49 hours of wall clock**, not the ~50 hours at
4k/batch previously implied — the difference being that it now actually
progresses.


## Round 8 — 2026-08-04 — CORRECTING THE TARGETING MISTAKE

### The mistake, measured

Eight rounds all went to GitHub. A per-domain depth audit — one query that
should have run at the start — shows what that cost:

```
$ sqlite3 people_v2_gh.sqlite "select domain, count(distinct person_id) people,
    count(*) edges, sum(meta_json='{}') empty from person_content group by 1;"
github        |245175|463230|     0
book          | 35366|101124|100518
youtube_channel|   35|    35|     0
youtube_video |    24|    97|     0
```

**99.4% of book edges carried an empty meta_json** while every one of 463,230
github edges was enriched. Books are the second-largest population in the graph
(35,366 people) and had one signal on 0.6% of their edges. I let "where the rows
are" stand in for "where the value is".

### #17 — book edge enrichment (`pipelines/books/load_book_edge_signal.py`)

```
$ python3 load_book_edge_signal.py --locator locator.sqlite --graph /tmp/people_v2_gh.sqlite --apply
{
  "edges": 101124, "with_addressable": 100758, "with_subjects": 101105,
  "before": {"book_edges_empty_meta": 100518, "book_edges_addressable": 0},
  "after":  {"book_edges_empty_meta": 0,      "book_edges_addressable": 100758},
  "elapsed_s": 55.29
}
```

**Empty book edges: 100,518 → 0.**

`text_addressable` is deliberately NOT the same claim as `has_text`:

- `passage.gid`  = text SEGMENTED — 500 books (the builder is the bottleneck)
- `location.gid` = text ADDRESSABLE by byte range — **77,540 books and rising**

I earlier reported locator's growth as if the passage loader would pick it up.
It did not: re-running `load_passage_signal.py` returned `606 → 606` because
`passage` is still at 500. Different stages; I conflated them.

### A bug I shipped and then fixed

The first run wrote a `subjects` field per edge. The output exposed it:

```
A. L. O. E.|The Crown of Success                |["Adopted children -- Juvenile fiction","Adventure stories","Afghanist…
A. L. O. E.|Hebrew Heroes: A Tale Founded on…   |["Adopted children -- Juvenile fiction","Adventure stories","Afghanist…
A. L. O. E.|The Rambles of a Rat                |["Adopted children -- Juvenile fiction","Adventure stories","Afghanist…
```

Four different books, identical subjects — the exact smearing my own docstring
claimed to fix. Verified that per-book subject data does not exist anywhere:
every lcsh row is keyed by person (`aristotle` → `Aesthetics -- Early works to
1800`) and locator.sqlite has only `location` and `asset` tables.

Renamed to **`author_subjects`**, with the old key removed on re-run:

```
$ sqlite3 people_v2_gh.sqlite "select sum(json_extract(meta_json,'$.author_subjects') is not null),
    sum(json_extract(meta_json,'$.subjects') is not null) from person_content where domain='book';"
101105|0
```

Calling a person-level rollup `subjects` asserts a per-book fact we do not have
— the same class of error v2's schema was written to prevent. "What is THIS book
about" needs per-gid subject harvesting; it remains unanswerable.

### #18 — YouTube hosts and the graph's first person↔person relation

YouTube was written off as "fully loaded" because the source has 97 rows. True
about the rows, wrong about the structure. The queue holds **two** sets of
people and only one was loaded:

```
$ sqlite3 people_video_queue.sqlite "select count(*), count(distinct person_slug),
    count(distinct channel_name) from people_video_queue where channel_name != '';"
97|24|25
```

`person_slug` is the GUEST (loaded). `channel_name` is the HOST — never loaded,
and mostly named individuals: Matthew Berman (21), David Ondrej (12),
Dwarkesh Patel, Networkchuck.

```
$ python3 load_channels_and_appearances.py --queue people_video_queue.sqlite --graph … --apply
{
  "distinct_hosts": 24, "new_host_people": 21, "host_edges": 96,
  "guest_edges_updated": 98, "skipped_no_channel": 1,
  "before": {"youtube_people": 58, "youtube_edges": 132, "host_edges": 0},
  "after":  {"youtube_people": 74, "youtube_edges": 225, "host_edges": 93}
}
```

**Why this matters out of proportion to its size.** Every other edge in the
graph is person→artifact. A guest appearance is person→artifact→person — the
only relational data available. Round 4 measured the naive co-membership
alternative at 720,107,620 pairs and rejected it. This is 97 videos, but
"who has appeared with whom" was previously unanswerable by any means:

```
Demis Hassabis|["Bloomberg Technology","Dwarkesh Podcast","Google DeepMind","Lex Fridman","WIRED"]
Dario Amodei  |["Dwarkesh Clips","Dwarkesh Patel"]
Bob Lazar     |["PowerfulJRE / The Joe Rogan Experience","Jeremy Corbell","The Richard Dolan Show",…]
```

Hosts land as `kind='unknown'` — 'AI Grid' and 'WIRED' are not humans, and
guessing is what the honest-null convention exists to avoid.

### Per-domain depth after this round

```
github         |245175|463230|0 empty
book           | 35366|101124|0 empty
youtube_video  |    47|   190|0 empty
youtube_channel|    35|    35|0 empty
```

**Zero empty edges in every domain.**

### Revised judgement on idea #7 (enrich_owners)

Now running authenticated, but the ~49-hour full grind is **mostly not worth
it**. Its original justification was unblocking the book stitch, which is capped
at 419 people. What remains is org-vs-human classification for GitHub — useful,
not transformative. Better: cap it at the top ~20k owners by rated value and
drop the long tail.


## Round 9 — 2026-08-04 — the 49-hour job was the wrong shape

### The diagnosis

`enrich_owners.py` issues ONE REST request per login against `/users/{login}`,
serialised, with a sleep between. Two independent costs, and the rate limit is
the *smaller* one:

- 235,732 owners × 1 round trip, serial = ~49 hours of wall clock
- REST charges **1 rate-limit unit per user**, so 5,000/hr is a hard ceiling

Measured from the live REST run before it was stopped — the log states the cost
exactly:

```
2000/4500 (rate limit remaining: 2990)
...
2650/4500 (rate limit remaining: 2339)
```

**2,650 owners consumed 2,661 units in 45 minutes** — 1 unit each, ~3,500/hr.

### The fix: GraphQL multi-alias batching

GraphQL bills by query complexity, not by entity. Probed against the live API
before writing anything:

```
$ 100 aliased repositoryOwner lookups in one POST
aliases_returned: 100
rateLimit: {'cost': 1, 'remaining': 4194, 'limit': 5000}
HTTP:200 TIME:2.27s
```

**cost: 1 for 100 users.** A 100× reduction in rate-limit consumption on top of
removing 99% of the round trips.

`repositoryOwner` + inline fragments is the right selector: a login may be a
User or an Organization, and the REST script could only discover which by
fetching and reading `type`. `__typename` reports it in the same call, so
org-vs-human classification — the whole remaining value of this job, now that
the book stitch is known to cap at 419 people — comes free.

### Measured end-to-end

```
$ python3 enrich_owners_graphql.py --graph people_v2.sqlite --limit 1000 --apply
{
  "candidates": 1000, "batches": 10, "resolved": 990,
  "users": 451, "orgs": 539, "null_aliases": 10, "failed_batches": 0,
  "gql_cost": 10,
  "before": {"kind_unknown": 233456, "real_name": 5823},
  "after":  {"kind_unknown": 232929, "real_name": 6617},
  "elapsed_s": 27.36,
  "owners_per_hour": 130263
}
```

| | REST | GraphQL |
|---|---|---|
| owners/hour | ~3,500 | **130,263** |
| rate units per 1,000 owners | 1,000 | **10** |
| full backlog (235,732) | ~49 hours | **~1.8 hours** |

**37× faster end-to-end, 100× cheaper in rate limit.** The remaining bound is
HTTP throughput, not GitHub. Budget after the 1,000-owner test:
`{"limit":5000,"remaining":4975,"used":25}`.

Two fields arrived free that the REST version never collected — `location` (348)
and `company` (125) — because they cost nothing extra inside a query already
being made.

### Notes on correctness

**Partial results are the normal case, not an error.** A deleted or renamed
login returns null for THAT alias plus a top-level error, while every other
alias still resolves. The REST loop treated an error as a failed request; here a
null alias is recorded as resolved-to-nothing (10 of 1,000 in the test) so a
batch is never retried forever.

**Written as a new file, not an edit.** `enrich_owners.py` was executing against
the same graph at the time; rewriting a file mid-execution produces a
half-old/half-new process. The REST job was stopped by exact PID afterwards.

### Generalisable lesson

A long-running serial API job should be interrogated for a batch endpoint before
it is left to grind. The ratio here was not 2× or 5× — it was 37× wall clock and
100× quota, and the entire cost was one script author reaching for the obvious
per-entity REST call. **Check whether the provider bills per request or per
entity**; when it is per request, batching is nearly free throughput.


## Round 10 — 2026-08-04 — the passage build could never have finished

### It was not slow. It was dead, and it was the wrong shape.

`passages.sqlite` sat at exactly 500 books of 77,540 available. Two causes, both
found by reading rather than assuming:

```
$ cat /Volumes/SISO-STORAGE-VAULT/library/gutenberg/passages.log
2026-08-03T16:52:30Z passages done
Traceback (most recent call last):
  File "/tmp/build_passages.py", line 234, in main
    con.commit()
sqlite3.OperationalError: disk I/O error
2026-08-03T16:53:19Z passages done
```

**It crashed, then logged "passages done" anyway.** A `--limit 500` flag capped
it, and the crash meant nobody noticed it had stopped.

Throughput was never the problem — measured directly:

```
$ /usr/bin/time -p python3 build_passages.py --tar txt-files.tar --db /tmp/probe.sqlite --limit 200
"passages_this_run": 131518, "elapsed_s": 3.37
real 3.40
```

No API, no rate limit, pure local CPU over a 30 GB tar.

### The real constraint: it cannot fit on the disk

Re-running to local disk revealed the actual wall:

```
2000 books, 1188761 passages   ->  788,598,784 bytes
$ python3 -c "print(788598784/2000*77540/1e9)"
30.6   # GB projected for the full corpus
$ df -g /tmp
25 GB free
```

**30.6 GB needed against 25 GB free.** A full per-passage build was physically
impossible on this machine, which is almost certainly what produced the original
`disk I/O error`. Stopped by exact PID at 1.5 GB before it exhausted the volume.

### The fix: build what the consumer actually reads

`load_passage_signal.py` issues exactly one query against this table:

```sql
SELECT gid, COUNT(*), SUM(words), MIN(heading) FROM passage GROUP BY gid
```

A per-book rollup. The pipeline was storing **~590 rows per book to derive 1**,
then aggregating the rest away. `build_passage_summary.py` computes the rollup
while streaming the tar, never materialising passage rows:

| | per-passage | per-book summary |
|---|---|---|
| 500 books | 788 MB (measured at 2,000) | **40 KB** |
| projected 77,540 | ~30.6 GB — does not fit | **~6 MB** |

**~5,000× smaller**, and it fits with room to spare.

### A correctness trap I walked into and backed out of

The first draft split on blank lines. It produced **704,697** passages for the
same 500 books where the real builder produces **295,646** — 2.4× off, because
`split_passages()` merges short blocks up to MIN_CHARS, splits oversized ones on
sentence boundaries, and `body_bounds()` trims Gutenberg boilerplate first.

Fixed by importing the real functions rather than reimplementing them:

```
$ python3 build_passage_summary.py --tar txt-files.tar --db /tmp/psum_probe.sqlite --limit 500
"passages_represented": 295646, "db_bytes": 40960, "elapsed_s": 3.53

summary: 500|295646
real   : 500|295646
```

**Exact match.** A summary that silently disagreed with its source would have
been worse than no summary at all — it would have put wrong word counts on
person edges with no way to notice.

### What is given up, stated plainly

Per-passage byte offsets are what make "retrieve THIS paragraph by range" work
— the entire point of the passages design. The summary cannot do that. It is
the right structure for the people graph's question ("how much readable text
does this person have") and the wrong one for retrieval. If passage-level
retrieval is wanted later: build it per-book on demand from the tar, or run the
full build somewhere with 40 GB free. Both are cheap. A 30 GB table that cannot
fit is not.

### The pattern across three jobs

| job | believed | actually |
|---|---|---|
| enrich (REST, run 1) | rate-limited at 5,000/hr | 60/hr — no auth token passed |
| enrich (REST, run 2) | ~49 hours, unavoidable | 1.8 hours via GraphQL batching |
| passages | slow builder, 500 done | 22 min of CPU; **crashed**, logged "done", and could never fit |

Same root cause every time: **a job's self-reported status was trusted instead
of measured.** `rate_limited: true` did not say *which* limit. "passages done"
was printed after a traceback. Neither was ever checked against a clock, a
target count, or free disk.


## Round 11 — 2026-08-04 — cross-domain significance

### The gap

`person.rank_score` is populated for everyone but is a DIFFERENT UNIT per domain:

```
origin  |      n | ranked |    max
github  | 245171 | 245171 | 520358   <- summed stars
books   |  35363 |  35363 |    336   <- work count
youtube |     48 |     48 |     62
registry|    140 |      3 |     94
```

Sorting by it returns 245,171 GitHub accounts before the first author — measured:

```
$ select origin, count(*) from (select * from person order by rank_score desc limit 1000) group by 1;
github|1000
```

"Who are the most significant people here" — the question a people graph exists
to answer — was unanswerable across domains.

### `build_cross_domain_rank.py`

Writes a `cross_rank` table (280,722 rows) with percentile-within-domain,
evidence breadth, domain count, and a combined `cross_score`.

**Percentile, not normalised raw value.** Star counts are power-law distributed;
linear scaling puts torvalds at 100 and everyone else near zero, so books would
still lose to GitHub's tail. "How does this person rank among their peers" is
the only comparison that means the same thing in both populations.

**A separate table, not a person column.** `rank_score` is written by the domain
loaders and means "significance within my domain"; overwriting it would destroy
that and break every loader that resumes from it.

### The first attempt was still 997/1000 GitHub — and why

```
=== DOMAIN MIX IN TOP 1000 (first attempt) ===
github|997
registry|3
```

Better than 1000/1000, but not fixed. The cause was in my own scoring:
`evidence_breadth` was divided by a fixed constant of 5, while the number of
evidence keys a domain can even carry differs sharply — GitHub edges can hold 5
of them (value, dependent_repos, list_count, star_velocity, legal_lane), book
edges at most 2 (has_text, text_addressable). Every author was therefore capped
at 40% of that axis **for reasons that have nothing to do with the person**.

Fixed by normalising breadth against the maximum achievable *within each origin*:

```
=== DOMAIN MIX IN TOP 1000 (after fix) ===
github|741
books|256
registry|3
```

```
Jensen Huang         |registry|95.0|ev 5
Shakespeare, William |books   |90.0|ev 2
Affaan Mustafa       |github  |90.0|ev 5
Twain, Mark          |books   |90.0|ev 2
Dickens, Charles     |books   |90.0|ev 2
Dumas, Alexandre     |books   |90.0|ev 2
Balzac, Honoré de    |books   |90.0|ev 2
```

Shakespeare, Twain, Dickens and Balzac now rank alongside the strongest GitHub
accounts. **Lesson: a "fair" cross-domain metric silently inherits whichever
domain has richer instrumentation, unless the denominator is per-domain too.**

The weights (0.6 percentile / 0.25 breadth / 0.15 domain count) are a JUDGEMENT,
not a measurement, and sit in one visible expression so they can be argued with.

### Correction: v_contemporaries was never broken

An earlier round called the era layer missing and `v_contemporaries` "currently
meaningless". Wrong — the view exists, 27,583 people have birth years, and it
works as designed:

```
$ select contemporary_name, overlap_start, overlap_end from v_contemporaries where name like 'Spinoza%';
Milton, John   |1632|1674
Descartes, René|1632|1650
Bunyan, John   |1632|1677
Dryden, John   |1632|1677
```

No work was needed. Recorded because I nearly rebuilt something that already
functioned — the same classify-by-reading failure this log has flagged twice.


### GraphQL enrich — measured mid-run

The economics are no longer arguable. Partway through the backlog:

```
$ sqlite3 people_v2_gh.sqlite "select platform, count(*) from external_ids group by 1 order by 2 desc;"
github_login|245174
real_name   | 33657
website     | 24355
location    | 17473
x_handle    |  9900
company     |  8028

$ gh api rate_limit --jq '.resources.graphql'
{"limit":5000,"remaining":4775,"used":225}
```

**real_name 3,727 → 33,657 — 9× what the entire REST run achieved in its
lifetime — for 225 rate-limit units.** The equivalent REST work would have cost
~30,000 units, i.e. six hours of waiting on quota alone.

`kind` resolution over the same window: unknown 232,929 → 202,641,
human 40,219 → 57,790+, organisation 8,616 → 18,248.

`location` (17,473) and `company` (8,028) are fields the REST version never
collected at all — they cost nothing extra inside a query already being made.

### Passage summary — measured mid-run

62,000 of 77,540 books summarised, versus the 500 the per-passage builder
managed before crashing. Same segmentation functions, so the counts are
identical to what the 30 GB table would have held.

## Round 12 — 2026-08-04 — full book text, and five attempts at a fair ranking

### Passage summary complete

```
$ python3 build_passage_summary.py --tar txt-files.tar --db passage_summary.sqlite
{
  "books_total": 77539, "passages_represented": 41501325,
  "words_total": 4676260710, "db_bytes": 3907584, "elapsed_s": 789.22
}
```

**77,539 books · 41.5M passages · 4.68 billion words · 3.9 MB · 13 minutes.**
The per-passage equivalent was projected at 30.6 GB and could not fit on the
disk. Integrity checks: zero books with zero passages, 76 with under 100 words.

Loaded:

```
$ python3 load_passage_signal.py --passages passage_summary.sqlite --graph … --apply
{
  "passage_books": 77539, "matched_gids": 72467,
  "edges_to_update": 100757, "distinct_people": 35219,
  "before": {"book_edges_with_text": 606},
  "after":  {"book_edges_with_text": 100757}
}
```

**606 → 100,757 edges; 442 → 35,219 people.** Book text coverage went from 1.25%
of the population to essentially all of it.

```
Dumas, Alexandre        |184 works|18,726,168 words
Scott, Walter           |134|14,884,280
Dickens, Charles        |180|14,787,374
Oliphant, Mrs. (Margaret)|143|13,581,253
Balzac, Honoré de       |153|12,181,891
```

### Five attempts at cross_score, and the arithmetic that settled it

The target is **proportional representation**: github holds 87.3% of the graph
and books 12.6%, so a sound ranking puts ~873 github / ~126 books in the top
1,000. Neither 1000/0 nor 50/50 is "fair" — proportional is. Measured:

| version | breadth treatment | top-1000 result |
|---|---|---|
| v1 | `/ 5` fixed | **997 github** — books cap at 40%, only 2 keys exist |
| v2 | `/ max-in-origin` | **866 BOOKS** — flat +25 domain bonus |
| v3 | percentile, 0 when tied | **993 github** — books axis zeroed entirely |
| v4 | percentile, midpoint ties | **997 github** — books all share one midpoint |
| **v5** | **removed from the score** | **871 gh / 125 bk / 3 reg / 1 yt** |

Every failure traced to one root cause: **`evidence_breadth` measures how well
instrumented a DOMAIN is, not how significant a PERSON is.**

```
$ select origin, evidence_breadth, count(*) from cross_rank group by 1,2;
books |0|   147      github|0| 69899
books |2| 35216      github|1|113153
                     github|2| 41148
                     github|3| 17407
                     github|4|  3365
                     github|5|   199
```

**35,216 of 35,363 book people sit at exactly 2.** The axis is constant there,
so it can only ever act as a domain-level thumb on the scale — in whichever
direction the normalisation happens to push.

v5 drops it from `cross_score` and keeps it as a stored column, because "how
much do we know about this person" is genuinely useful; it is simply not a
component of significance. Ranking now rests on percentile-within-domain, which
means the same thing in every corpus, plus a 10% multi-domain bonus.

```
$ top 1000:  github|871  books|125  registry|3  youtube|1
  expected:  github 873  books 126  registry 0.5 youtube 0.2
$ top 5000:  github|4361 books|635  registry|3  youtube|1
```

Within a couple of people of proportional, and all four domains present.

```
Jensen Huang       |registry|96.7      Shakespeare, William|books |93.3
Andrej Karpathy    |registry|96.0      CodeCrafters        |github|93.3
Fireship           |github  |95.8      react               |github|93.3
Simon Willison     |registry|95.4      Widger, David       |books |93.3
Fireship           |youtube |93.3      The Algorithms      |github|93.3
```

**Tie handling also fixed along the way.** Both percentile axes used ordinal
position, which spread github's 69,899 people tied at rank_score 0 across a
0–28 range purely by sort order — array-position noise presented as signal.
Both now assign the midpoint of the tie block.


### Identity stitch — retested at 172× the sample, still zero

The original "the stitch is dead" verdict was reached with 172 resolved real
names. That is a small sample to kill an idea on, so it was retested once the
GraphQL enrich had produced enough names to be decisive:

```
$ plausible human real names (2+ words, no punctuation, <40 chars): 29672
$ exact case-insensitive matches against book-origin person names:      0
```

**Zero matches against 29,672 names**, versus 851 names at the first test. The
conclusion is unchanged but now rests on evidence rather than an early sample:
Gutenberg is a public-domain corpus (20,246 book people died pre-1950, at most
419 could be alive) and GitHub is live accounts. They are genuinely different
people, not the same people under different names.

This also retires the last remaining justification for the enrich grind as a
*stitch* enabler. Its value is `kind` resolution and contact fields, which it is
delivering — 232,929 → 184,208 unknowns so far.


### #19 — geography and affiliation (`pipelines/github/load_geo_affiliation.py`)

The GraphQL enrich collects two fields REST never did, and nothing consumed
them. As raw strings they are barely queryable:

```
San Francisco, CA|410      Google |142
San Francisco    |362      @google| 57
Beijing, China   |319      Microsoft|97
Beijing          |317
```

```
$ python3 load_geo_affiliation.py --graph people_v2.sqlite --apply
{
  "location_raw": 32208, "location_kept": 31376, "country_rollups": 6557,
  "company_raw": 15107, "company_kept": 14877, "topic_rows": 52810,
  "before": {"geo": 0, "org": 0},
  "after":  {"geo": 37933, "org": 14877}
}
```

Two new queryable dimensions:

```
$ -- gh_family='AI / Machine Learning Core' AND geo='berlin'
ahmedeltaher | Abdul Fatir | Serhii Potapov | Eduardo Lacerda | Bo Liu

$ -- orgs ranked by average rated value of their people's work
igalia|5 people|68.9      photoroom|6|65.7
cursor|5|65.9             cornell university|7|64.7
cmu  |8|65.9              atlassian|13|63.8
```

Normalisation is deliberately conservative — lowercase, strip `@`, drop a small
explicit noise list (`remote`, `earth`, `freelance`), and map high-frequency
aliases observed in THIS data. It does **not** geocode: "Bay Area" is not
resolved, and unrecognised values pass through normalised-but-unmapped rather
than guessed. A country roll-up is emitted only where the string names a country
or carries a known city→country mapping. **A wrong geography is worse than a
missing one.** Raw strings stay untouched in external_ids.

Idempotent: `37933 / 14877` → unchanged.

---

## Session state — checkpoint

**Loaders shipped (13, all verified idempotent):** repo value, awesome signal,
activity, adoption, topic bridge, momentum, passages, legal lane, family topics,
book edges, youtube hosts, cross-domain rank, geo/affiliation. Plus the GraphQL
enricher replacing the REST one.

**Working copy:** `/tmp/people_v2_gh.sqlite` on the mini. Canonical
`~/foundry-data/domains/people/people.sqlite` never written (C3).
Backup: `/tmp/people_v2_gh.PRE-ENRICH-20260803-174831.sqlite`.

**Still running:** `enrich_owners_graphql.py` — kind unknown 232,929 → ~184,000
and falling. Monitor armed (task bqz2qqf5i).

**Open, not started:** per-gid book subjects (needed for "what is THIS book
about"); a contemporary corpus (the real unlock for cross-domain identity);
capping the enrich to top-N owners by value rather than the full 245k.

### Refresh pass — derived layers picked up the enrich's later output

The GraphQL enrich kept running after the geo/org and cross_rank builds, so both
derived layers were stale. Re-running is the intended workflow (both are
idempotent by value, not by "already done"):

```
external_ids growth since the first geo build:
  real_name 33,657 -> 73,846    location 32,208 -> 43,276
  website   24,355 -> 50,616    company  15,107 -> 20,449
  kind: unknown 232,929 -> 161,678 | human 40,219 -> 89,292 | org 8,616 -> 29,752

$ python3 load_geo_affiliation.py --apply
{"location_kept": 42199, "company_kept": 20124,
 "before": {"geo": 37933, "org": 14877},
 "after":  {"geo": 50893, "org": 20124}}
```

geo 37,933 → 50,893 and org 14,877 → 20,124, confirming the loaders are
correctly incremental rather than merely idempotent.

Normalisation is doing its job — the `Google` / `@google` split is consolidated:

```
google|340   tencent|154   apple   |89
microsoft|248 alibaba|141   facebook|86
bytedance|185 nvidia |98
```

**cross_rank balance held after the rebuild**, which is the real check — a
ranking that drifts as inputs grow would be worthless:

```
github|871  books|125  registry|3  youtube|1     (expected 873 / 126 / 0.5 / 0.2)
```

Identical to the pre-refresh figures, so the percentile design is stable under
population growth.

**Standing follow-up when the enrich finishes:** re-run these two again. Both
take seconds and pick up whatever resolved after this pass.

### CORRECTION — the stitch retest number was stated imprecisely

The entry above reports "0 exact matches against book-origin people" from
29,672 names. That number is real but it describes the **filtered** population,
and the entry does not say so clearly enough.

Two tests were run and they measure different things:

```
filtered   (2+ words, no punctuation, <40 chars) -> 29,672 names -> 0 matches
unfiltered (every real_name value)               -> all names    -> 9 matches
```

Both are correct. The 9 come from single-word or punctuated values, which is the
same class as the round-1 false positives (`Gildas` matching a 6th-century monk,
`Parallax` matching a 19th-century pseudonym) — a modern GitHub handle colliding
with a historical mononym, not the same person.

**The conclusion is unchanged: there is no usable github↔book identity stitch.**
But "0" was the filtered figure presented without its qualifier, and the honest
statement is "0 among plausible human names, 9 unfiltered and all of them
handle-collisions". Recorded because a bare "0" in a log invites someone later
to trust a stronger claim than the evidence supports.

Also noted: this join is slow enough to time out repeatedly because
`lower(person.name)` cannot use the `ix_person_name` index — the same
function-on-indexed-column trap that made the first topic-bridge build 600×
too slow. It is worth a generated column if identity matching is ever revisited.

### The 9 unfiltered matches, resolved by inspection

Rather than assume the unfiltered matches were collisions, they were pulled and
read. Every one is a **single-word first name** colliding with a historical
mononym:

```
('Horace',   'Horace',   -66, -9)      <- the Roman poet, d. 8 BCE
('Timur',    'Timur',    1336, 1405)
('Gildas',   'Gildas',    516,  570)
('Florian',  'Florian',  1755, 1794)
('Casey',    'Casey',    1864, 1932)
('Parallax', 'Parallax', 1816, 1884)
('Pansy',    'Pansy',    1841, 1930)
('saki',     'Saki',     1870, 1916)
('ariel',    'Ariel',    1799, 1883)
('maria',    'Maria',    1846, 1916)
('Levi',     'Levi',     1844, 1911)
('Vera',     'Vera',     1865, None)
```

A GitHub user whose profile name is "Horace" is not the poet who died in 8 BCE.
**Zero of the unfiltered matches are real identity links** — the collision
hypothesis is now confirmed by reading the rows, not inferred from their shape.

### Two incidental findings

**`lower(col)` defeats the index — again.** This join timed out repeatedly
because `ix_person_name` cannot serve `lower(person.name)`. Adding
`CREATE INDEX ix_pname_lower ON person(lower(name))` made it return instantly.
Same trap as the first topic-bridge build (600× slower). Third occurrence in
this log; it is a systemic pattern in this schema, not bad luck.

**Do not `cp` a live WAL database.** A plain `cp` of `people_v2_gh.sqlite` while
the enrich held it produced `database disk image is malformed` — the `-wal` file
carries committed data the main file does not yet have. `sqlite3.Connection.backup()`
against a `mode=ro` source copies correctly under concurrent writes. The source
graph was never at risk; only the bad copy was. Recorded because the failure
looks alarming and is trivially avoidable.

### #20 — expression indexes on `lower(col)` (`core/add_lower_indexes.sql`)

`lower(col)` defeating the index bit this pipeline **three separate times**
before the pattern was recognised as systemic rather than unlucky:

1. `build_topic_bridge.py` — 1,638 queries, each a full scan of ~2M rows at
   ~0.25s. Still running after 15 minutes; the set-based rewrite made it 1.33s.
2. The identity-stitch join on `lower(person.name)` — timed out repeatedly at
   120s, returned instantly once an expression index existed.
3. Every loader's `known` dict: 245k rows pulled into Python purely because
   per-row `lower(login)` lookups would have been unusably slow. That workaround
   exists *because of* this missing index.

An audit confirmed no expression index existed anywhere in the schema — all 17
were plain case-sensitive indexes.

**Measured before and after on a real 951 MB snapshot:**

```
                     before      after
topic lookup        1.532 s  ->  0.000 s
extid login lookup  0.135 s  ->  0.000 s
person-name join    0.331 s  ->  0.112 s   (was >120 s TIMEOUT with no index at all)
```

Migration cost: **6.5 seconds to build, 127 MB of disk** (951 MB → 1,078 MB).

The name join is the headline: the same query that timed out at 120 s before any
lower-index existed now returns in 0.112 s. The topic and extid lookups drop to
under a millisecond — these are the predicates every cross-scheme and every
login-resolution query in the pipeline uses.

Additive and re-runnable (`IF NOT EXISTS`); adding an index changes no data and
no query results, only the plan. Applied to the working copy, not the canonical
DB (C3).

**Worth generalising:** an index on `col` does NOT serve `lower(col)`. If a
codebase joins case-insensitively anywhere, it needs expression indexes, and the
absence shows up as "this query is mysteriously slow" rather than as an error.

### Migration applied to the working graph (not just benchmarked)

The benchmark above ran on a snapshot. Applying to the live working copy is the
step that matters, and it initially FAILED because the `sqlite3` CLI does not
wait on a lock:

```
$ sqlite3 /tmp/people_v2_gh.sqlite < core/add_lower_indexes.sql
Runtime error near line 55: database is locked (5)
Runtime error near line 60: database is locked (5)
Runtime error near line 63: database is locked (5)
```

Re-applied through a connection with `busy_timeout=3600000` so it queues behind
the running enrich instead of failing:

```
3.7s ix_person_name_lower
0.4s ix_extid_value_lower
1.3s ix_ptopic_topic_lower
0.5s ix_pc_ref_lower
DONE
```

**5.9 seconds total, applied cleanly alongside a live writer.** Verified on the
working graph rather than the snapshot:

```
topic lookup  0.001s  -> 630
extid login   0.000s  -> 1
name join     0.173s  -> 28 rows
```

Matches the snapshot figures. **Lesson: benchmarking a migration on a throwaway
copy proves the plan, not the deployment.** The perf claim was briefly reported
as live when only the snapshot had it.

### Stitch finding re-confirmed at a larger sample

The name join now returns more rows than when it was first inspected, because
the enrich keeps resolving names. Re-checked rather than assumed:

```
distinct_matches 16
multi_word (potential REAL links): 0

Alain|1868-1951      Horace|-66 to -9     Pansy|1841-1930
Aragon|1897-1982     Levi|1844-1911       Parallax|1816-1884
Ariel|1799-1883      Casey|1864-1932      Timur|1336-1405
Evangeline|1806-1877 Florian|1755-1794    Vera|1865
Gildas|516-570       maria|1846-1916      saki|1870-1916
```

**Zero multi-word matches at any sample size tested** (851 names → 29,672 →
current). Every match is a single-word mononym collision. The conclusion is now
robust to population growth, which is a stronger claim than the original
single-sample verdict.

## Round 13 — 2026-08-04 — promoted out of /tmp, and the query surface works

### The graph was in /tmp the entire session

Every loader in this log wrote to `/tmp/people_v2_gh.sqlite` on a machine where
`/tmp` is not durable. Twelve rounds of enrichment sat on a volume that a reboot
clears. Promoted:

```
promoted 2.2s person=280722 content=564579 topic=2450492 extid=550965 bytes=1083887616
-> ~/foundry-data/domains/people/people_v2.sqlite
```

**Copied with `Connection.backup()`, not `cp`** — there was a **1.8 GB WAL file**
beside the 938 MB main file, and a plain copy would have silently dropped every
write in it (the same trap that produced `database disk image is malformed`
earlier). Swapped into place with `os.replace()` so a canonical file is never
observed half-written.

The pre-existing `people.sqlite` (471 people, a v1 relic) is untouched beside it.

### /tmp cleanup — classified by reading, not by filename

Two files there were **not mine** and predated this session. They were preserved,
not deleted:

```
books.sqlite      181 MB, 79,071 books   -> ~/foundry-data/domains/books/
people_v2.sqlite   35,834 people         -> _snapshots/people_v2.books-only.sqlite
```

Also preserved: the PRE-ENRICH baseline (the rollback point) and
`passage_summary.sqlite` (13 minutes to rebuild).

Only then were redundant copies removed, and redundancy was **proven by row
count first**:

```
promoted (canonical)  280722 people / 564579 edges / 2450492 topics
snap_stitch           280722 people / 564579 edges   <- exact duplicate
bench                 280722 people / 564579 edges   <- exact duplicate
people_graph_snapshot 280708 people / 564486 edges   <- superseded state
stitch_test           280708 people / 564486 edges   <- superseded state
```

3.3 GB reclaimed.

### A silent wrong-source bug in `core/ask.py`

`ask.py` already existed and already looked for `people_v2.sqlite` — so the
query surface did not need building, only pointing at real data. But its
`CANDIDATES` list put a **bare relative filename ahead of the canonical path**:

```
"people": ["people_v2.sqlite", "~/foundry-data/domains/people/people_v2.sqlite", ...]
```

Measured consequence, same command, same machine, same minute:

```
from /tmp     -> /tmp/people_v2.sqlite                       (35,834 people)
from ~        -> ~/foundry-data/.../people_v2.sqlite         (280,722 people)
```

**The file it found in /tmp was not junk, which is what makes this dangerous.**
Reading its contents shows an earlier checkpoint of this same graph — books
35,363 and registry 140 identical to the promoted copy, but github 297 against
245,171, i.e. the state before the GitHub owner load. A plausible, structurally
valid, 245,000-people-missing answer is the worst failure mode available,
because it looks exactly like a correct one.

Fixed by ordering canonical paths first and the bare filename last (still
honoured, so local-copy workflows survive; it just cannot shadow the promoted
DB by accident). Verified cwd-independent:

```
from /tmp     -> …/foundry-data/domains/people/people_v2.sqlite (280722 people)
from ~        -> …/foundry-data/domains/people/people_v2.sqlite (280722 people)
from /        -> …/foundry-data/domains/people/people_v2.sqlite (280722 people)
```

### The query surface, working

```
$ ask.py --who "Karpathy"
andrej-karpathy | produced: github 52, youtube_video 4
  topics: AI / Machine Learning Core, llm-inference-runtime, nlp-text-library,
          autonomous-agent-tool, ml-inference-model, Blockchain / Web3

$ ask.py --who "Spinoza"
bk:spinoza, benedictus de|1632-1677 | lived 1632-1677 | produced: book 13
  topics: Ethics, Free thought -- Early works to 1800, Philosophy and religion…
```

Thirteen enrichment layers are reachable through one command.

### Found, not fixed: duplicate person records

`--who Spinoza` returns TWO people — `baruch-spinoza` (registry, **0 edges**) and
`bk:spinoza, benedictus de|1632-1677` (books, 13 edges). Same human, two
person_ids, no link between them. `--who Karpathy` shows the merged case working
correctly (registry id carrying both github and youtube edges), so the mechanism
exists and simply was not applied to the registry↔books pair.

The schema has `person.merged_into` and an empty `identity_claim` table designed
for exactly this. Registry people are hand-curated and few (140), so this is a
small, bounded, high-precision matching job — unlike the github↔books stitch,
which is measured dead. **Recorded, not attempted**, since it is a new piece of
work rather than a fix to something shipped.

### #21 — registry identity claims (`pipelines/link_registry_identities.py`)

The duplicate-person problem found via `ask.py` in the previous round, addressed
for the population where it is tractable. 113 of 140 hand-curated registry
people had no output attached:

```
$ select count(*) total, sum(person_id in (select person_id from person_content))
  from person where origin='registry';
140|27
```

**Why this works where the book stitch does not.** The github↔books stitch is
measured dead across three sample sizes — Gutenberg is a public-domain corpus of
dead people. The registry is the opposite population: living technologists,
exactly the people who have GitHub accounts. Measured:

```
match via github real_name : 6
match via book name        : 0
```

Applied — 5 confident, 1 ambiguous, 107 no-match:

```
claim_id|person_a      |person_b        |confidence|status
1|andrew-ng      |gh:andrewyng    |0.9|proposed
2|gh:t3dotgg     |theo-browne     |0.9|proposed
3|gh:rauchg      |guillermo-rauch |0.9|proposed
4|gh:gwern       |gwern-branwen   |0.9|proposed
5|adam-smith     |gh:ScriptSmith  |0.4|proposed
6|ben-thompson   |gh:tbenthompson |0.9|proposed
```

**Nothing is merged.** Every row is `status='proposed'`; confidence carries how
sure the matcher is, status carries whether a human agreed. Collapsing the two
is how a 0.9 guess silently becomes a merge, and `merged_into` being
non-destructive only helps if the bad merge was a decision someone *made*.

**Ambiguity is the normal case, not an edge case.** "Adam Smith" matched three
logins (`gh:adchsm`, `gh:ScriptSmith`, `gh:adamsmith`) and is also plausibly the
18th-century economist rather than any GitHub user. A loader taking the first
candidate would have asserted that the author of *The Wealth of Nations*
maintains a JavaScript library — the same class of error as the mononym
collisions on the books side. It is stored at confidence 0.4 with every
candidate listed in `evidence`.

### A bug caught by the idempotency check itself

First `--apply` wrote 6 claims. Re-running produced **12**:

```
=== IDEMPOTENCY ===
{"identity_claims": 12, "proposed": 12}
```

`INSERT OR IGNORE` cannot dedupe this table: `claim_id` is an autoincrement
PRIMARY KEY, so every row is unique by construction, and `CHECK (person_a <
person_b)` gives canonical ordering but no uniqueness constraint. Fixed by
reading existing pairs and inserting only new ones — which also means a claim a
human has moved off `proposed` is never overwritten by a re-run.

The 6 duplicates were removed targeting exactly those rows
(`delete where claim_id not in (select min(claim_id) ... group by person_a,
person_b)`), keeping the earliest claim per pair. Re-verified:

```
re-run 1: {"already_claimed": 6, "after": {"identity_claims": 6}}
re-run 2: {"already_claimed": 6, "after": {"identity_claims": 6}}
```

Worth noting the idempotency check has now earned its place twice: it is the
only reason this bug was found before the table filled with duplicates.

### Split-brain, caused by promoting while a writer was live

Promoting the graph mid-session created two diverging copies, because the enrich
kept writing to `/tmp` while the promoted snapshot received the identity claims:

```
WORKING (/tmp, live enrich)  kind_unknown=106189 real_name=124242 claims=0
PROMOTED (~/foundry-data)    kind_unknown=122608 real_name=109409 claims=6
```

**Neither copy was complete.** `/tmp` held 14,833 more resolved names; the
promoted copy held the only identity claims. This is precisely the failure the
schema's single-writer law exists to prevent, and I created it by snapshotting a
live database rather than moving the writer first.

Resolved by stopping the `/tmp` writer (by exact PID), merging its newer
enrichment into the promoted copy, and resuming the enrich against the canonical
path so there is one writer again:

```
external_ids 550965 -> 591161 (+40196)
kind_unknown 122608 -> 106189 (-16419)
claims preserved: 6
```

The merge is deliberately asymmetric on `kind`:

```sql
UPDATE person SET kind = (SELECT w2.kind FROM w.person w2 WHERE ...)
WHERE kind='unknown' AND EXISTS (... AND w2.kind != 'unknown')
```

**It only ever moves a person AWAY from 'unknown'.** A symmetric "newer wins"
merge would let the stale copy overwrite a resolved kind with `unknown` — losing
work in the direction that looks like success. `external_ids` needed no such
care: its PK `(person_id, platform, value)` makes `INSERT OR IGNORE` naturally
additive.

**Lesson: promote a database by moving its writer, not by copying it.** The
copy is the easy half; the writer is what makes the copy authoritative. Every
subsequent run now targets `~/foundry-data/domains/people/people_v2.sqlite`.

### An observability gap I built, and the four rounds it cost

After resuming the enrich against the canonical DB, it looked dead:

```
19:39:10 unknown=106189 extid=591161
19:39:50 unknown=106189 extid=591161
19:40:30 unknown=106189 extid=591161   <- flat across 80s
$ ls -la /tmp/gql_canonical.out
0 bytes                                 <- empty log
```

A running process, an empty log, and frozen counts is exactly the silent-no-op
signature flagged three times earlier in this session, so it was diagnosed
rather than assumed fine. It took four separate checks to establish the truth:

1. process alive, 1m35s elapsed
2. `gql_used=42` — so calls WERE being made
3. a 250-owner dry run resolved 239 — so resolution worked
4. finally, correlating both over a longer window:

```
20:41:52 gql_used=107 unknown=106189
20:42:42 gql_used=124 unknown=106189
monitor:          unknown=105506   <- it WAS progressing
```

**The job was healthy the whole time.** Writes land only every 2,000 people, so
any sample shorter than the flush interval shows frozen counts while the API
budget drains — indistinguishable from a job that is spinning uselessly.

That ambiguity is a design flaw I introduced: the loader printed nothing until
completion. Fixed with a per-batch progress line:

```
batch 1 | resolved 93 | users 93 orgs 0 | null 7 | cost 1
batch 2 | resolved 189 | users 189 orgs 0 | null 11 | cost 2
batch 3 | resolved 239 | users 239 orgs 0 | null 11 | cost 3
```

The running job was NOT restarted to pick this up — it is making progress and a
restart would discard completed work for a logging improvement.

**Generalisable: "is it working?" must be answerable by reading one line.** If
establishing liveness requires correlating an external rate-limit counter
against database row counts over a multi-minute window, the job is
under-instrumented — and the cost is paid every single time someone checks.

### /tmp fully cleared, durable set verified

With the writer moved to the canonical path, the working copy could finally be
removed. Supersession was **proven by content before deleting**, not assumed
from the promotion having happened:

```
/tmp working : person=280722 content=564579 topic=2450492 extid=591161 unknown=106189 claims=0
CANONICAL    : person=280722 content=564579 topic=2450492 extid=622754 unknown= 93177 claims=6
```

Canonical matches on people/edges/topics and **exceeds on every axis that moved**
— +31,593 external_ids, 13,012 fewer unknowns, and the only identity claims. The
/tmp copy held nothing unique.

One orphan found while checking: a benchmark process of mine from 29 minutes
earlier still held the file read-only, stuck on an unindexed join writing to
`/tmp/bench.sqlite` — a file already deleted. Stopped by exact PID.

**Final durable layout** (nothing of value in a temp location):

```
~/foundry-data/domains/people/
  people_v2.sqlite                     1.10 GB  <- canonical, single writer
  people.sqlite                          28 MB  <- v1 relic, 471 people, untouched
  _snapshots/
    people_v2_gh.PRE-ENRICH-…sqlite     584 MB  <- rollback point
    people_v2.books-only.sqlite          81 MB  <- pre-existing, not mine
~/foundry-data/domains/books/
  books.sqlite                          182 MB  <- pre-existing, not mine
  passage_summary.sqlite                3.9 MB  <- 77,539 books, 13 min to rebuild
```

`/tmp` now contains zero databases. Across both cleanup passes ~5.3 GB was
reclaimed, and every file removed was first shown redundant by row count against
a durable copy.

### Second refresh — derived layers against the enlarged population

The enrich has now classified a large majority of the GitHub population:

```
unknown=93177  human=142258  org=45287  real_name=135909
remaining candidates: 106044
```

Refreshed the derived layers against it:

```
geo 50,893 -> 98,706        (+94%)
org 20,124 -> 39,729        (+97%)
registry claims: 6 -> 6     (already_claimed: 6 — idempotency fix confirmed in production)
```

**cross_rank balance held EXACTLY** while its inputs nearly doubled:

```
github|871  books|125  registry|3  youtube|1   (expected 873 / 126 / 0.5 / 0.2)
```

Identical to both previous builds. This is the strongest available evidence that
the percentile design is sound rather than tuned to one snapshot — a ranking
whose domain mix drifted as the population grew would have been silently
overfitted to the data it was built on.

The org layer roughly doubled with it:

```
google|616   tencent|290
microsoft|479 alibaba|235
bytedance|314 nvidia|181
```

(google was 340 at the previous refresh.)

### A query returning "no data" when the graph held 457 rows

Testing `ask.py`'s other modes (only `--who` had been exercised) found
`--contemporaries Spinoza` returning an empty list. The view was fine; the
resolution was not:

```
$ select person_id, name, birth_year from person where name like '%Spinoza%' limit 3;
baruch-spinoza                     |Baruch Spinoza        |          <- no birth year
bk:spinoza, benedictus de|1632-1677|Spinoza, Benedictus de|1632
gh:rmax                            |R Max Espinoza        |          <- substring hit

$ select count(*) from v_contemporaries where person_id='bk:spinoza, benedictus de|1632-1677';
457
```

The query used `WHERE name LIKE ? LIMIT 1`, which picked the **registry
duplicate with no dates** — so the graph knew 457 contemporaries and reported
none. An empty result that reads as "we have no data" but means "you asked the
wrong duplicate" is the same failure class as the cwd-shadowed database
resolution: plausible, silent, and wrong.

Fixed by ordering candidates so people who can answer the question come first
(`ORDER BY (birth_year IS NULL), length(name)`), without excluding the undated —
a genuinely dateless person still resolves and correctly returns nothing. The
response now also carries `resolved_to`, so the disambiguation is visible rather
than silent:

```
$ ask.py --contemporaries "Spinoza"
resolved_to: bk:spinoza, benedictus de|1632-1677
  Chiabrera, Gabriello  1632-1638
  Holland, Philemon     1632-1637

$ ask.py --contemporaries "Plato"
resolved_to: plato
  Sophocles  -428--407
```

Plato's result confirms the BCE handling works end to end — negative birth years
survive the view, the join and the formatter, which the schema explicitly
designed for ("so antiquity participates instead of silently dropping out").

`--about` needed no fix: `cryptography` correctly returns `jedisct1` (libsodium)
at the top, ahead of google and cloudflare.

**This is the second bug found by simply exercising a query surface rather than
assuming it worked.** Both were invisible from the data side — the tables were
correct and every count was right; only the questions were being answered wrong.

### All five query modes exercised

Having found two bugs by testing rather than assuming, the remaining modes were
run against the canonical graph:

```
$ ask.py --works "Dumas"
person: Dumas, Alexandre (bk:dumas, alexandre|1802-1870) | count: 184
  book 18321 "Acté" -> https://www.gutenberg.org/ebooks/18321.txt.utf-8
     (direct plaintext, no auth, no local copy needed)

$ ask.py --works "Torvalds"
person: Linus Torvalds (gh:torvalds) | count: 9
  github torvalds/pesconvert "Brother PES file converter" -> github.com/...
```

`--works` resolves across both domains and emits fetch routes, so an answer is
actionable rather than just a reference.

**The count of 9 for Torvalds was checked rather than assumed suspicious** — it
is correct. Nine non-fork repos, with the important one present and rated:

```
torvalds/linux     |237311 stars|value 100
torvalds/AudioNoise|  4384|50
torvalds/uemacs    |  2055|35
torvalds/GuitarPedal| 2027|65
```

Status of the five modes: `--who` ✓, `--about` ✓, `--works` ✓,
`--inventory` ✓, `--contemporaries` ✓ (after the fix above). Two of five were
broken when first exercised; both bugs were in resolution, not data.

### Third resolution bug — `--who` returned the empty duplicate first

After fixing `--contemporaries`, the same class of flaw was looked for rather
than waited for. `--works` turned out to be **written correctly by design** —
line 237 takes `max(matches)` by content count, with a comment naming the exact
duplicate problem. So the original author knew about it; `--contemporaries` just
never received the same treatment.

`--who` had not either. It returned matches in index order:

```
baruch-spinoza                        produced={}          <- FIRST, zero edges
bk:spinoza, benedictus de|1632-1677   produced={book: 13}  <- the actual Spinoza
gh:rmax                               produced={github: 3}
gh:luisespinoza, gh:jecovier, ...     produced={github: 1} each
```

Any caller taking `matches[0]` got an empty person — precisely the trap that
made `--contemporaries` report nothing while 457 rows existed. Fixed by sorting
on evidence count once, in `who()`, rather than leaving each consumer to
rediscover it:

```
bk:spinoza, benedictus de|1632-1677   {book: 13}   <- now first
gh:rmax                               {github: 3}
...
baruch-spinoza                        {}           <- now last
```

Regression-checked: `--works Spinoza` still 13, `--works Torvalds` still 9.

**Three resolution bugs, one root cause.** The graph contains duplicate person
records (registry vs books, registry vs github), and every code path that picks
"a person" by name must decide which duplicate it means. `works()` decided
correctly, `who()` and `contemporaries()` did not. The data was never wrong —
row counts, topic counts and edge counts were all correct throughout — and no
amount of verifying them would have surfaced any of this.

The durable fix is the `identity_claim` work: 6 proposed links exist, and
accepting them would collapse the duplicates so no consumer has to choose. Until
a human adjudicates those, evidence-ordering is the correct defensive behaviour.

## Round 14 — 2026-08-04 — external source survey, and a correction about our own population

No loader ran this round. The mini was unreachable (tailnet is 100.64.0.x; ssh
config points at 100.66.34.21; 100% packet loss), so this is measurement and
staging only. Everything below is re-derived from source, not carried over.

### CORRECTION — the graph is not missing people; it has a star floor

An earlier claim in this session — that ~370k crawled owners "were never loaded"
— was wrong in framing. Measured against repo_card:

```
$ sqlite3 identity.sqlite "select case when stars is null then 'null'
    when stars>=100 then '100+' when stars>=10 then '10-99' else 'under10' end b,
    count(distinct lower(substr(full_name,1,instr(full_name,'/')-1)))
    from repo_card where instr(full_name,'/')>0 group by 1;"
10-99|496482
100+|245166
null|1052
under10|277
```

The graph holds 245,175 github people. Owners with a 100+ star repo: 245,166.
**A 9-person match.** The loader ran with a 100-star floor and did exactly that.
Nothing was dropped by accident.

Duplicate check — the count is clean, not case-inflated:

```
$ raw distinct owner:      614868
$ lower(distinct) owner:   614801
```

67 case-duplicates across 614k. So the real open question is not "who did we
lose" but "does the 10-99 band (496,482 owners) belong in the graph at all".
That is a judgement call, and the evidence cuts both ways: a star floor is a
reasonable noise gate, but this graph's own headline finding is that stars are
a bad proxy (yargs/yargs-parser: 517 stars, 4,384,968 dependent repos). A
low-star owner whose crate half of Rust depends on is exactly who a star floor
hides. NOT ACTIONED — recorded as an open decision.

### External sources surveyed (all counts measured, not estimated)

Wikidata, via the live SPARQL endpoint. NOTE: the first four use COUNT(*) over
statements, so a person with two employers counts twice — treat as upper bounds.
The last two use COUNT(DISTINCT ?p) and are exact.

```
humans with employer (P108):          2382217   [statement count]
humans with ORCID (P496):             2060228   [statement count]
humans with award (P166):             1753750   [statement count]
humans with doctoral advisor (P184):   399750   [statement count]
humans with GitHub username (P2037):    11124   [statement count]
DISTINCT humans with X handle (P2002):  249428
DISTINCT humans with Google Scholar:    124112
```

Cross-cut, the single most valuable number found:

```
humans with BOTH GitHub username and ORCID:  6824
```

The graph currently has 3 people spanning more than one domain. This is a
pre-built set of ~6,824 verified multi-domain humans requiring no name matching
— the exact thing the Round 1 negative result proved we cannot manufacture
ourselves (github<->book name join returned literally zero).

P106 occupation and P214 VIAF both TIMEOUT at the 60s endpoint — too large to
count live. They need the dump, which is itself a finding.

### crates.io — join surface measured against our own corpus

```
$ distinct owners of Rust repos:                     19657
$ Rust repos already carrying a rated overall_value:  6863
```

crates.io's own dump README confirms the join is native, not inferred:
"teams.login - this will look something like `github:foo:bar`" and "as we only
support GitHub, the first component will always be `github`". It also carries
crate_owners.owner_kind (0=user, 1=team), which maps directly onto the schema's
human/organisation distinction — classification for free rather than another
238k people sitting at kind='unknown'.

Dump verified live: 1,669,443,386 bytes, last-modified 2026-08-04T02:11:26Z,
rebuilt daily. Read its README via a 12MB HTTP range request rather than
downloading 1.67GB.

### Licenses — two settled, two not

- Stack Exchange: CC BY-SA 4.0, and Users.xml does carry WebsiteUrl. USABLE.
- MusicBrainz: 2,949,792 artists, core data CC0. (Deprioritised by owner —
  music artists are out of scope.)
- crates.io: dump README states no license. Data described as "public
  information in the crates.io database". Repo license is MIT/Apache and covers
  CODE ONLY. NOT DETERMINED.
- Open Library: no named license. Internet Archive "does not assert any new
  copyright" but grants nothing explicitly. NOT DETERMINED.

Both NOT DETERMINED cases are fine for internal graph use; the exposure is
republication.

### Staged, not run — three loaders written this round

All follow the house pattern, all compile, none has run. Verified by reading the
code, not by trusting the author:

- pipelines/crates/load_crates_maintainers.py
- pipelines/wikidata/load_wikidata_identities.py
- pipelines/wikidata/load_person_person.py

Checked against the traps this log has already documented: zero `LIKE '%key%'`
counters in any of the three (the Round 4 bug that matched repos NAMED velocity);
no silent person creation, unmatched records become identity_claim proposals;
birth/death years written only WHERE the column IS NULL, with BCE negatives
preserved; busy_timeout=600000 on all three.

person_person is the first person<->person table in the graph:

```
person_a, person_b, relation, direction, confidence, source, observed_at, meta_json
PRIMARY KEY (person_a, person_b, relation)
CHECK (person_a <> person_b)
```

Direction is a first-class column, not flattened — advisor and student are
opposite claims, the same reasoning that kept book roles on the edge. The
composite primary key gives idempotency structurally. This is the table Round 4
wanted and correctly refused to build from 720,107,620 naive co-membership pairs;
Wikidata's 399,750 advisor edges are a legitimate source for it.

### Open design question — organisations are second-class

person.kind already allows 'organisation', and 870 book authors are flagged as
institutions. But orgs currently live inside the person table, which is why
`microsoft`, `google` and `apache` appear in rated-value leaderboards beside
Jensen Huang. Wikidata's 2.38M employer statements are person->organisation
edges — a second entity type, not an enrichment. Splitting orgs into their own
table (or at minimum giving them proper employer edges) is unresolved and
blocks nothing yet, but every "who does the best work" query is currently
answering across two different kinds of thing.

### Not in the Great Library

The people graph is not registered as a Work. SISO Foundry is, with a Release,
but a 280,708-person / 2,450,492-topic-row graph has no public identity, no
stable URL, and no record of decisions like the star floor. Worth registering.

## Round 15 — 2026-08-04 — crates.io loaded; a fifth domain

Worked on a copy pulled from the PUBLISHED release, not the mini:
`gh release download graph-v1 --repo sisodias/siso-people-graph` -> 220MB gz ->
688MB sqlite. The release-asset backup pattern works end to end; the mini was
not needed. NOTE the published v1 is a Round-12 snapshot and lags the mini:

```
                published v1   live on mini    delta
person              280708        280722         +14
person_content      564486        564579         +93
external_ids        253815        845004    +591189
person_topic       2050629       2555047    +504418
```

A graph-v2 release is owed once this round's loaders have run.

### #22 — crates.io maintainers (pipelines/crates/load_crates_maintainers.py)

crates.io is where Rust code is CONSUMED, as opposed to GitHub where it is
written. Same people, different act, and the consumption side carries real
install counts rather than star proxies.

Join quality is the best of any source surveyed: 69,169 crates.io users,
**69,169 with a gh_login — 100%**. No name matching at any point.

```
$ python3 load_crates_maintainers.py --dump <dump>/data --graph work.sqlite --apply
{"owners_seen": 350847, "matched_to_graph": 87079,
 "unmatched_proposed_claim": 249959, "edges_inserted": 87079,
 "after": {"crates_edges": 87079, "crates_io_external_ids": 9815}}
```

Independently re-derived (not the loader's counters):

```
$ sqlite3 work.sqlite "select domain,count(distinct person_id),count(*)
    from person_content group by 1 order by 3 desc;"
github|245175|463230
book|35366|101124
crates|9815|87079      <- new
youtube_video|24|97
youtube_channel|35|35
```

### THREE BUGS SHIPPED IN THE FIRST RUN, all found by running not reading

1. **csv.field_size_limit** — crates.csv embeds full READMEs; the stdlib 131072
   default raised `_csv.Error: field larger than field limit`. Fixed at import.

2. **Wrong column name, and it failed SILENTLY at zero.** The loader read
   `crate_user_id`/`user_id`. The real 2026-08-04 header is
   `crate_id,created_at,created_by,owner_id,owner_kind`. Neither name existed, so
   every row hit `continue` and the run reported a clean
   `matched_to_graph: 0` with no error. Verified the join was fine in isolation
   (9,872 direct matches) BEFORE touching the loader, which is what localised it
   to the column read rather than the lookup. A loader that returns 0 and exits 0
   is the most dangerous shape there is.

3. **owner_kind was being ignored.** 0=user, 1=team. Teams are organisations;
   minting them as humans is the error the schema's kind field exists to prevent.
   Now skipped explicitly — see the open item below.

### KNOWN DEFECTS in this load — do not treat as finished

- `crate_downloads.csv` (310,628 rows) NEVER LOADED. `crates_downloads_known: 0`.
  This is the strongest signal in the dump — real installs, not stars — and it is
  the whole reason the source is interesting. Must be wired before graph-v2.
- `meta_json` carries a dead `crate_count_so_far: null` key on every edge. Same
  class as the Round 8 `subjects` smear: a key that asserts nothing.
- identity_claim reported 58,509 proposed but `select count(*) from
  identity_claim` = 0. Nothing was written. Either the insert is wrong or the
  table shape differs; unresolved.

### The company gap, now concrete

`owner_kind=1` rows are being skipped entirely, so team-owned crates are dropped.
teams.csv holds 1,559 rows with github_id, login and org_id — GitHub org
identity, already resolved. Combined with Wikidata's 2.38M employer statements,
that is a companies entity with two independent sources and nowhere to live.
Today organisations sit inside `person` with kind='organisation', which is why
microsoft/google/apache rank beside Jensen Huang in every value query.

### Other corpora staged on the laptop, not yet loaded

- Wikidata: 6,824 people with BOTH github login and ORCID; 271,423 advisor edges.
- Open Library wikidata dump: author biography at exceptional density —
  VIAF 100%, birth 99%, ISNI 98%, **occupation 98%**, death 92%, citizenship 88%,
  birthplace 86%. Occupation TIMED OUT on the live SPARQL endpoint; it is
  trivially available here. Parse note: fields are TAB-split with TWO tabs, the
  JSON is CSV-escaped (doubled quotes), and the claims live under `statements`,
  NOT `claims` (newer REST shape). Three wrong guesses before that landed, each
  silently returning zero rather than erroring.

### #23 — crate artifact signal by REPOSITORY URL (pipelines/crates/load_crate_repo_signal.py)

The maintainer loader (#22) joins crates.io USERS to people. It cannot answer
"is the repo we already rated actually installed by anyone", because a
person-level join never touches the repo. 83% of crates declare a `repository`
and 78% of those point at github.com — a direct artifact join onto the same
content_ref the whole github domain is already keyed on. This was overlooked for
the entire first pass; the dump is fundamentally about artifacts and the
artifact-level joins match more than the person-level ones.

Measured against the full crawl before writing any loader:

```
$ crates scanned                     310,628
$ crate->repo matched our crawl       53,193
$ of which already rated              24,517
```

Applied to the graph (which holds only the 100+ star subset, hence the smaller
number — 7,336 of the 53,193 matches are people we actually have):

```
{"crates_scanned": 310628, "crates_with_github_repo": 142737,
 "repos_matched_in_graph": 7336, "edges_updated": 7348, "monorepo_repos": 26283,
 "before": {"edges_with_crate_downloads": 0},
 "after":  {"edges_with_crate_downloads": 7348}}
```

Independently re-derived with json_extract, not the loader's counters:

```
$ sqlite3 work.sqlite "select count(*) from person_content where domain='github'
    and json_extract(meta_json,'$.crate_downloads') is not null;"
7348
```

**THE PAYOFF — real installs against stars.** This is the yargs-parser inversion
computed on ground truth rather than inferred from dependent-repo estimates:

```
dtolnay/unicode-ident       110 stars   1,196,577,185 downloads
cuviper/autocfg             115         1,141,284,077
dtolnay/itoa                375         1,171,767,764
rust-random/getrandom       547         1,708,411,468
withoutboats/heck           591         1,140,782,656
rust-lang/cfg-if            637         1,266,601,671
marshallpierce/rust-base64  723         1,395,121,509
dtolnay/proc-macro2         922         1,419,083,078
```

110 stars and 1.2 BILLION downloads. These are load-bearing infrastructure for
every Rust build on earth, and a star-ranked graph files them below a toy.
dtolnay appears four times in the top twelve — Round 1 already surfaced him by
rated value; this is the harder, measured version of the same claim.

One crate per repo is kept (most-downloaded), with crate_count_at_repo recorded
alongside — 26,283 repos publish more than one crate and writing N conflicting
rows onto one edge, or silently taking the first, would both be wrong.
`score` is never touched: stars stay stars, because merging a vote with a
measurement destroys the comparison that makes either interesting.

### Why load_crates_maintainers.py reported crates_downloads_known: 0

Its docstring claimed downloads live in `crates.csv`. They do not — that header
is created_at,description,documentation,homepage,id,max_features,
max_upload_size,name,readme,repository,trustpub_only,updated_at. Downloads live
in a SEPARATE crate_downloads.csv (310,628 rows) which that loader never opens.
Third wrong-assumption-about-the-dump bug in one session, all of the same shape:
the code was consistent with a dump that does not exist. #23 reads the real file.

### Still open on the crates domain

- version_downloads.csv is a DAILY TIME SERIES spanning ~90 days (849 MB).
  Round 4's momentum signal used three consecutive days and was honestly labelled
  "a momentary reading, not a trend". This is 30x that window and unloaded.
- published_by is present on 92% of versions with 33,826 distinct publishers in a
  400k sample — who actually shipped each release, as distinct from who owns the
  crate. Per-release authorship exists nowhere else in the graph.
- yanked (5,826 versions) is a NEGATIVE quality signal — work the author
  withdrew. The graph has no other source for "the maintainer retracted this".
- teams.csv (1,559 rows: github_id, login, org_id) is skipped entirely by the
  owner_kind=0 filter. That is the company graph, with GitHub org identity
  already resolved, sitting unused.

## Round 16 — 2026-08-04 — organisations become an entity; the crates domain deepened

### #24 — ORGANISATIONS as a first-class entity (pipelines/crates/load_organisations.py)

The long-standing modelling error: organisations lived INSIDE `person` with
kind='organisation', which is why microsoft, google and apache rank beside
Jensen Huang in every rated-value query. An organisation is not a person with a
flag — it has members, it outlives them, and it cannot author anything itself.

crates.io teams is the right seed because org identity is RESOLVED, not guessed:
`teams.login` has the shape `github:ORG:team`, so the GitHub organisation name is
embedded. And 13,809 crate-ownership rows carry owner_kind=1, which
load_crates_maintainers.py drops entirely rather than mint a team as a human.

Three new tables: `organisation`, `person_organisation` (person<->org with
relation, direction and date range, so Wikidata employment and crates team
membership can share one shape), `organisation_content` (org -> artifact).

```
{"teams_seen": 1559, "organisations_new": 1131, "team_owned_crates": 13809,
 "org_content_edges": 13809, "unparsable_team_logins": 0,
 "after": {"organisations": 1131, "organisation_content": 13533}}
```

Verified — real companies, correctly attributed rather than lost:

```
awslabs|385   paritytech|375   azure|328   rustcrypto|256
materializeinc|233  googleapis|224  rusoto|221  tailscale|195
```

No organisation is merged with an existing kind='organisation' person row. That
merge is an identity claim and belongs under human review — the same law that
stops two different "John Murray" rows becoming one person.

### #25 — download MOMENTUM from the real series (load_crate_momentum.py)

Round 4's star velocity was three consecutive days and was labelled honestly as
"a momentary reading, not a trend". version_downloads.csv is a DAILY series:

```
{"series_days": 92, "window_start": "2026-05-05", "window_end": "2026-08-04",
 "crates_with_series": 589792, "repos_matched": 7336, "edges_updated": 7348,
 "trend_omitted_no_baseline": 74,
 "after": {"edges_with_dl_recent": 7348, "edges_with_dl_trend": 7274}}
```

30x the window. `dl_trend` is recent-half/earlier-half and is OMITTED (not set to
infinity) for the 74 crates with no earlier baseline — a crate that did not exist
yet has no trend, and writing one would be a lie dressed as a number.

**Question unlocked — who is RISING, over a real window:**

```
knurling-rs/defmt          1187 stars  trend 6.117  8,024,121 recent dl
Ogeon/palette               824        2.571        3,074,798
yegor256/micromap           207        2.139        2,365,585
PyO3/pyo3-async-runtimes    190        1.875        2,384,881
```

### #26 — publishing ACTS and withdrawn work (load_publisher_signal.py)

Every other edge in the graph says "is associated with". `published_by` says
"this person cut this release, on this date" — the closest thing to a
contribution record in the dump, present on 92% of versions.

```
{"publisher_crate_pairs": 325003, "edges_matched": 77070,
 "total_releases_attributed": 720772, "total_yanks_attributed": 23288,
 "after": {"edges_with_releases": 77070, "edges_with_yanked": 77070}}
```

720,772 releases attributed to actual humans. And `yanked` (23,288 attributed) is
the graph's FIRST NEGATIVE signal — every other one is positive (stars, ratings,
downloads, citations). A yank is the author's own judgement that their work was
broken.

`yank_rate` is written only where releases >= 5 (below that, one yank out of one
release reads as 100% and means nothing) and is deliberately NOT folded into
score or rank_score: yanking a broken release is RESPONSIBLE, so treating it as a
demerit would invert its meaning.

### DEFECT FOUND IN #22 — content_ref holds a bare crate id

The publisher loader first matched ZERO of 325,003 pairs. Cause, found by looking
at the edges rather than guessing:

```
$ sqlite3 work.sqlite "select person_id, content_ref from person_content
    where domain='crates' limit 5;"
gh:reem|13
gh:reem|14
```

load_crates_maintainers.py wrote the raw crate_id into content_ref instead of the
crate name. `13` is an opaque pointer that means nothing without the dump in
hand, and it broke the join for every downstream loader. Mitigated here by keying
on the id and carrying `crate_name` into meta_json; content_ref itself is left
alone because rewriting a key column is a migration, not a signal load. OPEN.

### Crates domain state after this round

| signal | edges |
|---|---|
| maintainer edges (#22) | 87,079 |
| crate downloads on github edges (#23) | 7,348 |
| download trend, 92-day (#25) | 7,274 |
| releases published (#26) | 77,070 |
| releases yanked (#26) | 77,070 |
| org -> crate edges (#24) | 13,533 |

### #27 — Wikidata external identities (pipelines/wikidata/load_wikidata_csv_identities.py)

Pulled via the SPARQL query service as CSV rather than the ~100GB entity dump.
The graph needs a thin slice — which of OUR people carry which identifiers — and
the query service answers that in seconds.

```
{"rows_read": 17987, "matched_people": 2078, "unmatched_rows": 15088,
 "ids_new": 3342,
 "before": {"x_handle": 1663, "google_scholar": 0, "orcid": 0, "wikidata": 0},
 "after":  {"x_handle": 2730, "google_scholar": 664, "orcid": 806, "wikidata": 805}}
```

806 ORCIDs against the 807 predicted by the pre-load overlap check — the
measurement held.

**Question unlocked — three-domain humans.** People with a published ORCID AND
github repos AND shipped crates, which the graph could not express at all:

```
althonos    | orcid | 6 gh repos | 36 crates
jcreinhold  | orcid | 1          | 36
niklasf     | orcid | 3          | 15
RalfJung    | orcid | 2          | 11
```

Round 1 measured THREE people spanning more than one domain in the entire graph.

### THE OVERLAP LAW — stated because it cost real time this session

A source's headline size says NOTHING about its value to this graph. Only the
overlap with our population does, and that is a two-line query. Measured:

| source | headline | actually usable here |
|---|---|---|
| Wikidata advisor edges | 271,423 | **5** |
| Wikidata github+ORCID people | 6,824 | **807** |
| crates.io users | 69,169 | 19,768 matched crawl / 9,872 in graph |

The advisor collapse is the same structural fact Round 1 proved for the
github<->book name stitch: Wikidata's advisor graph is academics and historical
figures, our github population is living developers. Populations that do not
overlap cannot be joined by any method. The staged pipelines/wikidata/
load_person_person.py is therefore CORRECT IN DESIGN and WRONG IN SOURCE — the
person_person table is still the right structure, but Wikidata advisors will not
fill it. Do not run it against that CSV.

RULE: run the overlap query BEFORE writing the loader, not after.

### #28 — ADMISSION ON EVIDENCE OF USE (pipelines/crates/promote_crates_people.py)

The star floor, finally addressed — not by lowering it, but by replacing the
criterion.

Why not lower it. The floor is baked into the WHOLE pipeline, not just the
people loader:

```
$ sqlite3 identity.sqlite "select case when stars>=100 then '100+'
    when stars>=10 then '10-99' else 'under10' end band, count(*),
    sum(overall_value is not null) rated from repo_card
    left join repo_category using(full_name) group by 1;"
100+   |478907|226963     (47.4% rated)
10-99  |893266|     0     (0.0%)
under10|   277|     0     (0.0%)
```

The rating pass never looked below 100 stars. Admitting that band wholesale
would grow the graph 3.6x and make it THINNER — 893k people with no quality
signal of any kind. A worse graph, not a bigger one.

The rule used instead: **admit on external evidence of use.** A crates.io
publisher is vouched for by download counts measured by a third party — strictly
better evidence than a star count, and it does not require our rating pass to
have run.

```
{"candidates": 68324, "already_in_graph": 9815, "people_created": 58509,
 "edges_created": 249959, "ext_ids_created": 175527,
 "before": {"people_total": 280708, "people_tracked": 113, "crates_edges": 87079},
 "after":  {"people_total": 339217, "people_tracked": 58622, "crates_edges": 337038}}
```

**280,708 -> 339,217 people (+21%).** They enter as state='tracked', the schema's
own provision for "we care, nothing linked yet" (written for the 9,395 registry
people like Andrew Ng with zero content edges). kind stays 'unknown' rather than
guessed — crates.io accounts include bots and org accounts, and the honest null
is what person.kind exists to preserve.

**WHO THE FLOOR WAS HIDING** — newly admitted, ranked by measured downloads:

```
Artyom Pavlov (RustCrypto) | 216 crates | 10,720,459,743 downloads
Ed Page (clap)             | 138        | 10,576,029,291
Diggory Hardy              |  38        |  6,865,212,847
Jacob Pratt (time)         |  19        |  3,725,783,643
Josh Triplett              |  24        |  3,458,183,075
Alice Ryhl (Tokio)         |  57        |  3,156,187,336
```

Core Rust infrastructure maintainers — billions of downloads each — absent from
a 280k-person graph because their repos carry under 100 stars. This validates
the promotion rule better than any argument could.

### Schema trap hit on the way

`person` does NOT share person_content's provenance columns. Its real shape is
(person_id,name,sort_name,kind,state,merged_into,birth_year,death_year,
primary_tier,rank_score,origin,topics_json,built_at) — provenance is
`origin`/`built_at`, not `source`/`observed_at`. Assuming symmetry across tables
raised `sqlite3.OperationalError: table person has no column named source`.
Read PRAGMA table_info before writing INSERTs, not after.

## Round 17 — 2026-08-04 — the graph becomes relational

### #29 — person_person from CRATE DEPENDENCIES (load_person_dependency.py)

Third attempt at the hardest table in the graph, and the first that works.

```
Round 4   naive co-membership on shared gh_category  -> 720,107,620 pairs, REJECTED
Round 14  Wikidata doctoral advisors (P184)          -> 271,423 available, FIVE usable
Round 17  crate dependency edges                     -> 1,272,495 edges
```

Why this source and not the others: a dependency is not an inferred affinity, it
is a DECLARED technical fact. A's software does not build without B's. The
maintainer wrote it, the package manager machine-checks it, and it has a
direction that means something. Round 4 said person-person needed "shared RARE
category, co-citation, or genuine co-contribution, which this data does not
have". This data has it.

```
{"dependency_rows": 32243556, "runtime_rows": 27847334,
 "skipped_non_runtime": 4396222, "self_edges_dropped": 7351980,
 "pairs_distinct": 1272495,
 "after": {"person_person_total": 1272495, "depends_on_edges": 1272495}}
```

kind is NOT flattened: only kind=0 (runtime) loads. 4,396,222 dev and build rows
were skipped — "I test with your thing" is a different claim from "my thing
breaks without yours", and merging them repeats the book-roles error where a
volunteer editor became the second most prolific author in history.

**Question unlocked — WHO IS LOAD-BEARING.** Not who is famous, not who is rated
well, not even whose artifact is downloaded most. Whose disappearance breaks the
most other people's software:

```
person           dependents  evidence rows
dtolnay              45037       5,442,954
rust-lang-owner      29243       1,676,743
carllerche           25999       2,552,317
kbknapp              23661         471,623
Darksonn             22771       1,277,452
huonw                21728         967,336
seanmonstar          21051       1,159,392
BurntSushi           20447         758,206
```

Darksonn (Alice Ryhl, Tokio) was NOT IN THE GRAPH before round #28 admitted her
on download evidence — 22,771 people depend on her work and a 100-star floor
made her invisible. The promotion rule and the dependency layer validate each
other.

`weight` is evidence count, not importance: dtolnay at 5.4M means the relation is
heavily attested, not that anyone owes him 5.4M favours.

### FOUR NEW SOURCE TYPES found by asking a better question

The session kept asking "what other datasets exist". The better question was
"what other KINDS OF EDGE exist". Every signal loaded before today was metadata
ABOUT AN ARTIFACT. These are relations between PEOPLE, and the graph had zero:

1. **Crate dependencies** — loaded above. 1.27M edges.
2. **GitHub Sponsors** — VERIFIED reachable with existing auth:
   `gh api graphql` on dtolnay returns sponsorshipsAsMaintainer totalCount=122.
   A funding edge. Nobody sponsors by accident; it is "this person's work
   matters enough that I pay for it", which outranks a star, a rating and a
   download as a statement of value. The graph has NO economic layer at all.
3. **GitHub org membership** — VERIFIED: organization(login:"tokio-rs")
   membersWithRole totalCount=29 with logins. This is person_organisation
   populated DIRECTLY rather than inferred from crates team-name parsing.
4. **Repo contributors** — VERIFIED: `gh api repos/tokio-rs/tokio/contributors`
   returns 30. Genuine co-contribution, the exact thing Round 4 said the data
   did not have.

**AND THE GENERALISATION.** GitHub's own dependency graph API works with current
auth:

```
$ gh api graphql -f query='{ repository(owner:"tokio-rs", name:"tokio")
    { dependencyGraphManifests(first:1) { totalCount } } }'
{"data":{"repository":{"dependencyGraphManifests":{"totalCount":20}}}}
```

The dependency insight is NOT Rust-specific. It applies to npm, PyPI, Maven, Go
— every ecosystem on GitHub. crates.io was the proof of concept for a method,
not a one-off source.

### CORRECTIONS to earlier claims in this session

- **Open Library's author dump is THIN, contrary to my earlier enthusiasm.**
  remote_ids appears on 2% of author records (929 of 40,001 sampled). The 98%
  occupation / 100% VIAF density measured earlier was in their *Wikidata* dump,
  a different population. It is not a pre-built Gutenberg->Wikidata bridge.
- **npm replication is dead.** https://replicate.npmjs.com/registry returns
  "Not Found". The survey worker marked it UNVERIFIED and was right.
