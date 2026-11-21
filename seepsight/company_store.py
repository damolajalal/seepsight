
"""Firestore company records, ownership and membership."""

from firebase_admin import firestore

from seepsight.firestore_db import get_firestore_client


def _validate_uid(uid):
    """Require an authenticated Firebase UID."""
    if not isinstance(uid, str) or not uid.strip():
        raise ValueError("A valid Firebase user ID is required.")

    return uid.strip()


def ensure_company_for_user(uid, email, company_name):
    """
    Create a company workspace for a new user or retrieve their
    existing workspace.

    The company ID is derived from the Firebase UID, ensuring that
    repeated calls cannot create duplicate workspaces for that user.
    """

    uid = _validate_uid(uid)

    email = (email or "").strip().lower()
    company_name = (company_name or "").strip()

    if not email:
        raise ValueError("A verified email address is required.")

    if not company_name:
        raise ValueError("A company name is required.")

    client = get_firestore_client()

    # A user's first company is identified by their Firebase UID.
    # Membership records allow additional users to be added later.
    company_id = uid

    user_ref = client.collection("users").document(uid)
    company_ref = client.collection("companies").document(company_id)
    member_ref = company_ref.collection("members").document(uid)

    transaction = client.transaction()

    @firestore.transactional
    def _create_or_retrieve(transaction):
        user_snapshot = user_ref.get(transaction=transaction)

        company_snapshot = company_ref.get(transaction=transaction)
        member_snapshot = member_ref.get(transaction=transaction)

        if user_snapshot.exists:
            user_data = user_snapshot.to_dict() or {}
            existing_company_id = user_data.get("company_id")

            if existing_company_id != company_id:
                raise RuntimeError(
                    "The user's company association is inconsistent. "
                    "Contact the administrator."
                )

            if not company_snapshot.exists or not member_snapshot.exists:
                raise RuntimeError(
                    "The company workspace or membership record is missing. "
                    "Contact the administrator."
                )

            company_data = company_snapshot.to_dict() or {}
            member_data = member_snapshot.to_dict() or {}

            if member_data.get("uid") != uid:
                raise PermissionError("Company membership could not be verified.")

            if member_data.get("status") != "active":
                raise PermissionError("Your company membership is not active.")

            if company_data.get("status") != "active":
                raise PermissionError("This company workspace is not active.")

            return {
                "company_id": company_id,
                "company_name": company_data.get("name", "Company"),
                "uid": uid,
                "email": email,
                "role": member_data.get("role", "member"),
                "existing": True,
            }

        # Do not overwrite unexpected existing records.
        if company_snapshot.exists or member_snapshot.exists:
            raise RuntimeError(
                "Company records already exist without a valid user profile. "
                "Administrator review is required."
            )

        timestamp = firestore.SERVER_TIMESTAMP

        transaction.create(
            company_ref,
            {
                "name": company_name,
                "owner_uid": uid,
                "status": "active",
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

        transaction.create(
            member_ref,
            {
                "uid": uid,
                "email": email,
                "role": "owner",
                "status": "active",
                "created_at": timestamp,
            },
        )

        transaction.create(
            user_ref,
            {
                "uid": uid,
                "email": email,
                "company_id": company_id,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

        return {
            "company_id": company_id,
            "company_name": company_name,
            "uid": uid,
            "email": email,
            "role": "owner",
            "existing": False,
        }

    return _create_or_retrieve(transaction)


def get_company_for_user(uid):
    """
    Resolve an authenticated user's company through Firestore.

    Never accept a company ID supplied by the browser or session state.
    """

    uid = _validate_uid(uid)
    client = get_firestore_client()

    user_snapshot = (
        client.collection("users")
        .document(uid)
        .get()
    )

    if not user_snapshot.exists:
        raise PermissionError("No company workspace is linked to this account.")

    user_data = user_snapshot.to_dict() or {}
    company_id = user_data.get("company_id")

    if not company_id:
        raise PermissionError("Your account has no company association.")

    company_ref = client.collection("companies").document(company_id)

    company_snapshot = company_ref.get()
    member_snapshot = (
        company_ref.collection("members")
        .document(uid)
        .get()
    )

    if not company_snapshot.exists or not member_snapshot.exists:
        raise PermissionError("Your company membership could not be verified.")

    company_data = company_snapshot.to_dict() or {}
    member_data = member_snapshot.to_dict() or {}

    if member_data.get("uid") != uid:
        raise PermissionError("Company membership could not be verified.")

    if member_data.get("status") != "active":
        raise PermissionError("Your company membership is not active.")

    if company_data.get("status") != "active":
        raise PermissionError("This company workspace is not active.")

    return {
        "company_id": company_id,
        "company_name": company_data.get("name", "Company"),
        "uid": uid,
        "email": user_data.get("email"),
        "role": member_data.get("role", "member"),
    }
