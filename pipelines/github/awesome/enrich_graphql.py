#!/usr/bin/env python3
"""Bulk repo metadata via GitHub GraphQL, 100 repos per request.

WHY NOT REST
------------
`gh api repos/{owner}/{name}` is one HTTP request and one rate-limit unit per
repo. Enriching 90k repos that way is 90k calls against a 5,000/hr budget --
about 18 hours.

GraphQL lets you alias N repository lookups into ONE query, and the cost is
charged per REQUEST, not per repo. Measured 2026-08-04 against the live API:

    batch=  50 -> cost=1  got=50
    batch= 100 -> cost=1  got=100
    batch= 200 -> cost=1  got=0     <-- silent failure, see below
    batch= 300 -> cost=1  got=0

So 90k repos = 900 requests = 900 points, which fits inside a single hour's
5,000-point budget. ~100x fewer calls than REST.

THE 200 TRAP
------------
Past ~100 aliases the API returns HTTP 200 with `cost: 1` and NO DATA rather
than an error. A naive implementation would sail past it and write an empty
enrichment file while reporting success. BATCH is capped at 100 for that
reason, and every batch verifies it got rows back before advancing.

Output: JSONL compatible with load_enrichment.py.

Usage:
  enrich_graphql.py --db catalog_full.sqlite --out data/enriched_full.jsonl \
      [--min-lists 2] [--limit N] [--resume]
"""
import argparse
import concurrent.futures as cf
import json
import os
import subprocess
import sqlite3
import sys
import threading
import time

BATCH = 100          # measured ceiling; 200 silently returns nothing
FIELDS = ("nameWithOwner stargazerCount forkCount pushedAt createdAt "
          "isArchived isFork description "
          "primaryLanguage{name} repositoryTopics(first:20){nodes{topic{name}}}")


def build_query(chunk):
    parts = []
    for i, full in enumerate(chunk):
        owner, _, name = full.partition("/")
        # Escape quotes/backslashes -- repo names are attacker-adjacent input.
        o = owner.replace("\\", "\\\\").replace('"', '\\"')
        n = name.replace("\\", "\\\\").replace('"', '\\"')
        parts.append(f'r{i}: repository(owner:"{o}",name:"{n}"){{{FIELDS}}}')
    return "query{ rateLimit{cost remaining resetAt} " + " ".join(parts) + " }"


