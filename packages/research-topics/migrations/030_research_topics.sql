-- Research Topics — the canonical registry of broad research BUCKETS (subject areas).
-- Sibling to idea-engine (improvement_ideas) and the repo-catalog. A bucket is a durable
-- subject area ("Memory & Context", "Agent Orchestration") that agents file findings, repos,
-- and questions UNDER. Agents add-or-create buckets via topics.py; never delete (status only).
--
-- Design: location owns the research (the registry is the truth), agents are tenants that
-- propose buckets + link artifacts. Mirrors the agent-vs-location split proven in repo-catalog.

CREATE TABLE IF NOT EXISTS research_topics (
  slug          TEXT PRIMARY KEY,            -- kebab-case stable id ("memory-and-context")
  title         TEXT NOT NULL,               -- human title ("Memory & Context")
  description   TEXT,                         -- what this bucket covers (the scope boundary)
  parent_slug   TEXT,                         -- optional hierarchy (NULL = top-level area)
  -- discovery seeds (mirror repo-catalog/categories.json so the harvest runner can read these)
  keywords      TEXT,                         -- JSON array: signals that route an artifact here
  gh_topics     TEXT,                         -- JSON array: github topic slugs for harvesting
  -- weighting / lifecycle
  tier          INTEGER,                      -- 1=critical .. 4=foundational (BLACKBOX5 style), NULL=unranked
  weight        REAL,                          -- optional priority weight (0-1)
  status        TEXT NOT NULL DEFAULT 'active', -- 'active' | 'merged' | 'dormant' (NEVER deleted)
  merged_into   TEXT,                          -- if status=merged, the slug it folded into
  -- provenance (who/why this bucket exists)
  created_by    TEXT NOT NULL,                -- 'agent:research-lead' | 'human:shaan' | 'migration:<src>'
  rationale     TEXT,                          -- why this bucket was created (the "found nothing similar" note)
  source        TEXT,                          -- where it came from (migrated file / agent finding)
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  FOREIGN KEY (parent_slug) REFERENCES research_topics(slug)
);

CREATE INDEX IF NOT EXISTS idx_research_topics_status ON research_topics(status);
CREATE INDEX IF NOT EXISTS idx_research_topics_parent ON research_topics(parent_slug);

-- Links: an artifact (repo / finding / question / source) filed under a bucket. Append-only.
-- artifact_kind: 'repo' (canonical_id from identity.sqlite) | 'finding' | 'question' | 'source' | 'doc'
CREATE TABLE IF NOT EXISTS research_topic_links (
  link_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  slug          TEXT NOT NULL,                -- the bucket
  artifact_kind TEXT NOT NULL,
  artifact_ref  TEXT NOT NULL,               -- canonical_id, file path, question text, url
  note          TEXT,
  linked_by     TEXT NOT NULL,
  linked_at     TEXT NOT NULL,
  UNIQUE (slug, artifact_kind, artifact_ref),
  FOREIGN KEY (slug) REFERENCES research_topics(slug)
);

CREATE INDEX IF NOT EXISTS idx_topic_links_slug ON research_topic_links(slug);
CREATE INDEX IF NOT EXISTS idx_topic_links_artifact ON research_topic_links(artifact_kind, artifact_ref);
