"""Regression checks for the unified Phase 8 Ask Seepsight workflow."""

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Phase8AssistantIntegrationTests(unittest.TestCase):
    def test_hybrid_assistant_is_part_of_ask_seepsight_navigation(self):
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        page_paths = {
            node.args[0].value
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "Page"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        }
        self.assertIn("pages/ask.py", page_paths)
        self.assertNotIn("pages/ask_hybrid.py", page_paths)

    def test_integrated_assistant_uses_active_company_retrieval(self):
        source = (ROOT / "pages/ask.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        retrieval_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "retrieve_workspace_context"
        ]
        self.assertEqual(len(retrieval_calls), 1)
        call = retrieval_calls[0]
        keywords = {item.arg: item.value for item in call.keywords}
        self.assertIn("company_id", keywords)
        self.assertIn("cases", keywords)
        self.assertIsInstance(keywords["company_id"], ast.Name)
        self.assertEqual(keywords["company_id"].id, "company_id")

    def test_retrieved_context_is_reviewable_before_hybrid_handoff(self):
        source = (ROOT / "pages/ask.py").read_text(encoding="utf-8")
        self.assertIn('st.expander("Review retrieved evidence before sending"', source)
        self.assertIn("hybrid_ai.build_native_prompt(", source)
        self.assertIn('"context": evidence[:40000]', source)
        self.assertIn("ask_hybrid_pending_{workspace_key}", source)
        self.assertIn("ask_hybrid_review_{workspace_key}", source)
        self.assertIn('company_id = w.get("company_id")', source)

    def test_hybrid_handoff_uses_existing_secure_bridge(self):
        source = (ROOT / "seepsight/hybrid_ai.py").read_text(encoding="utf-8")
        self.assertIn("def render_workspace_assistant(", source)
        self.assertIn("seepsight:ask-hybrid-ai", source)
        self.assertIn("postMessage(payload", source)
        self.assertIn("target_origin", source)
        self.assertIn("[:40000]", source)

    def test_hybrid_bridge_accepts_the_full_bounded_workspace_context(self):
        source = (ROOT / "web-hybrid-ai/src/main.js").read_text(encoding="utf-8")
        self.assertIn("facts: 40000", source)
        self.assertNotIn("facts: 12000", source)
        bridge = (ROOT / "seepsight/hybrid_ai.py").read_text(encoding="utf-8")
        self.assertIn("[:40000]", bridge)


if __name__ == "__main__":
    unittest.main()
