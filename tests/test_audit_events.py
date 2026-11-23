"""Tests for bounded, credential-safe company audit events."""

import unittest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from seepsight import firestore_db


class CompanyAuditEventTests(unittest.TestCase):
    def test_audit_event_filters_secrets_and_persists_company_scoped_event(self):
        company = MagicMock()
        with patch.object(firestore_db, "_company_ref", return_value=company):
            event_id = firestore_db.write_company_audit_event(
                "company-a",
                "dataset.records_saved",
                "dataset",
                "dataset-a",
                {
                    "record_count": 12,
                    "api_key": "must-not-persist",
                    "nested": {"password": "hidden", "status": "complete"},
                    "amount": Decimal("10.000000000000000009"),
                },
            )

        self.assertTrue(event_id)
        event_ref = company.collection.return_value.document.return_value
        payload = event_ref.create.call_args.args[0]
        self.assertNotIn("api_key", payload["details"])
        self.assertNotIn("password", payload["details"]["nested"])
        self.assertEqual(payload["details"]["record_count"], 12)
        self.assertEqual(
            payload["details"]["amount"],
            {"__seepsight_decimal__": "10.000000000000000009"},
        )

    def test_audit_event_rejects_oversized_details(self):
        with self.assertRaisesRegex(ValueError, "size limit"):
            firestore_db.write_company_audit_event(
                "company-a", "dataset.records_saved", "dataset", "dataset-a",
                {"description": "x" * 13_000},
            )

    def test_audit_event_rejects_invalid_event_names(self):
        with self.assertRaises(ValueError):
            firestore_db.write_company_audit_event(
                "company-a", "UPLOAD SECRET", "dataset", "dataset-a", {}
            )


if __name__ == "__main__":
    unittest.main()
