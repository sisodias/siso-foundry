import json
from pathlib import Path
import unittest

import run_campaign


class CampaignContractTest(unittest.TestCase):
    def test_public_agent_campaign_is_valid_and_unique(self):
        path = Path(__file__).parent / "campaigns" / "agent-systems-v1.json"
        campaign = json.loads(path.read_text())
        run_campaign.validate_campaign(campaign)
        self.assertEqual(len(campaign["query_families"]), 10)
        self.assertEqual(len({item["key"] for item in campaign["query_families"]}), 10)
        self.assertTrue(all(item["capability_tags"] for item in campaign["query_families"]))

    def test_candidate_merge_preserves_query_lineage(self):
        prior = [{
            "candidate_key": "R_repo", "full_name": "owner/repo", "stars": 10,
            "source_query_keys": ["hooks"], "capability_tags": ["hooks"],
        }]
        incoming = [{
            "candidate_key": "R_repo", "full_name": "owner/repo", "stars": 12,
            "source_query_keys": ["skills"], "capability_tags": ["skills"],
        }]
        merged = run_campaign.merge_candidates(prior, incoming)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["source_query_keys"], ["hooks", "skills"])
        self.assertEqual(merged[0]["capability_tags"], ["hooks", "skills"])

    def test_candidate_defaults_to_rights_review(self):
        campaign = {"campaign_id": "test", "promotion_gate": "direct_source_review"}
        family = {"key": "memory", "capability_tags": ["memory"]}
        item = {
            "node_id": "R_repo", "full_name": "owner/repo", "html_url": "https://github.com/owner/repo",
            "license": None, "owner": {"login": "owner"}, "stargazers_count": 5,
        }
        result = run_campaign.candidate(item, family, "2026-08-02T00:00:00Z", campaign)
        self.assertEqual(result["declared_license_spdx"], "NOASSERTION")
        self.assertEqual(result["rights_state"], "review_required")
        self.assertEqual(result["promotion_gate"], "direct_source_review")


if __name__ == "__main__":
    unittest.main()
