"""Seepsight company data onboarding.

The page supports the twelve procurement dataset schemas exposed by the
engine. Dataset ingestion, mapping and relationship checks are distinct from
detector coverage: only the four established detector pipelines generate
procurement findings in this version.
"""

import hashlib
import os
import tempfile
import uuid

import pandas as pd
import streamlit as st

from seepsight import cloud_storage, engine, plain, ui, workspace
from seepsight.firestore_db import (
    save_company_dataset,
    save_company_mapping,
    save_dataset_records,
)


ui.page_header(
    "Connect your data",
    "Bring your company's procurement records into Seepsight. Preview the data, "
    "confirm its structure, map up to twelve procurement dataset types and review data quality before analysis.",
)

if cloud_storage.is_configured():
    st.info("Original uploads are saved to private company storage only when that service is configured. Validated, mapped procurement records, analysis summaries, findings and dashboard tables are saved to your company's Firestore workspace.")
else:
    st.warning("Private file storage is not configured yet, so original file bytes remain session-only. Validated, mapped procurement records and analysis results are saved separately to your company's Firestore workspace.")

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


def _dataset_guess(df, filename):
    ranked = engine.detect_dataset_type(df, filename)
    if not ranked:
        ranked = []

    # A flat order export can contain a supplier/vendor column, which may
    # otherwise make the generic registry score it as a supplier master.
    # Require the five core order fields before preferring the order dataset.
    order_map, _, _ = engine.suggest_mapping(
        df,
        engine.DEFAULT_CONFIG["accept_score"],
        ["po_id", "supplier", "po_date", "ordered_qty", "po_unit_price"],
    )
    if all(field in order_map for field in ("po_id", "supplier", "po_date", "ordered_qty", "po_unit_price")):
        best_score = min(float(order_map[field]["confidence"]) for field in order_map)
        ranked = [item for item in ranked if item["dataset"] != "orders"]
        ranked.insert(0, {
            "dataset": "orders",
            "label": DATASET_LABELS["orders"],
            "confidence": round(best_score, 3),
            "header_hits": 5,
            "filename_hits": 0,
        })
        return "orders", round(best_score, 3), ranked

    if not ranked:
        return "orders", 0.0, ranked
    return ranked[0]["dataset"], ranked[0]["confidence"], ranked


def _mapping_editor(df, fields, key_prefix, required_fields=None):
    """Show ranked suggestions and let the user confirm or correct each field."""
    required_fields = set(required_fields if required_fields is not None else engine.REQUIRED)
    suggested, _, _ = engine.suggest_mapping(
        df,
        engine.DEFAULT_CONFIG["accept_score"],
        fields,
    )
    candidates = engine.mapping_candidates(df, fields=fields, top_n=4)
    overrides = {}
    selected = {}
    columns = list(df.columns)

    for field in fields:
        info = suggested.get(field)
        default = info["column"] if info else NOT_MAPPED
        ranked = candidates.get(field, [])
        ranked_names = [item["column"] for item in ranked]
        options = [NOT_MAPPED] + list(dict.fromkeys(ranked_names + columns))
        if default not in options:
            default = NOT_MAPPED
        label = plain.FIELD_LABELS.get(field, field.replace("_", " ").title())
        if field in required_fields:
            label += " (required)"

        choice = st.selectbox(
            label,
            options,
            index=options.index(default),
            key=f"{key_prefix}_{field}",
            help=(
                "Ranked suggestions appear first. Choose the correct source "
                "column, or select Not present if this file does not contain it."
            ),
        )
        selected[field] = choice
        if choice == NOT_MAPPED:
            if info:
                overrides[field] = None
        elif not info or choice != info["column"]:
            overrides[field] = choice

        if ranked:
            best = ranked[0]
            if choice == best["column"]:
                st.caption(
                    f"Suggested match confidence: {best['confidence']:.0%}. "
                    f"Content compatibility: {best['content_fit']:.0%}."
                )
            elif choice != NOT_MAPPED:
                st.caption("Manual selection — please verify that the values match this field.")
        elif choice != NOT_MAPPED:
            st.caption("No strong automatic match was found. This is a manual selection.")

    return overrides, selected


