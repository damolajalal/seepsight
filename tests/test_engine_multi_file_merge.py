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

    def test_complementary_po_exports_are_coalesced_without_false_conflict(self):
        first = pd.DataFrame([{
            "po_id": "PO-2026-00116",
            "supplier": "North Star Supplies",
            "po_date": pd.Timestamp("2026-02-10"),
            "ordered_qty": 20,
            "po_unit_price": 150,
            "branch": None,
        }])
        second = pd.DataFrame([{
            "po_id": "PO-2026-00116",
            "supplier": "North Star Supplies",
            "po_date": pd.Timestamp("2026-02-10"),
            "ordered_qty": 20,
            "po_unit_price": 150,
            "branch": "Kano",
        }])
        combined, report = engine.combine_dataset_frames("orders", [first, second])
        self.assertEqual(len(combined), 1)
        self.assertEqual(combined.loc[0, "branch"], "Kano")
        self.assertEqual(report["duplicate_order_ids_removed"], 1)

    def test_conflicting_populated_values_still_block_po_merge(self):
        first = pd.DataFrame([{"po_id": "PO-001", "supplier": "Supplier A", "ordered_qty": 10}])
        second = pd.DataFrame([{"po_id": "PO-001", "supplier": "Supplier B", "ordered_qty": 10}])
        with self.assertRaisesRegex(ValueError, "supplier"):
            engine.combine_dataset_frames("orders", [first, second])

    def test_generator_branch_and_price_amendment_tables_are_supported(self):
        self.assertIn("branches", engine.TABLE_FIELDS)
        self.assertIn("price_amendments", engine.TABLE_FIELDS)
        self.assertIn("branches", engine.DATASET_REGISTRY)
        self.assertIn("price_amendments", engine.DATASET_REGISTRY)
        self.assertEqual(engine._table_key_fields("branches", pd.DataFrame(columns=["branch_id"])), ["branch_id"])
        self.assertEqual(engine._table_key_fields("price_amendments", pd.DataFrame(columns=["amendment_id"])), ["amendment_id"])

    def test_branch_master_relationship_is_checked(self):
        report, warnings = engine._relationship_quality({
            "orders": pd.DataFrame({
                "po_id": ["PO-1", "PO-2"],
                "branch_id": ["BR-01", "BR-99"],
            }),
            "branches": pd.DataFrame({
                "branch_id": ["BR-01"],
                "branch": ["Kano"],
            }),
        })
        self.assertEqual(report["orders_to_branches"]["matched_keys"], 1)
        self.assertEqual(report["orders_to_branches"]["source_keys"], 2)
        self.assertTrue(any("branch IDs" in warning for warning in warnings))

    def test_real_world_approval_export_headers_map_without_guessing(self):
        source = pd.DataFrame([{
            "approval_id": "APR-001", "po_id": "PO-001", "invoice_id": "INV-001",
            "approval_type": "Invoice", "approval_stage": "Finance",
            "requested_date": "2026-01-01", "approved_date": "2026-01-03",
            "approver_id": "USR-01", "approver_name": "Finance Lead",
            "approval_status": "Approved", "rejection_reason": "",
        }])
        mapping, _, _ = engine.suggest_mapping(source, fields=engine.TABLE_FIELDS["approvals"])
        self.assertEqual(mapping["approval_event_id"]["column"], "approval_id")
        self.assertEqual(mapping["approval_requested_at"]["column"], "requested_date")
        self.assertEqual(mapping["approval_completed_at"]["column"], "approved_date")

    def test_real_world_branch_master_headers_map_branch_name(self):
        source = pd.DataFrame([{
            "branch_id": "BR-01", "branch_name": "Kano", "city": "Kano",
            "state": "Kano", "region": "North West", "branch_type": "Regional",
            "manager_name": "Manager", "opened_date": "2020-01-01",
            "branch_status": "Active",
        }])
        mapping, _, _ = engine.suggest_mapping(source, fields=engine.TABLE_FIELDS["branches"])
        self.assertEqual(mapping["branch_id"]["column"], "branch_id")
        self.assertEqual(mapping["branch"]["column"], "branch_name")
        self.assertEqual(mapping["state"]["column"], "state")
        self.assertEqual(mapping["region"]["column"], "region")

    def test_real_world_price_amendment_headers_keep_approval_and_reason_distinct(self):
        source = pd.DataFrame([{
            "amendment_id": "AMD-001", "po_id": "PO-001", "contract_id": "",
            "supplier_id": "SUP-01", "product_id": "PRD-01",
            "original_unit_price": 100, "amended_unit_price": 110,
            "effective_date": "2026-01-01", "approval_date": "2025-12-29",
            "approved_by": "Finance Lead", "reason": "Market adjustment",
            "amendment_status": "Approved",
        }])
        mapping, _, _ = engine.suggest_mapping(source, fields=engine.TABLE_FIELDS["price_amendments"])
        self.assertEqual(mapping["effective_date"]["column"], "effective_date")
        self.assertEqual(mapping["amendment_approval_date"]["column"], "approval_date")
        self.assertEqual(mapping["amendment_approved_by"]["column"], "approved_by")
        self.assertEqual(mapping["amendment_reason"]["column"], "reason")
        self.assertEqual(mapping["approval_status"]["column"], "amendment_status")

    def test_every_registered_table_field_has_a_data_contract(self):
        for table_name, fields in engine.TABLE_FIELDS.items():
            for field in fields:
                self.assertIn(field, engine.CONTRACT, f"{table_name}.{field} has no field contract")

    def test_foreign_key_quality_reports_orphans_without_dropping_rows(self):
        report, warnings = engine._relationship_quality({
            "orders": pd.DataFrame({"po_id": ["PO-1"]}),
            "invoices": pd.DataFrame({
                "invoice_id": ["INV-1", "INV-2"],
                "po_id": ["PO-1", "PO-MISSING"],
            }),
        })
        relation = report["invoices.po_id_to_orders.po_id"]
        self.assertEqual(relation["orphan_keys"], 1)
        self.assertEqual(relation["coverage"], 0.5)
        self.assertTrue(any("Source rows were retained" in warning for warning in warnings))

    def test_identifier_normalisation_preserves_significant_leading_zeroes(self):
        keys = engine._id_key(pd.Series(["001", "1", "PO-001", "po 001"]))
        self.assertNotEqual(keys.iloc[0], keys.iloc[1])
        self.assertEqual(keys.iloc[2], keys.iloc[3])

    def test_pending_is_preserved_as_a_valid_business_status(self):
        cleaned = engine.clean_text(pd.Series(["Pending", "Approved", "N/A", ""]))
        self.assertEqual(cleaned.iloc[0], "Pending")
        self.assertEqual(cleaned.iloc[1], "Approved")
        self.assertTrue(pd.isna(cleaned.iloc[2]))
        self.assertTrue(pd.isna(cleaned.iloc[3]))

    def test_transaction_aggregates_do_not_shadow_order_columns_with_suffixes(self):
        orders = pd.DataFrame([{
            "po_id": "PO-1",
            "supplier": "Supplier A",
            "po_date": "2026-01-01",
            "ordered_qty": 10,
            "po_unit_price": 10,
            "received_qty": 2,
            "received_date": "2026-01-02",
            "invoice_qty": 2,
            "invoice_unit_price": 10,
            "approval_requested_at": "2026-01-01",
            "approval_completed_at": "2026-01-02",
        }])
        receipts = pd.DataFrame([{
            "receipt_id": "REC-1", "po_id": "PO-1",
            "received_qty": 8, "received_date": "2026-01-05",
        }])
        invoices = pd.DataFrame([{
            "invoice_id": "INV-1", "po_id": "PO-1",
            "invoice_qty": 9, "invoice_unit_price": 12,
            "invoice_date": "2026-01-06",
        }])
        approvals = pd.DataFrame([{
            "approval_event_id": "APR-1", "po_id": "PO-1",
            "approval_requested_at": "2026-01-01",
            "approval_completed_at": "2026-01-04",
            "approval_stage": "Finance",
        }])

        result = engine.onboard_tables({
            "orders": orders,
            "receipts": receipts,
            "invoices": invoices,
            "approvals": approvals,
        }, verbose=False, with_ml=False)

        self.assertNotIn("stopped", result)
        ledger = result["ledger"]
        self.assertEqual(len(ledger), 1)
        self.assertEqual(ledger.loc[0, "received_qty"], 8)
        self.assertEqual(ledger.loc[0, "received_date"], pd.Timestamp("2026-01-05"))
        self.assertEqual(ledger.loc[0, "invoice_qty"], 9)
        self.assertEqual(ledger.loc[0, "invoice_unit_price"], 12)
        self.assertEqual(
            ledger.loc[0, "approval_completed_at"], pd.Timestamp("2026-01-04")
        )
        self.assertFalse(any(column.endswith(("_x", "_y")) for column in ledger.columns))

    def test_missing_transaction_identifier_requires_review_not_silent_acceptance(self):
        result = engine.onboard_tables({
            "orders": pd.DataFrame([{
                "po_id": "PO-1", "supplier": "Supplier A",
                "po_date": "2026-01-01", "ordered_qty": 10, "po_unit_price": 5,
            }]),
            "receipts": pd.DataFrame([{"po_id": "PO-1", "received_qty": 10}]),
        }, verbose=False, with_ml=False)
        self.assertEqual(
            result["dataset_quality"]["receipts"]["readiness"],
            "needs review - no stable identifier",
        )
        self.assertTrue(any("no stable record identifier" in warning for warning in result["quality"]["warnings"]))

    def test_transaction_primary_keys_are_recognised(self):
        self.assertEqual(engine._table_key_fields("approvals", pd.DataFrame(columns=["approval_event_id"])), ["approval_event_id"])
        self.assertEqual(engine._table_key_fields("receipts", pd.DataFrame(columns=["receipt_id"])), ["receipt_id"])
        self.assertEqual(engine._table_key_fields("inventory", pd.DataFrame(columns=["inventory_id"])), ["inventory_id"])

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
