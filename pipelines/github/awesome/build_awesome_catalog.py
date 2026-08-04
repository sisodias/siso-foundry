#!/usr/bin/env python3
"""Harvest the awesome-list ecosystem into a queryable catalog.

Design notes (why it looks like this):
  * The value here is NOT the repo list -- GitHub already has every repo. The
    value is that a human decided repo X belongs under heading "Web Crawling"
    in a list about Python. That heading is an inherited taxonomy and an
    editorial quality signal, and it is the field this whole module exists to
    capture. entry.section is load-bearing; everything else is context for it.
  * Membership is a RELATION. A repo appearing in 9 curated lists is a much
    stronger signal than one appearing in 1, so entry is an edge table and the
    multi-list count is computed at read time, never stored as a verdict.
  * READMEs come from raw.githubusercontent.com, which costs ZERO API quota.
    The GitHub API is used only for repo metadata (stars/language/topics),
    which is optional and rate-limit-aware. A full parse run can be done with
    no token at all.
  * Resumable: every fetched README is cached to disk and every list is marked
    with its fetch status, so a re-run skips completed work. Interrupting this
    script never costs you the fetches you already paid for.

Two-level harvest:
  depth 0  seed list (sindresorhus/awesome) -> its github links are LIST repos
  depth 1  each of those lists              -> its github links are TARGET repos

Usage:
  build_awesome_catalog.py --db awesome_catalog.sqlite --cache .cache/ \
      [--limit N] [--enrich] [--seed owner/repo]
"""
import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

SEED = "sindresorhus/awesome"
UA = "siso-foundry-awesome-harvest"

# README lives at an unpredictable {branch}/{filename} combination. Measured:
# sindresorhus/awesome is main/readme.md, vinta/awesome-python is master/README.md.
# Ordered by observed frequency so the common case costs one request.
README_CANDIDATES = [
    ("main", "README.md"), ("master", "README.md"),
    ("main", "readme.md"), ("master", "readme.md"),
    ("main", "README.markdown"), ("master", "README.markdown"),
]

SCHEMA = """
-- A curated list repo we harvested (or tried to).
CREATE TABLE IF NOT EXISTS list (
  list_repo   TEXT PRIMARY KEY,          -- "owner/name"
  title       TEXT,                      -- first H1 of the README
  topic       TEXT,                      -- slug derived from the repo name
  depth       INTEGER NOT NULL,          -- 0 = seed, 1 = harvested from seed
  stars       INTEGER,                   -- NULL unless --enrich ran
  readme_path TEXT,                      -- which branch/file actually resolved
  n_entries   INTEGER,                   -- links parsed out of this list
  status      TEXT NOT NULL,             -- ok | notfound | error
  fetched_at  TEXT
);

-- The payload. One row per (list, target) reference, carrying the SECTION
-- HEADING the human filed it under. section_path keeps the full ## > ###
-- breadcrumb because heading depth is inconsistent across lists.
CREATE TABLE IF NOT EXISTS entry (
  list_repo    TEXT NOT NULL,
  target_repo  TEXT NOT NULL,            -- "owner/name", normalised
  section      TEXT,                     -- nearest enclosing heading
  section_path TEXT,                     -- "Parent > Child"
  description  TEXT,                     -- editor's own words about the repo
  position     INTEGER NOT NULL,         -- order of appearance in the list
  PRIMARY KEY (list_repo, target_repo, position)
);

-- Deduped targets. Populated by rollup from entry; metadata only via --enrich.
CREATE TABLE IF NOT EXISTS repo (
  full_name   TEXT PRIMARY KEY,
  owner       TEXT NOT NULL,
  name        TEXT NOT NULL,
  description TEXT,
  stars       INTEGER,
  language    TEXT,
  topics_json TEXT,
  list_count  INTEGER NOT NULL DEFAULT 0, -- how many distinct lists cite it
  -- Liveness. Stars are a PERMANENT record of past popularity and never decay,
  -- so they cannot distinguish a live project from an abandoned one. Measured
  -- on the curated top tier: 5.8% were untouched for >3y, including
  -- harthur/brain (7,990 stars, 5.9y) and clvv/fasd (5,912 stars, 6.2y) --
  -- exactly the repos a star-sorted search recommends and shouldn't. These
  -- two columns are what make that check reproducible from the DB.
  pushed_at   TEXT,
  archived    INTEGER,
  created_at  TEXT,
  enriched_at TEXT
);

-- People signal. Owner -> how much curated attention their work attracts.
-- Deliberately NOT written to the people graph here; this is a feed table.
CREATE TABLE IF NOT EXISTS owner_signal (
  owner        TEXT PRIMARY KEY,
  n_repos      INTEGER NOT NULL,   -- distinct repos of theirs that were cited
  n_lists      INTEGER NOT NULL,   -- distinct lists citing any of their repos
  n_entries    INTEGER NOT NULL,   -- total citations
  max_repo_lists INTEGER NOT NULL  -- best single repo's list count
);

CREATE INDEX IF NOT EXISTS ix_entry_target  ON entry(target_repo);
CREATE INDEX IF NOT EXISTS ix_entry_list    ON entry(list_repo);
CREATE INDEX IF NOT EXISTS ix_entry_section ON entry(section);
CREATE INDEX IF NOT EXISTS ix_repo_owner    ON repo(owner);
CREATE INDEX IF NOT EXISTS ix_repo_lists    ON repo(list_count);
"""

