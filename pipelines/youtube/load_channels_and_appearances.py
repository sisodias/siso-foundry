#!/usr/bin/env python3
"""Load YouTube channels as people, and guest appearances as edges.

WHY THIS EXISTS
---------------
The YouTube leg has 34 people and was written off as "fully loaded" because the
source has only 97 rows. That was true about the ROWS and wrong about the
STRUCTURE. The queue holds two distinct sets of people and only one was loaded:

    sqlite> select count(*), count(distinct person_slug), count(distinct channel_name)
            from people_video_queue where channel_name != '';
    97 | 24 | 25

  * person_slug  = the GUEST -- the person the video is about. Loaded already.
  * channel_name = the HOST -- who made it. NEVER loaded, and most of them are
                   named individuals, not brands:

        Matthew Berman|21   David Ondrej|12   Dwarkesh Patel|2
        Networkchuck|2      Ai Engineer|9     Latent Space|7

WHY THIS MATTERS OUT OF PROPORTION TO ITS SIZE. Every other edge in this graph
is person->artifact: someone wrote a repo, authored a book. A guest appearance
is person->artifact->person, which makes it the ONLY relational data available.
The graph has no person<->person representation at all -- round 4 measured the
naive co-membership alternative at 720,107,620 pairs and rejected it. This is
small (97 videos) but it is real: "who has appeared with whom" cannot be
answered today by any means.

WHAT THIS WRITES:
  1. person rows for hosts (kind='unknown' -- see below), origin='youtube'
  2. external_ids(youtube_channel_id) where the queue has one
  3. person_content(domain='youtube_video', role='host') for the host
  4. meta_json.co_appearances on the GUEST edge -- the hosts they appeared with

CHANNEL IS NOT ALWAYS A PERSON. 'Ai Grid', 'WIRED' and
'Archive upload / Art Bell-Coast to Coast AM material' are not humans. Rather
than guess, hosts land as kind='unknown', the same honest-null the GitHub owner
loader uses for 238k accounts. One obvious non-person pattern is filtered:
'web_search_seed' is a scrape artifact, not a channel.

ROLE LIVES ON THE EDGE. The schema comment already anticipated host/guest
("host | guest" is named in person_content.role) but nothing ever wrote them.
The same human can host one video and guest on another; that is exactly why v2
moved role off the person.

Usage:
  load_channels_and_appearances.py --queue people_video_queue.sqlite \
      --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import re
import sqlite3
import sys
import time

# Scrape artifacts and obvious non-channels seen in the actual data, not guessed.
NOT_A_CHANNEL = {"web_search_seed", "", "unknown"}


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or None


def load(queue_db, graph_db, apply_changes):
    src = sqlite3.connect(f"file:{queue_db}?mode=ro", uri=True)
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    before = {
        "youtube_people": g.execute(
            "SELECT COUNT(DISTINCT person_id) FROM person_content "
            "WHERE domain LIKE 'youtube%'"
        ).fetchone()[0],
        "youtube_edges": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE domain LIKE 'youtube%'"
        ).fetchone()[0],
        "host_edges": g.execute(
            "SELECT COUNT(*) FROM person_content WHERE role='host'"
        ).fetchone()[0],
    }

    known = {}
    for pid, name in g.execute("SELECT person_id, name FROM person"):
        known[(name or "").lower()] = pid

    rows = src.execute(
        "SELECT video_id, person_slug, person_name, title, channel_name, "
        "       channel_id, published_at, duration_seconds, score "
        "FROM people_video_queue"
    ).fetchall()

    hosts = {}          # slug -> {name, channel_id, videos}
    host_edges = []
    guest_co = {}       # (guest_pid, video_id) -> set(host names)
    stats = {"rows": len(rows), "skipped_no_channel": 0}

    for (video_id, guest_slug, guest_name, title, channel, channel_id,
         published_at, duration, score) in rows:
        chan = (channel or "").strip()
        if chan.lower() in NOT_A_CHANNEL:
            stats["skipped_no_channel"] += 1
            continue
        hslug = slugify(chan)
        if not hslug:
            stats["skipped_no_channel"] += 1
            continue
        # Reuse an existing person if this host is already in the graph by name.
        hpid = known.get(chan.lower(), f"yt:{hslug}")
        h = hosts.setdefault(
            hslug, {"pid": hpid, "name": chan, "channel_id": channel_id or "",
                    "videos": 0}
        )
        h["videos"] += 1

        meta = {"channel": chan}
        if published_at:
            meta["published_at"] = published_at
        if duration:
            meta["duration_seconds"] = duration
        if guest_name:
            meta["guest"] = guest_name
        host_edges.append(
            (hpid, "youtube_video", video_id, "host",
             float(score or 0), (title or "")[:200] or None,
             "video_queue", published_at or now, json.dumps(meta))
        )
        if guest_slug:
            guest_co.setdefault(guest_slug, set()).add(chan)

    new_people, new_extids = [], []
    for hslug, h in hosts.items():
        if h["pid"].startswith("yt:"):
            new_people.append(
                (h["pid"], h["name"], h["name"], "unknown", "linked",
                 "youtube", float(h["videos"]), now)
            )
        if h["channel_id"]:
            new_extids.append(
                (h["pid"], "youtube_channel_id", h["channel_id"], 1.0,
                 "video_queue")
            )

    # Co-appearance onto the guest's existing edges.
    guest_updates = []
    for guest_slug, channels in guest_co.items():
        for (pid, ref, meta_json) in g.execute(
            "SELECT person_id, content_ref, meta_json FROM person_content "
            "WHERE person_id=? AND domain LIKE 'youtube%'", (guest_slug,)
        ):
            try:
                meta = json.loads(meta_json or "{}")
            except (ValueError, TypeError):
                meta = {}
            meta["co_appearances"] = sorted(channels)
            guest_updates.append((json.dumps(meta), pid, ref))

    summary = dict(stats)
    summary.update({
        "distinct_hosts": len(hosts),
        "new_host_people": len(new_people),
        "host_edges": len(host_edges),
        "host_channel_ids": len(new_extids),
        "guest_edges_updated": len(guest_updates),
        "before": before,
        "applied": bool(apply_changes),
    })

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person "
            "(person_id,name,sort_name,kind,state,origin,rank_score,built_at) "
            "VALUES (?,?,?,?,?,?,?,?)", new_people,
        )
        g.executemany(
            "INSERT OR IGNORE INTO external_ids "
            "(person_id,platform,value,confidence,source) VALUES (?,?,?,?,?)",
            new_extids,
        )
        g.executemany(
            "INSERT OR IGNORE INTO person_content "
            "(person_id,domain,content_ref,role,score,title,source,observed_at,"
            " meta_json) VALUES (?,?,?,?,?,?,?,?,?)", host_edges,
        )
        g.executemany(
            "UPDATE person_content SET meta_json=? "
            "WHERE person_id=? AND content_ref=?", guest_updates,
        )
        g.commit()
        summary["after"] = {
            "youtube_people": g.execute(
                "SELECT COUNT(DISTINCT person_id) FROM person_content "
                "WHERE domain LIKE 'youtube%'"
            ).fetchone()[0],
            "youtube_edges": g.execute(
                "SELECT COUNT(*) FROM person_content WHERE domain LIKE 'youtube%'"
            ).fetchone()[0],
            "host_edges": g.execute(
                "SELECT COUNT(*) FROM person_content WHERE role='host'"
            ).fetchone()[0],
        }

    g.close()
    src.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--queue", required=True)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.queue, a.graph, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
