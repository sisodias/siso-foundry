#!/usr/bin/env python3
"""One query surface over every Foundry domain.

The problem this solves: an agent holding a Frontier Question should not need to
know that books live in books.sqlite, people in people_v2.sqlite, repos in
identity.sqlite, and that each has its own schema. It should ask, and the answer
should already be here.

So this is the "it's here" layer. It attaches every domain database that exists,
resolves the question against all of them, and returns evidence with provenance
attached -- which domain, which record, and enough of an identifier to fetch the
full artifact.

Design notes:
  * Read-only, always. Every attach uses ?mode=ro, per the single-writer law.
  * Missing domains are skipped silently, not fatal. A machine with only books
    still answers book questions; the mini with everything answers everything.
  * Nothing is computed here that a domain already computed. This is a router
    over existing indexes, not a second index that can drift out of sync.
  * Output is JSON by default because the primary caller is an agent, not a human.

Usage:
  ask.py --who "Spinoza"                  who is this, across every domain
  ask.py --about "Justice"                what do we have on this topic
  ask.py --contemporaries "Spinoza"       who was alive at the same time
  ask.py --works "Plato"                  everything a person produced
  ask.py --inventory                      what data exists at all
"""
import argparse
import json
import os
import sqlite3
import sys

# Where each domain's index lives, in resolution order. First hit wins.
# Deliberately a list rather than a config file: the search order IS the policy,
# and burying it in config makes it invisible.
#
# CANONICAL PATHS COME FIRST, cwd-relative names LAST. The original order had it
# the other way round, and the failure is silent rather than loud.
#
# Observed 2026-08-04: run from /tmp this reported 35,834 people; run from ~ it
# reported 280,722 -- same command, same machine, same minute. The file it found
# in /tmp was not junk, which is what makes this dangerous: reading its contents
# shows an earlier checkpoint of this same graph (books 35,363 and registry 140
# identical to the promoted copy, but github 297 against the promoted 245,171 --
# i.e. the state before the GitHub owner load). A plausible, structurally valid,
# months-of-work-missing answer is the worst possible failure mode, because the
# wrong answer looks exactly like the right one.
#
# A bare filename is still honoured last, so working on a local copy remains
# possible -- it just no longer shadows the promoted database by accident.
CANDIDATES = {
    "people": [
        "~/foundry-data/domains/people/people_v2.sqlite",
        "/Volumes/SISO-STORAGE-VAULT/foundry-data/domains/people/people_v2.sqlite",
        "~/foundry-data/domains/people/people.sqlite",
        "people_v2.sqlite",
    ],
    "books": [
        "~/foundry-data/domains/books/books.sqlite",
        "/Volumes/SISO-STORAGE-VAULT/library/_catalog/books.sqlite",
        "books.sqlite",
    ],
    "github": [
        "~/foundry-data/domains/github/identity/identity.sqlite",
        "/Volumes/SISO-STORAGE-VAULT/foundry-data/domains/github/identity/identity.sqlite",
    ],
    "awesome": [
        "pipelines/github/awesome/awesome_catalog.sqlite",
        "~/foundry-data/domains/github/awesome/awesome_catalog.sqlite",
    ],
    "locator": [
        "locator.sqlite",
        "~/foundry-data/domains/books/locator.sqlite",
        "/Volumes/SISO-STORAGE-VAULT/library/_catalog/locator.sqlite",
    ],
}


def resolve():
    """Which domains actually exist on this machine right now."""
    found = {}
    for domain, paths in CANDIDATES.items():
        for p in paths:
            full = os.path.expanduser(p)
            if os.path.exists(full):
                found[domain] = full
                break
    return found


def connect(found):
    """One connection with every available domain attached read-only."""
    if not found:
        return None
    first = next(iter(found.values()))
    con = sqlite3.connect(f"file:{first}?mode=ro", uri=True)
    for name, path in found.items():
        try:
            con.execute(f"ATTACH DATABASE 'file:{path}?mode=ro' AS {name}")
        except sqlite3.Error:
            pass  # already attached as main, or unreadable -- skip, never fail
    return con


def table_exists(con, schema, table):
    try:
        con.execute(f"SELECT 1 FROM {schema}.{table} LIMIT 1")
        return True
    except sqlite3.Error:
        return False