# github.com/owner/name -- stop at anything that is not a path char. Trailing
# ")" / "." / "," are stripped by the character class, and we reject non-repo
# URLs (gists, orgs, /topics/) in normalise().
LINK_RE = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9][\w.-]*)/([\w.-]+)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*$")

# GitHub's detected-language names, used ONLY to spot star dumps grouped by
# language (see is_list_readme). Deliberately includes non-curatable ones like
# Batchfile and Dockerfile -- their presence as a heading is the tell.
_GH_LANGUAGES = {
    "ActionScript", "Assembly", "Astro", "Batchfile", "C", "C#", "C++",
    "CMake", "COBOL", "CSS", "Clojure", "CoffeeScript", "Crystal", "Cuda",
    "D", "Dart", "Dockerfile", "Elixir", "Elm", "Emacs Lisp", "Erlang",
    "F#", "Fortran", "GDScript", "Go", "Groovy", "HCL", "HTML", "Handlebars",
    "Haskell", "Java", "JavaScript", "Julia", "Jupyter Notebook", "Kotlin",
    "LLVM", "Lua", "MDX", "Makefile", "Markdown", "Nim", "Nix", "OCaml",
    "Objective-C", "Objective-C++", "PHP", "PLpgSQL", "Perl", "PowerShell",
    "Python", "R", "Roff", "Ruby", "Rust", "SCSS", "Scala", "Scheme",
    "ShaderLab", "Shell", "Smarty", "Solidity", "Svelte", "Swift", "TeX",
    "TypeScript", "V", "Vim Script", "Vue", "Zig", "Others", "Unknown",
}
# "- [name](url) - description"  /  "* [name](url) — description"
DESC_RE = re.compile(r"^[-*+]\s+\[[^\]]*\]\([^)]*\)\s*[-–—:]\s*(.+)$")

