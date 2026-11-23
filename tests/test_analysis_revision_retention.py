"""Tests for safe retention of durable analysis revisions."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


class AnalysisRevisionRetentionTests(unittest.TestCase):
    def test_cleanup_never_deletes_active_or_recent_revisions(self):
        company = MagicMock()
        analysis_ref = MagicMock()
        company.collection.return_value.document.return_value = analysis_ref
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = {"active_revision": "revision-old"}
        analysis_ref.get.return_value = snapshot

        revisions = []
        for revision_id in ("revision-newest", "revision-middle", "revision-old", "revision-stale"):
            item = MagicMock()
            item.id = revision_id
            item.reference = f"ref:{revision_id}"
            revisions.append(item)

        query = analysis_ref.collection.return_value.order_by.return_value
        query.limit.return_value.stream.return_value = revisions
        client = MagicMock()

        with patch.object(firestore_db, "_company_ref", return_value=company):
            with patch.object(firestore_db, "get_firestore_client", return_value=client):
                deleted = firestore_db.cleanup_analysis_revisions(
                    "company-a", "analysis-a", keep=2
                )

        self.assertEqual(deleted, 1)
        client.recursive_delete.assert_called_once_with("ref:revision-stale")

    def test_cleanup_rejects_unsafe_retention_count(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 20"):
            firestore_db.cleanup_analysis_revisions(
                "company-a", "analysis-a", keep=0
            )


if __name__ == "__main__":
    unittest.main()
