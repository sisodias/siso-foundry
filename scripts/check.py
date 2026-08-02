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

value_matrix = json.loads((ROOT / "intelligence" / "agency" / "value-matrix.json").read_text())
assert value_matrix["record_type"] == "agency_os_value_matrix"
assert value_matrix["work_id"] == manifest["work_id"]
assert value_matrix["unit_of_analysis"] == "repository_x_siso_use_case_x_adoption_route"
assert value_matrix["source_universe"]["matrix_entries"] == len(value_matrix["entries"])
assert value_matrix["source_universe"]["deduplicated_repositories"] >= len(value_matrix["entries"])

value_weights = value_matrix["score_model"]["value_weights"]
feasibility_weights = value_matrix["score_model"]["feasibility_weights"]
assert sum(value_weights.values()) == 100
assert sum(feasibility_weights.values()) == 100

entry_ids = set()
authority_groups = set()
evidence_states = value_matrix["evidence_states"]
evidence_rank = {state: index for index, state in enumerate(evidence_states)}
for entry in value_matrix["entries"]:
    assert entry["entry_id"] not in entry_ids
    entry_ids.add(entry["entry_id"])
    authority_groups.add(entry["authority_group"])
    assert re.fullmatch(r"[^/\s]+/[^/\s]+", entry["repository"])
    assert entry["evidence_state"] in evidence_rank
    assert entry["agent_operations"]
    assert entry["hard_gates"]
    assert entry["evidence"]

    value = entry["value"]
    feasibility = entry["feasibility"]
    assert set(value) == set(value_weights) | {"total"}
    assert set(feasibility) == set(feasibility_weights) | {"total"}
    assert all(isinstance(value[key], int) and 0 <= value[key] <= 5 for key in value_weights)
    assert all(isinstance(feasibility[key], int) and 0 <= feasibility[key] <= 5 for key in feasibility_weights)
    calculated_value = round(sum(value[key] * weight / 5 for key, weight in value_weights.items()))
    calculated_feasibility = round(sum(feasibility[key] * weight / 5 for key, weight in feasibility_weights.items()))
    assert value["total"] == calculated_value
    assert feasibility["total"] == calculated_feasibility
    assert entry["priority_index"] == round(calculated_value * calculated_feasibility / 100)

    if entry["classification"] == "god_source":
        assert value["total"] >= 85
        assert feasibility["total"] >= 65
        assert value["agent_leverage"] >= 4
        assert value["agency_edition"] >= 4
        assert value["client_delivery"] >= 4
        assert evidence_rank[entry["evidence_state"]] >= evidence_rank["source_read"]

assert len(authority_groups) == len(value_matrix["entries"])

# Agency OS expansion coverage inventory: repository-level deduplication and
# evidence gates.  This is deliberately checked against the lane receipt's
# 497 application rows so aggregate percentages cannot silently drift.
coverage = json.loads((ROOT / "intelligence" / "agency" / "coverage-inventory.json").read_text())
assert coverage["record_type"] == "agency_os_coverage_inventory"
assert coverage["counts"]["candidate_application_rows"] == 497
assert coverage["counts"]["frontier_rows"] == 30
assert coverage["counts"]["atlas_capability_rows"] == 189
coverage_rows = coverage["rows"]
assert coverage["counts"]["unique_repositories"] == len(coverage_rows) == len({r["repository"] for r in coverage_rows})
assert coverage["coverage"]["inferred_rows_counted_as_verified"] == 0
assert all(r["evidence_grade"] in {"metadata", "inferred", "source-read", "adversarial-confirmed"} for r in coverage_rows)
assert all(r["verticals"] and r["categories"] for r in coverage_rows)
assert all("license" in r and "source_refs" in r and "analyzed" in r for r in coverage_rows)
assert sum(r["application_row_count"] for r in coverage_rows) == 497
assert sum(r["frontier_row_count"] for r in coverage_rows) == 30
assert coverage["coverage"]["adversarial_confirmed_unique_repositories"] == sum(r["analyzed"]["adversarial_confirmed"] for r in coverage_rows)
assert coverage["coverage"]["source_read_unique_repositories"] == sum(r["analyzed"]["source_read"] for r in coverage_rows)
assert coverage["coverage"]["reusable_analysis_unique_repositories"] <= coverage["counts"]["unique_repositories"]
assert coverage["coverage"]["source_read_candidate_application_rows"] == 89
assert coverage["counts"]["multi_vertical_projects"] == sum(len(r["canonical_verticals"]) > 1 for r in coverage_rows)
canonical = coverage["canonical_pillars"]
assert len(canonical) == 12 and len(set(canonical)) == 12
assert coverage["counts"]["unmapped_vertical_labels"] == 0
assert set(coverage["vertical_coverage"]) == set(canonical)
for row in coverage_rows:
    assert row["canonical_verticals"] and set(row["canonical_verticals"]).issubset(set(canonical))
    assert row["raw_vertical_labels"]
expected_mappings = {
    "knowledge-documents-files-legal": {"knowledge_research", "files_media_content", "legal_trust"},
    "agent-infrastructure-deployment-ops": {"automation_agents", "deployment_operations"},
    "marketing-growth-content-automation": {"marketing_growth", "automation_agents", "files_media_content"},
}
for raw, expected in expected_mappings.items():
    matching = [r for r in coverage_rows if raw in r["raw_vertical_labels"]]
    assert matching and all(expected.issubset(set(r["canonical_verticals"])) for r in matching)
for pillar, detail in coverage["vertical_coverage"].items():
    assert detail["repository_count"] == len(detail["projects"]) == len(set(detail["projects"]))

publication_patterns = [
    re.compile("/" + "Users" + "/"),
    re.compile("SISO_" + "Workspace"),
    re.compile("BEGIN (?:RSA |OPENSSH |EC |DSA )?" + "PRIVATE KEY"),
    re.compile("(?<![A-Za-z0-9])(?:ghp|github_pat|sk)" + "-[A-Za-z0-9_-]{16,}"),
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
