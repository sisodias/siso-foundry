# Agent guide

Foundry is a Research Work. Do not refile it under Agents merely because agents
run the pipeline. Existing project and system owners remain authoritative.

## Entry

Read the current project-scoped instructions and authorised canonical guide, then
this README, [foundation](docs/FOUNDATION.md), [architecture](ARCHITECTURE.md),
[dataset boundary](DATASETS.md) and relevant existing owner handoff. Use the
[source audit](docs/SOURCE-AUDIT-2026-09-07.md) as dated evidence, not live runtime
truth. Do not copy private guides or handoffs into public source.

Preserve these invariants:

1. Stable identity is independent from storage path and browse category.
2. Raw observations are append-only; deduplication is represented through identity and provenance.
3. Large or changing payloads stay out of Git and receive manifest/receipt records.
4. External source ownership and licenses are preserved.
5. SQLite uses one authorised local writer and read-only consumers; helpers do not elect or enforce that owner.
6. New repository boundaries require independent adoption or release value.
7. Knowledge Graph and People Graph are separate systems, not Foundry-owned merely because adapters exist here.
8. GitHub/source access, dataset availability and execution readiness are separate claims.

## Changes and verification

Use a scoped branch based on an observed commit. Preserve other branches,
unpublished work and existing research evidence. Before review/integration, run
`npm run test:source` and record the exact commit and actual result. Run `npm test`
with the explicit authorised atlas to establish the narrower external consistency
result; unavailable data is **blocked**, not a waived or passing full check.
GitHub-only changes may be submitted for CI review with local/full-test limits
explicit; do not claim a check was run before its receipt exists.

The publication guard scans Git-tracked and nonignored candidates. It is not a
complete secret, privacy or rights audit. Never commit databases, corpora,
transcripts, generated browsers, result folders, runtime logs, credentials,
personal absolute paths, private topology or private owner handoffs.

No bulk acquisition, deployment, runtime change, Graph migration, product
promotion or Library selection follows automatically from a branch or test pass.
Follow the [research-run playbook](docs/RESEARCH-RUN.md) for a bounded proposal,
using existing owner records rather than a second queue or registry.
