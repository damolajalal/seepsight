
"""
Seepsight Firestore Database Module
-----------------------------------
Secure server-side Firebase Admin connection and
tenant-isolated Firestore persistence.

Responsibilities:
- Initialize Firebase Admin securely.
- Connect to Cloud Firestore.
- Test read/write/delete permissions.
- Save and retrieve company datasets.
- Save and retrieve procurement records.
- Save and retrieve dataset mappings.
- Save and retrieve analysis results.
"""

import uuid
import math
import json
import re
import logging
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

import streamlit as st


# ============================================================
# 1. FIREBASE INITIALIZATION
# ============================================================

def get_firestore_client():
    """
    Return an authenticated Firestore client.

    Uses Firebase Admin credentials stored in Streamlit Secrets.
    Reuses an existing Firebase Admin application when available.
    """

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

    except ImportError as exc:
        raise RuntimeError(
            "Firebase Admin SDK is missing. "
            "Add firebase-admin to requirements.txt."
        ) from exc

    try:
        app = firebase_admin.get_app()

    except ValueError:

        if "firebase_admin" not in st.secrets:
            raise RuntimeError(
                "Firebase Admin credentials are missing. "
                "Configure [firebase_admin] in Streamlit Secrets."
            )

        service_account_info = dict(
            st.secrets["firebase_admin"]
        )

        required_fields = [
            "project_id",
            "private_key",
            "client_email",
        ]

        missing = [
            field
            for field in required_fields
            if not service_account_info.get(field)
        ]

        if missing:
            raise RuntimeError(
                "Firebase credentials are incomplete. "
                f"Missing fields: {', '.join(missing)}"
            )

        # Correct escaped newlines in service-account keys.
        service_account_info["private_key"] = (
            service_account_info["private_key"].replace(
                "\\n", "\n"
            )
        )

        try:
            credential = credentials.Certificate(
                service_account_info
            )

            app = firebase_admin.initialize_app(
                credential,
                options={
                    "projectId": service_account_info["project_id"]
                },
            )

        except Exception as exc:
            raise RuntimeError(
                "Firebase Admin initialization failed. "
                "Check your service-account credentials "
                "and Firebase project configuration."
            ) from exc

    try:
        return firestore.client(app=app)

    except Exception as exc:
        raise RuntimeError(
            "Could not create the Firestore client. "
            "Check that Cloud Firestore is enabled."
        ) from exc


# ============================================================
# 2. CONNECTION DIAGNOSTICS
# ============================================================

def test_firestore_connection():
    """Verify Firestore access and report cleanup failures without masking errors."""
    client = get_firestore_client()
    test_id = f"connection_{uuid.uuid4().hex}"
    test_ref = client.collection("_system").document(test_id)
    operation_error = None
    cleanup_error = None

    try:
        test_ref.set({
            "status": "connected",
            "purpose": "temporary_connection_test",
            "created_at": datetime.now(timezone.utc),
        })
        snapshot = test_ref.get()
        if not snapshot.exists:
            raise RuntimeError("Firestore test document could not be read.")
        data = snapshot.to_dict() or {}
        if data.get("status") != "connected":
            raise RuntimeError("Firestore returned unexpected test data.")
    except Exception as exc:
        operation_error = exc
    finally:
        try:
            test_ref.delete()
        except Exception as exc:
            cleanup_error = exc

    if operation_error is not None:
        raise RuntimeError("Firestore connection verification failed.") from operation_error
    if cleanup_error is not None:
        raise RuntimeError("Firestore connection test cleanup failed.") from cleanup_error
    return True

# ============================================================
# 3. INPUT VALIDATION AND NORMALISATION
# ============================================================