def _preview(name, df):
    with st.expander(f"Preview: {name} · {len(df):,} rows × {len(df.columns):,} columns", expanded=False):
        st.dataframe(df.head(10), hide_index=True, width="stretch")
        st.caption("Showing the first 10 rows. Original uploaded values are not changed in this preview.")


account = _account()
company_id = account.get("company_id")
company_name = str(account.get("company_name") or "").strip()
if not company_id or not company_name:
    st.error("Your company identity could not be confirmed. Please sign in again before connecting data.")
    st.stop()

st.markdown("### Company workspace")
st.write(f"**{company_name}**")
st.caption("Your upload will be associated with the signed-in company account.")

st.markdown("### Step 1. Choose your data")
left, right = st.columns([1, 1])
with left:
    currency = st.selectbox("Currency used in your procurement records", CURRENCIES, index=0, key="connect_currency")
with right:
    st.download_button(
        "Download a blank procurement template",
        data=_template_csv(),
        file_name="seepsight_procurement_template.csv",
        mime="text/csv",
        use_container_width=True,
    )

uploaded = st.file_uploader(
    "Upload procurement files",
    type=["csv", "tsv", "xlsx", "xls", "json"],
    accept_multiple_files=True,
    help="Supported file types in this version: CSV, TSV, XLSX, XLS and JSON.",
    key="connect_file_uploader",
)

if uploaded:
    current_fingerprint = _fingerprint(uploaded)
    if st.session_state.get("connect_upload_fingerprint") != current_fingerprint:
        loaded = {}
        source_file_bytes = {}
        errors = []
        for item in uploaded:
            try:
                frame = _read_upload(item)
                if frame.empty or len(frame.columns) == 0:
                    errors.append(f"{item.name}: no usable rows or columns were found.")
                else:
                    loaded[item.name] = frame
                    source_file_bytes[item.name] = item.getvalue()
            except Exception as exc:
                errors.append(f"{item.name}: could not be read ({exc}).")
        st.session_state["connect_raw"] = loaded
        st.session_state["connect_source_file_bytes"] = source_file_bytes
        st.session_state["connect_upload_fingerprint"] = current_fingerprint
        st.session_state.pop("connect_check", None)
        st.session_state.pop("_done", None)
        st.session_state["connect_load_errors"] = errors

if st.button("Clear uploaded files and start again", key="clear_connect_uploads"):
    for key in ("connect_raw", "connect_upload_fingerprint", "connect_check", "connect_check_signature", "connect_dataset_types", "connect_load_errors"):
        st.session_state.pop(key, None)
    st.session_state.pop("_done", None)
    st.rerun()

for message in st.session_state.get("connect_load_errors", []):
    st.error(message)

raw = st.session_state.get("connect_raw", {})
if not raw:
    st.info("Upload one or more procurement files to begin. You can also download the blank template to see the expected fields.")
    st.stop()

st.markdown("### Step 2. Preview and identify each dataset")
for filename, frame in raw.items():
    _preview(filename, frame)

st.caption(
    "Seepsight checks file names and column headers to suggest a dataset type. "
    "Confirm the classification before continuing."
)

kinds = {}
rankings = {}
for filename, frame in raw.items():
    guessed, confidence, ranked = _dataset_guess(frame, filename)
    rankings[filename] = ranked
    labels = list(DATASET_LABELS.values())
    guessed_label = DATASET_LABELS.get(guessed, DATASET_LABELS["orders"])
    with st.container(border=True):
        st.write(f"**{filename}**")
        st.caption(f"{len(frame):,} rows · {len(frame.columns):,} columns · suggested: {guessed_label} ({confidence:.0%} signal)")
        chosen_label = st.selectbox(
            "What kind of procurement information is this?",
            labels,
            index=labels.index(guessed_label),
            key=f"dataset_type_{hashlib.sha1(filename.encode()).hexdigest()[:10]}",
        )
        kinds[filename] = LABEL_TO_DATASET[chosen_label]
        if len(ranked) > 1:
            alternatives = ", ".join(f"{DATASET_LABELS[item['dataset']]} {item['confidence']:.0%}" for item in ranked[:3])
            st.caption(f"Other recognition signals: {alternatives}")

