
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


def _company_owner_ref(company_id):
    """Return a company reference only for a currently verified owner."""
    membership = verify_company_access(company_id)
    if membership.get("role") != "owner":
        raise PermissionError("Only the company owner can manage database connections.")
    return get_firestore_client().collection("companies").document(
        membership["company_id"]
    )



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
        # Audit is best-effort within Firestore boundaries; never report a
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
# 5A. ORIGINAL UPLOAD BYTE STORAGE (FIRESTORE ONLY)
# ============================================================

_ORIGINAL_FILE_CHUNK_BYTES = 512 * 1024
_ORIGINAL_FILE_ALLOWED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".xls", ".json"}
_ORIGINAL_FILE_DEFAULT_MAX_BYTES = 50 * 1024 * 1024


def save_original_file(company_id, dataset_id, filename, data, content_type=None):
    """Persist original upload bytes as bounded, tenant-scoped Firestore chunks."""
    import hashlib
    import mimetypes
    import os
    from pathlib import PurePath

    company = _company_ref(company_id)
    dataset_id = _validate_id(dataset_id, "dataset_id")
    if not isinstance(filename, str) or not filename.strip():
        raise ValueError("A filename is required.")
    safe_name = PurePath(filename.replace("\\", "/")).name.strip()
    if safe_name in {"", ".", ".."} or len(safe_name) > 180:
        raise ValueError("The filename is invalid.")
    if PurePath(safe_name).suffix.lower() not in _ORIGINAL_FILE_ALLOWED_EXTENSIONS:
        raise ValueError("This file type is not supported.")
    if not isinstance(data, (bytes, bytearray, memoryview)):
        raise TypeError("Original file data must be bytes.")
    payload = bytes(data)
    try:
        max_bytes = int(os.environ.get("SEEPSIGHT_MAX_UPLOAD_BYTES", _ORIGINAL_FILE_DEFAULT_MAX_BYTES))
    except (TypeError, ValueError):
        max_bytes = _ORIGINAL_FILE_DEFAULT_MAX_BYTES
    if max_bytes < 1 or len(payload) > max_bytes:
        raise ValueError(f"File exceeds the configured upload limit ({max_bytes} bytes).")
    if not payload:
        raise ValueError("The uploaded file is empty.")

    dataset_ref = company.collection("datasets").document(dataset_id)
    chunks_ref = dataset_ref.collection("original_file_chunks")
    digest = hashlib.sha256(payload).hexdigest()
    mime = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    count = (len(payload) + _ORIGINAL_FILE_CHUNK_BYTES - 1) // _ORIGINAL_FILE_CHUNK_BYTES
    dataset_ref.set({
        "original_file_status": "saving",
        "original_file_saved": False,
        "original_file": {
            "filename": safe_name, "content_type": mime,
            "size_bytes": len(payload), "sha256": digest,
            "chunk_count": count, "chunk_bytes": _ORIGINAL_FILE_CHUNK_BYTES,
        },
        "updated_at": datetime.now(timezone.utc),
    }, merge=True)

    client = get_firestore_client()
    try:
        client.recursive_delete(chunks_ref)
        for start in range(0, count, 16):
            batch = client.batch()
            for index in range(start, min(start + 16, count)):
                part = payload[index * _ORIGINAL_FILE_CHUNK_BYTES:(index + 1) * _ORIGINAL_FILE_CHUNK_BYTES]
                batch.set(chunks_ref.document(f"chunk_{index:06d}"), {
                    "chunk_index": index, "data": part, "size_bytes": len(part),
                })
            batch.commit()
        dataset_ref.set({
            "original_file_status": "complete",
            "original_file_saved": True,
            "updated_at": datetime.now(timezone.utc),
        }, merge=True)
    except Exception as exc:
        try:
            client.recursive_delete(chunks_ref)
        except Exception:
            logging.getLogger(__name__).warning("Partial original-file chunk cleanup failed.")
        try:
            dataset_ref.set({
                "original_file_status": "failed",
                "original_file_saved": False,
                "updated_at": datetime.now(timezone.utc),
            }, merge=True)
        except Exception:
            pass
        raise RuntimeError("The original file could not be saved completely to Firestore.") from exc

    write_company_audit_event(
        company_id, "dataset.original_file_saved", "dataset", dataset_id,
        {"filename": safe_name, "size_bytes": len(payload), "chunk_count": count, "sha256": digest},
    )
    return {"filename": safe_name, "size_bytes": len(payload), "sha256": digest, "chunk_count": count}


