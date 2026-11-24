"""Static syntax checks for Phase 3 Streamlit entry points."""

import ast
import unittest
from pathlib import Path


class Phase3PageSyntaxTests(unittest.TestCase):
    def test_settings_page_parses(self):
        source = Path("pages/settings.py").read_text(encoding="utf-8")
        ast.parse(source, filename="pages/settings.py")

    def test_connect_page_parses(self):
        source = Path("pages/connect.py").read_text(encoding="utf-8")
        ast.parse(source, filename="pages/connect.py")

    def test_ask_page_parses(self):
        source = Path("pages/ask.py").read_text(encoding="utf-8")
        ast.parse(source, filename="pages/ask.py")

    def test_hybrid_ai_module_parses(self):
        source = Path("seepsight/hybrid_ai.py").read_text(encoding="utf-8")
        ast.parse(source, filename="seepsight/hybrid_ai.py")

    def test_findings_page_parses(self):
        source = Path("pages/findings.py").read_text(encoding="utf-8")
        ast.parse(source, filename="pages/findings.py")

    def test_suppliers_page_parses(self):
        source = Path("pages/suppliers.py").read_text(encoding="utf-8")
        ast.parse(source, filename="pages/suppliers.py")

    def test_ask_page_has_no_charts(self):
        source = Path("pages/ask.py").read_text(encoding="utf-8")
        self.assertNotIn("st.bar_chart(", source)
        self.assertNotIn("st.line_chart(", source)

    def test_suppliers_page_has_no_charts(self):
        source = Path("pages/suppliers.py").read_text(encoding="utf-8")
        self.assertNotIn("st.bar_chart(", source)
        self.assertNotIn("st.line_chart(", source)

    def test_findings_and_overview_keep_visualisations(self):
        findings = Path("pages/findings.py").read_text(encoding="utf-8")
        overview = Path("pages/overview.py").read_text(encoding="utf-8")
        self.assertTrue("st.bar_chart(" in findings or "st.line_chart(" in findings)
        self.assertTrue("st.bar_chart(" in overview or "st.line_chart(" in overview)


if __name__ == "__main__":
    unittest.main()
