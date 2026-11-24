"""Regression tests for safe multi-file procurement dataset merging."""

import unittest

import pandas as pd

from seepsight import engine


class MultiFileDatasetMergeTests(unittest.TestCase):
    def test_exact_duplicate_order_rows_are_removed(self):
        row = {
            "po_id": "PO-001",
            "supplier": "Example Supplies",
            "po_date": pd.Timestamp("2026-01-01"),
            "ordered_qty": 10.0,
            "po_unit_price": 25.0,
        }
        combined, report = engine.combine_dataset_frames(
            "orders", [pd.DataFrame([row]), pd.DataFrame([row])]
        )
        self.assertEqual(len(combined), 1)
        self.assertEqual(report["files_combined"], 2)
        self.assertEqual(report["exact_duplicate_rows_removed"], 1)

    def test_conflicting_rows_for_same_normalised_po_id_are_blocked(self):
        first = {
            "po_id": "PO-001",
            "supplier": "Example Supplies",
            "ordered_qty": 10.0,
            "po_unit_price": 25.0,
        }
        conflicting = {
            "po_id": "po 001",
            "supplier": "Example Supplies",
            "ordered_qty": 12.0,
            "po_unit_price": 25.0,
        }
        with self.assertRaisesRegex(ValueError, "conflicting rows"):
            engine.combine_dataset_frames(
                "orders", [pd.DataFrame([first]), pd.DataFrame([conflicting])]
            )

    def test_equivalent_po_id_formatting_is_consolidated_when_other_fields_match(self):
        first = pd.DataFrame([{
            "po_id": "PO-001", "supplier": "Example Supplies", "ordered_qty": 10,
        }])
        second = pd.DataFrame([{
            "po_id": "po 001", "supplier": "Example Supplies", "ordered_qty": 10,
        }])
        combined, report = engine.combine_dataset_frames("orders", [first, second])
        self.assertEqual(len(combined), 1)
        self.assertEqual(report["duplicate_order_ids_removed"], 1)

    def test_different_purchase_orders_combine(self):
        first = pd.DataFrame([{"po_id": "PO-001", "ordered_qty": 10}])
        second = pd.DataFrame([{"po_id": "PO-002", "ordered_qty": 20}])
        combined, report = engine.combine_dataset_frames("orders", [first, second])
        self.assertEqual(len(combined), 2)
        self.assertEqual(report["exact_duplicate_rows_removed"], 0)

    def test_transaction_tables_keep_repeated_business_keys_but_remove_exact_rows(self):
        line = {"po_id": "PO-001", "invoice_qty": 5, "invoice_unit_price": 10}
        another_line = {"po_id": "PO-001", "invoice_qty": 7, "invoice_unit_price": 10}
        combined, report = engine.combine_dataset_frames(
            "invoices",
            [pd.DataFrame([line, another_line]), pd.DataFrame([line])],
        )
        self.assertEqual(len(combined), 2)
        self.assertEqual(report["exact_duplicate_rows_removed"], 1)
        self.assertEqual(combined["invoice_qty"].sum(), 12)

    def test_missing_columns_are_aligned_across_files(self):
        first = pd.DataFrame([{"supplier": "A", "supplier_id": "S-1"}])
        second = pd.DataFrame([{"supplier": "B"}])
        combined, _ = engine.combine_dataset_frames("suppliers", [first, second])
        self.assertEqual(combined.loc[0, "supplier_id"], "S-1")
        self.assertTrue(pd.isna(combined.loc[1, "supplier_id"]))


if __name__ == "__main__":
    unittest.main()
