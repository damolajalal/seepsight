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

    def test_invoice_question_lists_invoice_findings(self):
        result = answer_question(self.workspace, "Show me invoice price discrepancies")
        self.assertIn("1 invoice-price finding", result["answer"])
        self.assertIn("20.0000%", result["answer"])

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
