"""Tests for the authenticated Seepsight-to-Hybrid-AI context bridge."""

import base64
import json
import os
import re
import unittest
from unittest.mock import patch

from seepsight import hybrid_ai


class HybridAIHandoffTests(unittest.TestCase):
    @patch("seepsight.hybrid_ai.st.components.v1.html")
    def test_only_bounded_verified_context_is_embedded(self, render):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "https://example.web.app/"}):
            hybrid_ai.render_verified_context(
                "Northstar Supplies",
                "Invoice price above PO price",
                "Potential extra cost to review: NGN 120,000.00.",
                "Explain the discrepancy.",
            )

        html = render.call_args.args[0]
        encoded = re.search(r"const encoded = '([^']+)'", html).group(1)
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        self.assertEqual(payload["supplier"], "Northstar Supplies")
        self.assertEqual(payload["findingType"], "Invoice price above PO price")
        self.assertEqual(payload["verifiedFacts"], "Potential extra cost to review: NGN 120,000.00.")
        self.assertIn("postMessage(payload, 'https://example.web.app')", html)

    @patch("seepsight.hybrid_ai.st.info")
    @patch("seepsight.hybrid_ai.st.components.v1.html")
    def test_non_https_companion_is_not_embedded(self, render, info):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "http://example.web.app/"}):
            hybrid_ai.render_verified_context("Supplier", "Finding", "Verified facts", "Explain")
        render.assert_not_called()
        info.assert_called_once()

    @patch("seepsight.hybrid_ai.st.warning")
    @patch("seepsight.hybrid_ai.st.components.v1.html")
    def test_empty_evidence_is_not_sent(self, render, warning):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "https://example.web.app/"}):
            hybrid_ai.render_verified_context("Supplier", "Finding", " ", "Explain")
        render.assert_not_called()
        warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
