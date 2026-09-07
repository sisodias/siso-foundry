# Foundry source audit — 7 September 2026

Scope: a source/ownership-interface review and an isolated foundation repair.
Not a complete line-by-line security audit, live-machine inspection, data-plane
recovery, corpus valuation, product admission or deployment.

## Baseline and evidence discipline

The Foundry baseline is `sisodias/siso-foundry`, branch `main`, commit
`11f459597ce0c67dbfa89deeeafa3202e47dc6d5`. Source files were read through the GitHub
connector. The original `scripts/check.py` was reconstructed for isolated patching
and its complete Git blob SHA matched `cf00f8422eb55b3d239e9855d34914710a14e95d`.
That establishes exact source bytes, not a full baseline test run.

The public source ledger below gives exact observed blobs. Private steering and
handoffs are deliberately not copied here. Existing system owners and unpublished
work remain outside this change. Public sources are referenced, not relicensed.

## Findings and repair scope

| ID | Evidence-backed finding at baseline | This changeset | What remains unproved |
|---|---|---|---|
| F1 | `scripts/check.py` constructs an atlas path from checkout ancestors and reads it before the publication scan | Remove ancestor discovery; retain equality checking in an explicit, bounded external gate; run source safety first | Real atlas availability and consistency |
| F2 | The credential regex uses hyphens after GitHub token prefixes and skips non-UTF-8 files | Add underscore-prefixed token rules, redacted findings and binary ASCII-pattern detection with synthetic tests | Zero secrets or a full privacy/security audit |
| F3 | `core/db.py` interpolates filenames directly into a SQLite URI | Encode filenames with `Path.as_uri()` before `mode=ro`; test reserved characters, rejected writes and absent files | All other historical SQLite callers, actual warehouse health or writer exclusivity |
| F4 | Source scanning traverses the checkout with broad recursive reads | Enumerate Git-tracked/nonignored publication candidates; do not follow symlink targets into evidence | All public distribution surfaces outside this checkout |
| F5 | Root docs mix extracted modules, historical hardware descriptions and operational-sounding claims | Document separate system ownership and source/data/execution gates | Live host, connector, scheduler or deployment acceptance |
| F6 | Database path logic differs across core, pipeline and bank callers | Document the exact divergence; no silent multi-caller migration | Consumer inventory and path-precedence reconciliation |
| F7 | Baseline README describes four matrix projects missing from coverage and sixteen stronger records reduced to `inferred` | Preserve this as documented unresolved evidence debt | Independent rederivation or repair of the coverage/value records |

F1 is directly visible in the source; a clean-checkout failure was previously
documented, but the full baseline `npm test` was not rerun in this audit's partial
sandbox. F2/F3 have synthetic reproductions and regressions. In particular, a fragment
character in a synthetic filename caused the baseline reader to create a different,
writable database: its intended read-only parameter became part of the URI fragment.
The encoded reader opens the intended file, rejects writes and creates no extra file. The new source CI must
supply the full-checkout source result; local focused tests are not that result.

F7 is a **documented baseline claim**, not a fresh computation. The GitHub file
reader returned blob metadata but an empty payload for the large coverage file in
this audit. No complete row-level reconciliation is claimed from that response.
The reviewed valuation/industry records are not rewritten by this repair.

## Public source ledger

All Foundry links below are pinned to the baseline commit.

| Source | Observed blob SHA | What it supports |
|---|---|---|
| [AGENTS.md](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/AGENTS.md) | `c0f914a3506f258a80ed6de691fb78f654c778ac` | Research Work, append-only evidence, data boundaries and local-writer invariant |
| [README.md](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/README.md) | `4f6e481088f77b8c30556901207d46678370817c` | Existing modules and documented evidence debt |
| [ARCHITECTURE.md](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/ARCHITECTURE.md) | `3f738df2b0232d33297b1e98ed10634d85ce02ce` | Identity, append-only observations, separate software/data lifecycles |
| [DATASETS.md](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/DATASETS.md) | `32dec55157806b19ccc166c63fe460edf0d682e8` | External assets and unresolved snapshot-distribution milestone |
| [Dataset manifest](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/datasets/manifest.json) | `8a1a35677a70962d31737e68d9782910cd24937b` | July 30 checkpoint, not current dataset access |
| [Application mission](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/docs/AGENCY_OS_APPLICATION_MISSION.md) | `aa1048a9043fb4fa0a8e9fd0125aacd81470b590` | Demand-first discovery, system boundaries and adoption gates |
| [Source check](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/scripts/check.py) | `cf00f8422eb55b3d239e9855d34914710a14e95d` | F1, F2 and F4 |
| [SQLite helper](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/core/db.py) | `4d5369806b88d692c0bc0254acfded63874f32d5` | F3 and the limits of writer enforcement |
| [Core paths](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/core/paths.py) | `eb84118322e18794457bb764bd6da0452ae956ad` | Core path behavior and historical placement comments |
| [Package commands](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/package.json) | `9955f293c12399823a41082d2b31ab1e79f88834` | Previous single test entry point |

