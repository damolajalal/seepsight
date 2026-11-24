"""Tests for logical dataset-group inventory and extension references."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


def snapshot(snapshot_id, payload):
    item = MagicMock()
    item.id = snapshot_id
    item.to_dict.return_value = payload
    return item


class DatasetGroupManagementTests(unittest.TestCase):
    def test_group_inventory_exposes_source_file_references_and_types(self):
        company = MagicMock()
        datasets = MagicMock()
        analyses = MagicMock()
        company.collection.side_effect = lambda name: {
            "datasets": datasets,
            "analyses": analyses,
        }[name]
        dataset_rows = [
            snapshot("file-orders", {
                "dataset_group_id": "group-a",
                "filename": "orders.csv",
                "dataset_type": "orders",
                "source_sha256": "abc",
                "record_count": 12,
                "source_record_count": 12,
            }),
            snapshot("file-suppliers", {
                "dataset_group_id": "group-a",
                "filename": "suppliers.csv",
                "dataset_type": "suppliers",
                "source_sha256": "def",
                "record_count": 4,
                "source_record_count": 4,
            }),
        ]
        analysis_rows = [
            snapshot("group-a", {
                "dataset_group_id": "group-a",
                "company_name": "Example Co",
                "updated_at": None,
                "workspace_status": "complete",
            })
        ]
        with patch.object(firestore_db, "_company_ref", return_value=company):
            with patch.object(
                firestore_db,
                "_stream_query_pages",
                side_effect=[iter(dataset_rows), iter(analysis_rows)],
            ):
                groups = firestore_db.get_company_dataset_groups("company-a")

        self.assertEqual(len(groups), 1)
        group = groups[0]
        self.assertTrue(group["deletion_safe"])
        self.assertEqual(group["dataset_group_id"], "group-a")
        self.assertEqual(group["file_count"], 2)
        self.assertEqual(
            {item["dataset_type"] for item in group["file_items"]},
            {"orders", "suppliers"},
        )
        self.assertEqual(
            {item["dataset_id"] for item in group["file_items"]},
            {"file-orders", "file-suppliers"},
        )

    def test_legacy_file_without_group_link_is_not_marked_safe_to_extend_or_delete(self):
        company = MagicMock()
        datasets = MagicMock()
        analyses = MagicMock()
        company.collection.side_effect = lambda name: {
            "datasets": datasets,
            "analyses": analyses,
        }[name]
        dataset_rows = [
            snapshot("legacy-file", {
                "filename": "legacy-orders.csv",
                "dataset_type": "orders",
            })
        ]
        analysis_rows = [
            snapshot("legacy-file", {
                "company_name": "Legacy Co",
                "workspace_status": "complete",
            })
        ]
        with patch.object(firestore_db, "_company_ref", return_value=company):
            with patch.object(
                firestore_db,
                "_stream_query_pages",
                side_effect=[iter(dataset_rows), iter(analysis_rows)],
            ):
                groups = firestore_db.get_company_dataset_groups("company-a")

        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0]["deletion_safe"])
        self.assertEqual(groups[0]["file_items"][0]["dataset_id"], "legacy-file")


if __name__ == "__main__":
    unittest.main()
