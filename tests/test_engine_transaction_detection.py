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

    def test_one_day_late_is_detected_and_grouped_as_one_supplier_issue(self):
        findings = engine.detect(self.ledger)
        late = findings[findings["finding_type"] == "Late delivery"]
        self.assertEqual(len(late), 1)
        self.assertEqual(int(late.iloc[0]["affected_orders"]), 1)
        self.assertEqual(late.iloc[0]["po_ids"], ["PO-SMALL-001"])
        evidence = engine.build_evidence(self.ledger, findings, engine.DEFAULT_CONFIG)
        late_evidence = evidence[evidence["finding_id"] == late.iloc[0]["finding_id"]]
        self.assertEqual(len(late_evidence), 1)
        self.assertEqual(float(late_evidence.iloc[0]["days_late"]), 1.0)

    def test_many_orders_for_same_supplier_are_one_grouped_issue(self):
        ledger = pd.concat([self.ledger, self.ledger.assign(po_id="PO-SMALL-002")], ignore_index=True)
        findings = engine.detect(ledger)
        late = findings[findings["finding_type"] == "Late delivery"]
        self.assertEqual(len(late), 1)
        self.assertEqual(int(late.iloc[0]["affected_orders"]), 2)
        evidence = engine.build_evidence(ledger, findings, engine.DEFAULT_CONFIG)
        late_evidence = evidence[evidence["finding_id"] == late.iloc[0]["finding_id"]]
        self.assertEqual(set(late_evidence["po_id"]), {"PO-SMALL-001", "PO-SMALL-002"})

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

    def test_overpriced_invoice_is_not_hidden_by_a_cheaper_invoice(self):
        orders = pd.DataFrame([{
            "po_id": "PO-MULTI-001", "supplier": "Supplier A",
            "po_date": "2026-01-01", "ordered_qty": 20, "po_unit_price": 100,
        }])
        invoices = pd.DataFrame([
            {"invoice_id": "INV-HIGH", "po_id": "PO-MULTI-001", "invoice_qty": 1,
             "invoice_unit_price": 120, "invoice_date": "2026-01-03"},
            {"invoice_id": "INV-LOW", "po_id": "PO-MULTI-001", "invoice_qty": 1,
             "invoice_unit_price": 80, "invoice_date": "2026-01-04"},
        ])
        result = engine.onboard_tables(
            {"orders": orders, "invoices": invoices}, verbose=False, with_ml=False
        )
        price = result["findings"][
            result["findings"]["finding_type"] == "Invoice price above PO price"
        ]
        self.assertEqual(len(price), 1)
        self.assertAlmostEqual(float(price.iloc[0]["leakage"]), 20.0, places=6)
        self.assertIn("INV-HIGH", price.iloc[0]["evidence"])
        evidence = engine.build_evidence(result["ledger"], result["findings"], result["config"])
        price_evidence = evidence[evidence["finding_id"] == price.iloc[0]["finding_id"]]
        self.assertAlmostEqual(float(price_evidence.iloc[0]["exposure"]), 20.0, places=6)
        self.assertIn("INV-HIGH", price_evidence.iloc[0]["overpriced_invoice_ids"])

    def test_multiple_receipts_use_final_receipt_date_for_delivery_delay(self):
        orders = pd.DataFrame([{
            "po_id": "PO-RECEIPTS-001", "supplier": "Supplier B",
            "po_date": "2026-01-01", "ordered_qty": 10, "po_unit_price": 50,
            "promised_date": "2026-01-05",
        }])
        receipts = pd.DataFrame([
            {"po_id": "PO-RECEIPTS-001", "received_qty": 4, "received_date": "2026-01-02"},
            {"po_id": "PO-RECEIPTS-001", "received_qty": 6, "received_date": "2026-01-07"},
        ])
        result = engine.onboard_tables(
            {"orders": orders, "receipts": receipts}, verbose=False, with_ml=False
        )
        late = result["findings"][result["findings"]["finding_type"] == "Late delivery"]
        self.assertEqual(len(late), 1)
        self.assertIn("2 day", late.iloc[0]["evidence"])

    def test_outstanding_order_past_due_is_not_confirmed_as_late(self):
        ledger = self.ledger.copy()
        ledger.loc[0, "received_date"] = pd.NaT
        ledger.loc[0, "received_qty"] = 0
        ledger.loc[0, "days_late"] = pd.NA
        findings = engine.detect(ledger, {"as_of_date": "2026-01-10"})
        overdue = findings[findings["finding_type"] == "Overdue order awaiting receipt confirmation"]
        self.assertEqual(len(overdue), 1)
        self.assertEqual(int(overdue.iloc[0]["affected_orders"]), 1)
        self.assertNotIn("Late delivery", set(findings["finding_type"]))
        evidence = engine.build_evidence(ledger, findings, engine.DEFAULT_CONFIG)
        overdue_evidence = evidence[evidence["finding_id"] == overdue.iloc[0]["finding_id"]]
        self.assertEqual(len(overdue_evidence), 1)
        self.assertTrue(pd.isna(overdue_evidence.iloc[0]["received_date"]))

    def test_partial_delivery_before_due_date_is_not_short_delivery(self):
        ledger = self.ledger.copy()
        ledger.loc[0, "promised_date"] = pd.Timestamp("2026-12-01")
        ledger.loc[0, "received_date"] = pd.Timestamp("2026-11-20")
        ledger.loc[0, "received_qty"] = 1
        ledger.loc[0, "invoice_qty"] = 1
        findings = engine.detect(ledger, {"as_of_date": "2026-11-23"})
        self.assertNotIn("Short delivery", set(findings["finding_type"]))

    def test_evidence_is_scoped_to_the_single_purchase_order(self):
        findings = engine.detect(self.ledger)
        evidence = engine.build_evidence(self.ledger, findings, engine.DEFAULT_CONFIG)
        self.assertEqual(set(evidence["po_id"]), {"PO-SMALL-001"})
        for finding_id in findings["finding_id"]:
            self.assertEqual(int((evidence["finding_id"] == finding_id).sum()), 1)


if __name__ == "__main__":
    unittest.main()