For F6, the additional inspected code-search excerpts are
[pipeline configuration](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/pipelines/github/config.py)
and [bank query defaults](https://github.com/sisodias/siso-foundry/blob/11f459597ce0c67dbfa89deeeafa3202e47dc6d5/packages/bank-api/bank.py).
These were bounded source excerpts, not a complete caller audit.

## Public neighbouring interfaces inspected

| Repository | Observed main commit | README blob | Interface evidence, not an ownership transfer |
|---|---|---|---|
| `sisodias/siso-repo-bank` | `2d7d35ecbf7e1158d0a3527e1489040687ac214b` | `a348f0ffb50d661850dd1e917e3cdf69f39da41e` | Separately maintained derived indexes; query a handful then read upstream |
| `sisodias/siso-evidence-engines` | `71022ce4b1e00ea3ad9d6ab9bb75060d34730b0d` | `a08d8d07d47973d017227824a837915bca2eae5f` | Explicit JSON transforms; first release does not perform discovery/network reads |
| `sisodias/great-library-of-siso` | `a6cfb54152ba7cf08e258ff7fd43159ff97ab562` | `6c4987b423bd50ea46f31cfcd913c19f09eb7861` | Stable Work identity, immutable Releases/Snapshots and separate research responsibilities |

The README reads and branch-ref lookups were separate observations. No claim is
made that every neighbouring source file, owner handoff or runtime was verified.
The Library source has its own license boundary; it is cited here, not copied.

## Primary implementation references

[Python's SQLite URI documentation](https://docs.python.org/3/library/sqlite3.html#how-to-work-with-sqlite-uris)
documents read-only URI connections. The new filename regression tests establish
behavior for the implementation in this changeset, not production databases.

[GitHub's secure-use reference](https://docs.github.com/en/actions/reference/security/secure-use)
recommends full-commit action pins. The CI action is pinned to the directly checked
`actions/checkout` v4 ref, commit `11d5960a326750d5838078e36cf38b85af677262`.
The workflow has `contents: read`, no saved checkout credentials, no deployment
step and no external-dataset materialisation. Runner OS/tool versions are printed
by the run; the operating environment is not claimed to be bit-for-bit pinned.

## Verification and remaining integration work

The first isolated run passed 28 new synthetic regression tests. Record later
run results in the pull request with its exact head commit; do not retroactively
turn this dated observation into a claim about all future revisions.

The source-only CI and explicit external-data gate are independent. Full external
consistency is blocked until an authorised atlas is supplied. Even a match leaves
broader database checks, rights, snapshot replication, live execution and product
acceptance unproved. Preserve the existing immutable research metadata.

Next source work should inventory path-resolution consumers and mechanically
reconcile coverage/value evidence, with source refs and regression tests. Next
operational work requires an actual input/owner/runtime receipt. The
[research-run playbook](RESEARCH-RUN.md) proposes a demand-led pilot once those
inputs are verified; it creates no running job.


## Full-checkout CI follow-up

The initial workflow was rejected before job execution because a runner context
was used at job-level environment scope. It was moved to step scope, following
[GitHub's context-availability contract](https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability).
The next full-checkout run reached the source scanner and identified four
pre-existing files containing machine-specific locators.

The book-score diagnostic now requires an explicit authorised `--knowledge-root`
and refuses its already-unimplemented `--apply` mode before reading. It does not
write Knowledge data or change the historical scoring heuristic. The exporter's
example uses a generic input path. Two existing small run-summary JSON records
have only their database locator removed, retain all historical counts/timing,
and carry explicit redaction metadata and the original blob/revision. These are
sanitised derivatives, not newly measured runs. This does not purge Git history.
No new raw evidence is published and no Graph operation is executed.

Four synthetic input-gate tests extend the focused suite from 30 to 34. Full CI
results must still be read from the exact pull-request head rather than inferred
from this local fixture result.
