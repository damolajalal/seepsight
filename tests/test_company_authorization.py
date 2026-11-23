"""Security tests for server-side company tenant authorization."""

import unittest
from unittest.mock import patch

import firebase_admin
from firebase_admin import auth as firebase_auth

from seepsight import company_store, firestore_db


class CompanyAuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "uid": "user-a",
            "id_token": "firebase-test-token",
            "email": "user-a@example.com",
        }
        self.membership = {
            "uid": "user-a",
            "company_id": "company-a",
            "company_name": "Company A",
            "role": "owner",
            "email": "user-a@example.com",
        }

        self.session_patch = patch.object(
            firestore_db.st,
            "session_state",
            {"seepsight_auth": self.account},
        )
        self.session_patch.start()
        self.addCleanup(self.session_patch.stop)

        self.app_patch = patch.object(
            firebase_admin,
            "get_app",
            return_value="test-admin-app",
        )
        self.app_patch.start()
        self.addCleanup(self.app_patch.stop)

        self.token_patch = patch.object(
            firebase_auth,
            "verify_id_token",
            return_value={"uid": "user-a", "email": "user-a@example.com", "email_verified": True},
        )
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)

        self.membership_patch = patch.object(
            company_store,
            "get_company_for_user",
            return_value=self.membership,
        )
        self.membership_patch.start()
        self.addCleanup(self.membership_patch.stop)

    def test_company_access_requires_a_signed_in_session(self):
        with patch.object(firestore_db.st, "session_state", {}):
            with self.assertRaisesRegex(PermissionError, "Please sign in"):
                firestore_db.verify_company_access("company-a")

    def test_company_access_rejects_a_different_session_uid(self):
        with patch.object(
            firebase_auth,
            "verify_id_token",
            return_value={"uid": "different-user", "email": "user-a@example.com", "email_verified": True},
        ):
            with self.assertRaisesRegex(PermissionError, "identity"):
                firestore_db.verify_company_access("company-a")


    def test_company_access_rejects_unverified_email(self):
        with patch.object(
            firebase_auth,
            "verify_id_token",
            return_value={"uid": "user-a", "email": "user-a@example.com", "email_verified": False},
        ):
            with self.assertRaisesRegex(PermissionError, "verify your email"):
                firestore_db.verify_company_access("company-a")

    def test_company_access_rejects_revoked_or_invalid_token(self):
        with patch.object(
            firebase_auth,
            "verify_id_token",
            side_effect=ValueError("revoked token"),
        ):
            with self.assertRaisesRegex(PermissionError, "could not be verified"):
                firestore_db.verify_company_access("company-a")

    def test_company_access_rejects_another_company(self):
        with self.assertRaisesRegex(PermissionError, "do not have access"):
            firestore_db.verify_company_access("company-b")

    def test_company_access_returns_authoritative_membership(self):
        result = firestore_db.verify_company_access("company-a")

        self.assertEqual(result["uid"], "user-a")
        self.assertEqual(result["company_id"], "company-a")
        self.assertEqual(result["role"], "owner")

    def test_company_access_rejects_changed_session_email(self):
        account = dict(self.account, email="other@example.com")
        with patch.object(firestore_db.st, "session_state", {"seepsight_auth": account}):
            with self.assertRaisesRegex(PermissionError, "identity has changed"):
                firestore_db.verify_company_access("company-a")

    def test_company_access_rejects_membership_email_mismatch(self):
        membership = dict(self.membership, email="other@example.com")
        with patch.object(company_store, "get_company_for_user", return_value=membership):
            with self.assertRaisesRegex(PermissionError, "membership email"):
                firestore_db.verify_company_access("company-a")


if __name__ == "__main__":
    unittest.main()
