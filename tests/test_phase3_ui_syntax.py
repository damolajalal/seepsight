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


if __name__ == "__main__":
    unittest.main()
