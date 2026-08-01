#!/usr/bin/env python3
"""Run a public, resumable GitHub repository discovery campaign.

Raw API responses are append-only observations under the external Foundry data
plane. Checkpoint and candidate files are derived operational state and never
belong in Git. Discovery records metadata and locators only; promotion always
requires direct source, provenance, and rights review.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
DEFAULT_CAMPAIGN = HERE / "campaigns" / "agent-systems-v1.json"


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def data_root() -> Path:
    configured = os.environ.get("FOUNDRY_DATA")
    return Path(configured).expanduser() if configured else Path.home() / ".local" / "share" / "siso-foundry"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def validate_campaign(campaign: dict) -> None:
    required = {"schema_version", "campaign_id", "title", "source", "rights_policy", "promotion_gate", "query_families"}
    missing = sorted(required - campaign.keys())
    if missing:
        raise ValueError(f"campaign missing fields: {', '.join(missing)}")
    if campaign["schema_version"] != "1.0.0" or campaign["source"] != "github_repository_search":
        raise ValueError("unsupported campaign schema or source")
    families = campaign["query_families"]
    if not isinstance(families, list) or not families:
        raise ValueError("query_families must be a non-empty list")
    keys = []
    for family in families:
        for field in ("key", "label", "query", "capability_tags"):
            if not family.get(field):
                raise ValueError(f"query family missing {field}")
        keys.append(family["key"])
    if len(keys) != len(set(keys)):
        raise ValueError("query family keys must be unique")


def gh_json(arguments: list[str]) -> dict:
    result = subprocess.run(["gh", *arguments], text=True, capture_output=True)
    if result.returncode != 0:
        detail = "\n".join(part.strip() for part in (result.stderr, result.stdout) if part.strip())
        raise RuntimeError(f"gh {' '.join(arguments[:2])} failed: {detail}")
    return json.loads(result.stdout)


def search_quota() -> dict:
    payload = gh_json(["api", "rate_limit"])
    return payload["resources"]["search"]


def search(query: str, limit: int) -> dict:
    return gh_json([
        "api", "--method", "GET", "search/repositories",
        "-f", f"q={query}", "-f", f"per_page={limit}", "-f", "page=1",
    ])


def query_hash(query: str) -> str:
    return hashlib.sha256(query.encode()).hexdigest()


def candidate(item: dict, family: dict, observed_at: str, campaign: dict) -> dict:
    license_info = item.get("license") or {}
    owner = item.get("owner") or {}
    return {
        "candidate_key": item.get("node_id") or str(item.get("full_name", "")).lower(),
        "full_name": item.get("full_name"),
        "url": item.get("html_url"),
        "description": item.get("description") or "",
        "owner_login": owner.get("login") or "",
        "github_node_id": item.get("node_id") or "",
        "default_branch": item.get("default_branch") or "",
        "language": item.get("language") or "",
        "topics": sorted(item.get("topics") or []),
        "declared_license_spdx": license_info.get("spdx_id") or "NOASSERTION",
        "stars": item.get("stargazers_count") or 0,
        "forks": item.get("forks_count") or 0,
        "pushed_at": item.get("pushed_at"),
        "archived": bool(item.get("archived")),
        "fork": bool(item.get("fork")),
        "observed_at": observed_at,
        "campaign_id": campaign["campaign_id"],
        "source_query_keys": [family["key"]],
        "capability_tags": sorted(set(family["capability_tags"])),
        "rights_state": "review_required",
        "promotion_gate": campaign["promotion_gate"],
    }


def merge_candidates(existing: list[dict], incoming: list[dict]) -> list[dict]:
    merged = {item["candidate_key"]: item for item in existing}
    for item in incoming:
        prior = merged.get(item["candidate_key"])
        if prior:
            item["source_query_keys"] = sorted(set(prior["source_query_keys"] + item["source_query_keys"]))
            item["capability_tags"] = sorted(set(prior["capability_tags"] + item["capability_tags"]))
        merged[item["candidate_key"]] = item
    return sorted(merged.values(), key=lambda item: (-item["stars"], item["full_name"].lower()))


def run(args: argparse.Namespace) -> int:
    campaign_path = Path(args.campaign).resolve()
    campaign = load_json(campaign_path)
    validate_campaign(campaign)
    families = campaign["query_families"][: args.max_queries or None]
    limit = args.limit_per_query or campaign.get("default_results_per_query", 20)
    if not 1 <= limit <= 100:
        raise ValueError("limit-per-query must be between 1 and 100")

    if args.dry_run:
        print(f"CAMPAIGN {campaign['campaign_id']} queries={len(families)} limit={limit}")
        for family in families:
            print(f"QUERY {family['key']}\t{family['query']}")
        return 0

    root = Path(args.data_root).expanduser() if args.data_root else data_root()
    campaign_root = root / "incoming" / "github" / "campaigns" / campaign["campaign_id"]
    raw_root = campaign_root / "raw"
    checkpoint_path = campaign_root / "checkpoint.json"
    candidates_path = campaign_root / "candidates.json"
    checkpoint = load_json(checkpoint_path) if checkpoint_path.exists() else {
        "schema_version": "1.0.0", "campaign_id": campaign["campaign_id"], "completed_queries": []
    }
    completed = {(item["key"], item["query_sha256"]) for item in checkpoint.get("completed_queries", [])}
    candidates = load_json(candidates_path).get("candidates", []) if candidates_path.exists() else []

    for family in families:
        signature = query_hash(family["query"])
        if (family["key"], signature) in completed:
            print(f"SKIP {family['key']} already checkpointed")
            continue
        quota = search_quota()
        if quota["remaining"] < 2:
            checkpoint["stopped_reason"] = "search_quota_below_safety_floor"
            checkpoint["stopped_at"] = now()
            write_json(checkpoint_path, checkpoint)
            print("STOP GitHub search quota below safety floor", file=sys.stderr)
            return 75
        observed_at = now()
        try:
            response = search(family["query"], limit)
        except (RuntimeError, json.JSONDecodeError) as error:
            checkpoint["stopped_reason"] = str(error)
            checkpoint["stopped_at"] = now()
            write_json(checkpoint_path, checkpoint)
            print(f"STOP {error}", file=sys.stderr)
            return 75
        raw_path = raw_root / f"{observed_at.replace(':', '').replace('-', '')}-{family['key']}.json"
        write_json(raw_path, {
            "schema_version": "1.0.0", "campaign_id": campaign["campaign_id"],
            "query_key": family["key"], "query": family["query"], "observed_at": observed_at,
            "response": response,
        })
        incoming = [candidate(item, family, observed_at, campaign) for item in response.get("items", [])]
        candidates = merge_candidates(candidates, incoming)
        completed.add((family["key"], signature))
        checkpoint["completed_queries"] = [
            {"key": key, "query_sha256": digest} for key, digest in sorted(completed)
        ]
        checkpoint["last_completed_at"] = observed_at
        checkpoint.pop("stopped_reason", None)
        checkpoint.pop("stopped_at", None)
        write_json(candidates_path, {
            "schema_version": "1.0.0", "campaign_id": campaign["campaign_id"],
            "generated_at": observed_at, "rights_policy": campaign["rights_policy"],
            "candidate_count": len(candidates), "candidates": candidates,
        })
        write_json(checkpoint_path, checkpoint)
        print(f"PASS {family['key']} observations={len(incoming)} candidates={len(candidates)} quota_before={quota['remaining']}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", default=str(DEFAULT_CAMPAIGN))
    parser.add_argument("--data-root")
    parser.add_argument("--limit-per-query", type=int)
    parser.add_argument("--max-queries", type=int)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args()))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR {error}", file=sys.stderr)
        raise SystemExit(2)
