-- Foundry — People graph schema (the unified PERSON entity across domains)
--
-- This is the canonical person model that STITCHES the three pre-existing pieces:
--   1. PERSON MASTER  : SISO_Library/pipelines/people/leaderboard.yaml  (140 tiered people)
--   2. JOIN TABLE     : SISO_Library/pipelines/youtube/people_video_queue.sqlite (person->video)
--   3. SATELLITES     : youtube channel_rankings.json (creators) + github repo_card owners
--
-- Design law (FOUNDRY-PLAN): one canonical entity table + a thin external_ids model
-- (one row per platform identity) + a generic person_content edge table. We do NOT
-- duplicate the satellites; we reference them (content ref = repo full_name OR video_id).
--
-- Single-writer: this DB lives on the mini vault (~/foundry-data/domains/people/people.sqlite),
-- written only by build_people_graph.py; everyone else opens it ?mode=ro.

-- Build-time pragmas. The builder checkpoints + switches to DELETE journal at close
-- so the published artifact opens cleanly with `?mode=ro` (no -wal/-shm sidecars needed).
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- person : the canonical entity. person_id is STABLE (= leaderboard slug for
-- registry people, or "gh:<login>" / "yt:<slug>" for satellite-only people).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS person (
  person_id     TEXT PRIMARY KEY,          -- stable id: registry slug, else gh:<login> / yt:<slug>
  name          TEXT NOT NULL,
  primary_tier  TEXT,                       -- S/A/B/C from leaderboard, or scorer tier for satellites
  origin        TEXT NOT NULL,              -- 'registry' | 'github' | 'youtube' (where first materialized)
  line          TEXT,                       -- leaderboard 'line' grouping (nullable for satellites)
  role          TEXT,
  topics_json   TEXT NOT NULL DEFAULT '[]',
  rank_score    REAL,                       -- people-ranking score (ChannelScorer primitive, satellites)
  built_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_person_name ON person(name);
CREATE INDEX IF NOT EXISTS idx_person_tier ON person(primary_tier);
CREATE INDEX IF NOT EXISTS idx_person_origin ON person(origin);

-- ---------------------------------------------------------------------------
-- external_ids : one row per (person, platform) identity. This is the join key
-- that lets us match the same human across registry / youtube / github / x.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS external_ids (
  person_id     TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
  platform      TEXT NOT NULL,              -- 'youtube_channel_id' | 'github_login' | 'x_handle' | 'website'
  value         TEXT NOT NULL,
  PRIMARY KEY (person_id, platform)
);
CREATE INDEX IF NOT EXISTS idx_extids_platform_value ON external_ids(platform, value);

-- ---------------------------------------------------------------------------
-- person_content : the edge table. Links a person to a concrete content artifact
-- in another domain. content_ref is a repo full_name (github) OR a video_id (youtube)
-- OR a channel_id (youtube channel as content). domain says which satellite to resolve.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS person_content (
  person_id     TEXT NOT NULL REFERENCES person(person_id) ON DELETE CASCADE,
  domain        TEXT NOT NULL,              -- 'github' | 'youtube_video' | 'youtube_channel'
  content_ref   TEXT NOT NULL,             -- repo full_name | video_id | channel_id/slug
  score         REAL,                       -- domain-native score (repo stars, video score, channel overall_score)
  title         TEXT,                       -- human label (repo desc, video title, channel name)
  meta_json     TEXT NOT NULL DEFAULT '{}',
  PRIMARY KEY (person_id, domain, content_ref)
);
CREATE INDEX IF NOT EXISTS idx_pcontent_person ON person_content(person_id);
CREATE INDEX IF NOT EXISTS idx_pcontent_domain ON person_content(domain);

-- ---------------------------------------------------------------------------
-- A convenience view: the "3-layer stitch" — for each person, how many domains
-- they appear in. A person with layers=3 is a full cross-domain stitch (Karpathy).
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_person_layers;
CREATE VIEW v_person_layers AS
SELECT
  p.person_id,
  p.name,
  p.primary_tier,
  p.origin,
  SUM(CASE WHEN d.domain LIKE 'youtube%' THEN 1 ELSE 0 END) > 0 AS in_youtube,
  SUM(CASE WHEN d.domain = 'github' THEN 1 ELSE 0 END) > 0      AS in_github,
  (p.origin = 'registry')                                       AS in_registry,
  COUNT(DISTINCT CASE
     WHEN d.domain LIKE 'youtube%' THEN 'youtube'
     WHEN d.domain = 'github' THEN 'github'
   END) + (p.origin = 'registry') AS layer_count
FROM person p
LEFT JOIN person_content d ON d.person_id = p.person_id
GROUP BY p.person_id;
