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

    def test_case_question_includes_case_records_even_without_keyword_match(self):
        cases = {"F-101": {"status": "Open", "owner": "Reviewer", "note": "", "history": []}}
        result = retrieve_workspace_context(self.workspace, "Which cases are still open?", cases)
        self.assertIn("Cases and actions", result)
        self.assertIn("F-101", result)

    def test_missing_records_are_reported_as_coverage_limits(self):
        result = retrieve_workspace_context({"name": "Empty", "cur": "NGN"}, "Show supplier exposure")
        self.assertIn("Coverage limitations", result)
        self.assertIn("Do not treat absent records as zero risk", result)

    def test_empty_question_is_rejected(self):
        with self.assertRaises(ValueError):
            retrieve_workspace_context(self.workspace, "  ")


if __name__ == "__main__":
    unittest.main()
