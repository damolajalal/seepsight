
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
from datetime import date, datetime, timezone
from decimal import Decimal

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
    """
    Test Firestore write, read and delete operations.

    Returns True only when all operations succeed.
    """

    client = get_firestore_client()

    test_id = f"connection_{uuid.uuid4().hex}"

    test_ref = (
        client.collection("_system")
        .document(test_id)
    )

    try:
        test_ref.set({
            "status": "connected",
            "purpose": "temporary_connection_test",
            "created_at": datetime.now(timezone.utc),
        })

        snapshot = test_ref.get()

        if not snapshot.exists:
            raise RuntimeError(
                "Firestore test document could not be read."
            )

        data = snapshot.to_dict()

        if data.get("status") != "connected":
            raise RuntimeError(
                "Firestore returned unexpected test data."
            )

        return True

    finally:
        # Ensure temporary test data is removed.
        test_ref.delete()


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

    return value


def _normalise(value):
    """
    Convert common Python values into Firestore-compatible values.
    """

    if value is None:
        return None

    if isinstance(value, dict):
        return {
            str(key): _normalise(item)
            for key, item in value.items()
        }

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
        return float(value)

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

        if isinstance(missing, bool) and missing:
            return None

    except (ImportError, TypeError, ValueError):
        pass

    raise TypeError(
        f"Unsupported Firestore data type: {type(value).__name__}"
    )


def _company_ref(company_id):
    """Return a tenant-scoped company reference."""

    company_id = _validate_id(
        company_id,
        "company_id"
    )

    client = get_firestore_client()

    return (
        client.collection("companies")
        .document(company_id)
    )


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

    return dataset_id


def get_company_datasets(company_id):
    """Retrieve all dataset metadata for a company."""

    company = _company_ref(company_id)

    snapshots = (
        company.collection("datasets")
        .stream()
    )

    return [
        {
            "id": snapshot.id,
            **(snapshot.to_dict() or {}),
        }
        for snapshot in snapshots
    ]


# ============================================================
# 5. PROCUREMENT RECORD STORAGE
# ============================================================

def save_dataset_records(
    company_id,
    dataset_id,
    records,
):
    """
    Save procurement records in individual Firestore documents.

    Records are written in batches of 400 to stay below
    Firestore's batch-write limit.

    Use a unique dataset_id for each new upload so that
    previous uploads are not accidentally mixed with new ones.

    Returns the number of records saved.
    """

    from google.cloud.firestore_v1 import SERVER_TIMESTAMP

    company = _company_ref(company_id)

    dataset_id = _validate_id(
        dataset_id,
        "dataset_id"
    )

    if not isinstance(records, (list, tuple)):
        raise TypeError(
            "records must be a list of dictionaries."
        )

    dataset_ref = (
        company.collection("datasets")
        .document(dataset_id)
    )

    client = get_firestore_client()

    batch_size = 400
    saved_count = 0

    for start in range(0, len(records), batch_size):

        batch = client.batch()

        current_records = records[
            start:start + batch_size
        ]

        for index, record in enumerate(current_records):

            if not isinstance(record, dict):
                raise TypeError(
                    "Each procurement record must be a dictionary."
                )

            record_number = start + index

            record_id = f"record_{record_number:012d}"

            record_ref = (
                dataset_ref.collection("records")
                .document(record_id)
            )

            cleaned_record = _normalise(record)

            cleaned_record["_record_number"] = record_number
            cleaned_record["_saved_at"] = SERVER_TIMESTAMP

            batch.set(
                record_ref,
                cleaned_record,
            )

        batch.commit()

        saved_count += len(current_records)

    # Update metadata after successful record writes.
    dataset_ref.set(
        {
            "record_count": saved_count,
            "records_saved": True,
            "updated_at": datetime.now(timezone.utc),
        },
        merge=True,
    )

    return saved_count


def get_dataset_records(company_id, dataset_id):
    """Retrieve procurement records for one company dataset."""

    company = _company_ref(company_id)

    dataset_id = _validate_id(
        dataset_id,
        "dataset_id"
    )

    dataset_ref = (
        company.collection("datasets")
        .document(dataset_id)
    )

    snapshots = (
        dataset_ref.collection("records")
        .order_by("_record_number")
        .stream()
    )

    return [
        {
            key: value
            for key, value in (snapshot.to_dict() or {}).items()
            if not key.startswith("_")
        }
        for snapshot in snapshots
    ]


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

    mapping_ref.set({
        "mapping": _normalise(mapping),
        "updated_at": datetime.now(timezone.utc),
    })

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

    return snapshot.to_dict().get("mapping")


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

    analysis_ref.set(
        {
            **_normalise(summary),
            "analysis_id": analysis_id,
            "finding_count": len(findings),
            "updated_at": datetime.now(timezone.utc),
        },
        merge=True,
    )

    client = get_firestore_client()

    batch_size = 400

    for start in range(0, len(findings), batch_size):

        batch = client.batch()

        current_findings = findings[
            start:start + batch_size
        ]

        for index, finding in enumerate(current_findings):

            if not isinstance(finding, dict):
                raise TypeError(
                    "Each finding must be a dictionary."
                )

            finding_number = start + index

            finding_id = f"finding_{finding_number:012d}"

            finding_ref = (
                analysis_ref.collection("findings")
                .document(finding_id)
            )

            cleaned_finding = _normalise(finding)

            cleaned_finding["_finding_number"] = finding_number

            batch.set(
                finding_ref,
                cleaned_finding,
            )

        batch.commit()

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

    summary = snapshot.to_dict() or {}

    findings = (
        analysis_ref.collection("findings")
        .order_by("_finding_number")
        .stream()
    )

    summary["findings"] = [
        {
            key: value
            for key, value in (finding.to_dict() or {}).items()
            if not key.startswith("_")
        }
        for finding in findings
    ]

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
