# Foundry Podcast Intelligence

This directory owns reasoning over podcast corpora after acquisition. It does
not own YouTube enumeration, media download, caption retrieval, or speech-to-text;
those remain source-adapter responsibilities under ../youtube/.

## Read order

1. README.md — domain boundary, tree, and operating model.
2. projects/<slug>/README.md — project router and current state.
3. The project's canonical HTML decision record.
4. The external corpus manifest named by the project state file.

## Invariants

- Raw transcripts are immutable evidence, stored outside the repository.
- Every derived claim must point to an exact source span and timestamp.
- Thirty-second windows are navigation/coverage views, not knowledge atoms.
- MiniMax proposes, locates, extracts, classifies, and challenges; same-model
  agreement is not independent corroboration.
- Generated summaries, dossiers, graphs, and world models are derived views.
- Consequential syntheses and rejected hypotheses are versioned, never silently
  overwritten.
- High-downside recommendations require accountable human judgment and evidence
  outside the podcast corpus.
- No provider key, browser cookie, or source credential may be written here.

## Current task

- TASK-0828 — build the Foundry podcast adaptive evidence foundry.
- Parent TASK-0827 — acquire the Jack Neel long-form transcript corpus.

