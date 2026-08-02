# Agency repository economic valuation

Status: specification and calibration plan

Observed: 2026-08-03

Currency: GBP

Owner: SISO Foundry as evidence owner; SISO Agency OS product owner remains to be registered

## Purpose

Foundry currently answers what source exists, what business capability it may support, and how feasible an adoption route appears. It does not yet answer the commercial question:

> What can SISO save, sell, or compound because this source exists?

This document defines the economic layer required to turn source discovery into an investment and productization system. Foundry should become a capital-allocation engine for SISO Agency OS, not merely a repository catalog.

The model must never convert stars, source volume, or a qualitative score directly into a precise monetary claim. Every monetary result is a low/base/high range with assumptions, evidence date, confidence, rights state, and an explicit next proof.

## The stable economic unit

Repositories do not have one universal price. The stable economic unit extends the existing value-matrix contract:

```text
repository
  × capability or use case
  × client archetype
  × adoption route
  × commercial offer
```

The same source can have materially different value as:

- an internal SISO operating capability;
- a white-labelled client module;
- a managed sidecar service;
- a narrow extracted component;
- an API integration;
- an industry-specific bundle; or
- a source reference that should not be adopted.

Price belongs primarily to the offer. A repository receives source-asset and option value; a client pays for a proven business outcome, deployment, and ongoing service.

## Four values, not one

### 1. Full replacement value

Full replacement value estimates what equivalent production functionality would cost to reproduce.

```text
full_replacement_value =
  estimated_engineer_months × loaded_engineering_cost_per_month
```

Engineer-months should be triangulated from at least two independent estimates:

1. an effective-source-size model such as calibrated COCOMO II after generated, vendor, fixture, example, and duplicated code is excluded; and
2. a functional decomposition covering business domains, user surfaces, data model, permissions, APIs, realtime behavior, collaboration, import/export, migration, tests, observability, deployment, and documentation.

Commit count, stars, repository size, or line count may be evidence inputs. None is a replacement-value formula on its own.

### 2. Captured source value

SISO rarely captures the entire replacement value. The usable source value is risk-adjusted by the fraction of the product we actually need and our ability to operate it.

```text
captured_source_value =
  full_replacement_value
  × relevant_functionality
  × integration_maturity
  × rights_factor
  × maintainability_factor
  × evidence_confidence
```

All multipliers are in the inclusive range 0–1. A zero rights factor makes captured source value zero even when the software is technically excellent. Rights factors are planning priors, not legal conclusions; the recorded rights review is authoritative.

### 3. Client outcome value

```text
annual_client_outcome_value =
  annual_saas_displacement
  + annual_labor_savings
  + annual_attributable_revenue_gain
  + annual_expected_risk_reduction
```

Where:

```text
annual_labor_savings =
  hours_saved_per_month × loaded_hourly_cost × 12
```

Revenue uplift and risk reduction must remain zero until an assumption or observed receipt explains them. The model must not use the same benefit in two terms.

### 4. SISO commercial and portfolio value

```text
three_year_gross_profit_per_deployment =
  implementation_price
  - implementation_delivery_cost
  + 36 × (monthly_managed_fee - monthly_operating_cost)
```

```text
three_year_portfolio_value =
  captured_source_value
  + internal_operating_savings
  + expected_deployments
    × attach_rate
    × three_year_gross_profit_per_deployment
  - remaining_productization_cost
```

```text
repo_investment_roi =
  three_year_portfolio_value ÷ remaining_productization_cost
```

ROI is undefined rather than infinite when remaining productization cost is zero. Portfolio aggregation must deduplicate shared primitives and benefits so a common identity, search, or automation layer is not counted once per module.

## Pricing boundaries

Every offer records three pricing constraints:

```text
price_floor = delivery_cost ÷ (1 - target_gross_margin)
market_anchor = current total cost of the credible alternative
price_ceiling = defensible share of verified client outcome value
```

The chosen price must explain how it relates to all three. The market anchor and client outcome inputs are time-sensitive and must carry an observed date and source receipt.

## Evidence and confidence

The initial planning multipliers are defined in [`economics/model.json`](economics/model.json). They exist to widen or narrow a range; they do not upgrade evidence.

The evidence ladder is:

