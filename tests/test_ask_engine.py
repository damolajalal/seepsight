"""Regression tests for workspace-grounded Ask Seepsight answers."""
import unittest

import pandas as pd

from seepsight.ask_engine import answer_question


class AskEngineTests(unittest.TestCase):
    def setUp(self):
        self.workspace = {
            "cur": "NGN",
            "name": "Example Co",
            "findings": pd.DataFrame([
                {"finding_id": "F1", "finding_type": "Invoice price above PO price",
                 "supplier": "Northstar Supplies", "po_id": "PO-1", "severity": "High",
                 "identified_exposure": 120000.0, "order_value_held_up": 0.0,
                 "entity": "Northstar Supplies", "affected_orders": 1},
                {"finding_id": "F2", "finding_type": "Short delivery",
                 "supplier": "Cedarline Traders", "po_id": "PO-2", "severity": "High",
                 "identified_exposure": 70000.0, "order_value_held_up": 0.0,
                 "entity": "Cedarline Traders", "affected_orders": 1},
                {"finding_id": "F3", "finding_type": "Late delivery",
                 "supplier": "Cedarline Traders", "po_id": "PO-3", "severity": "Low",
                 "identified_exposure": 0.0, "order_value_held_up": 0.0,
                 "entity": "Cedarline Traders", "affected_orders": 1},
            ]),
            "evidence": pd.DataFrame([
                {"finding_id": "F1", "invoice_unit_price": 120.0, "po_unit_price": 100.0},
                {"finding_id": "F2", "ordered_qty": 10.0, "received_qty": 8.0},
                {"finding_id": "F3", "days_late": 1.0},
            ]),
            "exposure": pd.DataFrame([
                {"supplier": "Northstar Supplies", "total": 120000.0},
                {"supplier": "Cedarline Traders", "total": 70000.0},
            ]),
            "monthly": pd.DataFrame([{"spend": 3135000.0}]),
            "log": {"detectors": {"Short delivery": "ready", "Slow approvals": "ready",
                                  "Invoice price above PO price": "ready"}},
        }

    def test_supplier_exposure_answer_uses_saved_company_values(self):
        result = answer_question(self.workspace, "Which supplier has the highest potential exposure?")
        self.assertIn("Northstar Supplies", result["answer"])
        self.assertIn("NGN 120,000.00", result["answer"])
        self.assertIsNotNone(result["table"])

    def test_supplier_specific_question_uses_grouped_finding_supplier_names(self):
        self.workspace["findings"] = pd.DataFrame([
            {
                "finding_id": "F-GROUP-1",
                "finding_type": "Short delivery",
                "entity": "Multiple suppliers",
                "supplier_names": ["Northstar Supplies", "Cedarline Traders"],
                "severity": "High",
                "affected_orders": 2,
                "identified_exposure": 190000.0,
            }
        ])
        self.workspace["evidence"] = pd.DataFrame([
            {"finding_id": "F-GROUP-1", "supplier": "Northstar Supplies", "exposure": 120000.0},
            {"finding_id": "F-GROUP-1", "supplier": "Cedarline Traders", "exposure": 70000.0},
        ])

        result = answer_question(
            self.workspace, "Which supplier has the highest potential exposure: Cedarline Traders?"
        )

        self.assertIn("Cedarline Traders", result["answer"])
        self.assertIn("NGN 70,000.00", result["answer"])
        self.assertIn("1 finding group", result["answer"])

    def test_issue_type_exposure_question_ranks_finding_types(self):
        result = answer_question(
            self.workspace, "Which issue type contributes the most exposure?"
        )
        self.assertIn("Invoice price above PO price", result["answer"])
        self.assertIn("NGN 120,000.00", result["answer"])
        self.assertIsNotNone(result["table"])
        self.assertEqual(result["table"].iloc[0]["Issue type"], "Invoice price above PO price")

    def test_invoice_question_lists_invoice_findings(self):
        result = answer_question(self.workspace, "Show me invoice price discrepancies")
        self.assertIn("1 invoice-price finding", result["answer"])
        self.assertIn("20.0000%", result["answer"])

    def test_monthly_spend_trend_uses_saved_monthly_values(self):
        self.workspace["monthly"] = pd.DataFrame([
            {"po_month": "2026-08", "spend": 1000000},
            {"po_month": "2026-09", "spend": 1250000},
            {"po_month": "2026-10", "spend": 1500000},
        ])
        result = answer_question(self.workspace, "How has purchasing spend changed over time?")
        self.assertIn("increased", result["answer"])
        self.assertIn("NGN 500,000.00", result["answer"])
        self.assertIn("50.0%", result["answer"])
        self.assertEqual(len(result["table"]), 3)

    def test_one_month_does_not_claim_a_trend(self):
        result = answer_question(self.workspace, "How has purchasing spend changed over time?")
        self.assertIn("One month is not enough", result["answer"])

    def test_incomplete_detector_coverage_is_never_called_clean(self):
        self.workspace["log"]["detectors"]["Slow approvals"] = "skipped - missing approval dates"
        result = answer_question(self.workspace, "Were approvals slow?")
        self.assertIn("Coverage note", result["answer"])
        self.assertIn("incomplete", result["answer"].lower())

    def test_recommendations_are_based_on_present_finding_types(self):
        result = answer_question(self.workspace, "What should we investigate first?")
        self.assertIn("Invoice price above PO price", result["answer"])
        self.assertIn("Short delivery", result["answer"])
        self.assertIn("Late delivery", result["answer"])


if __name__ == "__main__":
    unittest.main()