def get_original_file(company_id, dataset_id):
    """Reassemble and integrity-check a company's original upload."""
    import hashlib
    company = _company_ref(company_id)
    dataset_id = _validate_id(dataset_id, "dataset_id")
    dataset_ref = company.collection("datasets").document(dataset_id)
    snapshot = dataset_ref.get()
    if not snapshot.exists:
        raise FileNotFoundError("The requested company dataset does not exist.")
    metadata = snapshot.to_dict() or {}
    if metadata.get("original_file_status") != "complete":
        raise RuntimeError("The original file is not in a complete saved state.")
    info = metadata.get("original_file") or {}
    expected = int(info.get("chunk_count", 0))
    if expected < 1:
        raise RuntimeError("The original file metadata is incomplete.")
    query = dataset_ref.collection("original_file_chunks").order_by("chunk_index")
    chunks = list(_stream_query_pages(query, page_size=300))
    if len(chunks) != expected:
        raise RuntimeError("The original file is missing one or more stored chunks.")
    parts = []
    for index, chunk in enumerate(chunks):
        item = chunk.to_dict() or {}
        if int(item.get("chunk_index", -1)) != index or not isinstance(item.get("data"), bytes):
            raise RuntimeError("The original file chunk sequence is invalid.")
        parts.append(item["data"])
    payload = b"".join(parts)
    if len(payload) != int(info.get("size_bytes", -1)):
        raise RuntimeError("The original file size does not match its stored metadata.")
    if hashlib.sha256(payload).hexdigest() != info.get("sha256"):
        raise RuntimeError("The original file integrity check failed.")
    write_company_audit_event(
        company_id, "dataset.original_file_downloaded", "dataset", dataset_id,
        {"size_bytes": len(payload), "sha256": info.get("sha256")},
    )
    return {"filename": info.get("filename"), "content_type": info.get("content_type"), "data": payload}


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
    """Delete a company dataset and its Firestore subcollections, including original-file chunks."""
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

    original_file_saved = metadata.get("original_file_status") == "complete"
    try:
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
        {"original_file_deleted": bool(original_file_saved)},
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

    company = _company_owner_ref(company_id)
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
    company = _company_owner_ref(company_id)
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
    company = _company_owner_ref(company_id)
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
    company = _company_owner_ref(company_id)
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

    if len(findings) > 250_000:
        raise ValueError("An analysis cannot contain more than 250,000 findings.")
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
    try:
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
    except Exception as exc:
        try:
            analysis_ref.set({
                "results_status": "failed",
                "updated_at": datetime.now(timezone.utc),
            }, merge=True)
        except Exception:
            pass
        raise RuntimeError("Analysis findings could not be saved completely.") from exc

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
    if summary.get("results_status") in {"saving", "failed"}:
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