# Every recognised dataset type is now an ingestible input. The orders table
# remains mandatory because the established ledger and detector calculations
# are order-centred.
core_files = dict(kinds)

if not core_files:
    st.error("Upload at least one procurement dataset to continue.")
    st.stop()

# One file per dataset type avoids silently concatenating records with different
# structures. Multi-file-per-entity support can be added with explicit append
# and deduplication rules in a later engine change.
for dataset_kind in CORE_DATASETS:
    matches = [filename for filename, kind in core_files.items() if kind == dataset_kind]
    if len(matches) > 1:
        st.error(
            f"You uploaded {len(matches)} files classified as {CORE_DATASETS[dataset_kind]}. "
            "This version accepts one file per dataset type. Combine files with the same "
            "structure before uploading, or classify the files correctly."
        )
        st.stop()

if "orders" not in core_files.values():
    st.error("A Purchase orders dataset is required. Add the purchase-order file before validating other procurement datasets.")
    st.stop()

st.markdown("### Step 3. Confirm column mappings")
multiple_tables = len(core_files) > 1
single_file = len(raw) == 1 and len(core_files) == 1 and next(iter(core_files.values())) == "orders"
mapping_overrides = {}
selected_mappings = {}

if single_file:
    filename = next(iter(core_files))
    frame = raw[filename]
    fields = engine.FLAT_FIELDS
    with st.expander(f"Map columns in {filename}", expanded=True):
        one_overrides, one_selected = _mapping_editor(frame, fields, "connect_single_map", engine.REQUIRED)
    mapping_overrides = one_overrides
    selected_mappings["orders"] = one_selected
else:
    for filename, kind in core_files.items():
        frame = raw[filename]
        fields = engine.TABLE_FIELDS[kind]
        with st.expander(f"{CORE_DATASETS[kind]} · {filename}", expanded=(kind == "orders")):
            required_fields = engine.REQUIRED if kind == "orders" else engine.DATASET_REGISTRY[kind].get("required", [])
            overrides, selected = _mapping_editor(frame, fields, f"map_{kind}", required_fields)
        mapping_overrides[kind] = overrides
        selected_mappings[kind] = selected

# Build a deterministic signature from every input that can change the result.
# This prevents a previous check from being processed after edits to data,
# dataset classification, company, currency or mapping selections.
signature_payload = {
    "fingerprint": st.session_state.get("connect_upload_fingerprint"),
    "company_id": str(company_id),
    "company_name": company_name,
    "currency": currency,
    "kinds": sorted(kinds.items()),
    "mappings": selected_mappings,
}
check_signature = hashlib.sha256(repr(signature_payload).encode("utf-8")).hexdigest()
if st.session_state.get("connect_check_signature") != check_signature:
    st.session_state.pop("connect_check", None)
    st.session_state.pop("_done", None)

st.markdown("### Step 4. Validate your procurement records")
st.caption("The check uses the mappings shown above. Review uncertain matches before proceeding.")

if st.button("Validate and analyse records", type="primary", use_container_width=True, key="run_connect_check"):
    config = {"currency": currency}
    try:
        with st.spinner("Recognising fields, validating records and running available checks..."):
            if single_file:
                filename = next(iter(core_files))
                result = engine.onboard(
                    df=raw[filename],
                    overrides=mapping_overrides,
                    config=config,
                    verbose=False,
                )
            else:
                tables = {}
                table_overrides = {}
                for filename, kind in core_files.items():
                    tables[kind] = raw[filename]
                    table_overrides[kind] = mapping_overrides.get(kind, {})
                result = engine.onboard_tables(
                    tables,
                    overrides=table_overrides,
                    config=config,
                    verbose=False,
                )
        st.session_state["connect_check"] = result
        st.session_state["connect_check_signature"] = check_signature
        st.session_state.pop("_done", None)
    except Exception as exc:
        st.error(f"We could not validate these records: {exc}")
        st.stop()

