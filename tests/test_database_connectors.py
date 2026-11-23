"""Tests for safe external connector boundaries."""

import unittest
from unittest.mock import patch

from seepsight import database_connectors, secrets_manager


class SecretReferenceTests(unittest.TestCase):
    def test_accepts_secret_version_resource(self):
        value = "projects/seepsight-prod/secrets/procurement-db/versions/latest"
        self.assertEqual(secrets_manager.validate_secret_reference(value), value)

    def test_rejects_non_resource_or_injected_reference(self):
        for value in ("password=secret", "projects/p/secrets/s/versions/latest/extra", ""):
            with self.assertRaises(ValueError):
                secrets_manager.validate_secret_reference(value)


class ReadOnlyQueryTests(unittest.TestCase):
    def test_accepts_select_and_cte(self):
        self.assertEqual(
            database_connectors.validate_readonly_sql("SELECT id FROM orders;"),
            "SELECT id FROM orders",
        )
        self.assertTrue(
            database_connectors.validate_readonly_sql(
                "WITH recent AS (SELECT id FROM orders) SELECT id FROM recent"
            ).startswith("WITH")
        )

    def test_rejects_mutations_and_multiple_statements(self):
        bad = [
            "DELETE FROM orders",
            "WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x",
            "SELECT * FROM orders; DROP TABLE orders",
            "SELECT * FROM orders FOR UPDATE",
            "SELECT * INTO archived_orders FROM orders",
            "SELECT * FROM orders -- comment",
            "UPDATE orders SET qty = 0",
        ]
        for sql in bad:
            with self.subTest(sql=sql):
                with self.assertRaises(ValueError):
                    database_connectors.validate_readonly_sql(sql)

    def test_rejects_unbounded_limits(self):
        with self.assertRaises(ValueError):
            database_connectors._validate_limits(1001, 10)
        with self.assertRaises(ValueError):
            database_connectors._validate_limits(10, 120)

    def test_readonly_query_dispatches_with_bounds_and_parameters(self):
        with patch.object(database_connectors, "access_secret_json", return_value={"host": "db"}):
            with patch.object(
                database_connectors, "_postgres",
                return_value=(["id"], [{"id": 1}], False),
            ) as adapter:
                result = database_connectors.execute_readonly_query(
                    "postgres",
                    "projects/p/secrets/db/versions/latest",
                    "SELECT id FROM orders WHERE id = %s",
                    parameters=[7],
                    max_rows=25,
                    timeout_seconds=8,
                )
        self.assertEqual(result["rows"], [{"id": 1}])
        self.assertEqual(result["provider"], "postgres")
        adapter.assert_called_once_with(
            {"host": "db"}, "SELECT id FROM orders WHERE id = %s",
            [7], 25, 8,
        )

    def test_secret_access_failure_is_sanitized(self):
        with patch.object(
            database_connectors, "access_secret_json",
            side_effect=RuntimeError("private secret payload"),
        ):
            with self.assertRaisesRegex(RuntimeError, "private secret payload"):
                database_connectors.execute_readonly_query(
                    "postgres",
                    "projects/p/secrets/db/versions/latest",
                    "SELECT 1",
                )

    def test_provider_timeout_is_sanitized(self):
        with patch.object(database_connectors, "access_secret_json", return_value={}):
            with patch.object(
                database_connectors, "_postgres",
                side_effect=TimeoutError("socket timeout"),
            ):
                with self.assertRaisesRegex(RuntimeError, "database query failed"):
                    database_connectors.execute_readonly_query(
                        "postgres",
                        "projects/p/secrets/db/versions/latest",
                        "SELECT 1",
                    )

    def test_invalid_query_is_rejected_before_secret_access(self):
        with patch.object(database_connectors, "access_secret_json") as secret:
            with self.assertRaises(ValueError):
                database_connectors.execute_readonly_query(
                    "postgres",
                    "projects/p/secrets/db/versions/latest",
                    "DROP TABLE orders",
                )
            secret.assert_not_called()


if __name__ == "__main__":
    unittest.main()
