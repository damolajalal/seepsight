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


    def test_session_only_demo_pack_is_not_counted_as_persistent_data(self):
        self.session["seepsight_demo_mode"] = False
        self.session["seepsight_auth"] = {"company_id": "company-a"}
        self.session["mine"] = {
            "company_id": "company-a",
            "session_only": True,
            "findings": [],
        }
        with patch.object(workspace, "restore_latest", return_value=None) as restore:
            self.assertFalse(workspace.has_company_data())
            self.assertIsNone(workspace.current(allow_empty=True))
        self.assertEqual(restore.call_count, 2)
        self.assertNotIn("mine", self.session)

    def test_legacy_demo_kind_is_not_counted_as_persistent_company_data(self):
        self.session["seepsight_demo_mode"] = False
        self.session["seepsight_auth"] = {"company_id": "company-a"}
        self.session["mine"] = {
            "company_id": "company-a",
            "kind": "demo",
            "findings": [],
        }
        with patch.object(workspace, "restore_latest", return_value=None) as restore:
            self.assertFalse(workspace.has_company_data())
            self.assertIsNone(workspace.current(allow_empty=True))
        self.assertEqual(restore.call_count, 2)
        self.assertNotIn("mine", self.session)

    def test_restore_latest_rejects_legacy_demo_analysis(self):
        saved = {
            "analysis_id": "demo-analysis",
            "summary": {"kind": "demo", "company_name": "Old Demo"},
            "tables": {},
        }
        with patch.object(
            workspace.firestore_db,
            "get_latest_analysis_workspace",
            return_value=saved,
        ):
            self.assertIsNone(workspace.restore_latest("company-a"))
        self.assertFalse(self.session.get("_workspace_restore_cache"))

    def test_workspace_picker_does_not_fetch_saved_analyses_on_initial_load(self):
        fake_streamlit = SimpleNamespace(
            session_state=self.session,
            caption=lambda *args, **kwargs: None,
            write=lambda *args, **kwargs: None,
            button=lambda *args, **kwargs: False,
        )
        self.session["seepsight_auth"] = {
            "company_id": "company-a",
            "company_name": "Company A",
        }
        with patch.object(workspace, "st", fake_streamlit), patch.object(
            workspace.firestore_db,
            "get_company_analysis_workspaces",
        ) as fetch:
            workspace.workspace_picker()

        fetch.assert_not_called()

    def test_demo_mode_never_reads_saved_workspace_list(self):
        self.session["seepsight_demo_mode"] = True
        with patch.object(
            workspace.firestore_db,
            "get_company_analysis_workspaces",
        ) as fetch:
            self.assertEqual(workspace._company_workspace_list("company-a"), [])
        fetch.assert_not_called()

    def test_demo_mode_never_restores_saved_workspace(self):
        self.session["seepsight_demo_mode"] = True
        with patch.object(
            workspace.firestore_db,
            "get_latest_analysis_workspace",
        ) as fetch:
            self.assertIsNone(workspace.restore_latest("company-a"))
        fetch.assert_not_called()

    def test_workspace_picker_hides_saved_analyses_in_demo_mode(self):
        self.session["seepsight_demo_mode"] = True
        self.session["seepsight_auth"] = {
            "company_id": "company-a",
            "company_name": "Company A",
        }
        fake_streamlit = SimpleNamespace(
            session_state=self.session,
            caption=lambda *args, **kwargs: None,
            write=lambda *args, **kwargs: None,
            button=lambda *args, **kwargs: self.fail("Saved-analysis controls must be hidden in demo mode"),
        )
        with patch.object(workspace, "st", fake_streamlit), patch.object(
            workspace.firestore_db,
            "get_company_analysis_workspaces",
        ) as fetch:
            workspace.workspace_picker()
        fetch.assert_not_called()

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
