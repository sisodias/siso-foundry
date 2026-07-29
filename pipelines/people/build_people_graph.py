#!/usr/bin/env python3
"""Foundry — build the unified People graph by CONNECTING the 3 existing pieces.

This does NOT rebuild people data. It adopts + stitches:

  1. PERSON MASTER  (registry):  leaderboard.yaml          -> person rows (origin='registry')
  2. JOIN TABLE     (yt videos): people_video_queue.sqlite -> person_content (youtube_video)
  3a. YOUTUBE SAT   (channels):  channel_rankings.json     -> person_content (youtube_channel)
                                                              + youtube_channel_id external_ids
  3b. GITHUB SAT    (owners):    identity.sqlite repo_card  -> github owners materialized as
                                 person rows / external_ids + person_content (github)
                                 (READ-ONLY: another agent is converging identity.sqlite)

People ranking primitive: REUSED from the YouTube ChannelScorer 6-dim engine
(scripts/scoring/engine.py -> ChannelScorer.calculate_overall_score + get_tier).
For github owners we map owner aggregates onto the same 6 dims, so one scorer ranks both.

Run location: the MINI (it owns the YouTube satellite, the scorer, and identity.sqlite).
The two laptop-only inputs (current leaderboard.yaml + people_video_queue.sqlite) are
staged next to this script before running. Canonical output is the mini vault:
  ~/foundry-data/domains/people/people.sqlite   (written locally — never over a net mount).

Usage:
  python3 build_people_graph.py \
      --leaderboard <leaderboard.yaml> \
      --video-queue <people_video_queue.sqlite> \
      --rankings    <channel_rankings.json> \
      --identity    <identity.sqlite>            (opened ?mode=ro) \
      --scorer-dir  <.../youtube-ai-research/scripts> \
      --out         <people.sqlite> \
      --top-owners  300
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

NOW = datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# ChannelScorer primitive (reused, not reinvented)
# --------------------------------------------------------------------------- #
def load_scorer(scorer_dir: Path):
    """Import the real ChannelScorer + get_tier from the youtube-ai-research package."""
    sys.path.insert(0, str(scorer_dir))
    from scoring.engine import ChannelScorer  # noqa: E402
    from scoring.weights import get_tier      # noqa: E402
    return ChannelScorer(), get_tier


def normalize_name(name: str) -> str:
    return " ".join(name.lower().replace(".", " ").replace("-", " ").split())


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #
def init_db(out: Path, schema_sql: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(out))
    con.executescript(schema_sql.read_text())
    return con


# --------------------------------------------------------------------------- #
# Piece 1 — registry person masters
# --------------------------------------------------------------------------- #
def import_registry(con, leaderboard: Path, handle_index: dict[str, str]) -> dict[str, str]:
    """Insert 140 registry people. Returns {normalized_name: person_id}.
    Also fills handle_index {lowercased_handle: person_id} from x/youtube handles —
    this is what lets a github login (e.g. 'karpathy') stitch to a registry person
    whose display name ('Andrej Karpathy') would never string-match the login."""
    data = yaml.safe_load(leaderboard.read_text()) or {}
    people = data.get("people", [])
    name_index: dict[str, str] = {}
    for p in people:
        name = (p.get("name") or "").strip()
        if not name:
            continue
        pid = p.get("slug") or normalize_name(name).replace(" ", "-")
        con.execute(
            "INSERT OR REPLACE INTO person"
            "(person_id,name,primary_tier,origin,line,role,topics_json,rank_score,built_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (pid, name, p.get("tier"), "registry", p.get("line"), p.get("role"),
             json.dumps(p.get("topics", [])), None, NOW),
        )
        # external ids from registry sources (x handle, youtube handle, website)
        for src in p.get("sources", []):
            t, url = src.get("type", ""), src.get("url", "")
            if t == "x" and "x.com/" in url:
                h = url.rstrip("/").split("/")[-1].lstrip("@")
                con.execute("INSERT OR IGNORE INTO external_ids VALUES (?,?,?)",
                            (pid, "x_handle", "@" + h))
                handle_index.setdefault(h.lower(), pid)
            elif t == "youtube":
                h = url.rstrip("/").split("/")[-1].lstrip("@")
                con.execute("INSERT OR IGNORE INTO external_ids VALUES (?,?,?)",
                            (pid, "youtube_handle", url.rstrip("/").split("/")[-1]))
                handle_index.setdefault(h.lower(), pid)
            elif t == "official":
                con.execute("INSERT OR IGNORE INTO external_ids VALUES (?,?,?)",
                            (pid, "website", url))
        name_index[normalize_name(name)] = pid
    return name_index


# --------------------------------------------------------------------------- #
# Piece 2 — people_video_queue joins (person -> video)
# --------------------------------------------------------------------------- #
def import_video_joins(con, video_queue: Path, name_index: dict[str, str]) -> int:
    src = sqlite3.connect(f"file:{video_queue}?mode=ro", uri=True)
    src.row_factory = sqlite3.Row
    rows = src.execute(
        "SELECT video_id,person_slug,person_name,title,channel_name,channel_id,score FROM people_video_queue"
    ).fetchall()
    src.close()
    n = 0
    for r in rows:
        pid = r["person_slug"]
        # ensure the person exists (some queue slugs may not be in the registry list)
        exists = con.execute("SELECT 1 FROM person WHERE person_id=?", (pid,)).fetchone()
        if not exists:
            con.execute(
                "INSERT OR IGNORE INTO person"
                "(person_id,name,primary_tier,origin,line,role,topics_json,rank_score,built_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, r["person_name"], None, "registry", None, None, "[]", None, NOW),
            )
            name_index[normalize_name(r["person_name"])] = pid
        con.execute(
            "INSERT OR REPLACE INTO person_content"
            "(person_id,domain,content_ref,score,title,meta_json) VALUES (?,?,?,?,?,?)",
            (pid, "youtube_video", r["video_id"], r["score"], r["title"],
             json.dumps({"channel_name": r["channel_name"], "channel_id": r["channel_id"]})),
        )
        n += 1
    return n


# --------------------------------------------------------------------------- #
# Piece 3a — YouTube channel rankings (creators as youtube satellites)
# Matched to existing people by name; satellite-only creators are added as people.
# --------------------------------------------------------------------------- #
def import_youtube_channels(con, rankings: Path, name_index: dict[str, str]) -> tuple[int, int]:
    data = json.loads(rankings.read_text())
    channels = data.get("overall", [])
    linked, created = 0, 0
    for ch in channels:
        cname = ch.get("channel_name", "").strip()
        if not cname:
            continue
        cid = ch.get("channel_id") or ch.get("slug")
        score = ch.get("overall_score")
        nkey = normalize_name(cname)
        pid = name_index.get(nkey)
        if pid is None:
            # satellite-only creator -> new person, origin youtube
            pid = "yt:" + (ch.get("slug") or nkey.replace(" ", "_"))
            con.execute(
                "INSERT OR REPLACE INTO person"
                "(person_id,name,primary_tier,origin,line,role,topics_json,rank_score,built_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, cname, ch.get("tier"), "youtube", None, None,
                 json.dumps(ch.get("categories", [])), score, NOW),
            )
            name_index[nkey] = pid
            created += 1
        else:
            linked += 1
        if cid:
            con.execute("INSERT OR IGNORE INTO external_ids VALUES (?,?,?)",
                        (pid, "youtube_channel_id", cid))
        con.execute(
            "INSERT OR REPLACE INTO person_content"
            "(person_id,domain,content_ref,score,title,meta_json) VALUES (?,?,?,?,?,?)",
            (pid, "youtube_channel", str(cid or ch.get("slug")), score, cname,
             json.dumps({"tier": ch.get("tier"), "rank": ch.get("overall_rank"),
                         "component_scores": ch.get("component_scores", {})})),
        )
    return linked, created


# --------------------------------------------------------------------------- #
# Piece 3b — GitHub owners materialized from repo_card (READ-ONLY identity.sqlite)
# Ranked by repo count + saucy count + max liftability, scored via ChannelScorer.
# --------------------------------------------------------------------------- #
def import_github_owners(con, identity: Path, scorer, get_tier, name_index, handle_index,
                         top_n, always_include):
    ro = sqlite3.connect(f"file:{identity}?mode=ro", uri=True)
    ro.row_factory = sqlite3.Row

    # Pass 1: ONE scan of repo_card -> per-owner repo count, star aggregates, top repo.
    # The substr() owner key is computed once per row in a single GROUP BY (fast),
    # never re-scanned per owner (the slow correlated-subquery shape we replaced).
    owners: dict[str, dict] = {}
    for rc in ro.execute(
        "SELECT substr(full_name,1,instr(full_name,'/')-1) AS owner, full_name, stars "
        "FROM repo_card WHERE full_name LIKE '%/%'"):
        o = rc["owner"]
        st = rc["stars"] or 0
        d = owners.get(o)
        if d is None:
            owners[o] = {"owner": o, "n_repos": 1, "max_stars": st,
                         "total_stars": st, "top_repo": rc["full_name"], "_top_stars": st,
                         "saucy_cnt": 0, "max_lift": 0}
        else:
            d["n_repos"] += 1
            d["total_stars"] += st
            if st > d["max_stars"]:
                d["max_stars"] = st
            if st > d["_top_stars"]:
                d["_top_stars"] = st
                d["top_repo"] = rc["full_name"]

    # Pass 2: ONE scan of repo_category -> per-owner saucy count + max liftability.
    for cat in ro.execute(
        "SELECT substr(full_name,1,instr(full_name,'/')-1) AS owner, saucy, liftability "
        "FROM repo_category WHERE full_name LIKE '%/%'"):
        d = owners.get(cat["owner"])
        if d is None:
            continue
        d["saucy_cnt"] += (cat["saucy"] or 0)
        if (cat["liftability"] or 0) > d["max_lift"]:
            d["max_lift"] = cat["liftability"]
    ro.close()

    # Rank owners by repo count + saucy weight + liftability; take top_n.
    ranked = sorted(
        owners.values(),
        key=lambda d: d["n_repos"] * 1.0 + d["saucy_cnt"] * 5.0 + d["max_lift"] * 0.1,
        reverse=True,
    )
    rows = ranked[:top_n]

    # Ensure stitch-critical owners are present even if outside top_n.
    have = {r["owner"] for r in rows}
    extra = [owners[login] for login in always_include
             if login not in have and login in owners]

    materialized = 0
    for r in list(rows) + extra:
        owner = r["owner"]
        # Map owner aggregates onto the ChannelScorer 6-dim space so the SAME engine ranks people.
        # knowledge<-saucy density, impact<-fame(stars), consistency<-breadth(repos),
        # quality<-liftability, novelty<-saucy presence, engagement<-stars/repo proxy.
        import math
        n_repos = r["n_repos"] or 1
        comp = {
            "knowledge":   min(100, (r["saucy_cnt"] or 0) / n_repos * 100 + 30),
            "engagement":  min(100, math.log10((r["total_stars"] or 0) + 10) * 12),
            "consistency": min(100, math.log10(n_repos + 1) * 35),
            "quality":     float(r["max_lift"] or 0),
            "impact":      min(100, math.log10((r["max_stars"] or 0) + 10) * 16),
            "novelty":     60.0 if (r["saucy_cnt"] or 0) > 0 else 40.0,
        }
        score = scorer.calculate_overall_score(comp)
        tier = get_tier(score)

        # Stitch order: (1) github login == a known x/youtube handle (the strong key —
        # this is what links 'karpathy' to registry 'andrej-karpathy'); else
        # (2) display-name match; else (3) new github-origin person.
        nkey = normalize_name(owner)
        pid = handle_index.get(owner.lower()) or name_index.get(nkey)
        if pid is None:
            pid = "gh:" + owner
            con.execute(
                "INSERT OR REPLACE INTO person"
                "(person_id,name,primary_tier,origin,line,role,topics_json,rank_score,built_at)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (pid, owner, tier, "github", None, "github owner", "[]", score, NOW),
            )
            name_index[nkey] = pid
        else:
            # existing registry/youtube person who is ALSO a github owner -> keep id, set score
            con.execute("UPDATE person SET rank_score=COALESCE(rank_score,?) WHERE person_id=?",
                        (score, pid))
        con.execute("INSERT OR IGNORE INTO external_ids VALUES (?,?,?)",
                    (pid, "github_login", owner))
        con.execute(
            "INSERT OR REPLACE INTO person_content"
            "(person_id,domain,content_ref,score,title,meta_json) VALUES (?,?,?,?,?,?)",
            (pid, "github", r["top_repo"] or owner, float(r["max_stars"] or 0),
             r["top_repo"],
             json.dumps({"n_repos": r["n_repos"], "saucy_cnt": r["saucy_cnt"],
                         "max_lift": r["max_lift"], "rank_score": score, "tier": tier})),
        )
        materialized += 1
    return materialized


# --------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--leaderboard", required=True, type=Path)
    ap.add_argument("--video-queue", required=True, type=Path)
    ap.add_argument("--rankings", required=True, type=Path)
    ap.add_argument("--identity", required=True, type=Path)
    ap.add_argument("--scorer-dir", required=True, type=Path)
    ap.add_argument("--schema", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--top-owners", type=int, default=300)
    args = ap.parse_args()

    if args.out.exists():
        args.out.unlink()  # fresh build
    args.out.parent.mkdir(parents=True, exist_ok=True)

    scorer, get_tier = load_scorer(args.scorer_dir)
    con = init_db(args.out, args.schema)

    handle_index: dict[str, str] = {}
    name_index = import_registry(con, args.leaderboard, handle_index)
    n_videos = import_video_joins(con, args.video_queue, name_index)
    yt_linked, yt_created = import_youtube_channels(con, args.rankings, name_index)
    n_owners = import_github_owners(
        con, args.identity, scorer, get_tier, name_index, handle_index,
        args.top_owners, always_include=["karpathy"])
    con.commit()
    # Leave the DB in a state where readers can open it ?mode=ro with no sidecar files.
    # (WAL needs a writable -shm to attach; a one-shot build has no concurrent writer,
    # so DELETE journal is the right resting mode for a read-mostly published artifact.)
    con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    con.execute("PRAGMA journal_mode=DELETE")

    # ---- report ----
    cur = con.cursor()
    counts = {
        "person":            cur.execute("SELECT COUNT(*) FROM person").fetchone()[0],
        "registry_people":   cur.execute("SELECT COUNT(*) FROM person WHERE origin='registry'").fetchone()[0],
        "youtube_people":    cur.execute("SELECT COUNT(*) FROM person WHERE origin='youtube'").fetchone()[0],
        "github_people":     cur.execute("SELECT COUNT(*) FROM person WHERE origin='github'").fetchone()[0],
        "external_ids":      cur.execute("SELECT COUNT(*) FROM external_ids").fetchone()[0],
        "person_content":    cur.execute("SELECT COUNT(*) FROM person_content").fetchone()[0],
        "pc_github":         cur.execute("SELECT COUNT(*) FROM person_content WHERE domain='github'").fetchone()[0],
        "pc_yt_video":       cur.execute("SELECT COUNT(*) FROM person_content WHERE domain='youtube_video'").fetchone()[0],
        "pc_yt_channel":     cur.execute("SELECT COUNT(*) FROM person_content WHERE domain='youtube_channel'").fetchone()[0],
    }
    print("=== BUILD COUNTS ===")
    print(json.dumps(counts, indent=2))
    print(f"yt channels: linked-to-existing={yt_linked} new-satellite-people={yt_created}")
    print(f"github owners materialized: {n_owners}")

    # ---- THE STITCH TEST: Karpathy across all 3 layers ----
    print("\n=== STITCH TEST: andrej-karpathy 3-layer proof ===")
    pid = con.execute(
        "SELECT person_id FROM external_ids WHERE platform='github_login' AND value='karpathy'"
    ).fetchone()
    if pid:
        pid = pid[0]
        person = con.execute("SELECT * FROM person WHERE person_id=?", (pid,)).fetchone()
        print(f"person_id = {pid}")
        cols = [d[0] for d in con.execute("SELECT * FROM person WHERE person_id=? LIMIT 1", (pid,)).description]
        print("person:", dict(zip(cols, person)))
        print("external_ids:")
        for row in con.execute("SELECT platform,value FROM external_ids WHERE person_id=?", (pid,)):
            print("   ", row[0], "=", row[1])
        print("layers (person_content domains):")
        for row in con.execute(
            "SELECT domain, COUNT(*) n, MIN(content_ref) ex FROM person_content WHERE person_id=? GROUP BY domain",
            (pid,)):
            print(f"    {row[0]}: {row[1]} (e.g. {row[2]})")
        lc = con.execute("SELECT layer_count FROM v_person_layers WHERE person_id=?", (pid,)).fetchone()
        print(f"layer_count (registry+youtube+github) = {lc[0] if lc else '?'}")
    else:
        print("FAIL: karpathy github_login not found")

    con.close()


if __name__ == "__main__":
    main()
