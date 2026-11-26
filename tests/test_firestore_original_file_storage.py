"""Tests for Firestore-only original upload persistence."""

import hashlib
import unittest
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


class OriginalFileStorageTests(unittest.TestCase):
    def setUp(self):
        self.company = MagicMock()
        self.dataset = MagicMock()
        self.chunks = MagicMock()
        self.company.collection.return_value.document.return_value = self.dataset
        self.dataset.collection.return_value = self.chunks
        self.client = MagicMock()
        self.batch = MagicMock()
        self.client.batch.return_value = self.batch
        self.company_patch = patch.object(firestore_db, "_company_ref", return_value=self.company)
        self.company_patch.start()
        self.addCleanup(self.company_patch.stop)
        self.client_patch = patch.object(firestore_db, "get_firestore_client", return_value=self.client)
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.audit_patch = patch.object(firestore_db, "write_company_audit_event")
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)

    def test_save_original_file_writes_chunk_and_checksum_metadata(self):
        payload = b"PO Number,Amount\nPO-1,100\n"
        result = firestore_db.save_original_file("company-a", "dataset-a", "orders.csv", payload)
        self.client.recursive_delete.assert_not_called()
        self.batch.set.assert_called_once()
        chunk = self.batch.set.call_args.args[1]
        self.assertEqual(chunk["data"], payload)
        self.assertEqual(chunk["chunk_index"], 0)
        final_metadata = self.dataset.set.call_args_list[-1].args[0]
        self.assertEqual(final_metadata["original_file_status"], "complete")
        self.assertTrue(final_metadata["original_file_saved"])
        self.assertEqual(result["sha256"], hashlib.sha256(payload).hexdigest())

    def test_save_rejects_unsupported_file_before_writing(self):
        with self.assertRaisesRegex(ValueError, "file type"):
            firestore_db.save_original_file("company-a", "dataset-a", "payload.exe", b"abc")
        self.dataset.set.assert_not_called()
        self.client.batch.assert_not_called()

    def test_save_rejects_empty_file(self):
        with self.assertRaisesRegex(ValueError, "empty"):
            firestore_db.save_original_file("company-a", "dataset-a", "orders.csv", b"")
        self.dataset.set.assert_not_called()

    def test_failed_chunk_write_marks_file_failed_and_cleans_up(self):
        self.batch.commit.side_effect = RuntimeError("Firestore unavailable")
        with self.assertRaisesRegex(RuntimeError, "could not be saved completely"):
            firestore_db.save_original_file("company-a", "dataset-a", "orders.csv", b"a,b\n1,2")
        self.assertEqual(self.dataset.set.call_args_list[-1].args[0]["original_file_status"], "failed")
        self.client.recursive_delete.assert_not_called()

    def test_get_original_file_reassembles_and_checks_sha256(self):
        payload = b"PO Number,Amount\nPO-1,100\n"
        metadata = MagicMock(exists=True)
        metadata.to_dict.return_value = {
            "original_file_status": "complete",
            "original_file": {
                "filename": "orders.csv",
                "content_type": "text/csv",
                "size_bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
                "chunk_count": 1,
            },
        }
        self.dataset.get.return_value = metadata
        chunk = MagicMock()
        chunk.to_dict.return_value = {"chunk_index": 0, "data": payload}
        query = self.chunks.order_by.return_value
        query.limit.return_value.start_after.return_value.stream.return_value = [chunk]
        query.limit.return_value.stream.return_value = [chunk]
        result = firestore_db.get_original_file("company-a", "dataset-a")
        self.assertEqual(result["filename"], "orders.csv")
        self.assertEqual(result["data"], payload)

    def test_get_rejects_checksum_mismatch(self):
        payload = b"tampered"
        metadata = MagicMock(exists=True)
        metadata.to_dict.return_value = {
            "original_file_status": "complete",
            "original_file": {
                "filename": "orders.csv",
                "size_bytes": len(payload),
                "sha256": "wrong",
                "chunk_count": 1,
            },
        }
        self.dataset.get.return_value = metadata
        chunk = MagicMock()
        chunk.to_dict.return_value = {"chunk_index": 0, "data": payload}
        self.chunks.order_by.return_value.limit.return_value.stream.return_value = [chunk]
        with self.assertRaisesRegex(RuntimeError, "integrity check failed"):
            firestore_db.get_original_file("company-a", "dataset-a")


if __name__ == "__main__":
    unittest.main()
