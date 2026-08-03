-- ---------------------------------------------------------------------------
-- Expression indexes on lower(col).
--
-- WHY THIS EXISTS
--
-- Every join in this pipeline that matches names, logins or topics does so
-- case-insensitively, because the sources disagree about case:
--
--   external_ids   'Microsoft' and 'microsoft' are separate owner_signal rows
--   person_topic   LCSH is Title Case, github topics are lowercase
--   person.name    'saki' (a github profile) vs 'Saki' (a book author)
--
-- But SQLite cannot use an index on `col` to satisfy a predicate on
-- `lower(col)`. Every such query therefore full-scans. This bit the pipeline
-- three separate times before anyone noticed the pattern:
--
--   1. build_topic_bridge.py -- 1,638 queries against person_topic, each a
--      full scan of ~2M rows at ~0.25s. The run was still going after 15
--      minutes; rewriting it set-based made it 1.33s (>600x).
--   2. the identity-stitch join on lower(person.name) -- timed out repeatedly
--      at 120s, returned instantly once an expression index existed.
--   3. every loader's `known` dict, which exists only because looking up
--      lower(login) per row would have been unusably slow. Those loaders pull
--      245k rows into a Python dict as a workaround for this missing index.
--
-- Three occurrences is a systemic gap in the schema, not bad luck.
--
-- SAFETY: adding an index changes no data and no query results -- only the
-- plan chosen to produce them. These are additive; nothing is dropped, and
-- IF NOT EXISTS makes the script re-runnable.
--
-- COST: indexes are not free. Each adds write amplification on insert and disk.
-- They are justified here because this graph is read-heavy by design (it is an
-- index of people) and because the loaders that write it do so in bulk
-- transactions where per-row index maintenance is amortised.
--
-- Apply with:
--   sqlite3 people_v2.sqlite < core/add_lower_indexes.sql
-- ---------------------------------------------------------------------------

-- person.name: the identity-matching join. Case differs constantly between a
-- github profile name and a book catalogue heading.
CREATE INDEX IF NOT EXISTS ix_person_name_lower
  ON person(lower(name));

-- external_ids.value: used to resolve a login or a real_name back to a person.
-- Kept alongside platform so the common "this platform, this value" lookup is
-- covered rather than needing a second probe.
CREATE INDEX IF NOT EXISTS ix_extid_value_lower
  ON external_ids(platform, lower(value));

-- person_topic.topic: the vocabulary-bridging predicate. Six schemes now share
-- this table (github_topic, github_lang, lcsh, gh_category, curated, bridge,
-- gh_family, geo, org) and cross-scheme matching is always case-insensitive.
CREATE INDEX IF NOT EXISTS ix_ptopic_topic_lower
  ON person_topic(lower(topic), scheme);

-- person_content.content_ref: book gids and repo full_names. full_name case
-- varies by source ('Microsoft/vscode' vs 'microsoft/vscode').
CREATE INDEX IF NOT EXISTS ix_pc_ref_lower
  ON person_content(domain, lower(content_ref));

ANALYZE;
