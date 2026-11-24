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
    @patch("seepsight.hybrid_ai.st.link_button")
    def test_only_bounded_verified_context_is_embedded(self, link_button, render):
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
        self.assertIn('allow="language-model"', html)
        link_button.assert_called_once_with("Open Hybrid AI separately for on-device testing", "https://example.web.app/")

    @patch("seepsight.hybrid_ai.st.info")
    @patch("seepsight.hybrid_ai.st.components.v1.html")
    @patch("seepsight.hybrid_ai.st.link_button")
    def test_non_https_companion_is_not_embedded(self, link_button, render, info):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "http://example.web.app/"}):
            hybrid_ai.render_verified_context("Supplier", "Finding", "Verified facts", "Explain")
        render.assert_not_called()
        info.assert_called_once()

    @patch("seepsight.hybrid_ai.st.warning")
    @patch("seepsight.hybrid_ai.st.components.v1.html")
    @patch("seepsight.hybrid_ai.st.link_button")
    def test_empty_evidence_is_not_sent(self, link_button, render, warning):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "https://example.web.app/"}):
            hybrid_ai.render_verified_context("Supplier", "Finding", " ", "Explain")
        render.assert_not_called()
        warning.assert_called_once()

    @patch("seepsight.hybrid_ai.st.components.v1.html")
    @patch("seepsight.hybrid_ai.st.link_button")
    def test_workspace_assistant_uses_separate_typed_payload(self, link_button, render):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "https://example.web.app/"}):
            hybrid_ai.render_workspace_assistant(
                "Northstar Supplies",
                "Company workspace: Northstar Supplies\nFindings: 2",
            )

        html = render.call_args.args[0]
        encoded = re.search(r"const encoded = '([^']+)'", html).group(1)
        payload = json.loads(base64.b64decode(encoded).decode("utf-8"))
        self.assertEqual(payload["type"], "seepsight:ask-hybrid-ai")
        self.assertEqual(payload["version"], 1)
        self.assertEqual(payload["supplier"], "Northstar Supplies")
        self.assertIn("Findings: 2", payload["verifiedFacts"])

    def test_native_prompt_includes_evidence_and_anti_invention_rules(self):
        prompt = hybrid_ai.build_native_prompt(
            "Which supplier has the highest potential exposure?",
            "Northstar Supplies: NGN 220,000.00. This is not a confirmed loss.",
        )
        self.assertIn("Northstar Supplies: NGN 220,000.00.", prompt)
        self.assertIn("Which supplier has the highest potential exposure?", prompt)
        self.assertIn("Do not invent suppliers", prompt)
        self.assertIn("transaction-level evidence was not included", prompt)

    def test_native_prompt_rejects_empty_evidence(self):
        with self.assertRaises(ValueError):
            hybrid_ai.build_native_prompt("What is the risk?", " ")

    def test_native_prompt_rejects_oversized_evidence(self):
        with self.assertRaises(ValueError):
            hybrid_ai.build_native_prompt("What is the risk?", "x" * 40001)

    def test_native_bridge_is_not_an_iframe(self):
        self.assertIsNotNone(hybrid_ai._NATIVE_AI_COMPONENT)
        self.assertIn("firebase-ai.js", hybrid_ai._NATIVE_AI_JS)
        self.assertIn("setStateValue", hybrid_ai._NATIVE_AI_JS)
        self.assertNotIn("<iframe", hybrid_ai._NATIVE_AI_JS)

    @patch("seepsight.hybrid_ai.st.warning")
    @patch("seepsight.hybrid_ai.st.components.v1.html")
    @patch("seepsight.hybrid_ai.st.link_button")
    def test_workspace_assistant_does_not_send_empty_summary(self, link_button, render, warning):
        with patch.dict(os.environ, {"SEEPSIGHT_HYBRID_AI_URL": "https://example.web.app/"}):
            hybrid_ai.render_workspace_assistant("Northstar Supplies", "")
        render.assert_not_called()
        warning.assert_called_once()




    @patch("seepsight.hybrid_ai.st.components.v1.html")
    @patch("seepsight.hybrid_ai.st.link_button")
    def test_deployed_hybrid_url_is_default_when_no_override_exists(self, link_button, render):
        with patch.dict(os.environ, {}, clear=True):
            hybrid_ai.render_workspace_assistant("Northstar Supplies", "Verified summary")
        html = render.call_args.args[0]
        self.assertIn("https://seepsight-hybrid-ai.web.app/", html)
        link_button.assert_called_once_with(
            "Open Hybrid AI separately for on-device testing",
            "https://seepsight-hybrid-ai.web.app/",
        )


if __name__ == "__main__":
    unittest.main()
