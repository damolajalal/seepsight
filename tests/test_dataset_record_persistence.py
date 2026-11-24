"""Tests for durable company procurement record storage."""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


class DatasetRecordPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.company = MagicMock()
        self.dataset_ref = MagicMock()
        self.company.collection.return_value.document.return_value = self.dataset_ref
        self.records = MagicMock()
        self.dataset_ref.collection.return_value = self.records
        self.batch = MagicMock()
        self.client = MagicMock()
        self.client.batch.return_value = self.batch
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
            firestore_db, "write_company_audit_event", return_value="audit-id"
        )
        self.audit_patch.start()
        self.addCleanup(self.audit_patch.stop)

    def test_records_are_written_and_marked_complete(self):
        saved = firestore_db.save_dataset_records(
            "company-a",
            "dataset-a",
            [{"po_id": "PO-1", "unit_price": Decimal("12.340000000000000009")}],
        )

        self.assertEqual(saved, 1)
        self.batch.set.assert_called_once()
        record_payload = self.batch.set.call_args.args[1]
        self.assertEqual(
            record_payload["unit_price"],
            {"__seepsight_decimal__": "12.340000000000000009"},
        )
        self.assertEqual(record_payload["_record_number"], 0)
        self.assertTrue(self.dataset_ref.set.call_args_list[-1].args[0]["records_saved"])
        self.assertEqual(
            self.dataset_ref.set.call_args_list[-1].args[0]["records_status"],
            "complete",
        )

    def test_failed_batch_marks_dataset_records_incomplete(self):
        self.batch.commit.side_effect = RuntimeError("write failed")
        with self.assertRaisesRegex(RuntimeError, "could not be saved completely"):
            firestore_db.save_dataset_records(
                "company-a", "dataset-a", [{"po_id": "PO-1"}]
            )
        states = [call.args[0] for call in self.dataset_ref.set.call_args_list]
        self.assertEqual(states[0]["records_status"], "saving")
        self.assertEqual(states[-1]["records_status"], "failed")
        self.assertFalse(states[-1]["records_saved"])

    def test_source_rows_use_separate_status_and_collection(self):
        saved = firestore_db.save_dataset_records(
            "company-a",
            "dataset-a",
            [{"Original PO Number": "0000123", "Original Amount": "123.4500"}],
            collection_name="source_records",
        )
        self.assertEqual(saved, 1)
        self.assertEqual(
            self.dataset_ref.set.call_args_list[-1].args[0]["source_records_status"],
            "complete",
        )
        self.assertTrue(
            self.dataset_ref.set.call_args_list[-1].args[0]["source_records_saved"]
        )
        self.assertEqual(
            self.records.document.call_args.args[0],
            "record_000000000000",
        )

    def test_reads_records_and_restores_decimal_values(self):
        metadata = MagicMock(exists=True)
        metadata.to_dict.return_value = {"records_status": "complete"}
        self.dataset_ref.get.return_value = metadata
        row = MagicMock()
        row.to_dict.return_value = {
            "po_id": "PO-1",
            "unit_price": {"__seepsight_decimal__": "0.100000000000000009"},
            "_record_number": 0,
        }
        query = self.records.order_by.return_value
        query.limit.return_value.stream.return_value = [row]

        with patch.object(firestore_db, "_company_ref", return_value=self.company):
            values = firestore_db.get_dataset_records("company-a", "dataset-a")

        self.assertEqual(values[0]["po_id"], "PO-1")
        self.assertEqual(values[0]["unit_price"], Decimal("0.100000000000000009"))
        self.assertNotIn("_record_number", values[0])

    def test_search_scans_middle_records_and_reports_complete_coverage(self):
        metadata = MagicMock(exists=True)
        metadata.to_dict.return_value = {"records_status": "complete", "record_count": 7}
        self.dataset_ref.get.return_value = metadata

        snapshots = []
        for number in range(7):
            row = MagicMock()
            row.to_dict.return_value = {
                "po_id": f"PO-{number}",
                "supplier": "Target Supplier" if number == 3 else "Other Supplier",
                "_record_number": number,
            }
            snapshots.append(row)

        with patch.object(firestore_db, "_stream_query_pages", return_value=iter(snapshots)):
            result = firestore_db.search_dataset_records(
                "company-a", "dataset-a", ["Target Supplier"], limit=5
            )

        self.assertEqual(result["scanned_count"], 7)
        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["records"][0]["po_id"], "PO-3")
        self.assertTrue(result["coverage_complete"])
        self.assertFalse(result["scan_limited"])

    def test_search_read_budget_reports_partial_coverage_not_no_match(self):
        metadata = MagicMock(exists=True)
        metadata.to_dict.return_value = {"records_status": "complete", "record_count": 7}
        self.dataset_ref.get.return_value = metadata

        snapshots = []
        for number in range(7):
            row = MagicMock()
            row.to_dict.return_value = {
                "po_id": f"PO-{number}", "supplier": "Other Supplier",
                "_record_number": number,
            }
            snapshots.append(row)

        with patch.object(firestore_db, "_stream_query_pages", return_value=iter(snapshots)):
            result = firestore_db.search_dataset_records(
                "company-a", "dataset-a", ["Missing Supplier"], limit=5, scan_limit=3
            )

        self.assertEqual(result["scanned_count"], 3)
        self.assertEqual(result["match_count"], 0)
        self.assertFalse(result["coverage_complete"])
        self.assertTrue(result["scan_limited"])

    def test_search_complete_no_match_is_distinguished_from_partial_scan(self):
        metadata = MagicMock(exists=True)
        metadata.to_dict.return_value = {"records_status": "complete", "record_count": 2}
        self.dataset_ref.get.return_value = metadata
        snapshots = []
        for number in range(2):
            row = MagicMock()
            row.to_dict.return_value = {
                "po_id": f"PO-{number}", "supplier": "Other Supplier",
                "_record_number": number,
            }
            snapshots.append(row)

        with patch.object(firestore_db, "_stream_query_pages", return_value=iter(snapshots)):
            result = firestore_db.search_dataset_records(
                "company-a", "dataset-a", ["Missing Supplier"], limit=5
            )

        self.assertEqual(result["match_count"], 0)
        self.assertTrue(result["coverage_complete"])
        self.assertFalse(result["scan_limited"])

    def test_dataset_deletion_recursively_removes_company_records(self):
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = {"storage": None}
        self.dataset_ref.get.return_value = snapshot
        with patch.object(firestore_db, "_company_ref", return_value=self.company):
            with patch.object(firestore_db, "get_firestore_client", return_value=self.client):
                with patch.object(firestore_db, "write_company_audit_event"):
                    deleted = firestore_db.delete_company_dataset(
                        "company-a", "dataset-a"
                    )
        self.assertTrue(deleted)
        self.client.recursive_delete.assert_called_once_with(self.dataset_ref)
        self.assertEqual(
            self.dataset_ref.set.call_args.args[0]["deletion_status"],
            "deleting",
        )

    def test_dataset_delete_recursively_removes_original_file_chunks(self):
        snapshot = MagicMock(exists=True)
        snapshot.to_dict.return_value = {
            "original_file_status": "complete",
            "original_file": {"filename": "orders.csv", "chunk_count": 1},
        }
        self.dataset_ref.get.return_value = snapshot
        with patch.object(firestore_db, "_company_ref", return_value=self.company):
            with patch.object(firestore_db, "get_firestore_client", return_value=self.client):
                with patch.object(firestore_db, "write_company_audit_event"):
                    deleted = firestore_db.delete_company_dataset("company-a", "dataset-a")
        self.assertTrue(deleted)
        self.client.recursive_delete.assert_called_once_with(self.dataset_ref)

    def test_missing_dataset_records_are_not_reported_as_empty_success(self):
        metadata = MagicMock(exists=False)
        self.dataset_ref.get.return_value = metadata
        with self.assertRaises(FileNotFoundError):
            firestore_db.get_dataset_records("company-a", "missing-dataset")
        
    def test_upload_record_count_is_bounded_before_writes(self):
        class OversizedList(list):
            def __len__(self):
                return 250_001

        records = OversizedList()
        with self.assertRaisesRegex(ValueError, "250,000 records"):
            firestore_db.save_dataset_records(
                "company-a", "dataset-a", records
            )
        self.dataset_ref.set.assert_not_called()

    def test_cross_company_dataset_delete_is_denied(self):
        with patch.object(
            firestore_db, "_company_ref",
            side_effect=PermissionError("cross-company access denied"),
        ):
            with self.assertRaises(PermissionError):
                firestore_db.delete_company_dataset("company-b", "dataset-a")
        self.client.recursive_delete.assert_not_called()

    def test_firestore_document_ids_are_bounded(self):
        with self.assertRaisesRegex(ValueError, "128 UTF-8 bytes"):
            firestore_db._validate_id("x" * 129, "dataset_id")

    def test_invalid_records_are_rejected_before_writes(self):
        with self.assertRaisesRegex(TypeError, "Each procurement record"):
            firestore_db.save_dataset_records(
                "company-a", "dataset-a", [{"po_id": "PO-1"}, "not-a-record"]
            )
        self.dataset_ref.set.assert_not_called()
        self.client.batch.assert_not_called()

    def test_cross_company_record_write_is_denied_before_firestore_client(self):
        with patch.object(
            firestore_db, "_company_ref",
            side_effect=PermissionError("cross-company access denied"),
        ):
            with self.assertRaises(PermissionError):
                firestore_db.save_dataset_records(
                    "company-b", "dataset-a", [{"po_id": "PO-1"}]
                )
        self.client.batch.assert_not_called()

    def test_oversized_record_is_rejected_before_writes(self):
        with self.assertRaisesRegex(ValueError, "too large"):
            firestore_db.save_dataset_records(
                "company-a", "dataset-a", [{"payload": "x" * 810_000}]
            )
        self.dataset_ref.set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
