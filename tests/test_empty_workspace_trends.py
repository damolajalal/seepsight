"""Regression coverage for empty-but-valid procurement analysis workspaces."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from seepsight import engine


class EmptyWorkspaceTrendTests(unittest.TestCase):
    def test_empty_ledger_writes_readable_trend_csv_schemas(self):
        findings = pd.DataFrame(columns=[
            "finding_id", "entity", "finding_type", "affected_orders",
            "leakage", "orders_held",
        ])
        ledger = pd.DataFrame(columns=[
            "po_id", "supplier", "po_month", "ordered_qty",
            "received_qty", "po_total",
        ])
        result = {
            "config": dict(engine.DEFAULT_CONFIG),
            "ledger": ledger,
            "findings": findings,
            "quality": {
                "rows_in_file": 3,
                "rows_used": 0,
                "dropped": {"rows_without_order_number": 3},
                "warnings": ["No rows had a usable purchase-order number."],
                "detectors": {},
            },
            "mapping": {},
            "trace_all": pd.DataFrame(),
            "risk": None,
        }

        with tempfile.TemporaryDirectory() as folder:
            engine.build_data_pack(
                result, "Empty supplier dataset", out_dir=folder, zip_it=False
            )
            monthly = pd.read_csv(Path(folder) / "monthly_trend.csv")
            supplier_month = pd.read_csv(Path(folder) / "supplier_month.csv")

        self.assertTrue(monthly.empty)
        self.assertEqual(
            list(monthly.columns),
            [
                "po_month", "orders", "spend", "avg_days_late",
                "late_rate", "fill_rate", "avg_approval_days",
            ],
        )
        self.assertTrue(supplier_month.empty)
        self.assertEqual(
            list(supplier_month.columns),
            [
                "supplier", "po_month", "orders", "spend",
                "avg_days_late", "late_rate", "fill_rate",
                "avg_approval_days",
            ],
        )


if __name__ == "__main__":
    unittest.main()
