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

    def test_supplier_trend_without_quantity_fields_does_not_crash(self):
        dates = pd.date_range("2025-01-01", periods=6, freq="MS")
        ledger = pd.DataFrame({
            "po_id": [f"PO-{i}" for i in range(6)],
            "supplier": ["Supplier A"] * 6,
            "po_date": dates,
            "promised_date": dates,
            "received_date": dates + pd.to_timedelta([0, 0, 0, 5, 5, 5], unit="D"),
            "days_late": [0, 0, 0, 5, 5, 5],
            "po_month": dates.to_period("M").astype(str),
        })
        findings = engine.detect(ledger)
        self.assertIn("Supplier performance decline", set(findings["finding_type"]))

    def test_missing_order_value_does_not_break_slow_approval_detection(self):
        ledger = self.ledger.copy()
        ledger.loc[0, "po_total"] = pd.NA
        findings = engine.detect(ledger)
        self.assertIn("Slow approvals", set(findings["finding_type"]))

    def test_evidence_is_scoped_to_the_single_purchase_order(self):
        findings = engine.detect(self.ledger)
        evidence = engine.build_evidence(self.ledger, findings, engine.DEFAULT_CONFIG)
        self.assertEqual(set(evidence["po_id"]), {"PO-SMALL-001"})
        for finding_id in findings["finding_id"]:
            self.assertEqual(int((evidence["finding_id"] == finding_id).sum()), 1)


if __name__ == "__main__":
    unittest.main()
