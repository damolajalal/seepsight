"""Company membership integrity tests."""

import unittest
from unittest.mock import MagicMock, patch

from seepsight import company_store


class CompanyMembershipTests(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.user_snapshot = MagicMock(exists=True)
        self.user_snapshot.to_dict.return_value = {
            "uid": "user-a",
            "company_id": "company-a",
            "email": "user-a@example.com",
        }
        self.company_snapshot = MagicMock(exists=True)
        self.company_snapshot.to_dict.return_value = {
            "name": "Company A",
            "status": "active",
        }
        self.member_snapshot = MagicMock(exists=True)
        self.member_snapshot.to_dict.return_value = {
            "uid": "user-a",
            "email": "user-a@example.com",
            "role": "owner",
            "status": "active",
        }

        users = self.client.collection.return_value
        user_ref = users.document.return_value
        user_ref.get.return_value = self.user_snapshot

        companies = self.client.collection.return_value
        company_ref = companies.document.return_value
        company_ref.get.return_value = self.company_snapshot
        company_ref.collection.return_value.document.return_value.get.return_value = self.member_snapshot

        self.client.collection.side_effect = lambda name: {
            "users": self.users_collection,
            "companies": self.companies_collection,
        }[name] if hasattr(self, "users_collection") else users

        # Explicit collection references avoid relying on MagicMock's chained names.
        self.users_collection = MagicMock()
        self.users_collection.document.return_value.get.return_value = self.user_snapshot
        self.companies_collection = MagicMock()
        self.companies_collection.document.return_value.get.return_value = self.company_snapshot
        self.companies_collection.document.return_value.collection.return_value.document.return_value.get.return_value = self.member_snapshot
        self.client.collection.side_effect = lambda name: {
            "users": self.users_collection,
            "companies": self.companies_collection,
        }[name]

        self.client_patch = patch.object(
            company_store, "get_firestore_client", return_value=self.client
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)

    def test_resolves_email_from_authoritative_membership(self):
        result = company_store.get_company_for_user("user-a")
        self.assertEqual(result["email"], "user-a@example.com")
        self.assertEqual(result["role"], "owner")

    def test_rejects_missing_user_record(self):
        self.user_snapshot.exists = False
        with self.assertRaisesRegex(PermissionError, "No company workspace"):
            company_store.get_company_for_user("user-a")

    def test_rejects_user_profile_uid_mismatch(self):
        self.user_snapshot.to_dict.return_value = {
            "uid": "user-b",
            "company_id": "company-a",
            "email": "user-a@example.com",
        }
        with self.assertRaisesRegex(PermissionError, "profile could not be verified"):
            company_store.get_company_for_user("user-a")

    def test_rejects_missing_company_or_membership(self):
        self.member_snapshot.exists = False
        with self.assertRaisesRegex(PermissionError, "membership"):
            company_store.get_company_for_user("user-a")

    def test_rejects_inactive_membership(self):
        self.member_snapshot.to_dict.return_value = {
            "uid": "user-a", "email": "user-a@example.com",
            "role": "owner", "status": "suspended",
        }
        with self.assertRaisesRegex(PermissionError, "not active"):
            company_store.get_company_for_user("user-a")

    def test_rejects_suspended_company(self):
        self.company_snapshot.to_dict.return_value = {
            "name": "Company A", "status": "suspended",
        }
        with self.assertRaisesRegex(PermissionError, "workspace is not active"):
            company_store.get_company_for_user("user-a")

    def test_rejects_mismatched_membership_uid(self):
        self.member_snapshot.to_dict.return_value = {
            "uid": "user-b", "email": "user-a@example.com",
            "role": "owner", "status": "active",
        }
        with self.assertRaisesRegex(PermissionError, "membership could not be verified"):
            company_store.get_company_for_user("user-a")

    def test_rejects_user_and_membership_email_mismatch(self):
        self.member_snapshot.to_dict.return_value = {
            "uid": "user-a", "email": "other@example.com",
            "role": "owner", "status": "active",
        }
        with self.assertRaisesRegex(PermissionError, "emails do not match"):
            company_store.get_company_for_user("user-a")


if __name__ == "__main__":
    unittest.main()
