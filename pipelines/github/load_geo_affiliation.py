#!/usr/bin/env python3
"""Normalise GitHub location and company into queryable topic layers.

WHY THIS EXISTS
---------------
The GraphQL enrich collects two fields the REST loader never did:

    location | 17473
    company  |  8028

Nothing consumes them, and as raw strings they are barely queryable -- the same
place and the same employer appear under many spellings:

    San Francisco, CA|410      Google |142
    San Francisco    |362      @google| 57
    Beijing, China   |319      Microsoft|97
    Beijing          |317

"Who works on databases in Berlin" and "who at Google does highly-rated work"
are natural questions for a people graph and are unanswerable while the values
stay unnormalised.

WHAT THIS WRITES
  person_topic(scheme='geo')  normalised place, plus a country roll-up
  person_topic(scheme='org')  normalised employer

WHY TOPICS AND NOT COLUMNS. Both are many-to-one attributes that queries want to
filter on, which is exactly what person_topic is for, and it keeps them beside
the subject layers so one query shape serves all of them. The raw strings stay
in external_ids untouched -- normalisation is lossy and the original is the
record of what GitHub actually said.

NORMALISATION IS DELIBERATELY CONSERVATIVE. This is string tidying, not
geocoding: lowercase, strip @ and leading punctuation, drop obvious noise, and
map a small explicit table of high-frequency aliases observed in THIS data
("san francisco, ca" -> "san francisco"). It does NOT attempt to resolve
"Bay Area" or "remote" to a place, and unrecognised values pass through
normalised-but-unmapped rather than being guessed at or dropped. A wrong
geography is worse than a missing one.

COUNTRY ROLL-UP is only emitted where the string names a country explicitly or
carries a known city->country mapping. A city we do not recognise yields a geo
topic and no country, rather than a guess.

Usage:
  load_geo_affiliation.py --graph people_v2.sqlite [--apply]
"""
import argparse
import json
import re
import sqlite3
import sys
import time

# High-frequency aliases observed in the actual data, not invented.
PLACE_ALIAS = {
    "san francisco, ca": "san francisco",
    "san francisco, california": "san francisco",
    "sf": "san francisco",
    "london, uk": "london",
    "london, england": "london",
    "beijing, china": "beijing",
    "shanghai, china": "shanghai",
    "tokyo, japan": "tokyo",
    "berlin, germany": "berlin",
    "paris, france": "paris",
    "usa": "united states",
    "u.s.a.": "united states",
    "us": "united states",
    "united states of america": "united states",
    "uk": "united kingdom",
    "new york, ny": "new york",
    "new york city": "new york",
    "nyc": "new york",
    "seattle, wa": "seattle",
    "boston, ma": "boston",
    "toronto, canada": "toronto",
    "bangalore, india": "bangalore",
    "bengaluru": "bangalore",
    "moscow, russia": "moscow",
    "amsterdam, netherlands": "amsterdam",
}

CITY_COUNTRY = {
    "san francisco": "united states", "new york": "united states",
    "seattle": "united states", "boston": "united states",
    "los angeles": "united states", "austin": "united states",
    "london": "united kingdom", "cambridge": "united kingdom",
    "beijing": "china", "shanghai": "china", "shenzhen": "china",
    "hangzhou": "china", "guangzhou": "china", "chengdu": "china",
    "tokyo": "japan", "berlin": "germany", "munich": "germany",
    "paris": "france", "amsterdam": "netherlands", "toronto": "canada",
    "vancouver": "canada", "bangalore": "india", "mumbai": "india",
    "delhi": "india", "singapore": "singapore", "seoul": "south korea",
    "sydney": "australia", "melbourne": "australia", "moscow": "russia",
    "warsaw": "poland", "madrid": "spain", "barcelona": "spain",
    "stockholm": "sweden", "zurich": "switzerland", "tel aviv": "israel",
}