# Paths under github.com that are never a repo.
NOT_REPOS = {
    "topics", "sponsors", "orgs", "users", "collections", "events", "explore",
    "features", "about", "pricing", "settings", "notifications", "search",
    "marketplace", "apps", "login", "join", "readme", "trending", "new",
    # CDN / asset hosts that look like owner names in an image URL. Observed:
    # "user-attachments/assets" scored 16 lists purely because 16 READMEs
    # embedded a screenshot -- it ranked above real tools in the candidate
    # export before this was excluded.
    "user-attachments", "user-images", "avatars", "camo", "badges", "shields",
    "raw", "assets", "img", "media", "gist",
}


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def normalise(owner, name):
    """Return 'owner/name' or None if this is not a real repo reference."""
    if owner.lower() in NOT_REPOS:
        return None
    name = name.rstrip(".")
    if name.endswith(".git"):
        name = name[:-4]
    if not name or name in (".", ".."):
        return None
    # Fragments like "/blob", "/tree" never reach here: the regex captures only
    # the first two path segments, so owner/name is already the repo root.
    return f"{owner}/{name}"


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def fetch_readme(repo, cache_dir):
    """Return (text, path_used) or (None, None). Cached on disk; resumable."""
    safe = repo.replace("/", "__")
    cache_file = os.path.join(cache_dir, safe + ".md")
    meta_file = os.path.join(cache_dir, safe + ".path")
    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            text = f.read()
        path = ""
        if os.path.exists(meta_file):
            with open(meta_file, encoding="utf-8") as f:
                path = f.read().strip()
        return text, path or "cached"

    for branch, fname in README_CANDIDATES:
        url = f"https://raw.githubusercontent.com/{repo}/{branch}/{fname}"
        try:
            text = fetch(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            if e.code in (403, 429):        # C4: back off, do not hammer
                time.sleep(5)
                continue
            continue
        except Exception:
            continue
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(text)
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(f"{branch}/{fname}")
        return text, f"{branch}/{fname}"

    # Fallback: the candidate ladder misses two real cases -- repos that were
    # RENAMED (raw.githubusercontent does not follow repo redirects, unlike the
    # API) and repos whose default branch or README filename is unusual.
    # Measured: 2/51 lists in an early run. One API call each, only on miss.
    try:
        out = subprocess.run(
            ["gh", "api", f"repos/{repo}", "--jq", ".full_name+\" \"+.default_branch"],
            capture_output=True, text=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            real_repo, branch = out.stdout.strip().split()
            # Ask the repo what its README is actually called rather than
            # guessing capitalisations -- observed in the wild: "Readme.md".
            names = []
            try:
                ls = subprocess.run(
                    ["gh", "api", f"repos/{real_repo}/contents", "--jq", ".[].name"],
                    capture_output=True, text=True, timeout=30)
                if ls.returncode == 0:
                    names = [n for n in ls.stdout.split()
                             if n.lower().startswith("readme.")]
            except Exception:
                pass
            for fname in names + ["README.md", "readme.md", "README.markdown"]:
                url = f"https://raw.githubusercontent.com/{real_repo}/{branch}/{fname}"
                try:
                    text = fetch(url)
                except Exception:
                    continue
                with open(cache_file, "w", encoding="utf-8") as f:
                    f.write(text)
                path = f"{real_repo}@{branch}/{fname}"
                with open(meta_file, "w", encoding="utf-8") as f:
                    f.write(path)
                return text, path
    except Exception:
        pass
    return None, None


def parse_readme(text):
    """-> (title, [ {target, section, section_path, description, position} ])

    Walks the README line by line maintaining a heading stack, so every link
    inherits the breadcrumb of headings enclosing it. A link appearing before
    any heading gets section=None rather than a guessed one.
    """
    title = None
    stack = {}          # level -> heading text
    entries = []
    pos = 0
    in_code = False

    # Many awesome READMEs open with an HTML banner and never use a markdown
    # H1, so a markdown-only title parse returns empty for them. Fall back to
    # the first <h1> before giving up.
    hm = re.search(r"<h1[^>]*>(.*?)</h1>", text, re.S | re.I)
    if hm:
        title = re.sub(r"<[^>]+>", " ", hm.group(1))
        title = re.sub(r"\s+", " ", title).strip() or None

    for line in text.splitlines():
        stripped = line.strip()

        # Fenced code blocks contain example URLs that are not curation.
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_code = not in_code
            continue
        if in_code:
            continue

        m = HEADING_RE.match(stripped)
        if m:
            level = len(m.group(1))
            text_h = m.group(2).strip()
            # Strip markdown link syntax from headings: "## [Foo](#foo)" -> "Foo"
            text_h = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text_h).strip()
            # Strip inline HTML. Observed in the wild: a heading that was an
            # entire <picture><source srcset=...> block, and many carrying
            # "<kbd>4 projects</kbd>" badges. Left raw these become distinct
            # "sections", inflating the taxonomy with markup noise.
            text_h = re.sub(r"<[^>]+>", " ", text_h)
            text_h = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text_h)   # images
            text_h = re.sub(r"&[a-z]+;|&#\d+;", " ", text_h)        # entities
            text_h = re.sub(r"\s+", " ", text_h).strip(" #*_-·|")
            if level == 1 and title is None:
                title = text_h
            stack[level] = text_h
            for deeper in [k for k in stack if k > level]:
                del stack[deeper]
            continue

        links = LINK_RE.findall(line)
        if not links:
            continue

        levels = sorted(k for k in stack if k > 1)
        section = stack[levels[-1]] if levels else None
        section_path = " > ".join(stack[k] for k in levels) if levels else None
        dm = DESC_RE.match(stripped)
        description = dm.group(1).strip() if dm else None

        seen_in_line = set()
        for owner, name in links:
            repo = normalise(owner, name)
            if not repo or repo in seen_in_line:
                continue
            seen_in_line.add(repo)
            entries.append({
                "target": repo, "section": section, "section_path": section_path,
                "description": description, "position": pos,
            })
            pos += 1

    return title, entries


