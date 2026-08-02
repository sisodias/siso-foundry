import json
from pathlib import Path
import unittest

import run_campaign


class CampaignContractTest(unittest.TestCase):
    def test_agency_business_software_contract_covers_all_pillars(self):
        campaign_path = Path(__file__).parent / "campaigns" / "agency-business-software-v1.json"
        contract_path = (
            Path(__file__).parents[2]
            / "packages"
            / "business-application"
            / "agency-os-routing-contract.json"
        )
        campaign = json.loads(campaign_path.read_text())
        contract = json.loads(contract_path.read_text())
        families = campaign["query_families"]

        self.assertEqual(len(families), 12)
        primary_pillars = {family["capability_tags"][0] for family in families}
        self.assertEqual(primary_pillars, set(contract["pillars"]))
        for family in families:
            with self.subTest(query_family=family["key"]):
                self.assertIn("stars:>=10000", family["query"])
                self.assertIn("archived:false", family["query"])
                self.assertIn("fork:false", family["query"])
        self.assertTrue(campaign["rights_policy"])
        self.assertTrue(campaign["promotion_gate"])
        self.assertTrue(campaign["stop_conditions"])

    def test_public_campaigns_are_valid_and_unique(self):
        paths = sorted((Path(__file__).parent / "campaigns").glob("*.json"))
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            with self.subTest(campaign=path.name):
                campaign = json.loads(path.read_text())
                run_campaign.validate_campaign(campaign)
                families = campaign["query_families"]
                self.assertEqual(len({item["key"] for item in families}), len(families))
                self.assertTrue(all(item["capability_tags"] for item in families))

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
