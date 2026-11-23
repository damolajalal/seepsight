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
