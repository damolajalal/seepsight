"""Regression tests for saved dataset extension eligibility."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


class Snapshot:
    def __init__(self, snapshot_id, data):
        self.id = snapshot_id
        self._data = data

    def to_dict(self):
        return self._data


class DatasetGroupEligibilityTests(unittest.TestCase):
    def _groups(self, dataset_data, analysis_data):
        company = MagicMock()
        with patch.object(firestore_db, "_company_ref", return_value=company):
            with patch.object(
                firestore_db,
                "_stream_query_pages",
                side_effect=[
                    [Snapshot(key, value) for key, value in dataset_data],
                    [Snapshot(key, value) for key, value in analysis_data],
                ],
            ):
                return firestore_db.get_company_dataset_groups("company-a")

    def test_legacy_unlinked_dataset_is_not_extendable_or_deletable(self):
        groups = self._groups(
            [("legacy-file", {"filename": "legacy.csv"})],
            [("legacy-analysis", {"dataset_group_id": "legacy-file"})],
        )
        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0]["extendable"])
        self.assertFalse(groups[0]["deletion_safe"])

    def test_complete_group_with_original_file_is_extendable(self):
        groups = self._groups(
            [("file-a", {
                "dataset_group_id": "group-a",
                "filename": "orders.csv",
                "original_file_status": "complete",
                "record_count": 10,
                "source_record_count": 10,
            })],
            [("analysis-a", {"dataset_group_id": "group-a", "updated_at": None})],
        )
        self.assertTrue(groups[0]["extendable"])
        self.assertTrue(groups[0]["deletion_safe"])
        self.assertEqual(groups[0]["file_count"], 1)

    def test_group_with_missing_original_file_is_not_extendable(self):
        groups = self._groups(
            [("file-a", {
                "dataset_group_id": "group-a",
                "filename": "orders.csv",
                "original_file_status": "failed",
            })],
            [("analysis-a", {"dataset_group_id": "group-a"})],
        )
        self.assertFalse(groups[0]["extendable"])
        self.assertTrue(groups[0]["deletion_safe"])


if __name__ == "__main__":
    unittest.main()