def save_analysis_workspace(company_id, analysis_id, summary, tables, dataset_group_id=None):
    """Persist a new workspace revision, then atomically make it active.

    Existing completed revisions remain readable if a replacement write fails.
    """
    company = _company_ref(company_id)
    analysis_id = _validate_id(analysis_id, "analysis_id")
    if not isinstance(summary, dict) or not isinstance(tables, dict):
        raise TypeError("summary and tables must be dictionaries.")

    # Validate and normalise the complete payload before changing Firestore.
    cleaned_summary = _normalise_workspace_value(summary)
    if dataset_group_id is not None:
        cleaned_summary['dataset_group_id'] = _validate_id(dataset_group_id, 'dataset_group_id')
    if len(json.dumps(cleaned_summary, default=str).encode("utf-8")) > 800_000:
        raise ValueError("Analysis workspace summary is too large to store safely.")
    prepared = {}
    total_rows = 0
    for table_name, records in tables.items():
        if (
            not isinstance(table_name, str)
            or not table_name.replace("_", "").isalnum()
            or len(table_name.encode("utf-8")) > 128
        ):
            raise ValueError("Invalid analysis table name.")
        if records is None:
            records = []
        if not isinstance(records, (list, tuple)):
            raise TypeError("Each analysis table must be a list of records.")
        total_rows += len(records)
        if total_rows > 250_000:
            raise ValueError("An analysis workspace cannot exceed 250,000 total rows.")
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
            **cleaned_summary,
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
    protected = {active_revision} if active_revision else set()
    client = get_firestore_client()
    deleted = 0
    recent_count = 0
    for item in _stream_query_pages(query, page_size=200):
        if recent_count < keep:
            protected.add(item.id)
        recent_count += 1
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


def get_latest_analysis_workspace(company_id, analysis_id=None):
    """Load a selected complete analysis, or the latest one, with bounded row reads."""
    company = _company_ref(company_id)
    if analysis_id is None:
        company_snapshot = company.get()
        if not company_snapshot.exists:
            return None
        analysis_id = (company_snapshot.to_dict() or {}).get("latest_analysis_id")
        if not analysis_id:
            return None
    analysis_id = _validate_id(analysis_id, "analysis_id")

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

def get_company_dataset_groups(company_id):
    """Return logical dataset groups and their saved files for the company."""
    company = _company_ref(company_id)
    groups = {}
    for snapshot in _stream_query_pages(company.collection("datasets").order_by("__name__"), page_size=200):
        data = _denormalise_workspace_value(snapshot.to_dict() or {})
        group_id = data.get("dataset_group_id") or snapshot.id
        item = groups.setdefault(group_id, {
            "dataset_group_id": group_id,
            "files": [],
            "file_count": 0,
            "record_count": 0,
            "source_record_count": 0,
            "company_name": data.get("company_name") or "Procurement dataset",
            "all_files_linked": True,
            "all_original_files_restorable": True,
            "has_analysis": False,
        })
        if not data.get("dataset_group_id"):
            item["all_files_linked"] = False
        if data.get("original_file_status") != "complete":
            item["all_original_files_restorable"] = False
        filename = data.get("filename") or snapshot.id
        item["files"].append(filename)
        item.setdefault("file_items", []).append({
            "dataset_id": snapshot.id,
            "filename": filename,
            "dataset_type": data.get("dataset_type"),
            "source_sha256": data.get("source_sha256"),
        })
        item["file_count"] += 1
        item["record_count"] += int(data.get("record_count", data.get("normalized_record_count", 0)) or 0)
        item["source_record_count"] += int(data.get("source_record_count", 0) or 0)

    for snapshot in _stream_query_pages(company.collection("analyses").order_by("updated_at", direction="DESCENDING"), page_size=200):
        data = _denormalise_workspace_value(snapshot.to_dict() or {})
        group_id = data.get("dataset_group_id")
        if not group_id:
            continue
        item = groups.setdefault(group_id, {
            "dataset_group_id": group_id,
            "files": [],
            "file_count": 0,
            "record_count": 0,
            "source_record_count": 0,
            "company_name": data.get("company_name") or "Procurement dataset",
            "all_files_linked": True,
            "all_original_files_restorable": True,
            "has_analysis": False,
        })
        item["has_analysis"] = True
        if "analysis_id" not in item:
            item["analysis_id"] = snapshot.id
            item["updated_at"] = data.get("updated_at")
    for item in groups.values():
        # Deletion needs complete logical links and a saved analysis. Extension
        # additionally needs every original upload to be present and verifiable.
        item["deletion_safe"] = bool(
            item["all_files_linked"] and item["has_analysis"]
        )
        item["extendable"] = bool(
            item["all_files_linked"]
            and item["has_analysis"]
            and item["all_original_files_restorable"]
            and item["file_items"]
        )
        item.pop("all_files_linked", None)
        item.pop("all_original_files_restorable", None)
        item.pop("has_analysis", None)
    return sorted(groups.values(), key=lambda item: item.get("updated_at") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)


