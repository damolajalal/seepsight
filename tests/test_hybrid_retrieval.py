"""Tests for question-aware, tenant-local workspace retrieval."""

import unittest

import pandas as pd

from seepsight.hybrid_retrieval import retrieve_workspace_context


class HybridRetrievalTests(unittest.TestCase):
    def setUp(self):
        self.workspace = {
            "name": "Northstar Supplies",
            "cur": "NGN",
            "findings": pd.DataFrame([
                {"finding_id": "F-101", "finding_type": "Short delivery", "severity": "High", "supplier": "Apex"},
                {"finding_id": "F-102", "finding_type": "Invoice price mismatch", "severity": "Medium", "supplier": "Beacon"},
            ]),
            "evidence": pd.DataFrame([
                {"finding_id": "F-101", "evidence_id": "E-1", "order_id": "PO-77", "variance": "12 units"},
                {"finding_id": "F-102", "evidence_id": "E-2", "invoice_id": "INV-9", "variance": "NGN 500"},
            ]),
            "exposure": pd.DataFrame([
                {"supplier": "Apex", "exposure": "NGN 9000"},
                {"supplier": "Beacon", "exposure": "NGN 4000"},
            ]),
            "monthly": pd.DataFrame([{"month": "2026-10", "late_orders": 3}]),
            "supplier_month": pd.DataFrame([{"supplier": "Apex", "month": "2026-10", "score": 70}]),
            "risk": pd.DataFrame([{"order_id": "PO-77", "risk_type": "Short delivery"}]),
            "explanations": pd.DataFrame([{"finding_id": "F-101", "explanation": "Quantity mismatch"}]),
            "scorecard": pd.DataFrame([{"supplier": "Apex", "score": 70}]),
        }

    def test_supplier_question_retrieves_supplier_tables_and_question(self):
        result = retrieve_workspace_context(self.workspace, "Which supplier has the highest exposure?")
        self.assertIn("User question: Which supplier has the highest exposure?", result)
        self.assertIn("Exposure", result)
        self.assertIn("Apex", result)

    def test_broad_question_includes_cross_workspace_records_and_cases(self):
        cases = {"F-101": {"status": "Investigating", "owner": "Reviewer", "note": "Check PO", "history": ["Opened"]}}
        result = retrieve_workspace_context(self.workspace, "Give me an overall workspace summary", cases)
        self.assertIn("Scorecard", result)
        self.assertIn("Cases and actions", result)
        self.assertIn("F-101", result)

    def test_comparison_includes_all_matching_workspace_rows_and_all_fields(self):
        workspace = dict(self.workspace)
        workspace["supplier_month"] = pd.DataFrame([
            {"supplier": "Cedarline Traders", "fill_rate": 0.8, "custom_field_a": "alpha"},
            {"supplier": "Northstar Supplies Ltd", "fill_rate": 1.0, "custom_field_b": "beta"},
            {"supplier": "Maple Industrial", "fill_rate": 1.0, "custom_field_c": "gamma"},
        ])
        result = retrieve_workspace_context(
            workspace, "Compare Cedarline Traders and Northstar Supplies"
        )
        self.assertIn("Cedarline Traders", result)
        self.assertIn("Northstar Supplies Ltd", result)
        self.assertIn("Maple Industrial", result)
        self.assertIn("custom_field_a=alpha", result)
        self.assertIn("custom_field_b=beta", result)
        self.assertIn("custom_field_c=gamma", result)

    def test_case_question_includes_case_records_even_without_keyword_match(self):
        cases = {"F-101": {"status": "Open", "owner": "Reviewer", "note": "", "history": []}}
        result = retrieve_workspace_context(self.workspace, "Which cases are still open?", cases)
        self.assertIn("Cases and actions", result)
        self.assertIn("F-101", result)

    def test_missing_records_are_reported_as_coverage_limits(self):
        result = retrieve_workspace_context({"name": "Empty", "cur": "NGN"}, "Show supplier exposure")
        self.assertIn("Coverage limitations", result)
        self.assertIn("Do not treat absent records as zero risk", result)


    def test_reads_company_scoped_normalized_dataset_records(self):
        from unittest.mock import patch

        dataset = {
            "id": "dataset-1", "dataset_type": "orders", "filename": "orders.csv",
            "record_count": 30, "source_record_count": 30, "status": "complete",
        }
        rows = {"records": [{"po_id": "PO-10", "supplier": "Apex"}], "scanned_count": 30, "total_count": 30, "scan_limited": False}
        with patch("seepsight.firestore_db.get_company_datasets", return_value=[dataset]), \
             patch("seepsight.firestore_db.get_company_mapping", return_value={"supplier": "Supplier name"}), \
             patch("seepsight.firestore_db.search_dataset_records", return_value=rows) as search:
            result = retrieve_workspace_context(
                self.workspace, "Show purchase orders for Apex", company_id="company-1"
            )
        self.assertIn("orders normalized records", result)
        self.assertIn("PO-10", result)
        self.assertIn("Supplier name", result)
        search.assert_called_once()

    def test_partial_saved_dataset_scan_is_explicitly_warned(self):
        from unittest.mock import patch

        dataset = {
            "id": "dataset-1", "dataset_type": "orders",
            "filename": "orders.csv", "record_count": 3000,
        }
        rows = {
            "records": [], "scanned_count": 500, "total_count": 3000,
            "match_count": 0, "coverage_complete": False, "scan_limited": True,
        }
        with patch("seepsight.firestore_db.get_company_datasets", return_value=[dataset]), \
             patch("seepsight.firestore_db.get_company_mapping", return_value={}), \
             patch("seepsight.firestore_db.search_dataset_records", return_value=rows):
            result = retrieve_workspace_context(
                self.workspace, "Show purchase orders for Apex", company_id="company-1"
            )

        self.assertIn("coverage incomplete", result)
        self.assertIn("Do not conclude that no matching risk exists", result)
        self.assertNotIn("no records matched the search terms in the complete", result)

    def test_complete_saved_dataset_no_match_is_reported_as_complete(self):
        from unittest.mock import patch

        dataset = {
            "id": "dataset-1", "dataset_type": "orders",
            "filename": "orders.csv", "record_count": 30,
        }
        rows = {
            "records": [], "scanned_count": 30, "total_count": 30,
            "match_count": 0, "coverage_complete": True, "scan_limited": False,
        }
        with patch("seepsight.firestore_db.get_company_datasets", return_value=[dataset]), \
             patch("seepsight.firestore_db.get_company_mapping", return_value={}), \
             patch("seepsight.firestore_db.search_dataset_records", return_value=rows):
            result = retrieve_workspace_context(
                self.workspace, "Show purchase orders for Apex", company_id="company-1"
            )

        self.assertIn("coverage complete", result)
        self.assertIn("no records matched the search terms in the complete normalized dataset scan", result)

    def test_source_rows_are_only_requested_explicitly(self):
        from unittest.mock import patch

        dataset = {"id": "dataset-1", "dataset_type": "orders", "filename": "orders.csv"}
        result_rows = {"records": [], "scanned_count": 0, "total_count": 0, "scan_limited": False}
        with patch("seepsight.firestore_db.get_company_datasets", return_value=[dataset]), \
             patch("seepsight.firestore_db.get_company_mapping", return_value={}), \
             patch("seepsight.firestore_db.search_dataset_records", return_value=result_rows) as search:
            retrieve_workspace_context(
                self.workspace, "Show the original source rows for orders", company_id="company-1"
            )
        collections = [call.kwargs.get("collection_name") for call in search.call_args_list]
        self.assertIn("source_records", collections)

    def test_specific_purchase_order_id_reaches_saved_company_records(self):
        from unittest.mock import patch

        dataset = {
            "id": "orders-1", "dataset_type": "orders",
            "filename": "orders.csv", "record_count": 120,
        }
        rows = {
            "records": [{
                "po_id": "PO-002", "supplier": "Greenfield Supplies",
                "ordered_qty": 100, "received_qty": 80,
            }],
            "scanned_count": 120, "total_count": 120,
            "match_count": 1, "coverage_complete": True, "scan_limited": False,
        }
        with patch("seepsight.firestore_db.get_company_datasets", return_value=[dataset]), \
             patch("seepsight.firestore_db.get_company_mapping", return_value={}), \
             patch("seepsight.firestore_db.search_dataset_records", return_value=rows) as search:
            result = retrieve_workspace_context(
                self.workspace, "Find PO-002", company_id="company-1"
            )

        self.assertIn("PO-002", result)
        self.assertIn("Greenfield Supplies", result)
        search.assert_called_once()
        args, kwargs = search.call_args
        self.assertEqual(args[:2], ("company-1", "orders-1"))
        self.assertIn("po-002", args[2])
        self.assertEqual(kwargs.get("collection_name", "records"), "records")

    def test_ordinary_saved_record_question_does_not_read_original_source_rows(self):
        from unittest.mock import patch

        dataset = {"id": "orders-1", "dataset_type": "orders", "filename": "orders.csv"}
        rows = {
            "records": [{"po_id": "PO-10", "supplier": "Apex"}],
            "scanned_count": 1, "total_count": 1,
            "match_count": 1, "coverage_complete": True, "scan_limited": False,
        }
        with patch("seepsight.firestore_db.get_company_datasets", return_value=[dataset]), \
             patch("seepsight.firestore_db.get_company_mapping", return_value={}), \
             patch("seepsight.firestore_db.search_dataset_records", return_value=rows) as search:
            retrieve_workspace_context(
                self.workspace, "Find PO-10", company_id="company-1"
            )

        collections = [call.kwargs.get("collection_name", "records") for call in search.call_args_list]
        self.assertEqual(collections, ["records"])

    def test_empty_question_is_rejected(self):
        with self.assertRaises(ValueError):
            retrieve_workspace_context(self.workspace, "  ")


if __name__ == "__main__":
    unittest.main()