def who(con, found, name):
    """Everything we know about a person, across every domain."""
    out = {"query": name, "matches": []}
    if "people" not in found:
        return out

    rows = []
    if table_exists(con, "people", "person_search"):
        try:
            rows = con.execute(
                """SELECT p.person_id, p.name, p.birth_year, p.death_year,
                          p.kind, p.origin
                   FROM people.person_search s
                   JOIN people.person p ON p.person_id = s.person_id
                   WHERE people.person_search MATCH ? LIMIT 8""",
                (name,),
            ).fetchall()
        except sqlite3.Error:
            rows = []
    if not rows:
        rows = con.execute(
            """SELECT person_id, name, birth_year, death_year, kind, origin
               FROM people.person WHERE name LIKE ? LIMIT 8""",
            (f"%{name}%",),
        ).fetchall()

    for pid, nm, b, d, kind, origin in rows:
        rec = {
            "person_id": pid,
            "name": nm,
            "lived": fmt_life(b, d),
            "kind": kind,
            "first_seen_in": origin,
            "produced": {},
        }
        for domain, n in con.execute(
            "SELECT domain, COUNT(*) FROM people.person_content "
            "WHERE person_id=? GROUP BY 1",
            (pid,),
        ):
            rec["produced"][domain] = n
        rec["_evidence"] = sum(rec["produced"].values())
        if table_exists(con, "people", "person_topic"):
            rec["topics"] = [
                t
                for (t,) in con.execute(
                    "SELECT topic FROM people.person_topic WHERE person_id=? "
                    "ORDER BY weight DESC LIMIT 6",
                    (pid,),
                )
            ]
        out["matches"].append(rec)

    # Best-attested match first. `works()` already does this (it takes
    # max(matches) by content count, with a comment naming the problem), but
    # `who()` returned rows in index order -- so "Spinoza" led with
    # `baruch-spinoza`, a registry record with ZERO edges, while the record
    # holding his 13 books sat second, below several people named Espinoza.
    #
    # Any caller taking matches[0] therefore got an empty person. That is the
    # exact trap that made --contemporaries report nothing while the graph held
    # 457 rows, so the ordering is applied here once rather than left for each
    # consumer to rediscover.
    out["matches"].sort(key=lambda m: -m.get("_evidence", 0))
    return out


def fetchable(con, found, domain, ref):
    """Every route to the actual bytes for one work.

    A reference is an identity, not a location. An agent holding a question
    needs to GET the text, so every record carries its routes: a direct URL it
    can fetch right now, and -- where the archive has been indexed -- a byte
    range so one book can be pulled from a 30 GB container without unpacking it.
    Routes are listed cheapest-first.
    """
    routes = []
    if domain == "book":
        # Always available, no local data required. This is the route that makes
        # the answer useful on a machine that holds none of the corpus.
        routes.append(
            {
                "route": "origin",
                "url": f"https://www.gutenberg.org/ebooks/{ref}.txt.utf-8",
                "note": "direct plaintext, no auth, no local copy needed",
            }
        )
        routes.append(
            {
                "route": "html",
                "url": f"https://www.gutenberg.org/ebooks/{ref}",
                "note": "human reading surface",
            }
        )
        if "locator" in found:
            for container, member, off, ln, uri in con.execute(
                """SELECT container, member, offset, length, uri
                   FROM locator.location WHERE gid=?""",
                (int(ref),),
            ):
                routes.append(
                    {
                        "route": "byte_range",
                        "container": container,
                        "uri": uri,
                        "member": member,
                        "offset": off,
                        "length": ln,
                        "note": "seek+read, or HTTP Range: bytes=%d-%d"
                                % (off, off + ln - 1),
                    }
                )
    elif domain == "github":
        routes.append({"route": "origin", "url": f"https://github.com/{ref}"})
        routes.append(
            {
                "route": "api",
                "url": f"https://api.github.com/repos/{ref}",
                "note": "metadata without cloning",
            }
        )
    elif domain.startswith("youtube"):
        routes.append(
            {"route": "origin", "url": f"https://www.youtube.com/watch?v={ref}"}
        )
    return routes


def works(con, found, name):
    """Everything a person produced, each with routes to the actual bytes."""
    res = who(con, found, name)
    if not res["matches"]:
        return {"query": name, "works": []}
    # Prefer the match that actually has content -- the registry row for a person
    # is often the emptier of two records for the same human.
    best = max(res["matches"], key=lambda m: sum(m["produced"].values()))
    pid = best["person_id"]
    rows = con.execute(
        """SELECT domain, content_ref, role, title FROM people.person_content
           WHERE person_id=? ORDER BY domain, title LIMIT 200""",
        (pid,),
    ).fetchall()
    return {
        "query": name,
        "person": best["name"],
        "person_id": pid,
        "count": len(rows),
        "works": [
            {
                "domain": d,
                "ref": r,
                "role": ro,
                "title": t,
                "fetch": fetchable(con, found, d, r),
            }
            for d, r, ro, t in rows
        ],
    }