def topic_slug(repo):
    """awesome-python -> python. Best-effort; the list name IS the topic."""
    name = repo.split("/", 1)[1].lower()
    name = re.sub(r"^awesome[-_]?", "", name)
    name = re.sub(r"[-_]?awesome$", "", name)
    name = re.sub(r"^(list|lists)[-_]", "", name)
    return name or repo.split("/", 1)[1].lower()


def looks_like_list(repo):
    """DEPRECATED name heuristic. Kept only for --classify=name.

    Measured on the seed: this excluded 64 of 681 links, and reading them,
    most were genuine curated lists that simply do not say "awesome" --
    js-must-watch, 30-seconds-of-code, frontend-dev-bookmarks. A name is a
    signal to investigate, never a verdict. Use is_list_readme() instead.
    """
    name = repo.split("/", 1)[1].lower()
    return "awesome" in name or name.startswith("list-of-")


def is_list_readme(text, min_links=20, min_ratio=0.05):
    """Classify by READING: is this README shaped like a curated list?

    A curated list is defined by structure, not by its name: many outbound
    repo links organised under headings. Returns (bool, stats) so the decision
    is auditable per repo.

    Calibrated against the 64 links the old name heuristic threw away:
      * min_ratio started at 0.20 and REJECTED open-source-mac-os-apps -- 889
        links, 888 of them sectioned -- purely because its README is 9,483
        lines long. A density gate punishes thorough lists, which is backwards.
        Absolute link count already carries the signal; ratio only needs to
        exclude prose pages that mention a repo or two in passing.
      * Lists curating NON-GitHub resources (frontend-dev-bookmarks,
        30-seconds-of-code) legitimately score ~0 links, because LINK_RE only
        matches github.com. They are out of scope for a repo catalog, not
        misclassified -- this function should keep returning False for them.
    """
    if not text:
        return False, {"reason": "empty"}

    # Reject AUTO-GENERATED star dumps. Tools like `starred` and
    # github-stars-generator emit a README of someone's starred repos grouped
    # by language, titled "Awesome Stars". These are not editorial judgements
    # -- nobody chose the set, a bot exported it -- and because hundreds of
    # unrelated repos land under a single "Python" heading they severely
    # corrupt the co-occurrence graph. Measured 2026-08-04: 2 such lists
    # carried 15,434 entries, 5.9% of the entire corpus.
    head = text[:4000]
    if re.search(r"(?im)^\s*#\s*(awesome\s+stars|my\s+stars|starred\s+repositories)\b", head):
        return False, {"reason": "auto-generated star dump"}
    if re.search(r"(?i)(github-stars-generator|maguowei/starred|awesome-stars\s+generator)", head):
        return False, {"reason": "star-dump generator signature"}

    title, entries = parse_readme(text)
    n_links = len(entries)
    n_lines = max(1, len(text.splitlines()))
    linked = len({e["target"] for e in entries})
    with_section = sum(1 for e in entries if e["section"])
    ratio = n_links / n_lines
    # A large list with almost no headings is machine filler, not curation:
    # the whole value here is that a human SORTED things. Measured:
    # awesome-interview-questions-5000-jobs had 4,462 entries under ONE
    # section. Small lists legitimately have few headings, so this only
    # applies past the point where a human would obviously have subdivided.
    n_sections = len({e["section"] for e in entries if e["section"]})
    unsorted_bulk = n_links > 300 and n_sections <= 2

    # Star dumps whose title lacks the generator marker still betray
    # themselves: `maguowei/starred` groups by GitHub's DETECTED LANGUAGE, so
    # the headings are bare language names -- including ones no human curates
    # ("Batchfile", "Dockerfile", "Handlebars", "CoffeeScript"). A real
    # language list has topical subheadings; a dump has only the languages.
    # Observed on r44cx/stars: 758 links, 42 sections, every one a language.
    secs = {(e["section"] or "").strip() for e in entries if e["section"]}
    lang_like = sum(1 for s in secs if s in _GH_LANGUAGES)
    language_dump = len(secs) >= 8 and lang_like >= len(secs) * 0.8

    is_list = (
        n_links >= min_links
        and ratio >= min_ratio
        and with_section >= n_links * 0.5
        and not unsorted_bulk
        and not language_dump
    )
    return is_list, {
        "links": n_links, "unique": linked, "lines": n_lines,
        "ratio": round(ratio, 3), "with_section": with_section,
        "sections": n_sections, "unsorted_bulk": unsorted_bulk,
        "language_dump": language_dump,
        # The parsed entries, handed back so callers do not re-parse. This
        # function already ran parse_readme() to make its decision; profiling
        # showed ingest_cache.py then parsed the same text a SECOND time,
        # which was ~1/3 of total ingest wall-clock.
        "entries": entries, "title": title,
    }


