"""Tests for the session-scoped company workspace-list cache."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from seepsight import workspace


class CompanyWorkspaceListCacheTests(unittest.TestCase):
    def setUp(self):
        self.session = {}
        self.streamlit_patch = patch.object(
            workspace, "st", SimpleNamespace(session_state=self.session)
        )
        self.streamlit_patch.start()
        self.addCleanup(self.streamlit_patch.stop)

    def test_reuses_list_within_ttl_for_same_company(self):
        expected = [{"analysis_id": "a1"}]
        with patch.object(
            workspace.firestore_db,
            "get_company_analysis_workspaces",
            return_value=expected,
        ) as fetch:
            first = workspace._company_workspace_list("company-a")
            second = workspace._company_workspace_list("company-a")

        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        fetch.assert_called_once_with("company-a")

    def test_cache_is_separate_between_companies(self):
        with patch.object(
            workspace.firestore_db,
            "get_company_analysis_workspaces",
            side_effect=[
                [{"analysis_id": "a1"}],
                [{"analysis_id": "b1"}],
            ],
        ) as fetch:
            company_a = workspace._company_workspace_list("company-a")
            company_b = workspace._company_workspace_list("company-b")

        self.assertEqual(company_a[0]["analysis_id"], "a1")
        self.assertEqual(company_b[0]["analysis_id"], "b1")
        self.assertEqual(fetch.call_count, 2)

    def test_successful_workspace_save_invalidates_company_cache(self):
        self.session["_workspace_list_cache"] = {
            "company-a": {"fetched_at": 1, "items": [{"analysis_id": "old"}]},
            "company-b": {"fetched_at": 1, "items": [{"analysis_id": "other"}]},
        }
        pack = {
            "company_id": "company-a",
            "name": "Company A",
            "cur": "NGN",
            "log": {},
            "kind": "company",
            "findings": None,
            "evidence": None,
            "exposure": None,
            "monthly": None,
            "supplier_month": None,
            "risk": None,
            "explanations": None,
            "scorecard": None,
        }
        with patch.object(
            workspace.firestore_db,
            "save_analysis_workspace",
            return_value="analysis-new",
        ):
            result = workspace.persist(pack, "analysis-new")

        self.assertEqual(result, "analysis-new")
        self.assertNotIn("company-a", self.session["_workspace_list_cache"])
        self.assertIn("company-b", self.session["_workspace_list_cache"])


if __name__ == "__main__":
    unittest.main()
