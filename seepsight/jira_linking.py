"""Short-lived, single-use pairing codes for the Seepsight Jira app."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from seepsight.company_store import get_company_for_user
from seepsight.firestore_db import get_firestore_client


PAIRING_TTL = timedelta(minutes=10)
PAIRING_COOLDOWN = timedelta(seconds=60)


def _code_hash(code):
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def create_jira_pairing_code(uid, email, email_verified):
    """Create a one-time pairing code for the currently authenticated user.

    Call only after the Firebase ID token has been verified by the existing
    authentication flow. Company membership is independently re-resolved
    here; no company ID or role is accepted from the browser/session.
    """
    if not isinstance(uid, str) or not uid.strip():
        raise PermissionError("A verified Seepsight account is required.")
    email = str(email or "").strip().lower()
    if not email or not email_verified:
        raise PermissionError("Verify your email address before connecting Jira.")

    membership = get_company_for_user(uid)
    if membership.get("uid") != uid:
        raise PermissionError("Your Seepsight account could not be verified.")
    if str(membership.get("email") or "").strip().lower() != email:
        raise PermissionError("Your company membership email does not match your verified account.")

    client = get_firestore_client()
    user_ref = client.collection("users").document(uid)
    code = secrets.token_urlsafe(32)
    code_hash = _code_hash(code)
    pairing_ref = client.collection("_jira_pairing_codes").document(code_hash)
    transaction = client.transaction()
    now = datetime.now(timezone.utc)

    @firestore.transactional
    def _create(txn):
        user_snapshot = user_ref.get(transaction=txn)
        if not user_snapshot.exists:
            raise PermissionError("Your Seepsight account could not be verified.")
        user = user_snapshot.to_dict() or {}
        if user.get("uid") != uid:
            raise PermissionError("Your Seepsight account could not be verified.")
        if str(user.get("email") or "").strip().lower() != email:
            raise PermissionError("Your Seepsight account could not be verified.")

        last_issued = user.get("jira_pairing_last_issued_at")
        if isinstance(last_issued, datetime):
            if last_issued.tzinfo is None:
                last_issued = last_issued.replace(tzinfo=timezone.utc)
            if now - last_issued < PAIRING_COOLDOWN:
                raise ValueError("Please wait one minute before generating another Jira code.")

        txn.set(user_ref, {"jira_pairing_last_issued_at": now}, merge=True)
        txn.create(pairing_ref, {
            "firebase_uid": uid,
            "company_id": membership["company_id"],
            "email": email,
            "status": "pending",
            "created_at": now,
            "expires_at": now + PAIRING_TTL,
        })

    _create(transaction)
    return {
        "code": code,
        "expires_at": now + PAIRING_TTL,
        "expires_in_seconds": int(PAIRING_TTL.total_seconds()),
    }
