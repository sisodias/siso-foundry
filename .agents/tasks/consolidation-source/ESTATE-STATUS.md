# SISO estate — where every project stands (2026-08-07)

Derived by reading contents, not filenames. All four repos cloned locally.

## 1. Repo inventory — the work allocated 2026-08-06/07

| repo | unique lines | branches w/ commits | open PRs | merged ever |
|---|---:|---:|---:|---:|
| siso-people-graph | 37,242 | 9 | 9 | **0** |
| great-library-of-siso | 16,552 | 20 | 8 | 0 (1 old PR#1) |
| siso-foundry | 15,384 | 2 | **0** | 0 |
| siso-book-library | 9,493 | 4 | 3 | 0 |
| **total** | **78,671** | **35** | **20** | **0** |

siso-librarian: 286 commits since Aug 1, straight to main, no branches, no PRs.
Separate lineage — the only repo where work actually landed.

## 2. Lane delivery — the honest count

13 lanes designed (parallel-slam pack). Delivered properly: **8**.

| lane | branch | status |
|---|---|---|
| 1 GL registry spine | gls/people-graph-parallel-spine | DELIVERED 26 commits |
| 2 red-team | pg/red-team-fixtures | DELIVERED 4,804 lines, 16 findings |
| 3 v3 ontology | pg/v3-ontology-schema | DELIVERED 6,687 lines, 26/26 tests |
| 4 identity | pg/identity-resolution-parallel | DELIVERED 3,505 lines, 15 tests |
| 5 reproducible builds | — | **NEVER PUSHED** |
| 6 query surface | — | **NEVER PUSHED** |
| 7 book integrity | books/integrity-export-…-3 | DELIVERED 5,378 lines, 13 tests |
| 8 source research | gls/people-graph-source-research | DELIVERED 39 sources |
| 9 scholarly pilot | pg/scholarly-authority-pilot | **BRANCH EXISTS, 0 LINES** |
| 10 software/AI pilot | pg/software-ai-pilot | DELIVERED 4,655 lines, 18 tests |
| 11 creators/media | pg/living-creators-media-pilot | DELIVERED 5,876 lines, 18 tests |
| 12 claims/temporal | pg/claims-temporal-relations | **165 lines, WRONG CONTENT** (2 CI files vs declared claims/**, projections/**) |
| 13 integration contract | pg/parallel-integration-contract | DELIVERED 4,712 lines, 27 tests |

Plus 4 unlaunched-lane artifacts: GL audit-record, GL first-principles program,
PG 100x dossier, PG+BL first-principles audits.

## 3. The two P0s nobody can fix with what shipped

- **PG-AUDIT-004 / PGRT-001** clean-checkout build broken (schema path
  loaders/ vs schema/). Owner = Lane 5. Never pushed.
- **PG-AUDIT-002 / PGRT-004** accepted identity claims inert — ask.py never
  reads identity_claim. Owner = Lane 6. Never pushed.

BOTH have complete specs in TWO independent versions (v0 Prompts 4+5;
parallel-slam Prompts 5+6). Executable, not re-derivable. Cheapest high-value work.

## 4. What is genuinely finished and mergeable now

- GL control-plane spine (ADR-0005, Works, Releases, V37, GQ-010) — additive
  schema only, touches no immutable record, ships `npm run verify`.
- Red-team suite — tests/docs only, zero production code.
- v3 schema — 6,687 lines beside v2, zero v2 edits.
- Identity v3 — closes PGRT-003/009/011 by construction.
- Book Library -3 — retires direct graph mutation (`--apply` fails closed).
- Three source pilots — all offline, all emitting pg-observation-0.1.
- Integration harness — validators + 13-lane registry + merge-risk analyzer.
- Foundry crates-and-relational-layer — the enrichment log + crates/wikidata
  pipelines. NO PR EVER OPENED.

## 5. Zero file-path conflicts

Verified across PG PRs #1–#8: no exact-path overlaps. Only shared directory is
docs/handoffs/, and every lane writes a differently-named file there.
The exclusive-path-ownership design held.

## 6. Repo topology decision

GL branch content is 66% `research/` (10,964 of 16,552 lines) — including
working code with tests (target_manager.py 463 + 183 test, verify_module.py 334).
GL README: "a catalog, not a giant monorepo". ADR-0005 rejected storing the PG
database for the same reason.

**Split into 3 new repos, each registered back as a GL Work with a
source_repository locator (the People Graph / Book Library pattern):**
1. `siso-unsolveable-mathematics` ← cut from `agent/erdos-09-23` (contains all
   11 other erdos branches; verified by merge-base ancestry). Delete the 11.
2. `siso-stargate-library` ← remote-viewing + psychoenergetics (forked at
   c9e4876, trivially reunited). The module's own HANDOFF already specifies a
   9-step promotion to an independent Work, and psychoenergetics explicitly
   avoided "pretending that a separate siso-stargate-library repository already
   exists" — i.e. this repo was already the intended destination.
3. `siso-declassified-records` ← DGR department (1 commit, 2,067 lines).

GL then keeps ~2,300 lines of actual control-plane records on one main.

## 7. Proposed repo architecture (per Shaan, modelled on oracle-streaming)

```
<repo>/
  .agents/           agent infrastructure: runs, tasks, prompts, lane registry
    scratchpad/      temporary agent writes (NOT /tmp, NOT memory files)
  .docs/             HTML docs (agent+machine artifacts per house style)
  registry/          GL only — Works/Releases/Decisions/Events/Snapshots
  schemas/
  scripts/
  site/              generated only
```
The prompt packs, lane_registry.json, swarm-status, and run records all belong
under `.agents/`. Charters/models/audits belong under `.docs/`.

## 8. Three competing lane numbering schemes — pick ONE before merging
v0 Prompts 0–12 | parallel-slam Prompts 1–13 (launched) | PG agent-program
Lanes 00–12. "Lane 5" means three different things. Mis-merge hazard.

## 9. Data-integrity item before merging the spine
registry/works/siso-people-graph.json cites person=339,217 /
person_person=1,272,495 / org=1,131 as `integration_check` with verified:true.
TWO independent audits state they never verified these: PG first-principles
("Published row counts are therefore treated as repository claims, not
independently re-counted observations") and the red-team ("No production SQLite
assets were opened. Dataset-wide counts and collision rates are therefore not
claimed"). Amend the evidence summary while the branch is still unmerged.

## 10. Missing convergence step
v0 Prompt 12 was a cross-repo adversarial RELEASE GATE (8 gates, incl. "run
Prompt 1's original failure fixtures and prove the selected P0s are resolved",
"do not paper over a red gate"). The parallel redesign dropped it for Prompt 13's
launch-time harness. Nobody owns final convergence. Spec survives — reuse it.
