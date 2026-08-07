# pipelines/wikidata

Two loaders that ingest Wikidata into the people graph. Both follow the house
pattern in `../crates/load_crates_maintainers.py`: argparse, `--apply` vs dry-run,
before/after counters via `json_extract`, busy_timeout=600000, single-writer
graph, idempotent on re-run.

## load_wikidata_identities.py

Ingest Wikidata human records into `external_ids`. Each input record becomes
one `wikidata` row plus one row per P-property the record carries:

| Property | platform            | confidence |
|----------|---------------------|------------|
| P2037    | github_login        | 0.9        |
| P496     | orcid               | 0.9        |
| P2002    | x_handle            | 0.9        |
| P1960    | google_scholar      | 0.9        |
| P214     | viaf                | 1.0        |
| P213     | isni                | 1.0        |
| P2963    | goodreads           | 0.9        |

Authority identifiers (VIAF, ISNI, Wikidata) are 1.0; self-asserted platforms
are 0.9, matching the schema's law that only `shared_external_id` and
`authority_file` justify auto-acceptance.

Matching: a record whose P2037 (GitHub login) matches an existing `gh:<login>`
person is attached to that person. Otherwise an `identity_claim` is proposed
(method=`authority_file`, confidence=0.95) -- the loader NEVER mints a new
person silently. P569 / P570 write `birth_year` / `death_year` only where the
field is currently NULL; BCE negative years survive.

```
python3 load_wikidata_identities.py --wikidata records.jsonl --graph people_v2.sqlite [--apply]
```

## load_person_person.py

Create and populate a NEW `person_person` table from Wikidata relations:

| Property | relation          | direction                       |
|----------|-------------------|---------------------------------|
| P184     | doctoral_advisor  | subject_has_advisor             |
| P802     | student           | subject_has_student             |
| P1066    | student_of        | subject_studied_under           |
| P737     | influenced_by     | subject_was_influenced_by       |

Direction is recorded explicitly -- P184 is asymmetric (X has advisor Y) and
flattening it to undirected would be the same kind of role-flattening the
schema's header comment railed against for `role` on `person_content`.

The table is created on first run, guarded with `IF NOT EXISTS`, with the
same provenance columns (`source`, `observed_at`) as `person_content`.
Edges whose target QID does not resolve to an existing `person_id` are
DROPPED and counted in the summary -- this loader does not mint people.

```
python3 load_person_person.py --wikidata relations.jsonl --graph people_v2.sqlite [--apply]
```

## Input format (both)

JSONL: one JSON object per line. Each object carries `qid` (Wikidata QID as a
string, e.g. `"Q868"`) and any subset of the P-keys listed above as either
plain values (`"P2037": "torvalds"`) or wrapped (`"P2037": {"value": "..."}`).
For relations, the value of each P-key is the other person's QID.

The caller extracts from Wikidata; this loader does not download anything.
The target DB lives on another machine and is unreachable from here -- both
scripts are correct-by-construction and must be smoke-tested on a local
graph before the first `--apply`.
