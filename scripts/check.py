#!/usr/bin/env python3
"""Repository-level source, fixture, and publication-safety checks."""

import json
import os
from pathlib import Path
import py_compile
import re
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".git", "node_modules", "__pycache__", "run", "results"}


def source_files(suffix):
    return [path for path in ROOT.rglob(f"*{suffix}") if not IGNORED_PARTS.intersection(path.parts)]


def run(command, **kwargs):
    subprocess.run(command, cwd=ROOT, check=True, **kwargs)


for path in source_files(".py"):
    py_compile.compile(str(path), doraise=True)

for path in source_files(".mjs"):
    run(["node", "--check", str(path)])

for path in source_files(".sh"):
    run(["bash", "-n", str(path)])

run([sys.executable, "-m", "unittest", "discover", "-s", "pipelines/github", "-p", "test_*.py"], stdout=subprocess.DEVNULL)
run([
    sys.executable, "pipelines/github/run_campaign.py", "--dry-run",
    "--campaign", "pipelines/github/campaigns/agent-systems-v1.json",
], stdout=subprocess.DEVNULL)

with tempfile.TemporaryDirectory(prefix="siso-foundry-check-") as directory:
    env = dict(os.environ)
    env["FOUNDRY_TOPICS_DB"] = str(Path(directory) / "topics.sqlite")
    topics = ROOT / "packages" / "research-topics" / "topics.py"
    run([sys.executable, str(topics), "init"], env=env, stdout=subprocess.DEVNULL)
    run([sys.executable, str(topics), "list"], env=env, stdout=subprocess.DEVNULL)

manifest = json.loads((ROOT / "datasets" / "manifest.json").read_text())
assert manifest["work_id"].startswith("gls:work:")
assert manifest["assets"]
for asset in manifest["assets"]:
    assert asset["observed_bytes"] >= 0
    assert asset["publication_state"]
    assert asset["required_release_receipts"]

agency_snapshot = json.loads((ROOT / "intelligence" / "agency" / "snapshot.json").read_text())
assert agency_snapshot["record_type"] == "agency_intelligence_snapshot"
assert agency_snapshot["work_id"] == manifest["work_id"]
assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", agency_snapshot["observed_at"])
assert agency_snapshot["publication_state"] == "metadata_only"
assert agency_snapshot["payload_materialization"] == "not_materialized"
assert agency_snapshot["source_components"]
database_receipt = agency_snapshot["source_components"][0]
assert database_receipt["logical_asset_id"] == "foundry-github-identity-live"
assert database_receipt["observed_bytes"] == 1879339008
assert re.fullmatch(r"[0-9a-f]{64}", database_receipt["sha256"])
assert database_receipt["wal_bytes"] == 0

corpus = agency_snapshot["corpus"]
adoption = corpus["adoption"]
assert adoption["total"] == sum(adoption[key] for key in ("promote", "confirm", "demote", "unresolved"))
adoption_receipt = database_receipt["query_receipts"]["adoption"]
assert adoption["total"] == adoption_receipt["row_count"]
assert adoption["promote"] == adoption_receipt["promote_rows"]
assert adoption["confirm"] == adoption_receipt["confirm_rows"]
assert adoption["demote"] == adoption_receipt["demote_rows"]
assert adoption["unresolved"] == adoption_receipt["unresolved_rows"]
proof = corpus["proof_selection"]
assert proof["rows"] == sum(proof[key] for key in ("promote", "confirm", "demote"))
proven_pick_receipt = agency_snapshot["source_components"][1]
assert proof["rows"] == proven_pick_receipt["rows_excluding_header"]
assert re.fullmatch(r"[0-9a-f]{64}", proven_pick_receipt["sha256"])
graph = corpus["capability_graph"]
assert graph["edges"] == graph["hard_edges"] + graph["soft_edges"]
graph_receipt = database_receipt["query_receipts"]["capability_graph"]
assert graph["nodes"] == graph_receipt["node_rows"]
assert graph["edges"] == graph_receipt["edge_rows"]
assert graph["hard_edges"] == graph_receipt["hard_edge_rows"]
assert graph["soft_edges"] == graph_receipt["soft_edge_rows"]
assert graph["closure_rows"] == graph_receipt["closure_rows"]
cards = corpus["reuse_bank"]
verified_cards = cards["verified_harness_subset"]
assert cards["contract_cards_total"] >= verified_cards["total"]
assert verified_cards["total"] == verified_cards["self_smoke"] + verified_cards["import_smoke"]
assert verified_cards["total"] >= verified_cards["trust_rung_3"]
card_receipt = database_receipt["query_receipts"]["contract_cards"]
assert cards["contract_cards_total"] == card_receipt["row_count"]
assert verified_cards["total"] == card_receipt["trust_and_smoke_populated_rows"]
assert agency_snapshot["agency_candidate_ideas"]["evidence_state"] == "operator_nominated_pending_direct_source_review"
assert agency_snapshot["agency_candidate_ideas"]["clusters"]
assert agency_snapshot["siso_control_plane_gaps"]

publication_patterns = [
    re.compile("/" + "Users" + "/"),
    re.compile("SISO_" + "Workspace"),
    re.compile("BEGIN (?:RSA |OPENSSH |EC |DSA )?" + "PRIVATE KEY"),
    re.compile("(?:ghp|github_pat|sk)" + "-[A-Za-z0-9_-]{16,}"),
]
for path in ROOT.rglob("*"):
    if IGNORED_PARTS.intersection(path.parts):
        continue
    if path.is_symlink():
        text = os.readlink(path)
    elif path.is_file():
        try:
            text = path.read_text()
        except UnicodeDecodeError:
            continue
    else:
        continue
    for pattern in publication_patterns:
        if pattern.search(text):
            raise SystemExit(f"publication safety match {pattern.pattern!r} in {path.relative_to(ROOT)}")

print(f"FOUNDRY_CHECK_OK ({len(source_files('.py'))} Python files)")
