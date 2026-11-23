"""Regression tests for the four-file procurement sample headers."""

import unittest

import pandas as pd

from seepsight import engine


class SampleHeaderMappingTests(unittest.TestCase):
    def test_four_file_headers_map_invoice_and_approval_fields(self):
        orders = pd.DataFrame([{
            "Order Number": "PO00001",
            "Vendor": "Example Supplier",
            "Order Date": "2026-01-01",
            "Qty": "10",
            "Unit Price": "100",
            "Site": "Kano",
            "Due Date": "2026-01-05",
        }])
        receipts = pd.DataFrame([{
            "PO No.": "po-00001",
            "Delivery Date": "2026-01-07",
            "Qty Delivered": "8",
        }])
        invoices = pd.DataFrame([{
            "PO Number": "po00001",
            "Invoice Date": "2026-01-08",
            "Qty Billed": "10",
            "Rate Billed": "110",
        }])
        approvals = pd.DataFrame([{
            "Order Ref": "PO00001",
            "Approval Level": "Finance",
            "Sent On": "2026-01-01 09:00:00.000000",
            "Completed On": "2026-01-08 09:00:00.000000",
        }])

        result = engine.onboard_tables(
            {
                "orders": orders,
                "receipts": receipts,
                "invoices": invoices,
                "approvals": approvals,
            },
            verbose=False,
            with_ml=False,
        )

        mapping = result["mapping"]
        self.assertEqual(mapping["invoices.invoice_unit_price"]["column"], "Rate Billed")
        self.assertEqual(mapping["invoices.invoice_qty"]["column"], "Qty Billed")
        self.assertEqual(mapping["approvals.approval_requested_at"]["column"], "Sent On")
        self.assertEqual(mapping["approvals.approval_completed_at"]["column"], "Completed On")

        ledger = result["ledger"]
        self.assertEqual(float(ledger.loc[0, "invoice_qty"]), 10.0)
        self.assertEqual(float(ledger.loc[0, "invoice_unit_price"]), 110.0)
        self.assertEqual(float(ledger.loc[0, "received_qty"]), 8.0)
        self.assertEqual(float(ledger.loc[0, "approval_days"]), 7.0)

        detector_status = result["quality"]["detectors"]
        self.assertEqual(detector_status["Short delivery"], "ready")
        self.assertEqual(detector_status["Invoice price above PO price"], "ready")
        self.assertEqual(detector_status["Slow approvals"], "ready")

        finding_types = set(result["findings"]["finding_type"])
        self.assertIn("Short delivery", finding_types)
        self.assertIn("Invoice price above PO price", finding_types)
        self.assertIn("Slow approvals", finding_types)


if __name__ == "__main__":
    unittest.main()
