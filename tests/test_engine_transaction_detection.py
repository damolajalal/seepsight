"""Transaction-level procurement discrepancy detector regression tests."""

import unittest

import pandas as pd

from seepsight import engine


class TransactionLevelDetectionTests(unittest.TestCase):
    def setUp(self):
        self.ledger = pd.DataFrame([{
            "po_id": "PO-SMALL-001",
            "supplier": "Example Supplier",
            "branch": "Kano",
            "po_date": pd.Timestamp("2026-01-01"),
            "promised_date": pd.Timestamp("2026-01-05"),
            "received_date": pd.Timestamp("2026-01-06"),
            "ordered_qty": 2.0,
            "received_qty": 1.0,
            "invoice_qty": 1.0,
            "po_unit_price": 100.00,
            "invoice_unit_price": 100.01,
            "invoice_date": pd.Timestamp("2026-01-06"),
            "approval_requested_at": pd.Timestamp("2026-01-01"),
            "approval_completed_at": pd.Timestamp("2026-01-06 00:14:24"),
            "approval_days": 5.01,
            "days_late": 1.0,
            "po_total": 200.0,
            "po_month": "2026-01",
        }])

    def test_one_small_record_generates_transaction_findings(self):
        findings = engine.detect(self.ledger)
        types = set(findings["finding_type"])

        self.assertIn("Short delivery", types)
        self.assertIn("Invoice price above PO price", types)
        self.assertIn("Slow approvals", types)
        self.assertIn("Late delivery", types)
        self.assertEqual(len(findings), 4)
        short = findings[findings["finding_type"] == "Short delivery"]
        self.assertEqual(float(short.iloc[0]["leakage"]), 0.0)

    def test_tiny_positive_price_difference_is_not_suppressed(self):
        findings = engine.detect(self.ledger)
        price = findings[findings["finding_type"] == "Invoice price above PO price"]

        self.assertEqual(len(price), 1)
        self.assertAlmostEqual(float(price.iloc[0]["leakage"]), 0.01, places=6)
        self.assertEqual(price.iloc[0]["severity"], "Low")

    def test_one_day_late_is_detected(self):
        findings = engine.detect(self.ledger)
        late = findings[findings["finding_type"] == "Late delivery"]
        self.assertEqual(len(late), 1)
        self.assertIn("1 day", late.iloc[0]["evidence"])

    def test_evidence_is_scoped_to_the_single_purchase_order(self):
        findings = engine.detect(self.ledger)
        evidence = engine.build_evidence(self.ledger, findings, engine.DEFAULT_CONFIG)
        self.assertEqual(set(evidence["po_id"]), {"PO-SMALL-001"})
        for finding_id in findings["finding_id"]:
            self.assertEqual(int((evidence["finding_id"] == finding_id).sum()), 1)


if __name__ == "__main__":
    unittest.main()