COUNTRIES = set(CITY_COUNTRY.values()) | {
    "brazil", "italy", "mexico", "argentina", "norway", "denmark",
    "finland", "belgium", "austria", "portugal", "ireland", "turkey",
    "indonesia", "vietnam", "thailand", "ukraine", "romania", "czechia",
    "new zealand", "south africa", "nigeria", "egypt", "pakistan", "iran",
}

# Values that name no place at all. Passing these through would create topics
# like 'remote' and 'earth' sitting beside real cities.
PLACE_NOISE = {
    "remote", "earth", "world", "internet", "everywhere", "worldwide",
    "the internet", "localhost", "/dev/null", "home", "global", "n/a",
    "somewhere", "planet earth", "moon", "mars", "space", "anywhere",
}

ORG_NOISE = {
    "freelance", "self-employed", "self employed", "independent", "none",
    "student", "unemployed", "open source", "opensource", "n/a", "me",
    "myself", "personal", "home", "-", "--",
}


def norm_place(raw):
    s = (raw or "").strip().lower()
    s = re.sub(r"[​-‏﻿]", "", s)
    s = re.sub(r"^[^\w]+|[^\w)]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    if not s or len(s) > 60 or s in PLACE_NOISE:
        return None, None
    s = PLACE_ALIAS.get(s, s)
    if s in PLACE_NOISE:
        return None, None
    country = s if s in COUNTRIES else CITY_COUNTRY.get(s)
    return s, country


def norm_org(raw):
    s = (raw or "").strip().lower()
    s = re.sub(r"[​-‏﻿]", "", s)
    s = s.lstrip("@")
    s = re.sub(r"^[^\w]+|[^\w)]+$", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[,.]?\s*(inc|llc|ltd|gmbh|corp|co)\.?$", "", s)
    if not s or len(s) > 60 or s in ORG_NOISE:
        return None
    return s


def load(graph_db, apply_changes):
    g = sqlite3.connect(graph_db, timeout=600.0)
    g.execute("PRAGMA busy_timeout=600000")

    before = {
        s: g.execute(
            "SELECT COUNT(*) FROM person_topic WHERE scheme=?", (s,)
        ).fetchone()[0]
        for s in ("geo", "org")
    }

    rows, stats = [], {
        "location_raw": 0, "location_kept": 0, "country_rollups": 0,
        "company_raw": 0, "company_kept": 0,
    }
    seen = set()

    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='location'"
    ):
        stats["location_raw"] += 1
        place, country = norm_place(value)
        if not place:
            continue
        stats["location_kept"] += 1
        if (pid, place, "geo") not in seen:
            seen.add((pid, place, "geo"))
            rows.append((pid, place, "geo", 1.0, "github_graphql"))
        if country and country != place and (pid, country, "geo") not in seen:
            seen.add((pid, country, "geo"))
            stats["country_rollups"] += 1
            rows.append((pid, country, "geo", 0.8, "github_graphql"))

    for pid, value in g.execute(
        "SELECT person_id, value FROM external_ids WHERE platform='company'"
    ):
        stats["company_raw"] += 1
        org = norm_org(value)
        if not org:
            continue
        stats["company_kept"] += 1
        if (pid, org, "org") not in seen:
            seen.add((pid, org, "org"))
            rows.append((pid, org, "org", 1.0, "github_graphql"))

    summary = dict(stats)
    summary["topic_rows"] = len(rows)
    summary["before"] = before
    summary["applied"] = bool(apply_changes)

    if apply_changes:
        g.executemany(
            "INSERT OR IGNORE INTO person_topic "
            "(person_id,topic,scheme,weight,source) VALUES (?,?,?,?,?)", rows,
        )
        g.commit()
        summary["after"] = {
            s: g.execute(
                "SELECT COUNT(*) FROM person_topic WHERE scheme=?", (s,)
            ).fetchone()[0]
            for s in ("geo", "org")
        }

    g.close()
    return summary


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--graph", required=True)
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    t = time.time()
    s = load(a.graph, a.apply)
    s["elapsed_s"] = round(time.time() - t, 2)
    print(json.dumps(s, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
