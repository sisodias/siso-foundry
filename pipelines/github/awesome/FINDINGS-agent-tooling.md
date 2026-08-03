# Peer-validated agent tooling

Extracted from `catalog_full.sqlite` on 2026-08-04. **N = number of DISTINCT
curated lists citing the repo** — how many independent maintainers each chose
it. Not stars. List-to-list badge references excluded from every count.

Corpus at extraction: 2,544 lists · 437,859 entries · 62,070 peer-validated
repos. **Every N below was re-derived individually against the DB** with:

```sql
SELECT COUNT(DISTINCT list_repo) FROM entry
WHERE target_repo = :repo
  AND target_repo NOT IN (SELECT list_repo FROM list);
```

(An earlier draft of this file used per-theme counts, which undercounted by
2-3× because each theme's `LIKE` filter only saw a subset of citing lists.
`litellm` read 18 there and 45 here. Use global counts.)

## Agent frameworks / orchestration

| N | repo | |
|---|---|---|
| 67 | `microsoft/autogen` | multi-agent conversation framework |
| 55 | `langchain-ai/langchain` | |
| 48 | `browser-use/browser-use` | drives a real Chrome for agent tasks |
| 46 | `langchain-ai/langgraph` | graph runtime, stateful + human-in-the-loop |
| 45 | `crewAIInc/crewAI` | role-playing agent orchestration |
| 43 | `pydantic/pydantic-ai` | type-safe, model-agnostic |
| 33 | `openai/openai-agents-python` | lightweight multi-agent |
| 33 | `huggingface/smolagents` | minimal agent library |
| 24 | `camel-ai/camel` | communicative-agent research framework |

## Agent memory — relevant to the SISO memory system

| N | repo | |
|---|---|---|
| 54 | `mem0ai/mem0` | universal memory layer, persistent recall |
| 29 | `letta-ai/letta` | formerly MemGPT; memory as a first-class agent concern |
| 27 | `topoteretes/cognee` | memory/knowledge-graph layer |
| 21 | `getzep/graphiti` | **temporal** knowledge graphs — closest to the people-graph work |
| 18 | `getzep/zep` | context-engineering platform |

Co-placement confirms these are mutual alternatives, not complements:
`mem0` → `letta` [22], `cognee` [18], `zep` [17], `graphiti` [13].

## Observability / eval — the "is my fleet healthy" layer

| N | repo | |
|---|---|---|
| 59 | `langfuse/langfuse` | traces, evals, prompt management |
| 48 | `Arize-ai/phoenix` | trace inspection, experiments |
| 42 | `comet-ml/opik` | tracing + monitoring |
| 37 | `promptfoo/promptfoo` | test-driven prompt eval + red-teaming |
| 34 | `Helicone/helicone` | observability proxy: logs, cache, cost |
| 31 | `confident-ai/deepeval` | pytest-for-LLMs, CI-friendly |
| 26 | `traceloop/openllmetry` | OpenTelemetry-based, 25+ backends |

## LLM gateways / routing — compare against the local Bifrost setup

| N | repo | |
|---|---|---|
| 45 | `BerriAI/litellm` | 100+ providers behind one OpenAI-format API |
| 13 | `Portkey-AI/gateway` | |
| 7 | `maximhq/bifrost` | adaptive load-balancing, OpenTelemetry-native |

Note: `maximhq/bifrost` is the same project the SISO router fronts on :8080.
Its citation count is low relative to `litellm`, which is worth knowing when
deciding whether the local setup is on the mainstream path.

## Code agents

`openai/codex` [49] · `google-gemini/gemini-cli` [45] ·
`anthropics/claude-code` [31] · `cline/cline` [29] · `Aider-AI/aider` [28] ·
`OpenHands/OpenHands` [19]

## Agent sandboxing / execution isolation

`e2b-dev/E2B` [14] · `steel-dev/steel-browser` [12] · `trycua/cua` [3]

Distinct from container security. See the caveat below — a query keyed on
"container" returns CVE scanners, not agent isolation.

## Context engineering — prior art on the token-cost problem

| N | repo | |
|---|---|---|
| 26 | `luoyuctl/agenttrace` | audits agent session health, cost, failures |
| 15 | `rtk-ai/rtk` | CLI proxy, claims 60-90% token reduction |
| 8 | `mufeedvh/code2prompt` | codebase → single prompt |

**Read these skeptically.** The SISO context-discipline notes argue naive input
compression can *cost* more — stripping input makes the model emit ~50% more
output to compensate, and output bills ~5× input. These are prior art on the
problem, not validated solutions to it.

## Method caveat — lexical matching, not semantic

Sections and descriptions are matched with `LIKE`, so themes drift. Three real
examples caught in review:

- A "sandboxing" query keyed on *container* returned `trivy`, `grype`, `syft`,
  `cosign` — container **vulnerability scanners**, nothing to do with agent
  isolation. The genuine answer (`E2B`) ranked 9th behind six irrelevant tools.
- A "context engineering" query keyed on *compression* returned `zstd`,
  `brotli`, `smaz`, `borg` — **data compression** libraries.
- A "memory" query returned `volatility` and `inVtero.net` — **forensic**
  memory analysis.

Citation counts are trustworthy. The theme assignment that produced the
candidate set is not — always read the output.
