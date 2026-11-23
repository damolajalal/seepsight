"""Security tests for server-side company tenant authorization."""

import pytest
import firebase_admin
from firebase_admin import auth as firebase_auth

from seepsight import company_store, firestore_db


@pytest.fixture
def authenticated_company_session(monkeypatch):
    """Provide a verified test identity and its active company membership."""
    account = {
        "uid": "user-a",
        "id_token": "firebase-test-token",
    }
    membership = {
        "uid": "user-a",
        "company_id": "company-a",
        "company_name": "Company A",
        "role": "owner",
    }

    monkeypatch.setattr(
        firestore_db.st,
        "session_state",
        {"seepsight_auth": account},
    )
    monkeypatch.setattr(firebase_admin, "get_app", lambda: "test-admin-app")
    monkeypatch.setattr(
        firebase_auth,
        "verify_id_token",
        lambda token, app: {"uid": "user-a"},
    )
    monkeypatch.setattr(
        company_store,
        "get_company_for_user",
        lambda uid: membership if uid == "user-a" else {},
    )
    return membership


def test_company_access_requires_a_signed_in_session(monkeypatch):
    monkeypatch.setattr(firestore_db.st, "session_state", {})

    with pytest.raises(PermissionError, match="Please sign in"):
        firestore_db.verify_company_access("company-a")


def test_company_access_rejects_a_different_session_uid(
    monkeypatch,
    authenticated_company_session,
):
    monkeypatch.setattr(
        firebase_auth,
        "verify_id_token",
        lambda token, app: {"uid": "different-user"},
    )

    with pytest.raises(PermissionError, match="identity"):
        firestore_db.verify_company_access("company-a")


def test_company_access_rejects_another_company(
    authenticated_company_session,
):
    with pytest.raises(PermissionError, match="do not have access"):
        firestore_db.verify_company_access("company-b")


def test_company_access_returns_authoritative_active_membership(
    authenticated_company_session,
):
    result = firestore_db.verify_company_access("company-a")

    assert result["uid"] == "user-a"
    assert result["company_id"] == "company-a"
    assert result["role"] == "owner"
