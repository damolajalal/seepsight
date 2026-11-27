"""Tests for the optional, fixed-query BigQuery enrichment layer."""

import unittest
from unittest.mock import patch

from seepsight import bigquery_enrichment


class BigQueryQuestionRoutingTests(unittest.TestCase):
    def setUp(self):
        self.project = "traceiq-514409"
        self.dataset = "traceiq"

    def assert_readonly_bounded_query(self, question, expected_view):
        view, sql = bigquery_enrichment._query_for_question(
            question, self.project, self.dataset
        )
        self.assertEqual(view, expected_view)
        self.assertTrue(sql.lstrip().upper().startswith("SELECT"))
        self.assertIn(f"`{self.project}.{self.dataset}.{expected_view}`", sql)
        self.assertIn("LIMIT 12", sql)
        self.assertNotIn(question, sql)

    def test_short_delivery_questions_use_short_delivery_view(self):
        self.assert_readonly_bounded_query(
            "Show short delivery exposure", "v_short_delivery"
        )

    def test_price_questions_use_price_variance_view(self):
        self.assert_readonly_bounded_query(
            "Which invoices have a price discrepancy?", "v_price_variance"
        )

    def test_approval_questions_use_slow_approvals_view(self):
        self.assert_readonly_bounded_query(
            "Which approvals took the longest?", "v_slow_approvals"
        )

    def test_supplier_performance_questions_use_deterioration_view(self):
        self.assert_readonly_bounded_query(
            "Which supplier has declining performance?", "v_supplier_deterioration"
        )

    def test_monthly_supplier_questions_use_monthly_view(self):
        self.assert_readonly_bounded_query(
            "Show monthly delivery rates", "v_supplier_month"
        )

    def test_general_exposure_questions_use_findings_register(self):
        self.assert_readonly_bounded_query(
            "Which finding has the highest exposure?", "v_findings_register"
        )

    def test_unrelated_questions_do_not_run_bigquery(self):
        self.assertEqual(
            bigquery_enrichment._query_for_question(
                "Tell me a joke", self.project, self.dataset
            ),
            (None, None),
        )

    def test_disabled_configuration_is_a_safe_noop(self):
        with patch.object(bigquery_enrichment, "_settings", return_value=None):
            self.assertEqual(
                bigquery_enrichment.enrich_question("Show exposure", "company-a"),
                {"status": "disabled"},
            )


if __name__ == "__main__":
    unittest.main()
