-- tier_queries.sql
-- Query layer over the books catalog: turns the priority list into named VIEWS.
-- All views filter media_type='Text'. Counts measured against books_copy.sqlite.

-- TIER 1 — Core: philosophy/psych/religion, history, social sciences, polsci, science, medicine, tech, education
-- WHY: the bulk of "what's actually valuable" — the LoC sections the owner flagged as extract-first.
CREATE VIEW v_tier1_core AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_class c ON c.gid = b.gid
WHERE b.media_type = 'Text'
  AND c.bookcase IN ('B','C','D','E','F','H','J','Q','R','T','L');

-- TIER 1 — Essays, letters, speeches ("god source")
-- WHY: cross-cutting; these sit inside language/literature (P) which would otherwise be discarded.
CREATE VIEW v_tier1_essays AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_subject s ON s.gid = b.gid
WHERE b.media_type = 'Text'
  AND (s.subject LIKE '%essays%'
       OR s.subject LIKE '%letters%'
       OR s.subject LIKE '%speech%'
       OR s.subject LIKE '%correspondence%');

-- TIER 1 — Journalism / periodicals, century-old especially
-- WHY: AP-coded periodicals are dense primary source; owner wants the old ones.
CREATE VIEW v_tier1_journalism AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_subject s ON s.gid = b.gid
WHERE b.media_type = 'Text'
  AND (s.subject LIKE '%journalism%'
       OR s.subject LIKE '%periodical%'
       OR s.subject LIKE '%newspaper%'
       OR s.subject LIKE '%press%');

-- TIER 1 — Mythology, legends, folklore
-- WHY: cultural heritage — owner explicit pick.
CREATE VIEW v_tier1_mythology AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_subject s ON s.gid = b.gid
WHERE b.media_type = 'Text'
  AND (s.subject LIKE '%mytholog%'
       OR s.subject LIKE '%legend%'
       OR s.subject LIKE '%folklore%'
       OR s.subject LIKE '%fable%');

-- TIER 1 — Biographies
-- WHY: always valuable; cross-cuts sections.
CREATE VIEW v_tier1_biography AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_subject s ON s.gid = b.gid
WHERE b.media_type = 'Text'
  AND (s.subject LIKE '%biograph%');

-- TIER 1 — Classical Greek/Latin (PA)
-- WHY: primary sources from antiquity; sits inside P but flagged.
CREATE VIEW v_tier1_classical AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_class c ON c.gid = b.gid
WHERE b.media_type = 'Text'
  AND c.bookcase = 'PA';

-- TIER 1 — Literary criticism/theory (PN)
-- WHY: analytical layer over literature; owner explicit pick.
CREATE VIEW v_tier1_criticism AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_class c ON c.gid = b.gid
WHERE b.media_type = 'Text'
  AND c.bookcase = 'PN';

-- TIER 2 — Hold, revisit: language, geography/anthropology, agriculture, fine arts
-- WHY: owner marked these for second pass; not discarded.
CREATE VIEW v_tier2 AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
JOIN book_class c ON c.gid = b.gid
WHERE b.media_type = 'Text'
  AND c.bookcase IN ('P','G','S','N');

-- TIER 3 — Store, don't extract: juvenile fiction (PZ), romance, music, fashion, cookery
-- WHY: explicitly low-value for extraction pipeline.
CREATE VIEW v_tier3 AS
SELECT DISTINCT b.gid, b.title, b.authors, b.issued
FROM book b
LEFT JOIN book_class c ON c.gid = b.gid AND c.bookcase = 'PZ'
LEFT JOIN book_subject s ON s.gid = b.gid
WHERE b.media_type = 'Text'
  AND (c.gid IS NOT NULL
       OR s.subject LIKE '%romance%'
       OR s.subject LIKE '%music%'
       OR s.subject LIKE '%fashion%'
       OR s.subject LIKE '%cookery%'
       OR s.subject LIKE '%cooking%');

-- v_extraction_queue: union of tier1, deduped at highest tier, with reason.
-- Priority order: core > criticism > classical > biography > mythology > essays > journalism.
CREATE VIEW v_extraction_queue AS
SELECT 'tier1' AS tier, 'core_sections' AS reason, gid, title, authors, issued FROM v_tier1_core
UNION SELECT 'tier1', 'criticism_PN', gid, title, authors, issued FROM v_tier1_criticism
UNION SELECT 'tier1', 'classical_PA', gid, title, authors, issued FROM v_tier1_classical
UNION SELECT 'tier1', 'biography', gid, title, authors, issued FROM v_tier1_biography
UNION SELECT 'tier1', 'mythology', gid, title, authors, issued FROM v_tier1_mythology
UNION SELECT 'tier1', 'essays_letters_speeches', gid, title, authors, issued FROM v_tier1_essays
UNION SELECT 'tier1', 'journalism_periodicals', gid, title, authors, issued FROM v_tier1_journalism
UNION SELECT 'tier2', 'hold_revisit', gid, title, authors, issued FROM v_tier2;

-- ---------------------------------------------------------------------------
-- CORRECTION, recorded so nobody repeats the mistake.
--
-- `book.issued` is Gutenberg's DIGITISATION date, not the work's publication
-- date. Receipts: the Declaration of Independence carries issued=1971-12-01;
-- Lincoln's Gettysburg Address carries 1973-11-01. Gutenberg's own metadata
-- documentation states print-source publication dates are deliberately excluded.
--
-- Consequence: an earlier pass concluded "zero periodicals pre-1950, all 4,334
-- post-2000" and dropped a date filter as a result. That reading was wrong. The
-- century-old journalism IS in the corpus; `issued` simply cannot find it.
--
-- The correct proxy is AUTHOR LIFE DATES, which the people graph holds for
-- 27,568 people (BCE stored negative). A periodical whose author died in 1890
-- is 19th-century journalism regardless of when a volunteer typed it up.
-- Join people_books.sqlite person/person_work on gid to filter by era.
-- ---------------------------------------------------------------------------
