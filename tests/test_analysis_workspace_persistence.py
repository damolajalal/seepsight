"""Failure-safety tests for revisioned durable analysis workspaces."""

import json
import unittest
import zlib
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

    def test_analysis_table_loader_reads_and_validates_compressed_chunks(self):
        data_ref = MagicMock()
        table_ref = MagicMock()
        data_ref.collection.return_value.document.return_value = table_ref
        table_ref.get.return_value.exists = True
        table_ref.get.return_value.to_dict.return_value = {
            "storage_format": "zlib-json-v1",
            "row_count": 1,
        }
        chunk_payload = zlib.compress(
            json.dumps([{"finding_id": "F-1"}]).encode("utf-8")
        )
        chunk_snapshot = MagicMock()
        chunk_snapshot.to_dict.return_value = {
            "payload_zlib_json": chunk_payload,
        }
        with patch.object(
            firestore_db,
            "_stream_query_pages",
            return_value=[chunk_snapshot],
        ), patch.object(
            firestore_db,
            "_denormalise_workspace_value",
            side_effect=lambda value: value,
        ):
            name, rows = firestore_db._load_analysis_workspace_table(
                data_ref, "findings"
            )

        self.assertEqual(name, "findings")
        self.assertEqual(rows, [{"finding_id": "F-1"}])

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
        revision_writes = [call.args[0] for call in self.revision_ref.set.call_args_list]
        self.assertTrue(any(payload.get("workspace_status") == "complete" for payload in revision_writes))
        self.assertEqual(revision_writes[-1]["save_stage"], "activating_workspace")
        transaction = self.client.transaction.return_value
        self.assertEqual(transaction.set.call_count, 2)
        analysis_payload = transaction.set.call_args_list[0].args[1]
        self.assertEqual(analysis_payload["workspace_status"], "complete")
        self.assertEqual(analysis_payload["tables"], {"findings": 1})

    def test_oversized_workspace_summary_is_rejected_before_firestore_writes(self):
        with patch.object(firestore_db, "_company_ref", return_value=self.company):
            with self.assertRaisesRegex(ValueError, "summary is too large"):
                firestore_db.save_analysis_workspace(
                    "company-a", "analysis-a",
                    {"description": "x" * 810_000}, {},
                )
        self.company.collection.assert_not_called()

    def test_workspace_total_row_count_is_bounded(self):
        class OversizedList(list):
            def __len__(self):
                return 250_001

        with patch.object(firestore_db, "_company_ref", return_value=self.company):
            with self.assertRaisesRegex(ValueError, "250,000 total rows"):
                firestore_db.save_analysis_workspace(
                    "company-a", "analysis-a", {},
                    {"findings": OversizedList()},
                )
        self.company.collection.assert_not_called()

    def test_legacy_analysis_results_mark_failed_after_batch_error(self):
        company = MagicMock()
        analysis_ref = MagicMock()
        company.collection.return_value.document.return_value = analysis_ref
        client = MagicMock()
        client.batch.return_value.commit.side_effect = RuntimeError("write failed")
        with patch.object(firestore_db, "_company_ref", return_value=company):
            with patch.object(firestore_db, "get_firestore_client", return_value=client):
                with self.assertRaisesRegex(RuntimeError, "could not be saved completely"):
                    firestore_db.save_analysis_results(
                        "company-a", "analysis-a", {}, [{"finding_id": "F-1"}]
                    )
        statuses = [call.args[0].get("results_status") for call in analysis_ref.set.call_args_list]
        self.assertEqual(statuses, ["saving", "failed"])

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
