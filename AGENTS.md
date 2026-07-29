# Agent guide

Foundry is a Research Work. Do not refile it under Agents merely because agents run the pipeline.

Preserve these invariants:

1. Stable identity is independent from storage path and browse category.
2. Raw observations are append-only; deduplication is represented through identity and provenance.
3. Large or changing payloads stay out of Git and receive manifest/receipt records.
4. External source ownership and licenses are preserved.
5. SQLite uses one local writer and read-only consumers.
6. New repository boundaries require independent adoption or release value.

Before pushing, run `npm test`. Never commit databases, corpora, transcripts, generated browsers, result folders, runtime logs, credentials, or personal absolute paths.