def about(con, found, topic):
    """What evidence exists on a topic, across domains."""
    out = {"query": topic, "people": [], "books": []}
    if "people" in found and table_exists(con, "people", "person_topic"):
        out["people"] = [
            {"name": n, "topic": t, "weight": w}
            for n, t, w in con.execute(
                """SELECT p.name, pt.topic, pt.weight
                   FROM people.person_topic pt
                   JOIN people.person p ON p.person_id = pt.person_id
                   WHERE pt.topic LIKE ? ORDER BY pt.weight DESC LIMIT 15""",
                (f"%{topic}%",),
            )
        ]
    if "books" in found:
        out["books"] = [
            {"gid": g, "title": t, "subject": s}
            for g, t, s in con.execute(
                """SELECT b.gid, b.title, s.subject
                   FROM books.book_subject s
                   JOIN books.book b ON b.gid = s.gid
                   WHERE s.subject LIKE ? LIMIT 15""",
                (f"%{topic}%",),
            )
        ]
    return out


def contemporaries(con, found, name):
    """Who was alive at the same time -- intellectual-history adjacency."""
    if "people" not in found or not table_exists(con, "people", "v_contemporaries"):
        return {"query": name, "error": "v_contemporaries unavailable"}
    # Resolve to a person who can actually ANSWER this question -- i.e. one with
    # a birth year -- rather than whichever row the index happens to return
    # first.
    #
    # "Spinoza" matches three people: baruch-spinoza (registry, NO birth year),
    # bk:spinoza, benedictus de|1632-1677 (books, 457 contemporaries), and
    # gh:rmax "R Max Espinoza" (a substring hit). A bare LIMIT 1 picked the
    # registry row and returned an empty list -- the graph knows 457
    # contemporaries and reported none. An empty result that looks like
    # "we have no data" but actually means "you asked the wrong duplicate" is
    # the same failure class as the cwd-shadowed database resolution.
    #
    # Ordering by (birth_year IS NULL) puts dated people first without excluding
    # the undated, so a genuinely dateless person still resolves and simply
    # returns nothing.
    row = con.execute(
        """SELECT person_id, name FROM people.person
           WHERE name LIKE ?
           ORDER BY (birth_year IS NULL), length(name)
           LIMIT 1""",
        (f"%{name}%",),
    ).fetchone()
    if not row:
        return {"query": name, "contemporaries": [], "resolved_to": None}
    pid, resolved_name = row
    return {
        "query": name,
        "resolved_to": {"person_id": pid, "name": resolved_name},
        "contemporaries": [
            {"name": n, "overlap": f"{s}-{e}"}
            for n, s, e in con.execute(
                """SELECT contemporary_name, overlap_start, overlap_end
                   FROM people.v_contemporaries
                   WHERE person_id = ? LIMIT 25""",
                (pid,),
            )
        ],
    }


def inventory(con, found):
    """What data exists at all -- the honest answer to 'what have we got'."""
    inv = {"domains": {}}
    for domain, path in found.items():
        d = {"path": path, "tables": {}}
        for (t,) in con.execute(
            f"SELECT name FROM {domain}.sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ):
            try:
                d["tables"][t] = con.execute(
                    f"SELECT COUNT(*) FROM {domain}.{t}"
                ).fetchone()[0]
            except sqlite3.Error:
                pass
        inv["domains"][domain] = d
    return inv


def fmt_life(b, d):
    if b is None and d is None:
        return None
    f = lambda y: "?" if y is None else (f"{abs(y)} BCE" if y < 0 else str(y))
    return f"{f(b)}-{f(d)}"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--who")
    ap.add_argument("--works")
    ap.add_argument("--about")
    ap.add_argument("--contemporaries")
    ap.add_argument("--inventory", action="store_true")
    a = ap.parse_args()

    found = resolve()
    con = connect(found)
    if con is None:
        print(json.dumps({"error": "no domain databases found",
                          "searched": CANDIDATES}, indent=2))
        return 1

    if a.inventory:
        r = inventory(con, found)
    elif a.who:
        r = who(con, found, a.who)
    elif a.works:
        r = works(con, found, a.works)
    elif a.about:
        r = about(con, found, a.about)
    elif a.contemporaries:
        r = contemporaries(con, found, a.contemporaries)
    else:
        ap.print_help()
        return 2

    r["_domains_available"] = sorted(found)
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