def _validate_id(value, field_name):
    """Validate Firestore document identifiers."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{field_name} must be a non-empty string."
        )

    value = value.strip()

    if "/" in value:
        raise ValueError(
            f"{field_name} cannot contain '/'."
        )
    if len(value.encode("utf-8")) > 128:
        raise ValueError(f"{field_name} cannot exceed 128 UTF-8 bytes.")

    return value


def _normalise(value):
    """
    Convert common Python values into Firestore-compatible values.
    """

    if value is None:
        return None

    if isinstance(value, dict):
        cleaned = {
            str(key): _normalise(item)
            for key, item in value.items()
        }
        if set(cleaned) in ({_DECIMAL_MARKER}, {_ESCAPED_MAP_MARKER}):
            return {
                _ESCAPED_MAP_MARKER: {
                    "entries": [[key, item] for key, item in cleaned.items()]
                }
            }
        return cleaned

    if isinstance(value, (list, tuple)):
        return [
            _normalise(item)
            for item in value
        ]

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(
            value,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )

    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return {_DECIMAL_MARKER: format(value, "f")}

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, (str, int, bool)):
        return value

    # Handle common Pandas and NumPy scalar values.
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()

    if hasattr(value, "item"):
        try:
            return _normalise(value.item())
        except (ValueError, TypeError):
            pass

    # Handle pandas missing values where available.
    try:
        import pandas as pd

        missing = pd.isna(value)

        if missing is True or type(missing).__name__ == "bool_" and bool(missing):
            return None

    except (ImportError, TypeError, ValueError):
        pass

    raise TypeError(
        f"Unsupported Firestore data type: {type(value).__name__}"
    )


_DECIMAL_MARKER = "__seepsight_decimal__"
_ESCAPED_MAP_MARKER = "__seepsight_escaped_map__"


def _normalise_workspace_value(value):
    """Preserve Decimal values exactly in durable analysis workspaces."""
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return {_DECIMAL_MARKER: format(value, "f")}
    if isinstance(value, dict):
        cleaned = {
            str(key): _normalise_workspace_value(item)
            for key, item in value.items()
        }
        # Escape user dictionaries that would otherwise be mistaken for our
        # internal Decimal marker during restoration.
        if set(cleaned) in ({_DECIMAL_MARKER}, {_ESCAPED_MAP_MARKER}):
            return {
                _ESCAPED_MAP_MARKER: {
                    "entries": [[key, item] for key, item in cleaned.items()]
                }
            }
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_normalise_workspace_value(item) for item in value]
    return _normalise(value)


def _denormalise_workspace_value(value):
    """Restore exact Decimal values encoded in durable Firestore payloads."""
    if isinstance(value, dict):
        if set(value) == {_ESCAPED_MAP_MARKER} and isinstance(value[_ESCAPED_MAP_MARKER], dict):
            payload = value[_ESCAPED_MAP_MARKER]
            if set(payload) == {"entries"} and isinstance(payload["entries"], list):
                return {
                    key: _denormalise_workspace_value(item)
                    for key, item in payload["entries"]
                }
        if (
            set(value) == {_DECIMAL_MARKER}
            and isinstance(value[_DECIMAL_MARKER], str)
        ):
            try:
                return Decimal(value[_DECIMAL_MARKER])
            except InvalidOperation:
                return dict(value)
        return {
            key: _denormalise_workspace_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_denormalise_workspace_value(item) for item in value]
    return value


def verify_company_access(company_id):
    """
    Verify the current Firebase identity and active membership.

    A company ID from session state is only a requested resource. Access
    is granted only when Firebase verifies the ID token and Firestore
    membership records resolve that same company for the verified UID.
    """
    company_id = _validate_id(company_id, "company_id")

    account = st.session_state.get("seepsight_auth")
    if not isinstance(account, dict):
        raise PermissionError("Please sign in before accessing company data.")

    id_token = account.get("id_token")
    session_uid = account.get("uid")
    if not id_token or not session_uid:
        raise PermissionError("Your sign-in session is incomplete. Please sign in again.")

    try:
        import firebase_admin
        from firebase_admin import auth as firebase_auth

        app = firebase_admin.get_app()
        decoded_token = firebase_auth.verify_id_token(
            id_token,
            app=app,
            check_revoked=True,
        )
    except Exception as exc:
        raise PermissionError(
            "Your sign-in session could not be verified. Please sign in again."
        ) from exc

    verified_uid = decoded_token.get("uid")
    verified_email = str(decoded_token.get("email") or "").strip().lower()
    session_email = str(account.get("email") or "").strip().lower()
    if not verified_uid or verified_uid != session_uid:
        raise PermissionError("The signed-in identity could not be verified.")
    if not decoded_token.get("email_verified", False):
        raise PermissionError("Please verify your email address before accessing company data.")
    if not verified_email or verified_email != session_email:
        raise PermissionError("Your sign-in identity has changed. Please sign in again.")

    # Import locally to avoid the company_store/firestore_db import cycle.
    from seepsight import company_store

    membership = company_store.get_company_for_user(verified_uid)
    if membership.get("company_id") != company_id:
        raise PermissionError("You do not have access to this company workspace.")
    if str(membership.get("email") or "").strip().lower() != verified_email:
        raise PermissionError("Your company membership email does not match your verified account.")

    return membership


def _company_ref(company_id):
    """Return a tenant-scoped company reference after membership verification."""
    membership = verify_company_access(company_id)
    client = get_firestore_client()
    return client.collection("companies").document(membership["company_id"])



def _stream_query_pages(query, page_size=500):
    """Yield Firestore query snapshots in bounded pages."""
    if not isinstance(page_size, int) or page_size < 1 or page_size > 1000:
        raise ValueError("page_size must be between 1 and 1000.")
    cursor = None
    while True:
        page_query = query.limit(page_size)
        if cursor is not None:
            page_query = page_query.start_after(cursor)
        page = list(page_query.stream())
        if not page:
            break
        yield from page
        cursor = page[-1]
        if len(page) < page_size:
            break



_AUDIT_SECRET_KEY_PARTS = (
    "password", "secret", "token", "credential", "private_key",
    "api_key", "authorization", "connection_string",
)


def _safe_audit_value(value):
    """Remove credential-like fields before an audit payload is persisted."""
    if isinstance(value, dict):
        return {
            str(key): _safe_audit_value(item)
            for key, item in value.items()
            if not any(part in str(key).lower() for part in _AUDIT_SECRET_KEY_PARTS)
        }
    if isinstance(value, (list, tuple)):
        return [_safe_audit_value(item) for item in value[:50]]
    return value


def write_company_audit_event(company_id, event_type, resource_type,
                              resource_id=None, details=None):
    """Append a bounded company-scoped audit event without credential values."""
    if not isinstance(event_type, str) or not re.fullmatch(r"[a-z][a-z0-9_.-]{1,79}", event_type):
        raise ValueError("event_type is invalid.")
    if not isinstance(resource_type, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{1,39}", resource_type):
        raise ValueError("resource_type is invalid.")
    if resource_id is not None:
        resource_id = _validate_id(resource_id, "resource_id")
    if details is None:
        details = {}
    if not isinstance(details, dict):
        raise TypeError("Audit details must be a dictionary.")

    safe_details = _normalise_workspace_value(_safe_audit_value(details))
    payload_size = len(json.dumps(safe_details, default=str).encode("utf-8"))
    if payload_size > 12_000:
        raise ValueError("Audit details exceed the safe size limit.")

    event_id = uuid.uuid4().hex
    try:
        company = _company_ref(company_id)
        company.collection("audit_events").document(event_id).create({
            "event_id": event_id,
            "event_type": event_type,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "details": safe_details,
            "actor_uid": (st.session_state.get("seepsight_auth") or {}).get("uid"),
            "created_at": datetime.now(timezone.utc),
        })
        return event_id
    except Exception:
        # Audit is best-effort across Firestore/GCS boundaries; never report a
        # successful data write as failed solely because the audit sink is down.
        logging.getLogger(__name__).warning("Company audit event could not be persisted.")
        return None


# ============================================================
# 4. COMPANY DATASET METADATA
# ============================================================

def save_company_dataset(
    company_id,
    dataset_id,
    metadata,
):
    """
    Save dataset metadata under the correct company.

    Example metadata:
    {
        "dataset_type": "purchase_orders",
        "filename": "purchase_orders.csv",
        "record_count": 250,
        "status": "validated"
    }
    """

    company = _company_ref(company_id)

    dataset_id = _validate_id(
        dataset_id,
        "dataset_id"
    )

    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dictionary.")

    document = _normalise(metadata)
    if len(json.dumps(document, default=str).encode("utf-8")) > 800_000:
        raise ValueError("Dataset metadata is too large to store safely.")

    document.update({
        "dataset_id": dataset_id,
        "updated_at": datetime.now(timezone.utc),
    })

    company.collection("datasets").document(
        dataset_id
    ).set(
        document,
        merge=True,
    )
    write_company_audit_event(
        company_id, "dataset.metadata_saved", "dataset", dataset_id,
        {"dataset_type": document.get("dataset_type"), "filename": document.get("filename"),
         "status": document.get("status"), "record_count": document.get("record_count")},
    )
    return dataset_id


def get_company_datasets(company_id):
    """Retrieve all dataset metadata for a company."""

    company = _company_ref(company_id)

    query = company.collection("datasets").order_by("__name__")
    datasets = [
        {
            "id": snapshot.id,
            **_denormalise_workspace_value(snapshot.to_dict() or {}),
        }
        for snapshot in _stream_query_pages(query, page_size=200)
    ]
    write_company_audit_event(
        company_id, "dataset.listed", "dataset", None,
        {"dataset_count": len(datasets)},
    )
    return datasets


# ============================================================
# 5. PROCUREMENT RECORD STORAGE
# ============================================================

def save_dataset_records(company_id, dataset_id, records, collection_name="records"):
    """Persist source or normalized procurement rows in idempotent bounded batches."""
    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    company = _company_ref(company_id)
    dataset_id = _validate_id(dataset_id, "dataset_id")
    if collection_name not in {"records", "source_records"}:
        raise ValueError("collection_name must be 'records' or 'source_records'.")
    if not isinstance(records, (list, tuple)):
        raise TypeError("records must be a list of dictionaries.")

    # Bound total Firestore work per upload; batch sizes alone do not bound
    # memory use when a caller supplies an unbounded in-memory list.
    if len(records) > 250_000:
        raise ValueError("A dataset upload cannot exceed 250,000 records.")
    # Validate and serialise the complete payload before the first write.
    prepared = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError("Each procurement record must be a dictionary.")
        cleaned = _normalise(record)
        cleaned["_record_number"] = index
        size = len(__import__("json").dumps(cleaned, default=str).encode("utf-8"))
        if size > 800_000:
            raise ValueError(f"Procurement record {index + 1} is too large to store safely.")
        prepared.append(cleaned)

    dataset_ref = company.collection("datasets").document(dataset_id)
    client = get_firestore_client()
    status_key = f"{collection_name}_status"
    saved_key = f"{collection_name}_saved"
    expected_key = f"{collection_name}_expected_count"
    count_key = "record_count" if collection_name == "records" else "source_record_count"
    dataset_ref.set({
        status_key: "saving",
        saved_key: False,
        expected_key: len(prepared),
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)

    try:
        for start in range(0, len(prepared), 400):
            batch = client.batch()
            for record in prepared[start:start + 400]:
                record_id = f"record_{record['_record_number']:012d}"
                record_ref = dataset_ref.collection(collection_name).document(record_id)
                batch.set(record_ref, {**record, "_saved_at": SERVER_TIMESTAMP})
            batch.commit()

        # Remove stale tail documents if this upload ID is retried with fewer rows.
        records_query = dataset_ref.collection(collection_name).order_by("_record_number")
        stale_batch = client.batch()
        stale_count = 0
        for snapshot in _stream_query_pages(records_query, page_size=400):
            if int((snapshot.to_dict() or {}).get("_record_number", -1)) >= len(prepared):
                stale_batch.delete(snapshot.reference)
                stale_count += 1
                if stale_count % 400 == 0:
                    stale_batch.commit()
                    stale_batch = client.batch()
        if stale_count % 400:
            stale_batch.commit()

        dataset_ref.set({
            count_key: len(prepared),
            saved_key: True,
            status_key: "complete",
            "updated_at": datetime.now(timezone.utc),
        }, merge=True)
    except Exception as exc:
        try:
            dataset_ref.set({
                saved_key: False,
                status_key: "failed",
                "updated_at": datetime.now(timezone.utc),
            }, merge=True)
        except Exception:
            pass
        raise RuntimeError("Validated procurement records could not be saved completely.") from exc

    write_company_audit_event(
        company_id, f"dataset.{collection_name}_saved", "dataset", dataset_id,
        {count_key: len(prepared), status_key: "complete"},
    )
    return len(prepared)


def get_dataset_records(company_id, dataset_id, collection_name="records"):
    """Retrieve source or normalized company records in bounded pages."""
    company = _company_ref(company_id)
    dataset_id = _validate_id(dataset_id, "dataset_id")
    if collection_name not in {"records", "source_records"}:
        raise ValueError("collection_name must be 'records' or 'source_records'.")
    dataset_ref = company.collection("datasets").document(dataset_id)
    metadata = dataset_ref.get()
    status_key = f"{collection_name}_status"
    if not metadata.exists:
        raise FileNotFoundError("The requested company dataset does not exist.")
    if metadata.exists:
        metadata_data = metadata.to_dict() or {}
        state = metadata_data.get(status_key)
        if metadata_data.get("deletion_status") in {"deleting", "failed"}:
            raise RuntimeError("This dataset is being deleted and is not available.")
        if state in {"saving", "failed"}:
            raise RuntimeError("This dataset's records are not in a complete saved state.")

    query = dataset_ref.collection(collection_name).order_by("_record_number")
    records = []
    for snapshot in _stream_query_pages(query, page_size=500):
        item = _denormalise_workspace_value(snapshot.to_dict() or {})
        records.append({
            key: value for key, value in item.items()
            if not key.startswith("_")
        })
    write_company_audit_event(
        company_id, f"dataset.{collection_name}_read", "dataset", dataset_id,
        {"record_count": len(records), "collection": collection_name},
    )
    return records

def delete_company_dataset(company_id, dataset_id):
    """Delete a company's dataset, source rows, mappings and private original file."""
    company = _company_ref(company_id)
    dataset_id = _validate_id(dataset_id, "dataset_id")
    dataset_ref = company.collection("datasets").document(dataset_id)
    snapshot = dataset_ref.get()
    if not snapshot.exists:
        return False

    metadata = snapshot.to_dict() or {}
    dataset_ref.set({
        "deletion_status": "deleting",
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)

    storage = metadata.get("storage") or {}
    object_name = storage.get("object_name")
    try:
        if object_name and not metadata.get("storage_deleted", False):
            from seepsight import cloud_storage
            cloud_storage.delete_company_file(
                company_id,
                object_name,
                if_generation_match=storage.get("generation"),
            )
            dataset_ref.set({
                "storage_deleted": True,
                "updated_at": datetime.now(timezone.utc),
            }, merge=True)

        get_firestore_client().recursive_delete(dataset_ref)
    except Exception as exc:
        try:
            dataset_ref.set({
                "deletion_status": "failed",
                "updated_at": datetime.now(timezone.utc),
            }, merge=True)
        except Exception:
            pass
        raise RuntimeError("The dataset could not be fully deleted. Retry the deletion or contact support.") from exc

    write_company_audit_event(
        company_id, "dataset.deleted", "dataset", dataset_id,
        {"original_file_deleted": bool(object_name)},
    )
    return True


# ============================================================
# 6. DATASET MAPPING STORAGE
# ============================================================

def save_company_mapping(
    company_id,
    dataset_id,
    mapping,
):
    """
    Save the confirmed column mapping for a company dataset.
    """

    company = _company_ref(company_id)

    dataset_id = _validate_id(
        dataset_id,
        "dataset_id"
    )

    if not isinstance(mapping, dict):
        raise TypeError(
            "mapping must be a dictionary."
        )

    mapping_ref = (
        company.collection("datasets")
        .document(dataset_id)
        .collection("configuration")
        .document("mapping")
    )

    cleaned_mapping = _normalise_workspace_value(mapping)
    if len(json.dumps(cleaned_mapping, default=str).encode("utf-8")) > 800_000:
        raise ValueError("Dataset mapping is too large to store safely.")
    mapping_ref.set({
        "mapping": cleaned_mapping,
        "updated_at": datetime.now(timezone.utc),
    })
    write_company_audit_event(
        company_id, "dataset.mapping_saved", "dataset", dataset_id,
        {"mapped_field_count": len(mapping)},
    )
    return True


def get_company_mapping(company_id, dataset_id):
    """Retrieve a saved dataset column mapping."""

    company = _company_ref(company_id)

    dataset_id = _validate_id(
        dataset_id,
        "dataset_id"
    )

    snapshot = (
        company.collection("datasets")
        .document(dataset_id)
        .collection("configuration")
        .document("mapping")
        .get()
    )

    if not snapshot.exists:
        return None

    mapping = _denormalise_workspace_value((snapshot.to_dict() or {}).get("mapping"))
    write_company_audit_event(
        company_id, "dataset.mapping_read", "dataset", dataset_id,
        {"mapped_field_count": len(mapping or {})},
    )
    return mapping


# ============================================================
# 7. COMPANY DATABASE CONNECTION PROFILES
# ============================================================

def save_company_connection_profile(company_id, connection_id, profile):
    """Store connection metadata and a Secret Manager reference, never credentials."""
    from seepsight.secrets_manager import validate_secret_reference

    company = _company_ref(company_id)
    connection_id = _validate_id(connection_id, "connection_id")
    if not isinstance(profile, dict):
        raise TypeError("profile must be a dictionary.")

    allowed = {
        "name", "provider", "secret_reference", "database",
        "schema", "description", "max_rows", "timeout_seconds",
    }
    if set(profile) - allowed:
        raise ValueError("Connection profiles may contain metadata and a secret reference only.")
    name = profile.get("name")
    provider = str(profile.get("provider") or "").strip().lower()
    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
        raise ValueError("A connection profile name of 1 to 120 characters is required.")
    if provider not in {"postgres", "mysql", "sqlserver", "bigquery"}:
        raise ValueError("Unsupported database provider.")
    secret_reference = validate_secret_reference(profile.get("secret_reference"))
    database = profile.get("database", "")
    schema = profile.get("schema", "")
    description = profile.get("description", "")
    if any(not isinstance(value, str) or len(value) > limit for value, limit in (
        (database, 128), (schema, 128), (description, 300)
    )):
        raise ValueError("Connection profile metadata exceeds the allowed length.")
    max_rows = profile.get("max_rows", 500)
    timeout_seconds = profile.get("timeout_seconds", 15)
    if isinstance(max_rows, bool) or not isinstance(max_rows, int) or not 1 <= max_rows <= 1000:
        raise ValueError("max_rows must be between 1 and 1000.")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 60:
        raise ValueError("timeout_seconds must be between 1 and 60.")

    payload = {
        "connection_id": connection_id,
        "name": name.strip(),
        "provider": provider,
        "secret_reference": secret_reference,
        "database": database,
        "schema": schema,
        "description": description,
        "max_rows": max_rows,
        "timeout_seconds": timeout_seconds,
        "status": "active",
        "updated_at": datetime.now(timezone.utc),
    }
    ref = company.collection("connections").document(connection_id)
    ref.set(_normalise_workspace_value(payload), merge=True)
    write_company_audit_event(
        company_id, "connection.profile_saved", "connection", connection_id,
        {"provider": provider, "name": name.strip()},
    )
    return connection_id


def set_company_connection_profile_status(company_id, connection_id, status):
    """Enable or disable one company-owned connection profile."""
    if status not in {"active", "inactive"}:
        raise ValueError("Connection status must be active or inactive.")
    company = _company_ref(company_id)
    connection_id = _validate_id(connection_id, "connection_id")
    ref = company.collection("connections").document(connection_id)
    snapshot = ref.get()
    if not snapshot.exists:
        raise FileNotFoundError("The requested company connection does not exist.")
    ref.set({
        "status": status,
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)
    write_company_audit_event(
        company_id, "connection.profile_status_changed", "connection",
        connection_id, {"status": status},
    )
    return True


def get_company_connection_profile(company_id, connection_id):
    """Load one authorized connection profile and its secret reference only."""
    company = _company_ref(company_id)
    connection_id = _validate_id(connection_id, "connection_id")
    snapshot = company.collection("connections").document(connection_id).get()
    if not snapshot.exists:
        return None
    profile = _denormalise_workspace_value(snapshot.to_dict() or {})
    write_company_audit_event(
        company_id, "connection.profile_read", "connection", connection_id,
        {"provider": profile.get("provider")},
    )
    return profile


def get_company_connection_profiles(company_id):
    """List connection profiles without fetching or exposing secret payloads."""
    company = _company_ref(company_id)
    query = company.collection("connections").order_by("__name__")
    profiles = [
        _denormalise_workspace_value(snapshot.to_dict() or {})
        for snapshot in _stream_query_pages(query, page_size=100)
    ]
    write_company_audit_event(
        company_id, "connection.profiles_listed", "connection", None,
        {"profile_count": len(profiles)},
    )
    return profiles


# ============================================================
# 7. ANALYSIS RESULT STORAGE
# ============================================================

def save_analysis_results(
    company_id,
    analysis_id,
    summary,
    findings=None,
):
    """
    Save an analysis summary and individual findings.

    The summary should contain compact metadata.
    Individual findings are stored separately to avoid
    exceeding Firestore's per-document size limit.
    """

    company = _company_ref(company_id)

    analysis_id = _validate_id(
        analysis_id,
        "analysis_id"
    )

    if not isinstance(summary, dict):
        raise TypeError(
            "summary must be a dictionary."
        )

    if findings is None:
        findings = []

    if not isinstance(findings, (list, tuple)):
        raise TypeError(
            "findings must be a list."
        )

    analysis_ref = (
        company.collection("analyses")
        .document(analysis_id)
    )
    cleaned_summary = _normalise_workspace_value(summary)
    if len(json.dumps(cleaned_summary, default=str).encode("utf-8")) > 800_000:
        raise ValueError("Analysis summary is too large to store safely.")

    prepared_findings = []
    for finding in findings:
        if not isinstance(finding, dict):
            raise TypeError("Each finding must be a dictionary.")
        cleaned = _normalise_workspace_value(finding)
        if len(json.dumps(cleaned, default=str).encode("utf-8")) > 800_000:
            raise ValueError("An analysis finding is too large to store safely.")
        prepared_findings.append(cleaned)

    analysis_ref.set({
        **cleaned_summary,
        "analysis_id": analysis_id,
        "finding_count": len(prepared_findings),
        "results_status": "saving",
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)

    client = get_firestore_client()
    for start in range(0, len(prepared_findings), 400):
        batch = client.batch()
        for index, finding in enumerate(
            prepared_findings[start:start + 400], start=start
        ):
            finding_id = f"finding_{index:012d}"
            finding_ref = analysis_ref.collection("findings").document(finding_id)
            batch.set(finding_ref, {
                **finding,
                "_finding_number": index,
            })
        batch.commit()

    existing_findings = analysis_ref.collection("findings").order_by("_finding_number")
    stale_batch = client.batch()
    stale_count = 0
    for snapshot in _stream_query_pages(existing_findings, page_size=400):
        if int((snapshot.to_dict() or {}).get("_finding_number", -1)) >= len(prepared_findings):
            stale_batch.delete(snapshot.reference)
            stale_count += 1
            if stale_count % 400 == 0:
                stale_batch.commit()
                stale_batch = client.batch()
    if stale_count % 400:
        stale_batch.commit()

    analysis_ref.set({
        "results_status": "complete",
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)
    write_company_audit_event(
        company_id, "analysis.results_saved", "analysis", analysis_id,
        {"finding_count": len(prepared_findings)},
    )
    return analysis_id


def get_analysis_results(company_id, analysis_id):
    """Retrieve an analysis summary and its findings."""

    company = _company_ref(company_id)

    analysis_id = _validate_id(
        analysis_id,
        "analysis_id"
    )

    analysis_ref = (
        company.collection("analyses")
        .document(analysis_id)
    )

    snapshot = analysis_ref.get()

    if not snapshot.exists:
        return None

    summary = _denormalise_workspace_value(snapshot.to_dict() or {})
    if summary.get("results_status") == "saving":
        return None

    findings = (
        analysis_ref.collection("findings")
        .order_by("_finding_number")
    )

    summary["findings"] = [
        {
            key: value
            for key, value in _denormalise_workspace_value(finding.to_dict() or {}).items()
            if not key.startswith("_")
        }
        for finding in _stream_query_pages(findings, page_size=500)
    ]
    write_company_audit_event(
        company_id, "analysis.results_read", "analysis", analysis_id,
        {"finding_count": len(summary["findings"])},
    )
    return summary


# ============================================================
# 8. HEALTH CHECK
# ============================================================

def get_firestore_status():
    """
    Return a safe connection status for the application.

    Does not expose credentials or private configuration.
    """

    try:
        client = get_firestore_client()

        # A read-only collection listing checks access to Firestore.
        list(client.collection("_system").limit(1).stream())

        return {
            "connected": True,
            "message": "Firestore is accessible.",
        }

    except Exception:
        return {
            "connected": False,
            "message": (
                "Firestore is unavailable. "
                "Check server credentials, project settings "
                "and database permissions."
            ),
        }


# ============================================================
# 9. DURABLE ANALYSIS WORKSPACES
# ============================================================

def save_analysis_workspace(company_id, analysis_id, summary, tables):
    """Persist a new workspace revision, then atomically make it active.

    Existing completed revisions remain readable if a replacement write fails.
    """
    company = _company_ref(company_id)
    analysis_id = _validate_id(analysis_id, "analysis_id")
    if not isinstance(summary, dict) or not isinstance(tables, dict):
        raise TypeError("summary and tables must be dictionaries.")

    # Validate and normalise the complete payload before changing Firestore.
    prepared = {}
    for table_name, records in tables.items():
        if not isinstance(table_name, str) or not table_name.replace("_", "").isalnum():
            raise ValueError("Invalid analysis table name.")
        if records is None:
            records = []
        if not isinstance(records, (list, tuple)):
            raise TypeError("Each analysis table must be a list of records.")
        cleaned_rows = []
        for record in records:
            if not isinstance(record, dict):
                raise TypeError("Each analysis row must be a dictionary.")
            cleaned = _normalise_workspace_value(record)
            size = len(__import__("json").dumps(cleaned, default=str).encode("utf-8"))
            if size > 800_000:
                raise ValueError(
                    f"An analysis row in '{table_name}' is too large to store safely."
                )
            cleaned_rows.append(cleaned)
        prepared[table_name] = cleaned_rows

    analysis_ref = company.collection("analyses").document(analysis_id)
    revision_id = uuid.uuid4().hex
    revision_ref = analysis_ref.collection("revisions").document(revision_id)
    revision_ref.set({
        "workspace_status": "saving",
        "created_at": datetime.now(timezone.utc),
    })

    client = get_firestore_client()
    table_counts = {}
    for table_name, records in prepared.items():
        rows_ref = (
            revision_ref.collection("tables")
            .document(table_name)
            .collection("rows")
        )
        for offset in range(0, len(records), 300):
            batch = client.batch()
            chunk = records[offset:offset + 300]
            for index, cleaned in enumerate(chunk, start=offset):
                batch.set(
                    rows_ref.document(f"row_{index:012d}"),
                    cleaned,
                )
            batch.commit()
        table_counts[table_name] = len(records)

    # Mark the revision complete before switching the active pointer. If this
    # final metadata write fails, the previous active revision remains intact.
    revision_ref.set({
        "workspace_status": "complete",
        "tables": table_counts,
        "completed_at": datetime.now(timezone.utc),
    }, merge=True)

    from firebase_admin import firestore
    switch_transaction = client.transaction()

    @firestore.transactional
    def _activate_revision(transaction):
        transaction.set(analysis_ref, {
            **_normalise_workspace_value(summary),
            "analysis_id": analysis_id,
            "active_revision": revision_id,
            "tables": table_counts,
            "workspace_status": "complete",
            "updated_at": datetime.now(timezone.utc),
        }, merge=True)
        transaction.set(company, {
            "latest_analysis_id": analysis_id,
            "latest_analysis_updated_at": datetime.now(timezone.utc),
        }, merge=True)

    _activate_revision(switch_transaction)
    write_company_audit_event(
        company_id, "analysis.workspace_saved", "analysis", analysis_id,
        {"revision_id": revision_id, "table_counts": table_counts},
    )
    # Retain a small recovery window without ever deleting the active revision.
    try:
        cleanup_analysis_revisions(company_id, analysis_id, keep=3)
    except Exception:
        # Cleanup must never turn a successfully committed analysis into a failed run.
        pass
    return analysis_id


def cleanup_analysis_revisions(company_id, analysis_id, keep=3):
    """Delete superseded analysis revisions while protecting the active revision."""
    if not isinstance(keep, int) or keep < 1 or keep > 20:
        raise ValueError("keep must be between 1 and 20.")
    company = _company_ref(company_id)
    analysis_id = _validate_id(analysis_id, "analysis_id")
    analysis_ref = company.collection("analyses").document(analysis_id)
    snapshot = analysis_ref.get()
    if not snapshot.exists:
        return 0
    active_revision = (snapshot.to_dict() or {}).get("active_revision")
    query = analysis_ref.collection("revisions").order_by(
        "created_at", direction="DESCENDING"
    )
    revisions = list(_stream_query_pages(query, page_size=200))
    protected = {active_revision} if active_revision else set()
    protected.update(item.id for item in revisions[:keep])
    client = get_firestore_client()
    deleted = 0
    for item in revisions:
        if item.id in protected:
            continue
        client.recursive_delete(item.reference)
        deleted += 1
    if deleted:
        write_company_audit_event(
            company_id, "analysis.revisions_pruned", "analysis", analysis_id,
            {"deleted_revision_count": deleted, "retained_revision_count": len(protected)},
        )
    return deleted


def get_latest_analysis_workspace(company_id):
    """Load the latest complete analysis using bounded, paginated row reads."""
    company = _company_ref(company_id)
    company_snapshot = company.get()
    if not company_snapshot.exists:
        return None
    analysis_id = (company_snapshot.to_dict() or {}).get("latest_analysis_id")
    if not analysis_id:
        return None

    analysis_ref = company.collection("analyses").document(
        _validate_id(analysis_id, "analysis_id")
    )
    snapshot = analysis_ref.get()
    if not snapshot.exists:
        return None
    summary = _denormalise_workspace_value(snapshot.to_dict() or {})
    if summary.get("workspace_status") != "complete":
        return None

    revision_id = summary.get("active_revision")
    data_ref = (
        analysis_ref.collection("revisions").document(revision_id)
        if revision_id else analysis_ref
    )
    if revision_id:
        revision_snapshot = data_ref.get()
        if not revision_snapshot.exists:
            return None
        if (revision_snapshot.to_dict() or {}).get("workspace_status") != "complete":
            return None

    tables = {}
    for table_name in (summary.get("tables") or {}):
        query = (
            data_ref.collection("tables")
            .document(table_name)
            .collection("rows")
            .order_by("__name__")
        )
        rows = []
        last_snapshot = None
        while True:
            page_query = query.limit(500)
            if last_snapshot is not None:
                page_query = page_query.start_after(last_snapshot)
            page = list(page_query.stream())
            if not page:
                break
            rows.extend(
                _denormalise_workspace_value(row.to_dict() or {})
                for row in page
            )
            last_snapshot = page[-1]
            if len(page) < 500:
                break
        tables[table_name] = rows

    write_company_audit_event(
        company_id, "analysis.workspace_restored", "analysis", analysis_id,
        {"table_counts": {name: len(rows) for name, rows in tables.items()}},
    )
    return {"analysis_id": analysis_id, "summary": summary, "tables": tables}
