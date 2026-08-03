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