1. runtime outcome — production cost and outcome receipts;
2. runtime proven — a repeatable behavior or integration proof;
3. host integrated — working inside the SISO host without outcome proof;
4. adversarial confirmed — independently challenged analysis;
5. source read — direct current source review;
6. metadata — repository metadata and indirect evidence;
7. inferred — capability or category inference only.

A metadata or inferred card may be generated for triage, but it must have a wide range, low confidence, and a direct-source-review next gate. It cannot become a client price or adoption authorization.

## Current intelligence defect that must be repaired first

The published 628-project coverage inventory and the existing 20-entry value matrix are separate projections and were not reconciled before v0.5.1.

The value matrix contains four decision-grade repositories missing from the coverage inventory:

- `coollabsio/coolify`
- `surveyjs/survey-library`
- `Open-Source-Legal/OpenContracts`
- `jhpyle/docassemble`

The other sixteen matrix repositories appear in the coverage inventory, but their matrix evidence states were projected as `inferred`. The matrix records eighteen entries at source-read or stronger evidence and two metadata-triaged entries.

The next coverage release must mechanically union all canonical sources and preserve raw evidence states. The expected current union is at least 632 unique repositories. If the matrix's eighteen direct-or-strong entries remain distinct from the published 89 source-read-or-confirmed coverage rows, the reconciled direct-or-strong population should be approximately 107. The generator must calculate and assert these numbers rather than copy them from this document.

No economic leaderboard should be called complete until that reconciliation passes.

## Provisional worked examples

The machine-readable assumptions and calculations are in [`economics/pilot-examples.json`](economics/pilot-examples.json). These examples explain the model; they are not audited valuations, offers, legal conclusions, or revenue forecasts.

| Measure | AFFiNE / SISO Docs | Teable / SISO Tables |
|---|---:|---:|
| Existing strategic priority | 66/100 | 73/100 |
| Full replacement planning range | £1.8m–£4.8m | £1.44m–£3.84m |
| Relevant functionality assumption | 40% | 70% |
| Integration maturity assumption | 65% | 75% |
| Captured source planning range | £194k–£517k | £355k–£947k |
| Remaining hardening assumption | £75k–£200k | £100k–£250k |
| Implementation price assumption | £8k–£25k | £15k–£40k |
| Managed fee assumption | £300–£1.2k/month | £600–£2.5k/month |
| Three-year gross revenue/client | £18.8k–£68.2k | £36.6k–£130k |

AFFiNE is the broader source product, but the current SISO use case consumes a narrower documents and knowledge slice. Teable supplies structured operational authority across CRM, delivery, reporting, and agent actions, so its current SISO-specific captured value and attach rate may be higher despite a smaller full product surface.

The combined offer—structured operations, documents, governed search, automation, SISO identity, audit, approvals, and agents—may have substantially more value than the isolated modules. That bundle value must be modeled as a stack recipe without double-counting shared source value.

## The world-class Agency OS capability gaps

The 12 pillars are useful routing labels but do not yet constitute a complete sellable Agency OS. High-value product capabilities that need explicit offer and source coverage include:

- proposals, quoting, CPQ, SOWs, and change requests;
- client portals, approvals, and creative proofing;
- resource allocation, capacity, utilisation, and project profitability;
- recruiting, contractors, payroll, and skills inventory;
- meeting recording, transcription, decisions, and action extraction;
- lead enrichment, outbound sequencing, calling, and attribution;
- customer success, health scoring, renewals, and expansion;
- website, CMS, landing-page, and digital-asset operations;
- retainer consumption, pricing, entitlements, and margin tracking;
- vendor, procurement, business-continuity, backup, and disaster recovery; and
- white-labelled executive and client reporting.

Many candidate repositories already exist in the coverage inventory. The missing value is direct review, economic modeling, product packaging, integration proof, and outcome evidence.

## SISO-owned leverage layer

Source applications provide domain depth. SISO should own the control plane that makes them one agent-native business system:

- identity, tenancy, permissions, and authority;
- capability discovery and typed actions;
- human approvals and escalation;
- append-only audit and provenance;
- reliable events, retries, dead-letter handling, and replay;
- usage metering, pricing, and entitlements;
- cross-module object contracts and read models;
- global search, knowledge, retention, and export;
- secrets and OAuth authority;
- module installation, upgrades, backup, and rollback;
- agent budgets, limits, observability, and evaluations; and
- outcome measurement that feeds Foundry.

