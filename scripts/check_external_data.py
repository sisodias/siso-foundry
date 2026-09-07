#!/usr/bin/env python3
"""Explicit, bounded, read-only atlas consistency gate. Never an execution gate."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

MAX_ATLAS_BYTES = 16 * 1024 * 1024


def result(status: str, reason: str, **details: Any) -> dict:
    return {
        "schema_version": "1.0.0", "check": "external_atlas_consistency",
        "status": status, "reason": reason,
        "classification": "private_operational_metadata",
        "execution_readiness": "not_established", **details,
    }


def capability_ids(document: dict) -> set[str]:
    rows = document["capabilities"]
    if not isinstance(rows, list) or not rows:
        raise ValueError("Invalid capability map")
    ids = [row["capability_id"] for row in rows]
    if any(not isinstance(value, str) or not value.strip() for value in ids):
        raise ValueError("Invalid capability identifier")
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate capability identifier")
    return set(ids)


def verify_atlas(path: Path | None, expected: set[str], *, max_bytes: int = MAX_ATLAS_BYTES) -> dict:
    if path is None:
        return result("blocked", "atlas_not_configured")
    if not expected:
        return result("fail", "empty_expected_capabilities")
    try:
        # A regular-file check prevents opening a FIFO or device accidentally.
        if not path.is_file():
            return result("blocked", "atlas_not_a_readable_file")
        with path.open("rb") as stream:
            before = os.fstat(stream.fileno())
            if before.st_size > max_bytes:
                return result("fail", "atlas_size_limit")
            payload = stream.read(max_bytes + 1)
            after = os.fstat(stream.fileno())
        if len(payload) > max_bytes:
            return result("fail", "atlas_size_limit")
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            return result("blocked", "atlas_changed_during_read")
    except OSError:
        return result("blocked", "atlas_not_a_readable_file")
    try:
        actual: set[str] = set()
        for line in payload.decode("utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            value = row["capability_id"]
            if not isinstance(value, str) or not value.strip():
                return result("fail", "invalid_atlas_identifier")
            if value in actual:
                return result("fail", "duplicate_atlas_identifier")
            actual.add(value)
    except (UnicodeError, ValueError, KeyError, TypeError):
        return result("fail", "invalid_atlas_record")
    details = {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "observed_bytes": len(payload), "expected_count": len(expected),
        "observed_count": len(actual), "missing_count": len(expected - actual),
        "unexpected_count": len(actual - expected),
    }
    if actual != expected:
        return result("fail", "capability_ids_differ", **details)
    return result("pass", "capability_ids_match", **details)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--atlas", help="Explicit atlas JSONL path; otherwise FOUNDRY_CAPABILITY_ATLAS. No path discovery.")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        expected = capability_ids(json.loads((root / "intelligence/agency/capability-pillar-map.json").read_text()))
    except (OSError, ValueError, KeyError, TypeError):
        receipt = result("fail", "invalid_public_capability_map")
    else:
        selected = args.atlas or os.environ.get("FOUNDRY_CAPABILITY_ATLAS")
        receipt = verify_atlas(Path(selected).expanduser() if selected else None, expected)
    # No path, source rows, credentials or raw exception text in the receipt.
    print(json.dumps(receipt, sort_keys=True))
    return {"pass": 0, "fail": 1, "blocked": 2}[receipt["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
