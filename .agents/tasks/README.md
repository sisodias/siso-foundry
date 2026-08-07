# Foundry — `.agents/tasks/`

Open engineering work owned by this repository, written down during the
2026-08-07 estate consolidation.

Adopts the SISO org `.agents/tasks/` convention: one task per
`backlog/TASK-NNNN/task.json` validated against `task_schema.json`, with the
`status` field canonical and the folder mirroring it. Tasks live in the
repository that owns the work, per ADR-0005's ownership model; estate-wide work
is tracked in the Great Library.

## Every task carries its receipt

Each `task.json` names the finding id, file path, branch or commit it came from,
in `evidence` and `spec.context`. A task without provenance becomes folklore
within a week and gets re-derived from scratch.

That failure already happened in this estate: `prompt-evolution.md` correctly
identified the empty-branch problem days before the consolidation, wrote it down
accurately, and nobody could reach it because it sat on an unmerged branch. The
findings were never lost, only unreachable — the same outcome as losing them.

## Durable rationale

`consolidation-source/` holds `ESTATE-STATUS.md` (where every repo, branch and
lane actually stood, derived by reading contents rather than filenames) and
`CONSOLIDATION-PLAN.md` (the reasoning, measured findings and preserved negative
results). Copied in deliberately: they were written in a session scratchpad and
would otherwise die with that session.