def delete_company_dataset_group(company_id, dataset_group_id):
    """Owner-only cascade deletion of one logical dataset and all dependent records."""
    company = _company_owner_ref(company_id)
    dataset_group_id = _validate_id(dataset_group_id, "dataset_group_id")
    datasets = []
    analyses = []
    cases = []
    has_unlinked_file = False

    for snapshot in _stream_query_pages(company.collection("datasets").order_by("__name__"), page_size=200):
        data = snapshot.to_dict() or {}
        if (data.get("dataset_group_id") or snapshot.id) == dataset_group_id:
            if data.get("dataset_group_id") != dataset_group_id:
                has_unlinked_file = True
            datasets.append(snapshot.reference)
    for snapshot in _stream_query_pages(company.collection("analyses").order_by("__name__"), page_size=200):
        data = snapshot.to_dict() or {}
        if data.get("dataset_group_id") == dataset_group_id:
            analyses.append(snapshot.reference)
    for snapshot in _stream_query_pages(company.collection("cases").order_by("__name__"), page_size=200):
        data = snapshot.to_dict() or {}
        if data.get("dataset_group_id") == dataset_group_id:
            cases.append(snapshot.reference)

    if has_unlinked_file or not analyses:
        raise RuntimeError("This dataset does not have complete file-to-analysis links and cannot be safely deleted.")
    if not datasets and not analyses and not cases:
        return False

    company_snapshot = company.get()
    company_data = company_snapshot.to_dict() or {}
    active_analysis_id = company_data.get("latest_analysis_id")
    deleting_active = any(ref.id == active_analysis_id for ref in analyses)

    client = get_firestore_client()
    for reference in datasets + analyses + cases:
        reference.set({
            "deletion_status": "deleting",
            "updated_at": datetime.now(timezone.utc),
        }, merge=True)
    try:
        for reference in datasets + analyses + cases:
            client.recursive_delete(reference)
    except Exception as exc:
        for reference in datasets + analyses + cases:
            try:
                reference.set({
                    "deletion_status": "deletion_failed",
                    "updated_at": datetime.now(timezone.utc),
                }, merge=True)
            except Exception:
                pass
        raise RuntimeError("The dataset deletion was incomplete. Retry the same deletion before using this dataset.") from exc

    if deleting_active:
        remaining = [item for item in _stream_query_pages(
            company.collection("analyses").order_by("__name__"), page_size=200
        ) if (item.to_dict() or {}).get("workspace_status") == "complete"]
        remaining.sort(
            key=lambda item: (item.to_dict() or {}).get("updated_at") or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        if remaining:
            company.set({
                "latest_analysis_id": remaining[0].id,
                "latest_analysis_updated_at": (remaining[0].to_dict() or {}).get("updated_at"),
            }, merge=True)
        else:
            from firebase_admin import firestore
            company.set({
                "latest_analysis_id": firestore.DELETE_FIELD,
                "latest_analysis_updated_at": firestore.DELETE_FIELD,
            }, merge=True)

    write_company_audit_event(
        company_id, "dataset_group.deleted", "dataset_group", dataset_group_id,
        {"files_deleted": len(datasets), "analyses_deleted": len(analyses), "cases_deleted": len(cases)},
    )
    return True


def get_company_analysis_workspaces(company_id):
    """List completed analysis workspaces for this authenticated company."""
    company = _company_ref(company_id)
    query = company.collection("analyses").order_by("updated_at", direction="DESCENDING")
    items = []
    for snapshot in _stream_query_pages(query, page_size=200):
        data = _denormalise_workspace_value(snapshot.to_dict() or {})
        if data.get("workspace_status") == "complete":
            items.append({
                "analysis_id": snapshot.id,
                "dataset_group_id": data.get("dataset_group_id") or snapshot.id,
                "company_name": data.get("company_name", "Company dataset"),
                "updated_at": data.get("updated_at"),
            })
    return items


def search_dataset_records(
    company_id, dataset_id, terms, collection_name="records",
    limit=10, scan_limit=5000,
):
    """Search a tenant-owned dataset in record order using paginated reads.

    Returned AI context remains bounded by limit. By default every stored row
    is scanned so a matching record in the middle cannot be silently missed.
    An explicit scan_limit is a read budget and reports incomplete coverage.
    """
    if collection_name not in {"records", "source_records"}:
        raise ValueError("collection_name must be 'records' or 'source_records'.")
    if not isinstance(limit, int) or limit < 1 or limit > 25:
        raise ValueError("limit must be between 1 and 25.")
    if scan_limit is None:
        scan_limit = 5000
    if not isinstance(scan_limit, int) or scan_limit < 1 or scan_limit > 5000:
        raise ValueError("scan_limit must be between 1 and 5000.")
    if not isinstance(terms, (list, tuple)) or not all(isinstance(x, str) for x in terms):
        raise TypeError("terms must be a list of strings.")

    company = _company_ref(company_id)
    dataset_id = _validate_id(dataset_id, "dataset_id")
    dataset_ref = company.collection("datasets").document(dataset_id)
    metadata_snapshot = dataset_ref.get()
    if not metadata_snapshot.exists:
        raise FileNotFoundError("The requested company dataset does not exist.")
    metadata = metadata_snapshot.to_dict() or {}
    status_key = f"{collection_name}_status"
    if metadata.get("deletion_status") in {"deleting", "failed"}:
        raise RuntimeError("This dataset is being deleted and is not available.")
    if metadata.get(status_key) in {"saving", "failed"}:
        raise RuntimeError("This dataset's records are not in a complete saved state.")

    count_key = "source_record_count" if collection_name == "source_records" else "record_count"
    total_count = int(metadata.get(count_key, 0) or 0)
    base_query = dataset_ref.collection(collection_name).order_by("_record_number")

    clean_terms = []
    for term in terms:
        term = term.casefold().strip()
        if not term:
            continue
        clean_terms.append(term)
        if term.endswith("ies") and len(term) > 4:
            clean_terms.append(term[:-3] + "y")
        elif term.endswith("s") and len(term) > 4:
            clean_terms.append(term[:-1])
    clean_terms = list(dict.fromkeys(clean_terms))

    ranked = []
    match_count = 0
    scanned = 0
    budget_reached = False
    page_size = min(500, scan_limit) if scan_limit is not None else 500
    for snapshot in _stream_query_pages(base_query, page_size=page_size):
        if scan_limit is not None and scanned >= scan_limit:
            budget_reached = True
            break
        item = _denormalise_workspace_value(snapshot.to_dict() or {})
        record_number = int(item.get("_record_number", scanned))
        searchable = " ".join(
            f"{key} {value}" for key, value in item.items()
            if not str(key).startswith("_") and value is not None
        ).casefold()
        score = sum(1 for term in clean_terms if term in searchable)
        scanned += 1
        if not clean_terms or score:
            match_count += 1
            record = {
                key: value for key, value in item.items()
                if not str(key).startswith("_")
            }
            ranked.append((score, record_number, record))

    # Sort once after the full scan; repeated sorting per row becomes expensive
    # when Ask Hybrid AI requests comprehensive dataset coverage.
    ranked.sort(key=lambda row: (-row[0], row[1]))
    coverage_complete = not budget_reached and scanned >= total_count
    selected = [row[2] for row in ranked[:limit]]
    write_company_audit_event(
        company_id, f"dataset.{collection_name}_searched", "dataset", dataset_id,
        {
            "scanned_count": scanned,
            "match_count": match_count,
            "returned_count": len(selected),
            "coverage_complete": coverage_complete,
            "collection": collection_name,
        },
    )
    return {
        "records": selected,
        "scanned_count": scanned,
        "total_count": total_count,
        "match_count": match_count,
        "coverage_complete": coverage_complete,
        "scan_limited": not coverage_complete,
    }