result = st.session_state.get("connect_check")
if result and st.session_state.get("connect_check_signature") == check_signature:
    quality = result.get("quality", {})
    st.markdown("### Step 5. Review validation results")

    if result.get("stopped"):
        st.error(result["stopped"])
        missing = result.get("needs_choice", [])
        if missing:
            st.write("Fields still requiring a match: " + ", ".join(plain.FIELD_LABELS.get(field, field) for field in missing))
    else:
        rows_in = int(quality.get("rows_in_file", 0) or 0)
        rows_used = int(quality.get("rows_used", 0) or 0)
        st.success(f"Validation completed: {rows_used:,} of {rows_in:,} order rows are available for analysis.")

        dropped = quality.get("dropped", {})
        if dropped:
            for reason, count in dropped.items():
                if count:
                    st.write(f"• {str(reason).replace('_', ' ').capitalize()}: {count:,}")

        warnings = quality.get("warnings", [])
        if warnings:
            st.markdown("**Items to review**")
            for warning in warnings:
                st.warning(warning)
        else:
            st.write("No additional data-quality warnings were returned by the current checks.")

        st.markdown("**Available procurement checks**")
        for detector, status in quality.get("detectors", {}).items():
            label = plain.CHECK_LABELS.get(detector, detector)
            if status == "ready":
                st.write(f"✓ {label} — ready")
            else:
                st.write(f"• {label} — not ready: {status}")

        with st.expander("Review confirmed column mappings"):
            mapping_rows = []
            for field, info in result.get("mapping", {}).items():
                mapping_rows.append({
                    "Seepsight field": plain.FIELD_LABELS.get(field.split(".")[-1], field),
                    "Source column": info.get("column"),
                    "Confidence": f"{float(info.get('confidence', 0)):.0%}",
                    "Mapping source": info.get("source", "automatic"),
                })
            if mapping_rows:
                st.dataframe(pd.DataFrame(mapping_rows), hide_index=True, width="stretch")
            else:
                st.info("No column mappings were returned.")

        dataset_quality = result.get("dataset_quality", {})
        if dataset_quality:
            st.markdown("**Dataset-level quality review**")
            quality_rows = []
            for dataset_name, details in dataset_quality.items():
                quality_rows.append({
                    "Dataset": DATASET_LABELS.get(dataset_name, dataset_name),
                    "Rows received": details.get("rows_in_file", 0),
                    "Rows normalised": details.get("rows_normalised", 0),
                    "Duplicate rows": details.get("duplicate_rows", 0),
                    "Duplicate key rows": details.get("duplicate_key_rows", 0),
                    "Readiness": details.get("readiness", "not assessed"),
                })
            st.dataframe(pd.DataFrame(quality_rows), hide_index=True, width="stretch")
            with st.expander("Review dataset field and key details"):
                for dataset_name, details in dataset_quality.items():
                    st.write(f"**{DATASET_LABELS.get(dataset_name, dataset_name)}**")
                    st.caption(f"Key field: {details.get('key_field') or 'No recognised key'}")
                    missing = details.get("missing_required_fields", [])
                    if missing:
                        st.warning("Required fields missing: " + ", ".join(plain.FIELD_LABELS.get(field, field) for field in missing))
                    unmapped_columns = details.get("unmapped_columns", [])
                    if unmapped_columns:
                        st.caption("Unmapped source columns: " + ", ".join(map(str, unmapped_columns)))
                    numeric_gaps = {field: count for field, count in details.get("missing_numeric_values", {}).items() if count}
                    if numeric_gaps:
                        st.caption("Missing or non-numeric values: " + ", ".join(f"{field}: {count}" for field, count in numeric_gaps.items()))

        relationships = result.get("relationships", {})
        if relationships:
            st.markdown("**Cross-dataset relationship checks**")
            relationship_rows = []
            for relationship, details in relationships.items():
                relationship_rows.append({
                    "Relationship": relationship.replace("_", " "),
                    "Matched keys": details.get("matched_keys", 0),
                    "Source keys": details.get("source_keys", 0),
                    "Coverage": f"{details.get('coverage', 0):.0%}",
                })
            st.dataframe(pd.DataFrame(relationship_rows), hide_index=True, width="stretch")
        else:
            st.caption("No cross-dataset key relationships could be assessed from the mapped fields supplied.")

        st.markdown("**Detector coverage**")
        st.caption("All uploaded dataset types are ingested and quality-checked where mapped. Findings are currently generated by the four established detector families listed below.")

        st.markdown("### Step 6. Open your company workspace")
        st.caption("Your results will be attached to the signed-in company identity shown at the top of this page.")
        if st.button("Review procurement intelligence", type="primary", use_container_width=True, key="open_company_workspace"):
            try:
                private_storage_ready = cloud_storage.is_configured()
                status_message = (
                    "Saving original files and preparing your company workspace..."
                    if private_storage_ready
                    else "Saving validated records to your company workspace..."
                )
                with st.status(status_message, expanded=True) as status:
                    saved_upload_ids = []
                    for source_filename, source_frame in raw.items():
                        upload_id = uuid.uuid4().hex
                        storage_metadata = None
                        if private_storage_ready:
                            storage_metadata = cloud_storage.upload_company_file(
                                company_id,
                                upload_id,
                                source_filename,
                                st.session_state["connect_source_file_bytes"][source_filename],
                            )
                            storage_status = "original_file_saved"
                        else:
                            storage_status = "session_only"

                        dataset_kind = kinds[source_filename]
                        dataset_metadata = {
                            "dataset_type": dataset_kind,
                            "filename": source_filename,
                            "status": storage_status,
                            "record_count": int(len(source_frame)),
                        }
                        if storage_metadata is not None:
                            dataset_metadata["storage"] = storage_metadata
                        normalized_tables = result.get("normalized_tables", {})
                        normalized_frame = normalized_tables.get(dataset_kind)
                        if not isinstance(normalized_frame, pd.DataFrame):
                            raise RuntimeError(
                                f"Validated records for {DATASET_LABELS.get(dataset_kind, dataset_kind)} "
                                "were not returned by the ingestion engine."
                            )
                        dataset_metadata["normalized_record_count"] = int(len(normalized_frame))
                        save_company_dataset(company_id, upload_id, dataset_metadata)
                        save_company_mapping(company_id, upload_id, selected_mappings.get(dataset_kind, {}))
                        saved_records = normalized_frame.astype(object).where(
                            pd.notna(normalized_frame), None
                        ).to_dict("records")
                        save_dataset_records(company_id, upload_id, saved_records)
                        saved_upload_ids.append(upload_id)
                    if private_storage_ready:
                        st.write(f"Saved {len(saved_upload_ids)} original file(s) to private company storage")
                    else:
                        st.write("Original file bytes remain session-only because private object storage is not configured. Validated, mapped procurement records are being saved separately to Firestore.")
                    st.write("Preparing findings and supporting evidence")
                    pack = workspace.from_result(result, company_name, company_id)
                    analysis_id = check_signature
                    workspace.persist(pack, analysis_id)
                    pack["analysis_id"] = analysis_id
                    st.session_state["mine"] = pack
                    status.update(label="Your procurement review is ready", state="complete")
                st.session_state["_ws_next"] = "mine"
                st.session_state["_done"] = True
                st.rerun()
            except Exception as exc:
                st.error(f"We could not prepare your workspace: {exc}")

if st.session_state.get("_done"):
    st.success("Your review is ready. Open Overview in the navigation menu to view your procurement intelligence.")
