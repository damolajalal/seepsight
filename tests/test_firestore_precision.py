"""Precision tests for durable analysis workspace serialization."""

import unittest
from decimal import Decimal

from seepsight import firestore_db


class WorkspaceDecimalSerializationTests(unittest.TestCase):
    def test_decimal_round_trip_preserves_exact_value(self):
        original = {
            "amount": Decimal("12345678901234567890.123456789012345678"),
            "nested": [
                {"tax": Decimal("0.000000000000000001")},
                Decimal("-987654321.000000000000000009"),
            ],
            "ordinary_text": "not a decimal",
            "count": 4,
        }

        encoded = firestore_db._normalise_workspace_value(original)
        decoded = firestore_db._denormalise_workspace_value(encoded)

        self.assertEqual(decoded, original)
        self.assertIsInstance(decoded["amount"], Decimal)
        self.assertIsInstance(decoded["nested"][0]["tax"], Decimal)
        self.assertIsInstance(decoded["nested"][1], Decimal)

    def test_workspace_decimal_encoding_is_firestore_compatible(self):
        encoded = firestore_db._normalise_workspace_value(
            {"amount": Decimal("10.2300")}
        )

        self.assertEqual(
            encoded,
            {"amount": {"__seepsight_decimal__": "10.2300"}},
        )

    def test_existing_non_decimal_values_remain_unchanged(self):
        value = {"label": "invoice", "units": 12, "ratio": 0.25}
        self.assertEqual(
            firestore_db._denormalise_workspace_value(
                firestore_db._normalise_workspace_value(value)
            ),
            value,
        )


if __name__ == "__main__":
    unittest.main()
