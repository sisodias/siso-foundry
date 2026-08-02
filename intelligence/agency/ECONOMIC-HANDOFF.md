# Agency repository economics handoff

Date: 2026-08-03

## Verified state

- Repository: `Lordsisodia/siso-foundry`
- Branch: `main`
- Selected public release before this specification: `v0.5.1` at `b28b0f7`
- Economic specification commit: `b3f6a7a` (`docs: specify Agency repository economics`)
- Verification observed after authoring: `npm test` passed four tests and `FOUNDRY_CHECK_OK (31 Python files)`.
- Economic example recalculation: `ECONOMIC_EXAMPLES_OK` for AFFiNE and Teable.
- Unrelated local state: `core/people_schema.sql` was dirty before this work and must remain untouched unless separately owned.

Read in this order:

1. repository `AGENTS.md`;
2. [`ECONOMIC-VALUATION.md`](ECONOMIC-VALUATION.md);
3. [`economics/model.json`](economics/model.json);
4. [`economics/repo-economic-card.schema.json`](economics/repo-economic-card.schema.json);
5. [`economics/pilot-examples.json`](economics/pilot-examples.json);
6. [`VALUE-MATRIX.md`](VALUE-MATRIX.md) and [`value-matrix.json`](value-matrix.json);
7. [`COVERAGE.md`](COVERAGE.md) and [`coverage-inventory.json`](coverage-inventory.json);
8. [`BACKLOG.md`](BACKLOG.md).

## What was decided

1. Foundry should become the economic and evidence engine for Agency OS investment decisions, not merely a repository search index.
2. The economic unit is `repository × capability × client archetype × adoption route × commercial offer`.
3. Full replacement value, captured source value, client outcome, SISO revenue, gross profit, and portfolio value remain separate.
4. Every monetary result is low/base/high with assumptions, observed date, confidence, rights state, and next proof.
5. Stars, source size, commit count, and forks are evidence inputs only; none is a valuation formula.
6. Product prices attach to offers. Repositories receive source-asset and option value.
7. Stack recipes must deduplicate shared primitives, costs, and client benefits.
8. Metadata and inferred cards are triage only and cannot authorize adoption or client pricing.
9. The provisional AFFiNE and Teable values demonstrate the math; they are not audited valuations or offers.

## Critical defect discovered

The v0.5.1 628-project coverage inventory is not the complete union of Foundry Agency intelligence.

The 20-entry value matrix contains four repositories absent from coverage:

- `coollabsio/coolify`
- `surveyjs/survey-library`
- `Open-Source-Legal/OpenContracts`
- `jhpyle/docassemble`

The remaining sixteen matrix repositories are present in coverage but appear as `inferred`, even though the matrix records stronger evidence. The matrix contains eighteen source-read-or-stronger entries and two metadata-triaged entries.

The expected current union is at least 632 repositories. If mechanical reconciliation confirms no overlap between the published 89 direct coverage rows and those eighteen stronger matrix rows, direct-or-strong coverage should become approximately 107. Calculate this from canonical files; do not copy these numbers into generated output without assertions.

Reproduce the gap with:

```bash
comm -23 \
  <(jq -r '.entries[].repository' intelligence/agency/value-matrix.json | sort -u) \
  <(jq -r '.rows[].repository' intelligence/agency/coverage-inventory.json | sort -u)
```

## Do these in order

### 1. Reconcile coverage before pricing

- Make `value-matrix.json` a canonical input to `scripts/build_agency_coverage.py`.
- Union repository identifiers mechanically with exact owner/repository casing.
- Preserve every raw source evidence state and source reference.
- Define and test one explicit evidence precedence rather than allowing broad capability inference to overwrite stronger evidence.
- Include the four missing projects.
- Assert source counts, union counts, identity equality, evidence preservation, and deterministic regeneration.
- Run `npm run build:agency-coverage` twice and compare hashes.
- Run `npm test`.
- Publish this as a corrective Foundry release before calling the economic universe complete.

### 2. Implement the first economic generator

- Add `scripts/build_repo_values.py` and `scripts/check_repo_values.py`.
- Validate every output against `economics/repo-economic-card.schema.json`.
- Keep model assumptions versioned separately from calculated cards.
- Reject unordered ranges, missing costs, impossible margins, missing evidence dates, and unsupported client prices.
- Generate cards only for the existing 20 value-matrix entries first.

### 3. Audit and calibrate the 20-entry pilot

For each entry, capture:

- exact source revision and relevant functionality;
- functional replacement effort using two independent methods;
- rights route and required review;
- maintenance and security condition;
- integration maturity and actual remaining hardening;
- credible alternative and its time-stamped total cost;
- client archetype, business job, and measurable outcome;
- implementation delivery cost, price, operating cost, and managed fee;
- expected deployments and attach rate; and
- the cheapest next proof that could materially change the valuation.

Adversarially review every high-value card before publication.

### 4. Publish the first leaderboard and offer catalog

- Rank by risk-adjusted three-year portfolio value per remaining engineering month, not stars.
- Publish low/base/high ranges and confidence in Foundry.
- Create initial General Agency stack recipes without double-counting shared capabilities.
- Register the Agency OS product-owning Work before advancing source candidates into product adoption.
- Promote the immutable Foundry release and successor snapshot through the Great Library workflow.

### 5. Expand and learn from outcomes

- Generate explicitly low-confidence triage cards for the reconciled 632+ universe.
- Directly review the top 50.
- Record real implementation cost, SaaS displacement, hours saved, revenue, risk, operating burden, agent behavior, willingness to pay, renewal, and expansion after deployment.
- Recalibrate the model from outcome receipts.

## Do not

- Do not describe the current 628 rows as the complete Foundry project universe.
- Do not manually transcribe repository identifiers or evidence grades.
- Do not convert stars, source volume, or the existing 0–100 strategic score directly into GBP.
- Do not collapse source value, client value, revenue, gross profit, and portfolio value into one number.
- Do not treat the pilot AFFiNE or Teable figures as audited valuations or client prices.
- Do not publish market anchors without current receipts.
- Do not present a rights multiplier as legal advice or reuse authorization.
- Do not price a bundle by summing module values without deduplicating shared primitives and benefits.
- Do not modify, stage, or discard the unrelated `core/people_schema.sql` change.

## External publication note

The authenticated GitHub API reports `Lordsisodia/siso-foundry` as public and the `v0.5.1` Release exists. Logged-out HTTP requests were observed returning `404` for the entire `Lordsisodia` profile. Treat this as an account-level visibility anomaly, not evidence that work is unpushed, and recheck it before relying on anonymous GitHub distribution.

## Continuation prompt

> Continue SISO Foundry Agency repository economics. Read `AGENTS.md`, then `intelligence/agency/ECONOMIC-HANDOFF.md` and `intelligence/agency/ECONOMIC-VALUATION.md`. Start at step 1: reconcile `value-matrix.json` into the coverage generator mechanically, preserve stronger evidence, restore the four missing repositories, add deterministic assertions, and verify twice before implementing valuation generation. Preserve the unrelated `core/people_schema.sql` change.