def run_batch(chunk, retries=5):
    """-> (records, remaining) or (None, remaining) on failure."""
    q = build_query(chunk)
    for attempt in range(retries):
        try:
            out = subprocess.run(["gh", "api", "graphql", "-f", f"query={q}"],
                                 capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            time.sleep(5 * (attempt + 1))
            continue
        # `gh` exits non-zero when the response carries ANY GraphQL error --
        # including a single NOT_FOUND for one deleted repo in the batch. The
        # body still holds the other 99 records, so parse stdout FIRST and only
        # treat this as a failure if there is genuinely nothing usable.
        err = (out.stderr or "") + (out.stdout or "")
        if "rate limit" in err.lower() or "RATE_LIMITED" in err:
            return "RATELIMIT", None
        try:
            d = json.loads(out.stdout)
        except json.JSONDecodeError:
            if out.returncode != 0:
                time.sleep(3 * (attempt + 1))
                continue
            time.sleep(3)
            continue
        # GraphQL returns PARTIAL data alongside `errors`: one deleted or
        # renamed repo yields a NOT_FOUND error for that alias while the other
        # 99 resolve fine. Measured -- `Awesome-Windows/Awesome` is gone, and
        # treating its error as a batch failure discarded 99 good records.
        # Always harvest whatever `data` contains, regardless of `errors`.
        data = d.get("data") or {}
        rl = data.get("rateLimit") or {}
        # An empty `data` with no records means the request was throttled or
        # dropped, NOT that every repo is missing. Retry with backoff instead
        # of accepting it -- under concurrency this fires intermittently, and
        # accepting it silently loses 100 repos per occurrence.
        if not any(k != "rateLimit" and v for k, v in data.items()):
            time.sleep(2 * (attempt + 1))
            continue

        recs = []
        for k, v in data.items():
            if k == "rateLimit" or not v:
                continue        # null = repo renamed/deleted; expected, skip
            topics = [t["topic"]["name"]
                      for t in ((v.get("repositoryTopics") or {}).get("nodes") or [])]
            recs.append({
                "full_name": v["nameWithOwner"],
                "stars": v.get("stargazerCount"),
                "forks": v.get("forkCount"),
                "language": (v.get("primaryLanguage") or {}).get("name"),
                "description": v.get("description"),
                "pushed_at": v.get("pushedAt"),
                "created_at": v.get("createdAt"),
                "archived": v.get("isArchived"),
                "is_fork": v.get("isFork"),
                "topics": topics,
            })
        return recs, rl.get("remaining")
    return None, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="catalog_full.sqlite")
    ap.add_argument("--out", default="data/enriched_full.jsonl")
    ap.add_argument("--min-lists", type=int, default=2,
                    help="only enrich repos cited by >= this many lists")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true",
                    help="skip repos already present in --out")
    ap.add_argument("--workers", type=int, default=6,
                    help="concurrent GraphQL requests (latency-bound, not "
                         "rate-limited; 6 is polite and ~6x faster)")
    args = ap.parse_args()

    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    q = ("SELECT full_name FROM repo WHERE list_count >= ?"
         " AND full_name NOT IN (SELECT list_repo FROM list)"
         " ORDER BY list_count DESC")
    todo = [r[0] for r in con.execute(q, (args.min_lists,))]

    done = set()
    if args.resume and os.path.exists(args.out):
        for line in open(args.out):
            try:
                done.add(json.loads(line)["full_name"].lower())
            except Exception:
                pass
        todo = [r for r in todo if r.lower() not in done]
    if args.limit:
        todo = todo[:args.limit]

    print(f"to enrich: {len(todo)} repos in {(len(todo)+BATCH-1)//BATCH} requests"
          f" (already have {len(done)})", file=sys.stderr)

    # Concurrency. The bottleneck is per-request LATENCY (~9s round-trip), not
    # the rate limit: 878 requests cost 878 of 5,000 points/hr. Serial that is
    # ~2h; at WORKERS=6 it is ~20 min. Kept modest to stay a polite client.
    chunks = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    t0, written, empty_batches = time.time(), 0, 0
    lock = threading.Lock()
    stop = threading.Event()

    def worker(idx, chunk):
        nonlocal written, empty_batches
        if stop.is_set():
            return
        recs, remaining = run_batch(chunk)
        if recs == "RATELIMIT":
            time.sleep(60)
            recs, remaining = run_batch(chunk)
        with lock:
            if not recs:
                # Never silently accept an empty batch -- that is exactly how
                # the >100 alias failure hides.
                empty_batches += 1
                print(f"  WARN empty batch #{idx}", file=sys.stderr)
                if empty_batches > 10:
                    stop.set()
                return
            for r in recs:
                f_out.write(json.dumps(r) + "\n")
            written += len(recs)
            if idx % 20 == 0:
                f_out.flush()
                print(f"  {written}/{len(todo)} rate_remaining={remaining}"
                      f" {round(time.time()-t0)}s", file=sys.stderr)
            if remaining is not None and remaining < 100:
                print("  budget nearly spent; stopping", file=sys.stderr)
                stop.set()

    with open(args.out, "a" if args.resume else "w") as f_out:
        with cf.ThreadPoolExecutor(max_workers=args.workers) as ex:
            list(ex.map(lambda p: worker(*p), enumerate(chunks)))

    print(json.dumps({
        "requested": len(todo),
        "written": written,
        "empty_batches": empty_batches,
        "requests_used": (len(todo) + BATCH - 1) // BATCH,
        "elapsed_sec": round(time.time() - t0, 1),
        "out": os.path.abspath(args.out),
    }, indent=2))


if __name__ == "__main__":
    main()
