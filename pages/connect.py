"""Seepsight company data onboarding.

The page supports the twelve procurement dataset schemas exposed by the
engine. Dataset ingestion, mapping and relationship checks are distinct from
detector coverage: only the four established detector pipelines generate
procurement findings in this version.
"""

import hashlib
import os
import tempfile

import pandas as pd
import streamlit as st

from seepsight import engine, plain, ui, workspace


ui.page_header(
    "Connect your data",
    "Bring your company's procurement records into Seepsight. Preview the data, "
    "confirm its structure, map up to twelve procurement dataset types and review data quality before analysis.",
)

# Uploads and results currently live in the Streamlit session. Keep this notice
# until durable, tenant-isolated storage has been implemented and verified.
st.warning(
    "Data storage is currently session-based. Uploaded records and analysis "
    "results are not yet permanently stored. Do not upload confidential or "
    "production customer data in this version."
)

CURRENCIES = ["NGN", "KES", "GHS", "ZAR", "USD", "EUR", "GBP", "TZS", "UGX", "INR"]
NOT_MAPPED = "— Not present in this file —"

# All registered procurement dataset schemas can now be uploaded, mapped,
# normalised and quality-checked by engine.onboard_tables(). The established
# findings engine still has four detector families; ingestion is not detector
# coverage.
CORE_DATASETS = {key: value["label"] for key, value in engine.DATASET_REGISTRY.items()}
DATASET_LABELS = {
    key: value["label"] for key, value in engine.DATASET_REGISTRY.items()
}
LABEL_TO_DATASET = {label: key for key, label in DATASET_LABELS.items()}


def _account():
    value = st.session_state.get("seepsight_auth")
    return value if isinstance(value, dict) else {}


def _read_upload(upload):
    suffix = os.path.splitext(upload.name)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(upload.getvalue())
        path = tmp.name
    try:
        return engine.read_any(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _fingerprint(uploaded_files):
    digest = hashlib.sha256()
    for item in sorted(uploaded_files, key=lambda x: x.name.lower()):
        digest.update(item.name.encode("utf-8", errors="replace"))
        digest.update(item.getvalue())
    return digest.hexdigest()


def _template_csv():
    sample = {
        "po_id": "PO-0001",
        "supplier": "Example Supplies Ltd",
        "po_date": "2026-01-15",
        "ordered_qty": 100,
        "po_unit_price": 250.00,
        "branch": "Main branch",
        "department": "Operations",
        "product": "Cartons",
        "promised_date": "2026-01-25",
        "received_date": "2026-01-24",
        "received_qty": 95,
        "invoice_qty": 100,
        "invoice_unit_price": 250.00,
        "invoice_date": "2026-01-30",
        "approval_requested_at": "2026-01-15 09:00",
        "approval_completed_at": "2026-01-16 14:00",
    }
    columns = [plain.FIELD_LABELS.get(field, field) for field in engine.FLAT_FIELDS]
    row = [sample.get(field, "") for field in engine.FLAT_FIELDS]
    return pd.DataFrame([row], columns=columns).to_csv(index=False)
