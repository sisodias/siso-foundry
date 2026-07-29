#!/usr/bin/env python3
"""Research-topics registry — the canonical home for broad research BUCKETS.

The contract agents use: `add-or-create` finds a similar existing bucket OR makes a new one,
so the registry doesn't fill with near-duplicates. Buckets are never deleted (merge/dormant only).

Usage:
  topics.py init                                  # apply migration (idempotent)
  topics.py list [--status active] [--tree]       # show buckets
  topics.py add-or-create "Agent Orchestration" \\
       --by agent:research-lead --rationale "found 40 swarm repos, no orchestration bucket" \\
       [--desc "..."] [--keywords swarm,orchestration] [--gh-topics multi-agent,orchestration] \\
       [--parent ai-agents] [--tier 2] [--threshold 0.6]
       # -> prints "MATCHED <slug>" (similar exists) or "CREATED <slug>"
  topics.py link <slug> --kind repo --ref <canonical_id> --by agent:x [--note ...]
  topics.py show <slug>                            # bucket + its linked artifacts + counts
  topics.py merge <from_slug> <into_slug> --by ... # fold one bucket into another (never deletes)
  topics.py suggest "some text"                    # which existing bucket(s) best match (no write)
"""
import argparse, json, os, re, sqlite3, sys, difflib
from datetime import datetime, timezone
from pathlib import Path

DB = os.environ.get(
    "FOUNDRY_TOPICS_DB",
    str(Path.home() / ".local" / "share" / "siso-foundry" / "research-topics.sqlite"),
)
MIGRATION = Path(__file__).resolve().parent / "migrations" / "030_research_topics.sql"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return re.sub(r"-+", "-", s)


def connect():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def ensure_schema(con):
    con.executescript(MIGRATION.read_text())
    con.commit()


def _norm(s):
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


def best_matches(con, text, limit=5):
    """Fuzzy-match text against existing buckets (title + description + keywords)."""
    rows = con.execute("SELECT slug, title, description, keywords FROM research_topics WHERE status='active'").fetchall()
    target = _norm(text)
    scored = []
    for r in rows:
        hay = _norm(" ".join(filter(None, [r["title"], r["description"] or "", r["keywords"] or ""])))
        ratio = difflib.SequenceMatcher(None, target, _norm(r["title"])).ratio()
        # token overlap boost: shared words between input and the bucket's text
        tw = set(target.split()); hw = set(hay.split())
        overlap = len(tw & hw) / max(1, len(tw))
        score = max(ratio, 0.5 * ratio + 0.5 * overlap)
        scored.append((score, r["slug"], r["title"]))
    scored.sort(reverse=True)
    return scored[:limit]


def cmd_init(_a):
    con = connect(); ensure_schema(con)
    n = con.execute("SELECT COUNT(*) FROM research_topics").fetchone()[0]
    print(f"research_topics ready ({n} buckets) at {DB}")


def cmd_add_or_create(a):
    con = connect(); ensure_schema(con)
    matches = best_matches(con, f"{a.title} {a.desc or ''} {a.keywords or ''}")
    if matches and matches[0][0] >= a.threshold:
        score, slug, title = matches[0]
        print(f"MATCHED {slug}  (\"{title}\", score {score:.2f})  — filing under existing bucket, not creating a duplicate.")
        print(f"  (override with a lower --threshold or a more distinct title to force-create)")
        return
    slug = a.slug or slugify(a.title)
    # collision: same slug already exists -> treat as match
    existing = con.execute("SELECT slug FROM research_topics WHERE slug=?", (slug,)).fetchone()
    if existing:
        print(f"MATCHED {slug}  (exact slug exists)")
        return
    ts = now()
    con.execute(
        """INSERT INTO research_topics
           (slug,title,description,parent_slug,keywords,gh_topics,tier,weight,status,
            created_by,rationale,source,created_at,updated_at)
           VALUES (?,?,?,?,?,?,?,?, 'active', ?,?,?,?,?)""",
        (slug, a.title, a.desc, a.parent,
         json.dumps([k.strip() for k in a.keywords.split(",")]) if a.keywords else None,
         json.dumps([k.strip() for k in a.gh_topics.split(",")]) if a.gh_topics else None,
         a.tier, a.weight, a.by, a.rationale, a.source, ts, ts),
    )
    con.commit()
    print(f"CREATED {slug}  (\"{a.title}\")")
    if matches:
        print(f"  nearest existing was \"{matches[0][2]}\" at {matches[0][0]:.2f} (< threshold {a.threshold})")


def cmd_suggest(a):
    con = connect(); ensure_schema(con)
    for score, slug, title in best_matches(con, a.text):
        print(f"  {score:.2f}  {slug}  ({title})")