This is likely the highest-value defensible SISO IP. Without it, the portfolio is a collection of applications. With it, Agency OS becomes a safe operating environment in which agents can act across the same business surfaces as humans.

## Required economic artifacts

The target package is:

```text
intelligence/agency/economics/
├── model.json
├── repo-economic-card.schema.json
├── pilot-examples.json
├── repo-value-cards.json       # generated after calibration
├── offer-catalog.json          # generated/curated after calibration
└── stack-recipes/              # tested Agency and industry bundles
```

The runtime implementation should add:

```text
scripts/build_repo_values.py
scripts/check_repo_values.py
```

The verifier must reject:

- a point estimate without low/base/high bounds;
- a monetary value without assumptions and an evidence date;
- a price without a client archetype and commercial offer;
- source value presented as client outcome or SISO revenue;
- metadata-only evidence presented as an adoption authorization;
- missing remaining productization or operating costs;
- negative or impossible margins;
- duplicated shared primitives or client benefits across bundles;
- rights assumptions presented as legal conclusions; and
- market anchors without current receipts.

## Execution sequence

### Phase 0 — reconcile intelligence

1. Add `value-matrix.json` as a canonical input to the coverage generator.
2. Mechanically union exact repository identities and preserve all raw evidence states.
3. Restore the four missing repositories and the sixteen downgraded evidence records.
4. Assert union size, source lineage, evidence precedence, and deterministic output.
5. Publish the correction before claiming comprehensive economic coverage.

### Phase 1 — calibrate the economic model

1. Directly audit the existing 20 value-matrix entries.
2. Record functional scope, effective source size, rights, maintenance, integration maturity, remaining hardening, alternatives, client job, and offer route.
3. Calculate low/base/high replacement and captured values using two independent effort methods.
4. Reconcile estimates with actual SISO integration effort where reliable receipts exist.
5. Adversarially review every high-value card.

### Phase 2 — create the first leaderboard

1. Generate economic cards for the calibrated 20.
2. Rank by three-year portfolio value, remaining productization cost, payback, confidence, strategic control, and agent leverage.
3. Publish ranges and confidence, never false precision.
4. Convert the strongest capabilities into explicit commercial offers.

### Phase 3 — expand safely

1. Generate low-confidence triage cards for the reconciled 632+ universe.
2. Directly review the top 50 by expected value per engineering month.
3. Build General Agency and industry-specific stack recipes.
4. Register the owning Agency OS Work before promoting source candidates into product adoption.

### Phase 4 — close the outcome loop

Every real deployment should record:

- implementation effort and cost;
- subscriptions displaced;
- hours saved;
- revenue created;
- risk reduced;
- operating cost and defects;
- agent actions, approvals, failures, and autonomy;
- user adoption and client willingness to pay; and
- renewal, retention, and expansion.

Those receipts recalibrate future estimates and create the compounding SISO moat.

## Target leaderboard

The Great Library should eventually expose a public-safe economic view with:

| Field | Purpose |
|---|---|
| Repository and exact revision | Identity and reproducibility |
| Capability and client archetype | Economic context |
| Adoption route | Fork, whole app, API, sidecar, extract, reference, or reject |
| Full replacement value | Cost to reproduce equivalent functionality |
| Captured source value | Risk-adjusted usable value to SISO |
| Remaining productization cost | Investment still required |
| Annual client outcome | Low/base/high client benefit |
| Implementation and managed price | Commercial offer |
| Expected deployments and attach rate | Portfolio assumptions |
| Three-year portfolio value and ROI | Investment ranking |
| Evidence confidence and rights state | Claim boundary |
| Next proof | Cheapest evidence that could change the decision |

The desired flywheel is:

```text
GitHub source
  → capability evidence
  → economic valuation
  → productized offer
  → deployment recipe
  → agent-safe integration
  → client outcome receipt
  → updated valuation
  → better next investment
```

That is the path from an impressive source corpus to a world-class, economically intelligent SISO Agency OS.
