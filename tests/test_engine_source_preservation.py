"""Source-file reader tests for preserving original procurement values."""

import json
import os
import tempfile
import unittest
from decimal import Decimal

from seepsight import engine


class SourceValuePreservationTests(unittest.TestCase):
    def _write_temp(self, suffix, content):
        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=suffix, encoding="utf-8", delete=False
        )
        handle.write(content)
        handle.close()
        self.addCleanup(lambda: os.path.exists(handle.name) and os.unlink(handle.name))
        return handle.name

    def test_csv_reader_preserves_leading_zeroes_and_decimal_text(self):
        path = self._write_temp(
            ".csv",
            "PO Number,Amount\n0000123,12345678901234567890.123456789\n",
        )
        frame = engine.read_any(path)
        self.assertEqual(frame.iloc[0]["PO Number"], "0000123")
        self.assertEqual(frame.iloc[0]["Amount"], "12345678901234567890.123456789")

    def test_json_reader_preserves_high_precision_decimal_values(self):
        path = self._write_temp(
            ".json",
            '[{"po_id":"PO-1","amount":12345678901234567890.123456789}]',
        )
        frame = engine.read_any(path)
        self.assertEqual(
            frame.iloc[0]["amount"],
            Decimal("12345678901234567890.123456789"),
        )


if __name__ == "__main__":
    unittest.main()