def cmd_link(a):
    con = connect(); ensure_schema(con)
    if not con.execute("SELECT 1 FROM research_topics WHERE slug=?", (a.slug,)).fetchone():
        print(f"ERROR: no bucket '{a.slug}' — create it first with add-or-create", file=sys.stderr); sys.exit(2)
    try:
        con.execute(
            """INSERT INTO research_topic_links (slug,artifact_kind,artifact_ref,note,linked_by,linked_at)
               VALUES (?,?,?,?,?,?)""",
            (a.slug, a.kind, a.ref, a.note, a.by, now()))
        con.commit()
        print(f"LINKED {a.kind}:{a.ref[:60]} -> {a.slug}")
    except sqlite3.IntegrityError:
        print(f"already linked: {a.kind}:{a.ref[:60]} -> {a.slug}")


def cmd_list(a):
    con = connect(); ensure_schema(con)
    where = "WHERE status=?" if a.status else ""
    args = (a.status,) if a.status else ()
    rows = con.execute(
        f"""SELECT t.slug,t.title,t.tier,t.status,t.parent_slug,
                   (SELECT COUNT(*) FROM research_topic_links l WHERE l.slug=t.slug) AS links
            FROM research_topics t {where} ORDER BY COALESCE(t.tier,9), t.title""", args).fetchall()
    if not rows:
        print("(no buckets yet — run init + seed)"); return
    for r in rows:
        ind = "  " if r["parent_slug"] else ""
        tier = f"T{r['tier']}" if r["tier"] else "—"
        print(f"{ind}{r['slug']:<28} {tier:<3} links={r['links']:<4} {r['title']}")
    print(f"\n{len(rows)} buckets")


def cmd_show(a):
    con = connect(); ensure_schema(con)
    t = con.execute("SELECT * FROM research_topics WHERE slug=?", (a.slug,)).fetchone()
    if not t:
        print(f"no bucket '{a.slug}'", file=sys.stderr); sys.exit(2)
    for k in t.keys():
        if t[k] is not None:
            print(f"  {k}: {t[k]}")
    links = con.execute(
        "SELECT artifact_kind, COUNT(*) n FROM research_topic_links WHERE slug=? GROUP BY artifact_kind", (a.slug,)).fetchall()
    print("  links:")
    for l in links:
        print(f"    {l['artifact_kind']}: {l['n']}")


def cmd_merge(a):
    con = connect(); ensure_schema(con)
    for s in (a.from_slug, a.into_slug):
        if not con.execute("SELECT 1 FROM research_topics WHERE slug=?", (s,)).fetchone():
            print(f"ERROR: no bucket '{s}'", file=sys.stderr); sys.exit(2)
    # move links, mark source merged (NEVER delete)
    con.execute("UPDATE OR IGNORE research_topic_links SET slug=? WHERE slug=?", (a.into_slug, a.from_slug))
    con.execute("UPDATE research_topics SET status='merged', merged_into=?, updated_at=? WHERE slug=?",
                (a.into_slug, now(), a.from_slug))
    con.commit()
    print(f"MERGED {a.from_slug} -> {a.into_slug} (source kept as status=merged, never deleted)")


def build():
    p = argparse.ArgumentParser(prog="topics.py")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init").set_defaults(fn=cmd_init)

    a = sub.add_parser("add-or-create")
    a.add_argument("title")
    a.add_argument("--by", required=True)
    a.add_argument("--rationale", default=None)
    a.add_argument("--desc", default=None)
    a.add_argument("--keywords", default=None)
    a.add_argument("--gh-topics", dest="gh_topics", default=None)
    a.add_argument("--parent", default=None)
    a.add_argument("--tier", type=int, default=None)
    a.add_argument("--weight", type=float, default=None)
    a.add_argument("--slug", default=None)
    a.add_argument("--source", default=None)
    a.add_argument("--threshold", type=float, default=0.6)
    a.set_defaults(fn=cmd_add_or_create)

    s = sub.add_parser("suggest"); s.add_argument("text"); s.set_defaults(fn=cmd_suggest)

    l = sub.add_parser("link")
    l.add_argument("slug"); l.add_argument("--kind", required=True)
    l.add_argument("--ref", required=True); l.add_argument("--by", required=True)
    l.add_argument("--note", default=None); l.set_defaults(fn=cmd_link)

    ls = sub.add_parser("list"); ls.add_argument("--status", default=None)
    ls.add_argument("--tree", action="store_true"); ls.set_defaults(fn=cmd_list)

    sh = sub.add_parser("show"); sh.add_argument("slug"); sh.set_defaults(fn=cmd_show)

    m = sub.add_parser("merge"); m.add_argument("from_slug"); m.add_argument("into_slug")
    m.add_argument("--by", required=True); m.set_defaults(fn=cmd_merge)
    return p


if __name__ == "__main__":
    args = build().parse_args()
    args.fn(args)
