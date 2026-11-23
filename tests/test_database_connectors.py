"""Tests for safe external connector boundaries."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import database_connectors, secrets_manager, firestore_db


class SecretReferenceTests(unittest.TestCase):
    def test_accepts_secret_version_resource(self):
        value = "projects/seepsight-prod/secrets/procurement-db/versions/latest"
        self.assertEqual(secrets_manager.validate_secret_reference(value), value)

    def test_rejects_non_resource_or_injected_reference(self):
        for value in ("password=secret", "projects/p/secrets/s/versions/latest/extra", ""):
            with self.assertRaises(ValueError):
                secrets_manager.validate_secret_reference(value)


class ConnectionProfileTests(unittest.TestCase):
    def test_profile_stores_secret_reference_not_password(self):
        company = MagicMock()
        with patch.object(firestore_db, "_company_ref", return_value=company):
            with patch.object(firestore_db, "write_company_audit_event"):
                result = firestore_db.save_company_connection_profile(
                    "company-a", "db-profile-1",
                    {
                        "name": "Procurement warehouse",
                        "provider": "postgres",
                        "secret_reference": "projects/p/secrets/db/versions/latest",
                        "database": "procurement",
                    },
                )
        self.assertEqual(result, "db-profile-1")
        payload = company.collection.return_value.document.return_value.set.call_args.args[0]
        self.assertEqual(payload["secret_reference"], "projects/p/secrets/db/versions/latest")
        self.assertNotIn("password", payload)

    def test_company_query_uses_tenant_scoped_saved_profile(self):
        profile = {
            "provider": "postgres",
            "secret_reference": "projects/p/secrets/db/versions/latest",
            "status": "active",
            "max_rows": 75,
            "timeout_seconds": 9,
        }
        with patch.object(
            firestore_db, "get_company_connection_profile", return_value=profile
        ) as get_profile:
            with patch.object(firestore_db, "write_company_audit_event"):
                with patch.object(
                    database_connectors, "execute_readonly_query",
                    return_value={"rows": [], "columns": [], "row_count": 0, "truncated": False, "provider": "postgres"},
                ) as execute:
                    result = database_connectors.execute_company_connection_query(
                        "company-a", "profile-a", "SELECT 1"
                    )
        get_profile.assert_called_once_with("company-a", "profile-a")
        self.assertEqual(result["provider"], "postgres")
        self.assertEqual(execute.call_args.kwargs["max_rows"], 75)
        self.assertEqual(execute.call_args.kwargs["timeout_seconds"], 9)

    def test_profile_rejects_raw_credentials(self):
        with patch.object(firestore_db, "_company_ref", return_value=MagicMock()):
            with self.assertRaisesRegex(ValueError, "metadata and a secret reference"):
                firestore_db.save_company_connection_profile(
                    "company-a", "db-profile-1",
                    {
                        "name": "Bad profile",
                        "provider": "postgres",
                        "secret_reference": "projects/p/secrets/db/versions/latest",
                        "password": "must-not-be-stored",
                    },
                )


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