def harvest(conn, repo, depth, cache_dir):
    text, path = fetch_readme(repo, cache_dir)
    if text is None:
        conn.execute(
            "INSERT OR REPLACE INTO list(list_repo,topic,depth,n_entries,status,fetched_at)"
            " VALUES(?,?,?,?,?,?)",
            (repo, topic_slug(repo), depth, 0, "notfound", now()))
        return []
    title, entries = parse_readme(text)
    conn.execute(
        "INSERT OR REPLACE INTO list"
        "(list_repo,title,topic,depth,readme_path,n_entries,status,fetched_at)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (repo, title, topic_slug(repo), depth, path, len(entries), "ok", now()))
    conn.executemany(
        "INSERT OR REPLACE INTO entry"
        "(list_repo,target_repo,section,section_path,description,position)"
        " VALUES(?,?,?,?,?,?)",
        [(repo, e["target"], e["section"], e["section_path"],
          e["description"], e["position"]) for e in entries])
    return [e["target"] for e in entries]


def rollup(conn):
    """Recompute repo + owner_signal from entry. Idempotent; never additive.

    Enrichment (stars/language/pushed_at/archived) is preserved across the
    rebuild. It comes from the GitHub API and costs one request per repo, so
    a DELETE FROM repo silently discards work that is expensive to redo --
    observed: a routine re-ingest dropped 1,197 enriched rows to 0, and it was
    only caught because an unrelated cleanup compared two DBs.
    """
    saved = {
        r[0]: r[1:] for r in conn.execute(
            "SELECT full_name, stars, language, topics_json, pushed_at,"
            " archived, created_at, enriched_at FROM repo"
            " WHERE enriched_at IS NOT NULL")
    }
    conn.execute("DELETE FROM repo")
    conn.execute("""
      INSERT INTO repo(full_name, owner, name, list_count, description)
      SELECT e.target_repo,
             substr(e.target_repo, 1, instr(e.target_repo,'/')-1),
             substr(e.target_repo, instr(e.target_repo,'/')+1),
             COUNT(DISTINCT e.list_repo),
             (SELECT description FROM entry x
               WHERE x.target_repo = e.target_repo AND x.description IS NOT NULL
               LIMIT 1)
      FROM entry e GROUP BY e.target_repo
    """)
    # Restore the enrichment onto the freshly rebuilt rows.
    if saved:
        conn.executemany(
            "UPDATE repo SET stars=?, language=?, topics_json=?, pushed_at=?,"
            " archived=?, created_at=?, enriched_at=? WHERE full_name=?",
            [(*vals, full) for full, vals in saved.items()])

    conn.execute("DELETE FROM owner_signal")
    # NOTE: the obvious formulation -- correlated subqueries over entry keyed on
    # substr(target_repo,...) -- is accidentally quadratic: substr() defeats the
    # index, so each of ~60k owners full-scans ~200k entries. Measured: still
    # running after 18 CPU-minutes. Materialising the owner column once and
    # grouping is a single pass and completes in seconds.
    conn.executescript("""
      DROP TABLE IF EXISTS _entry_owner;
      CREATE TEMP TABLE _entry_owner AS
        SELECT list_repo, target_repo,
               substr(target_repo, 1, instr(target_repo,'/')-1) AS owner
        FROM entry;
      CREATE INDEX ix_eo_owner ON _entry_owner(owner);
    """)
    conn.execute("""
      INSERT INTO owner_signal(owner, n_repos, n_lists, n_entries, max_repo_lists)
      SELECT eo.owner,
             COUNT(DISTINCT eo.target_repo),
             COUNT(DISTINCT eo.list_repo),
             COUNT(*),
             COALESCE((SELECT MAX(r.list_count) FROM repo r WHERE r.owner = eo.owner), 0)
      FROM _entry_owner eo GROUP BY eo.owner
    """)
    conn.commit()


def enrich(conn, limit):
    """Optional GitHub API pass for stars/language/topics. Rate-limit aware."""
    rows = conn.execute(
        "SELECT full_name FROM repo WHERE enriched_at IS NULL"
        " ORDER BY list_count DESC LIMIT ?", (limit,)).fetchall()
    done = 0
    for (full,) in rows:
        try:
            out = subprocess.run(
                ["gh", "api", f"repos/{full}",
                 "--jq", "{stars:.stargazers_count,lang:.language,"
                         "desc:.description,topics:.topics,"
                         "pushed:.pushed_at,arch:.archived,created:.created_at}"],
                capture_output=True, text=True, timeout=30)
            if out.returncode != 0:
                if "rate limit" in (out.stderr or "").lower():
                    print("rate limited; stopping enrich", file=sys.stderr)
                    break
                continue
            d = json.loads(out.stdout)
        except Exception:
            continue
        conn.execute(
            "UPDATE repo SET stars=?, language=?, description=COALESCE(?,description),"
            " topics_json=?, pushed_at=?, archived=?, created_at=?, enriched_at=?"
            " WHERE full_name=?",
            (d.get("stars"), d.get("lang"), d.get("desc"),
             json.dumps(d.get("topics") or []), d.get("pushed"),
             1 if d.get("arch") else 0, d.get("created"), now(), full))
        done += 1
        if done % 50 == 0:
            conn.commit()
    conn.commit()
    return done


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="awesome_catalog.sqlite")
    ap.add_argument("--cache", default=".cache")
    ap.add_argument("--seed", default=SEED)
    ap.add_argument("--limit", type=int, default=0,
                    help="max depth-1 lists to harvest (0 = all)")
    ap.add_argument("--enrich", type=int, default=0,
                    help="enrich top-N repos via GitHub API")
    ap.add_argument("--classify", choices=["read", "name"], default="read",
                    help="how to decide a candidate is a list: by reading its "
                         "README (default) or by the deprecated name heuristic")
    args = ap.parse_args()

    os.makedirs(args.cache, exist_ok=True)
    conn = sqlite3.connect(args.db)
    conn.executescript(SCHEMA)

    t0 = time.time()

    # depth 0: the seed's links are candidate LIST repos.
    candidates = harvest(conn, args.seed, 0, args.cache)
    conn.commit()

    uniq = [r for r in dict.fromkeys(candidates) if r != args.seed]
    if args.classify == "name":
        lists = [r for r in uniq if looks_like_list(r)]
    else:
        # Classify by READING each candidate's README, not by its name.
        # Costs one (cached) fetch per candidate and recovers real lists that
        # do not say "awesome" -- es6-tools, terminals-are-sexy, awsm.fish.
        lists = []
        for r in uniq:
            if looks_like_list(r):
                lists.append(r)          # name already sufficient; skip fetch
                continue
            txt, _ = fetch_readme(r, args.cache)
            ok, _st = is_list_readme(txt)
            if ok:
                lists.append(r)
        print(f"  classify=read: {len(lists)}/{len(uniq)} candidates are lists",
              file=sys.stderr)
    if args.limit:
        lists = lists[:args.limit]

    # Resume: skip lists already fetched ok in a previous run.
    already = {r[0] for r in conn.execute(
        "SELECT list_repo FROM list WHERE status='ok' AND depth=1")}
    todo = [r for r in lists if r not in already]

    for i, repo in enumerate(todo, 1):
        harvest(conn, repo, 1, args.cache)
        if i % 25 == 0:
            conn.commit()
            print(f"  ...{i}/{len(todo)} lists", file=sys.stderr)
    conn.commit()

    rollup(conn)

    enriched = enrich(conn, args.enrich) if args.enrich else 0

    q = lambda s: conn.execute(s).fetchone()[0]
    summary = {
        "seed": args.seed,
        "lists_total": q("SELECT COUNT(*) FROM list"),
        "lists_ok": q("SELECT COUNT(*) FROM list WHERE status='ok'"),
        "lists_notfound": q("SELECT COUNT(*) FROM list WHERE status='notfound'"),
        "entries": q("SELECT COUNT(*) FROM entry"),
        "unique_repos": q("SELECT COUNT(*) FROM repo"),
        "multi_list_repos": q("SELECT COUNT(*) FROM repo WHERE list_count>1"),
        "entries_with_section": q("SELECT COUNT(*) FROM entry WHERE section IS NOT NULL"),
        "distinct_sections": q("SELECT COUNT(DISTINCT section) FROM entry WHERE section IS NOT NULL"),
        "entries_with_description": q("SELECT COUNT(*) FROM entry WHERE description IS NOT NULL"),
        "owners": q("SELECT COUNT(*) FROM owner_signal"),
        "enriched": enriched,
        "elapsed_sec": round(time.time() - t0, 1),
        "db": os.path.abspath(args.db),
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
