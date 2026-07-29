# Foundry Podcast Intelligence

Podcast intelligence is a Foundry domain. Source adapters such as YouTube put
immutable transcripts and timestamp metadata into the external source bank;
this domain turns those sources into auditable evidence, discovery maps,
conditional theses, decision briefs, and experiments.

The central object is a **decision-linked proposition under uncertainty**, not
a transcript chunk, global summary, or knowledge-graph edge.

## Stable boundary

| Responsibility | Owner |
|---|---|
| Channel enumeration, Shorts exclusion, audio/captions, transcription | foundry/domains/youtube/ |
| Immutable corpus files | ~/SISO_Foundry_Data/domains/youtube/channels/<slug>/ |
| Podcast reconnaissance, evidence packets, contradiction search | foundry/domains/podcasts/ |
| Cross-source callable knowledge service | Foundry / knowledge-engine consumer layer |

## Memory model

- **Cold:** immutable raw transcript, timestamps, metadata, content hash.
- **Warm:** high-recall routing maps, semantic chapters, anomalies, entities,
  contradictions, and a discovery ledger.
- **Hot:** decision-linked evidence packets selected by active questions,
  substantial novelty, contradiction value, or protected exploration.
- **Live:** decisions, reversible experiments, observed outcomes, and scoped
  belief updates.

## Tree

    podcasts/
      AGENTS.md
      README.md
      projects/
        jack-neel/
          README.md
          STATE.json
          PILOT.json
          ADAPTIVE-EVIDENCE-FOUNDRY.html

Project Markdown files route cold agents. Human decision/state reports live in
self-contained HTML. Volatile machine state is JSON. Raw transcripts never
enter git.

## Projects

- jack-neel — first podcast corpus and pilot for the adaptive evidence
  process. Canonical task: TASK-0828.
