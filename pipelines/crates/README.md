# Foundry crates.io Loader

`load_crates_maintainers.py` ingests the official crates.io DB dump
(https://static.crates.io/db-dump.tar.gz) into the people graph. The dump
expands to a directory of CSV files; this loader reads `users.csv`,
`crates.csv`, and `crate_owners.csv`.

## What it does

For each `crate_owners` row:

1. Resolves the crates.io user to a `person_id` by looking up their
   `gh_login` in `external_ids(platform='github_login')` -- the same join
   key `load_owners_into_people_graph.py` already used.
2. Writes one `person_content` row per `(person, crate)` pair with
   `domain='crates'`, `source='crates_io'`, `role='owner'`, and
   `observed_at=<crate updated_at>`. Per-edge facts (downloads,
   description, homepage, repository, max_version) are written under
   `meta_json` rather than overwriting `score`.
3. Writes one `external_ids` row, `platform='crates_io'`,
   `value=<crates.io user id>`. The numeric id is a stable identifier
   even when a user later changes their gh_login.
4. Crates.io users with NO matching `gh:<login>` in the graph are NOT
   silently created. An `identity_claim` row is written with
   `method='shared_external_id'` and `confidence=0.6` so a downstream
   matcher or human can decide. The count is reported in the summary.

`score` is never overwritten. Re-runs are idempotent: every write uses
`INSERT OR IGNORE` on the relevant primary key.

## Usage

```bash
# 1. Download and extract once (out of band):
#    curl -O https://static.crates.io/db-dump.tar.gz
#    mkdir -p ~/SISO_Foundry_Data/crates && tar -xzf db-dump.tar.gz \
#        -C ~/SISO_Foundry_Data/crates
#
# 2. Dry-run first to see what would change:
python3 load_crates_maintainers.py \
  --dump ~/SISO_Foundry_Data/crates \
  --graph ~/SISO_Foundry_Data/people_v2.sqlite
#
# 3. Re-run with --apply once the dry-run summary looks right:
python3 load_crates_maintainers.py \
  --dump ~/SISO_Foundry_Data/crates \
  --graph ~/SISO_Foundry_Data/people_v2.sqlite \
  --apply
```

Optional `--limit N` caps the number of matched owners processed, for
smoke-testing against a partial extract.

## CSV columns assumed (verify against the real dump)

The loader was written from the published schema
(https://github.com/rust-lang/crates.io/blob/master/src/boot.rs). The
following column names should be checked against an actual extract
before the first real run; the dump schema has shifted across releases:

- `users.csv`: `id`, `gh_login` (may be empty for crates-only accounts)
- `crates.csv`: `name`, `updated_at`, `downloads`, `description`,
  `homepage`, `repository`, `max_version`, `max_stable_version`
- `crate_owners.csv`: column name for the user foreign key has been
  `crate_user_id` in recent dumps and `user_id` in older ones; both are
  accepted via a fallback in the loader.

## Output

A JSON summary is printed to stdout, including matched/unmatched
counts, edges inserted, and `before`/`after` counters computed with
`json_extract` (NOT `LIKE`, to avoid matching meta_json values that
merely contain the substring).
