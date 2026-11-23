"""Tests for authenticated session refresh and company binding."""

import unittest
from unittest.mock import patch

import firebase_admin
from firebase_admin import auth as firebase_auth

from seepsight import auth


class VerifiedSessionTests(unittest.TestCase):
    def setUp(self):
        self.account = {
            "uid": "user-a",
            "email": "user-a@example.com",
            "id_token": "old-id-token",
            "refresh_token": "refresh-token",
        }
        self.client_patch = patch(
            "seepsight.firestore_db.get_firestore_client",
            return_value=object(),
        )
        self.client_patch.start()
        self.addCleanup(self.client_patch.stop)
        self.token_patch = patch.object(
            firebase_auth,
            "verify_id_token",
            return_value={
                "uid": "user-a",
                "email": "user-a@example.com",
                "email_verified": True,
            },
        )
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)

    def test_verified_session_uses_authoritative_company_membership(self):
        company = {
            "uid": "user-a",
            "company_id": "company-a",
            "company_name": "Company A",
            "role": "owner",
            "email": "user-a@example.com",
        }
        with patch.object(auth.company_store, "get_company_for_user", return_value=company):
            result = auth._verified_account(self.account)
        self.assertEqual(result["company_id"], "company-a")
        self.assertEqual(result["email"], "user-a@example.com")

    def test_verified_session_rejects_membership_email_mismatch(self):
        company = {
            "uid": "user-a",
            "company_id": "company-a",
            "company_name": "Company A",
            "role": "owner",
            "email": "different@example.com",
        }
        with patch.object(auth.company_store, "get_company_for_user", return_value=company):
            self.assertIsNone(auth._verified_account(self.account))

    def test_verified_session_rejects_missing_membership(self):
        with patch.object(
            auth.company_store, "get_company_for_user",
            side_effect=PermissionError("no membership"),
        ):
            self.assertIsNone(auth._verified_account(self.account))


if __name__ == "__main__":
    unittest.main()
