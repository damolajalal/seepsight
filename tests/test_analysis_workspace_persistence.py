"""Failure-safety tests for revisioned durable analysis workspaces."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


class AnalysisWorkspacePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.company = MagicMock()
        self.analysis_ref = MagicMock()
        self.revision_ref = MagicMock()
        self.company.collection.return_value.document.return_value = self.analysis_ref
        self.analysis_ref.collection.return_value.document.return_value = self.revision_ref
        self.client = MagicMock()
        self.batch = MagicMock()
        self.client.batch.return_value = self.batch
        self.client.transaction.return_value = MagicMock()
        self.company_patch = patch.object(
            firestore_db, "_company_ref", return_value=self.company
        )
        self.company_patch.start()
        self.addCleanup(self.company_patch.stop)
        self.client_patch = patch.object(
            firestore_db, "get_firestore_client", return_value=self.client
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.audit_patch = patch.object(
            firestore_db, "write_company_audit_event"
        )
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)
        self.cleanup_patch = patch.object(
            firestore_db, "cleanup_analysis_revisions", return_value=0
        )
        self.cleanup_patch.start()
        self.addCleanup(self.cleanup_patch.stop)

    def test_complete_revision_is_activated_only_after_rows_commit(self):
        with patch(
            "firebase_admin.firestore.transactional",
            side_effect=lambda function: (lambda transaction: function(transaction)),
        ):
            result = firestore_db.save_analysis_workspace(
                "company-a", "analysis-a", {"summary": "ready"},
                {"findings": [{"finding_id": "F-1"}]},
            )
        self.assertEqual(result, "analysis-a")
        self.batch.commit.assert_called_once()
        self.assertEqual(self.revision_ref.set.call_args_list[0].args[0]["workspace_status"], "saving")
        self.assertEqual(self.revision_ref.set.call_args_list[-1].args[0]["workspace_status"], "complete")
        transaction = self.client.transaction.return_value
        self.assertEqual(transaction.set.call_count, 2)
        analysis_payload = transaction.set.call_args_list[0].args[1]
        self.assertEqual(analysis_payload["workspace_status"], "complete")
        self.assertEqual(analysis_payload["tables"], {"findings": 1})

    def test_failed_row_batch_never_switches_active_revision(self):
        self.batch.commit.side_effect = RuntimeError("Firestore unavailable")
        with self.assertRaises(RuntimeError):
            firestore_db.save_analysis_workspace(
                "company-a", "analysis-a", {"summary": "new"},
                {"findings": [{"finding_id": "F-1"}]},
            )
        self.client.transaction.assert_not_called()
        self.assertEqual(
            self.revision_ref.set.call_args_list[0].args[0]["workspace_status"],
            "saving",
        )


if __name__ == "__main__":
    unittest.main()
