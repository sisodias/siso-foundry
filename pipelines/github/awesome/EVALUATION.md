# Is this catalog actually better than just asking the model?

Run 2026-08-04. This is the test that decides whether the module is worth
keeping, and it is deliberately unflattering.

## Method

15 "what should I use for X" questions across common infrastructure domains.
**I wrote my five picks per question from memory FIRST**, committed them to a
file, and only then queried `bank_check.py`. No peeking, no re-ordering after
seeing results.

## Result

| | |
|---|---|
| my picks confirmed by curators | **31 / 75 (41%)** |
| repos surfaced that I did not name | **39** |

Per-question agreement was bimodal, and the split is the finding:

    workflow orchestration  5/5      vector database   4/5
    secrets management      4/5      time series db    4/5
    api gateway             3/5
    ...
    web scraping            0/5      full text search  0/5
    feature flags           1/5      message broker    1/5

## What this actually means

**Where we agree, the catalog adds nothing.** For well-known domains I already
name the right tools. Confirmation is not value.

**Where we disagree, the 39 "novel" repos are roughly half signal, half noise.**

Genuine finds I would not have named: `pgvector`, `huey`, `asynq`,
`machinery`, `crawl4ai`, `juicefs`, `lakefs`, `emqx`, `flexsearch`, `lura`,
`ocelot`, `knox`, `nixery`, `trow`.

Query noise: `awesome-web-scraping` (a list, not a tool), `helicone` and
`litellm` under "rate limiting" (LLM gateways that merely mention it in a
description), `gron` under "job scheduler" (a JSON tool matched on substring),
`certstream-server` under "log aggregation".

**Conclusion: the free-text query layer is the weak part.** It is `LIKE` over
section headings and descriptions, which is lexical, not semantic. The
underlying data is good; the retrieval is crude.

## The part that IS clearly better than asking a model

Two capabilities have no equivalent in model recall, and both are structural
rather than lexical:

**1. Co-placement (`--alts`).** A human filed these under one heading, so the
edge is a judgement, not a keyword match:

    langchain -> llama_index [8], pydantic-ai [5], dspy [4], autogen [4]
    ripgrep   -> fzf [25], fd [24], bat [20], the_silver_searcher [12]
    mem0      -> letta [24], cognee [21], zep [20], graphiti [16]

**2. Liveness.** Model recall has no concept of "this was true in 2022".
Measured on this corpus: **28.1% of peer-validated repos are >3y untouched**,
4,854 archived. Querying a dead tool returns the live successor with the other
dead options flagged:

    $ bank_check.py --alts ariya/phantomjs
      casperjs      7 lists    7,161*   ARCHIVED  !
      playwright    6 lists   93,917*   active
      slimerjs      5 lists    2,997*   DEAD 3y   !

I would have confidently listed casperjs and slimerjs as phantomjs
alternatives. They are both dead. That is the failure mode this fixes.

## Honest recommendation

Use `--alts` and the liveness flags. Treat keyword search as a starting point
that needs eyeballing, not an answer. The highest-value improvement is
replacing `LIKE` with embeddings or FTS5 over the curated descriptions — the
data is there, the retrieval is what is weak.
