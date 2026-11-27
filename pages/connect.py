"""Seepsight company data onboarding.

The page supports the registered procurement dataset schemas exposed by the
engine. Dataset ingestion, mapping and relationship checks are distinct from
detector coverage: only the four established detector pipelines generate
procurement findings in this version.
"""

import hashlib
import logging
import os
import tempfile
import time
import uuid

import pandas as pd
import streamlit as st

from seepsight import connection_ui, engine, firestore_db, plain, ui, workspace
from seepsight.firestore_db import (
    save_company_dataset,
    save_company_mapping,
    save_dataset_records,
    save_original_file,
)


ui.page_header(
    "Connect your data",
    "Bring your company's procurement records into Seepsight. Preview the data, "
    "confirm its structure, map the registered procurement dataset types and review data quality before analysis.",
)

account = st.session_state.get("seepsight_auth", {})
account = account if isinstance(account, dict) else {}
company_id = account.get("company_id")
company_name = str(account.get("company_name") or "").strip()
if not company_id or not company_name:
    st.error("Your company identity could not be confirmed. Please sign in again before connecting data.")
    st.stop()

# Session-only demo mode avoids all dataset reads and writes to Firestore.
if "seepsight_demo_mode" not in st.session_state:
    st.session_state["seepsight_demo_mode"] = True
DEMO_MODE = st.toggle(
    "Temporary Demo Mode (session-only; no Firestore dataset access)",
    key="seepsight_demo_mode",
    help="Uploads, mappings, analysis, findings and cases remain in this session only.",
)
if DEMO_MODE:
    st.warning("DEMO MODE IS ON · Data is held in memory only. Keep this session open until your video is recorded; a refresh or restart may clear it.")
else:
    st.info("Persistent mode is active. Dataset storage uses your company's Firestore workspace.")

# Populated once below in the persistent-mode section. Keeping placeholders
# here avoids duplicate Firestore reads and duplicate connection UI rendering.
saved_groups = []
extendable_groups = []

CURRENCIES = ["NGN", "KES", "GHS", "ZAR", "USD", "EUR", "GBP", "TZS", "UGX", "INR"]
NOT_MAPPED = "— Not present in this file —"
MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_BATCH_BYTES = 100 * 1024 * 1024

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


def _read_bytes(filename, payload):
    suffix = os.path.splitext(filename)[1].lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(payload)
        path = tmp.name
    try:
        return engine.read_any(path)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _read_upload(upload):
    return _read_bytes(upload.name, upload.getvalue())


def _upload_size(upload):
    size = getattr(upload, "size", None)
    return int(size if size is not None else len(upload.getvalue()))


def _fingerprint(uploaded_files):
    """Identify the current Streamlit upload without re-hashing large files on every rerun."""
    digest = hashlib.sha256()
    for item in sorted(uploaded_files, key=lambda x: x.name.lower()):
        file_id = getattr(item, "file_id", None)
        digest.update(item.name.encode("utf-8", errors="replace"))
        digest.update(str(getattr(item, "size", 0)).encode("ascii"))
        digest.update(str(getattr(item, "type", "") or "").encode("utf-8"))
        if file_id:
            # Streamlit assigns a stable upload ID for the lifetime of this
            # uploaded object. This avoids reading up to 100 MB just to decide
            # whether the same upload needs to be parsed again after a rerun.
            digest.update(str(file_id).encode("utf-8"))
        else:
            # Compatibility fallback for upload objects without a file ID.
            digest.update(hashlib.sha256(item.getvalue()).digest())
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


def _derived_cache():
    """Keep pure upload-derived calculations for this Streamlit session."""
    cache = st.session_state.get("_connect_derived_cache")
    if not isinstance(cache, dict):
        cache = {}
        st.session_state["_connect_derived_cache"] = cache
    return cache


def _dataset_guess(df, filename):
    cache_key = (
        "dataset_guess",
        st.session_state.get("connect_upload_fingerprint"),
        filename,
        len(df),
        tuple(map(str, df.columns)),
    )
    cache = _derived_cache()
    if cache_key in cache:
        return cache[cache_key]

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
        result = ("orders", round(best_score, 3), ranked)
    elif not ranked:
        result = ("orders", 0.0, ranked)
    else:
        result = (ranked[0]["dataset"], ranked[0]["confidence"], ranked)

    cache[cache_key] = result
    return result


def _mapping_editor(df, fields, key_prefix, required_fields=None, saved_mapping=None):
    """Show ranked suggestions and let the user confirm or correct each field."""
    required_fields = set(required_fields if required_fields is not None else engine.REQUIRED)
    saved_mapping = saved_mapping if isinstance(saved_mapping, dict) else {}
    cache_key = (
        "mapping_suggestions",
        st.session_state.get("connect_upload_fingerprint"),
        key_prefix,
        tuple(fields),
        len(df),
        tuple(map(str, df.columns)),
    )
    cache = _derived_cache()
    cached = cache.get(cache_key)
    if cached is None:
        suggested, _, _ = engine.suggest_mapping(
            df,
            engine.DEFAULT_CONFIG["accept_score"],
            fields,
        )
        candidates = engine.mapping_candidates(df, fields=fields, top_n=4)
        cache[cache_key] = (suggested, candidates)
    else:
        suggested, candidates = cached
    overrides = {}
    selected = {}
    columns = list(df.columns)

    # Keep the first view compact: required fields and fields with an actual
    # suggested/saved match are shown. Unmapped optional fields remain available
    # on demand instead of creating dozens of empty dropdowns on every rerun.
    visible_fields = [
        field for field in fields
        if field in required_fields
        or field in saved_mapping
        or suggested.get(field)
    ]
    show_all_optional = st.checkbox(
        "Show all optional mapping fields",
        value=False,
        key=f"{key_prefix}_show_all_optional",
        help="Reveal optional fields that have no suggested source-column match.",
    )
    if show_all_optional:
        visible_fields = list(fields)

    for field in visible_fields:
        info = suggested.get(field)
        saved_choice = saved_mapping.get(field)
        if saved_choice in columns or saved_choice == NOT_MAPPED:
            default = saved_choice
        else:
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

if not DEMO_MODE:
    with st.expander("Firestore write/read/cleanup verification", expanded=False):
        if st.button("Run Firestore read/write/cleanup test", key="connect_firestore_full_test"):
            try:
                with st.spinner("Testing Firestore write, read and temporary-document cleanup..."):
                    diagnostic = firestore_db.test_firestore_connection(company_id)
                latency = diagnostic.get("latency_ms") if isinstance(diagnostic, dict) else None
                if latency is not None:
                    st.success(
                        f"Firestore write, read and cleanup test passed. "
                        f"End-to-end latency: {latency:,} ms. Temporary test document deleted."
                    )
                else:
                    st.success("Firestore write, read and cleanup test passed. The temporary test document was deleted.")
            except Exception as exc:
                support_id = uuid.uuid4().hex[:12].upper()
                logging.getLogger(__name__).exception(
                    "Firestore company-dataset diagnostic failed; support_id=%s",
                    support_id,
                )
                st.error(
                    "Firestore verification failed. "
                    f"{str(exc)} "
                    f"Support reference: {support_id}. "
                    "No credential values are displayed."
                )

    st.markdown("### Company workspace")
    st.write(f"**{company_name}**")
    st.caption("Your upload will be associated with the signed-in company account.")

    st.markdown("### Database connections")
    connection_ui.render_company_database_connections(company_id, account)

    st.markdown("### Saved procurement datasets")
    try:
        saved_groups = firestore_db.get_company_dataset_groups(company_id)
    except Exception:
        saved_groups = []
        st.warning("Saved datasets could not be loaded right now. Refresh the page and try again.")

    if saved_groups:
        for group in saved_groups:
            files_label = ", ".join(group.get("files", [])[:4])
            if len(group.get("files", [])) > 4:
                files_label += f" and {len(group['files']) - 4} more"
            st.write(f"**{group.get('company_name') or 'Procurement dataset'}**")
            st.caption(
                f"{group.get('file_count', 0)} file(s) · "
                f"{group.get('record_count', 0):,} normalized rows · "
                f"{group.get('source_record_count', 0):,} source rows"
            )
            if files_label:
                st.caption(files_label)
        if account.get("role") == "owner":
            safe_groups = [item for item in saved_groups if item.get("deletion_safe")]
            used_groups = [item for item in saved_groups if item.get("used")]
            pending_groups = [
                item for item in saved_groups if item.get("pending_workspace")
            ]
            protected_groups = [
                item for item in saved_groups
                if not item.get("deletion_safe")
                and not item.get("used")
                and not item.get("pending_workspace")
            ]
            with st.expander("Delete an unused dataset", expanded=False):
                if safe_groups:
                    group_options = {
                        item["dataset_group_id"]: (
                            f"{item.get('company_name') or 'Dataset'} · "
                            f"{item.get('file_count', 0)} file(s) · {item['dataset_group_id'][:8]}"
                        )
                        for item in safe_groups
                    }
                    delete_group_id = st.selectbox(
                        "Choose an unused dataset to delete",
                        list(group_options),
                        format_func=lambda value: group_options[value],
                        key="delete_dataset_group_choice",
                    )
                    st.warning(
                        "This permanently removes only the selected unused upload, including its "
                        "original files, source rows and normalized rows. Datasets with analysis "
                        "history are not eligible and will remain in your workspace history."
                    )
                    confirm_delete = st.checkbox(
                        "I understand this unused dataset will be permanently deleted.",
                        key="confirm_delete_dataset_group",
                    )
                    if st.button(
                        "Delete selected unused dataset",
                        type="secondary",
                        disabled=not confirm_delete,
                        key="delete_selected_dataset_group",
                    ):
                        try:
                            deleted = firestore_db.delete_company_dataset_group(company_id, delete_group_id)
                            if deleted:
                                mine = st.session_state.get("mine")
                                if isinstance(mine, dict) and mine.get("dataset_group_id") == delete_group_id:
                                    st.session_state.pop("mine", None)
                                st.session_state.pop("cases", None)
                                st.success("Unused dataset deleted. Existing analysis history was not changed.")
                                st.rerun()
                            else:
                                st.info("That dataset no longer exists.")
                        except PermissionError:
                            st.error("Only the company owner can delete a dataset.")
                        except Exception as exc:
                            st.error(f"Deletion was not completed: {exc}")
                else:
                    st.caption("There are no unused, fully linked datasets eligible for deletion.")
                if used_groups:
                    st.caption("Datasets retained in analysis history:")
                    for item in used_groups:
                        st.write(
                            f"• {item.get('company_name') or 'Dataset'} — "
                            f"{item.get('file_count', 0)} file(s), "
                            f"{int(item.get('analysis_count', 1) or 1)} saved analysis(es)"
                        )
                    st.info(
                        "These datasets have been analysed. Their saved analysis history, findings "
                        "and cases are protected from dataset deletion."
                    )
                if pending_groups:
                    st.caption("Datasets with an unfinished analysis save (protected):")
                    for item in pending_groups:
                        st.write(
                            f"• {item.get('company_name') or 'Dataset'} — "
                            f"{item.get('file_count', 0)} file(s), "
                            f"{item['dataset_group_id'][:8]}"
                        )
                    st.info(
                        "An unfinished analysis save contains recovery diagnostics. These datasets "
                        "cannot be deleted until the incomplete save has been diagnosed."
                    )
                if protected_groups:
                    st.caption("Protected legacy datasets (not selectable for deletion):")
                    for item in protected_groups:
                        st.write(
                            f"• {item.get('company_name') or 'Dataset'} — "
                            f"{item.get('file_count', 0)} file(s), "
                            f"{item['dataset_group_id'][:8]}"
                        )
                    st.info(
                        "These older records are missing complete dataset-to-analysis links. "
                        "They remain protected until their links can be verified."
                    )

    extendable_groups = [
        item for item in saved_groups
        if item.get("extendable") and item.get("file_items")
    ]

upload_modes = ["Create a separate dataset"]
if extendable_groups:
    upload_modes.append("Add complementary files to an existing dataset")
upload_mode = st.radio(
    "How should this upload be handled?",
    upload_modes,
    horizontal=True,
    key="connect_upload_mode",
    disabled=False,
    help="Create a clean separate dataset, or add complementary files only when an existing dataset's original files can all be restored and verified.",
)
target_group_id = None
if not DEMO_MODE and upload_mode == "Add complementary files to an existing dataset" and extendable_groups:
    group_labels = {
        item["dataset_group_id"]: (
            f"{item.get('company_name') or 'Dataset'} · "
            f"{item.get('file_count', 0)} file(s) · {item['dataset_group_id'][:8]}"
        )
        for item in extendable_groups
    }
    target_group_id = st.selectbox(
        "Choose the dataset to extend",
        list(group_labels),
        format_func=lambda value: group_labels[value],
        key="connect_extend_dataset_group",
    )
    st.info("Seepsight will reload the saved original files, add your new complementary file types, and rebuild one combined analysis. Existing files are retained.")
elif not DEMO_MODE and not extendable_groups:
    st.caption("Create a separate dataset for now. Existing datasets can be extended once every original file is linked and verified.")

st.divider()

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
    oversized = [
        item.name for item in uploaded
        if _upload_size(item) > MAX_UPLOAD_FILE_BYTES
    ]
    total_upload_bytes = sum(_upload_size(item) for item in uploaded)
    if oversized or total_upload_bytes > MAX_UPLOAD_BATCH_BYTES:
        if oversized:
            st.error(
                "Each uploaded file must be 50 MB or smaller: "
                + ", ".join(oversized)
            )
        if total_upload_bytes > MAX_UPLOAD_BATCH_BYTES:
            st.error("The combined upload size must be 100 MB or smaller.")
        st.stop()

    current_fingerprint = _fingerprint(uploaded)
    if st.session_state.get("connect_upload_fingerprint") != current_fingerprint:
        loaded = {}
        source_file_bytes = {}
        errors = []
        for item in uploaded:
            try:
                payload = item.getvalue()
                frame = _read_bytes(item.name, payload)
                if frame.empty or len(frame.columns) == 0:
                    errors.append(f"{item.name}: no usable rows or columns were found.")
                else:
                    loaded[item.name] = frame
                    source_file_bytes[item.name] = payload
            except Exception:
                errors.append(f"{item.name}: could not be read. Check the file format and try again.")
        st.session_state["connect_raw"] = loaded
        st.session_state["connect_source_file_bytes"] = source_file_bytes
        st.session_state["connect_upload_fingerprint"] = current_fingerprint
        # Any upload change invalidates all derived detection/mapping results.
        st.session_state.pop("_connect_derived_cache", None)
        st.session_state.pop("connect_check", None)
        st.session_state.pop("_done", None)
        st.session_state["connect_load_errors"] = errors

if st.button("Clear uploaded files and start again", key="clear_connect_uploads"):
    for key in ("connect_raw", "connect_source_file_bytes", "connect_upload_fingerprint", "connect_check", "connect_check_signature", "connect_dataset_types", "connect_load_errors", "connect_dataset_group_signature", "connect_dataset_group_id", "_connect_derived_cache"):
        st.session_state.pop(key, None)
    st.session_state.pop("_done", None)
    st.rerun()

for message in st.session_state.get("connect_load_errors", []):
    st.error(message)

if target_group_id and not st.session_state.get("connect_raw"):
    st.info("Upload at least one new complementary file before extending this saved dataset.")
    st.stop()

raw = dict(st.session_state.get("connect_raw", {}))
source_file_bytes = dict(st.session_state.get("connect_source_file_bytes", {}))
saved_file_kinds = {}
saved_file_mappings = {}

if target_group_id:
    selected_group = next(
        (item for item in extendable_groups if item.get("dataset_group_id") == target_group_id),
        None,
    )
    if not selected_group:
        st.error("The selected saved dataset is no longer available. Refresh and choose it again.")
        st.stop()

    # Original files and mappings are immutable for a saved dataset group.
    # Reuse their parsed session copy on Streamlit reruns instead of repeating
    # one Firestore file read, one mapping read and one file parse per item.
    file_items = selected_group.get("file_items", [])
    saved_group_cache_key = (
        str(company_id),
        str(target_group_id),
        tuple(sorted(str(item.get("dataset_id") or "") for item in file_items)),
    )
    saved_group_cache = st.session_state.setdefault("_connect_saved_group_cache", {})
    cached_group = saved_group_cache.get(saved_group_cache_key)
    cache_is_fresh = (
        isinstance(cached_group, dict)
        and time.monotonic() - float(cached_group.get("fetched_at", 0)) < 300
    )

    try:
        if cache_is_fresh:
            restored = cached_group["restored"]
        else:
            restored = {
                "raw": {},
                "source_file_bytes": {},
                "saved_file_kinds": {},
                "saved_file_mappings": {},
            }
            for file_item in file_items:
                dataset_id = file_item["dataset_id"]
                saved = firestore_db.get_original_file(company_id, dataset_id)
                filename = saved.get("filename") or file_item.get("filename")
                restored["raw"][filename] = _read_bytes(filename, saved["data"])
                restored["source_file_bytes"][filename] = saved["data"]
                restored["saved_file_kinds"][filename] = file_item.get("dataset_type")
                saved_mapping = firestore_db.get_company_mapping(company_id, dataset_id) or {}
                restored["saved_file_mappings"][filename] = saved_mapping.get("mapping", saved_mapping)
            saved_group_cache[saved_group_cache_key] = {
                "fetched_at": time.monotonic(),
                "restored": restored,
            }

        conflicts = sorted(set(restored["raw"]).intersection(raw))
        if conflicts:
            st.error(
                "A new upload conflicts with a file already in the selected dataset: "
                + ", ".join(repr(name) for name in conflicts)
                + ". Rename the new file and retry."
            )
            st.stop()
        raw.update(restored["raw"])
        source_file_bytes.update(restored["source_file_bytes"])
        saved_file_kinds.update(restored["saved_file_kinds"])
        saved_file_mappings.update(restored["saved_file_mappings"])
    except Exception:
        st.error("The saved dataset's original files could not all be restored and verified. No combined analysis was started.")
        st.stop()

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
        saved_kind = saved_file_kinds.get(filename)
        if saved_kind in DATASET_LABELS:
            chosen_label = st.selectbox(
                "Saved procurement information type",
                labels,
                index=labels.index(DATASET_LABELS[saved_kind]),
                key=f"dataset_type_{target_group_id or 'new'}_{hashlib.sha1(filename.encode()).hexdigest()[:10]}",
                disabled=True,
            )
        else:
            chosen_label = st.selectbox(
                "What kind of procurement information is this?",
                labels,
                index=labels.index(guessed_label),
                key=f"dataset_type_{hashlib.sha1(filename.encode()).hexdigest()[:10]}",
            )
        kinds[filename] = saved_kind if saved_kind in DATASET_LABELS else LABEL_TO_DATASET[chosen_label]
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

# Multiple files of the same type are mapped individually and merged under
# explicit engine rules before the combined analysis is run.

if "orders" not in core_files.values():
    st.error("A Purchase orders dataset is required. Add the purchase-order file before validating other procurement datasets.")
    st.stop()

st.markdown("### Step 3. Confirm column mappings")
if any(list(core_files.values()).count(kind) > 1 for kind in set(core_files.values())):
    st.info(
        "Files of the same procurement type can be combined. Map each file separately. "
        "Exact duplicate rows are removed; conflicting purchase-order rows with the same PO number "
        "are blocked for review instead of choosing one version automatically."
    )
multiple_tables = len(core_files) > 1
single_file = len(raw) == 1 and len(core_files) == 1 and next(iter(core_files.values())) == "orders"
mapping_overrides = {}
selected_mappings = {}
file_mapping_overrides = {}

if single_file:
    filename = next(iter(core_files))
    frame = raw[filename]
    fields = engine.FLAT_FIELDS
    with st.expander(f"Map columns in {filename}", expanded=True):
        one_overrides, one_selected = _mapping_editor(
            frame, fields, f"connect_single_map_{target_group_id or 'new'}", engine.REQUIRED,
            saved_file_mappings.get(filename),
        )
    mapping_overrides = one_overrides
    selected_mappings["orders"] = one_selected
else:
    for filename, kind in core_files.items():
        frame = raw[filename]
        fields = engine.TABLE_FIELDS[kind]
        with st.expander(f"{CORE_DATASETS[kind]} · {filename}", expanded=(kind == "orders")):
            required_fields = engine.REQUIRED if kind == "orders" else engine.DATASET_REGISTRY[kind].get("required", [])
            overrides, selected = _mapping_editor(
                frame, fields, f"map_{kind}_{target_group_id or 'new'}_{hashlib.sha1(filename.encode()).hexdigest()[:8]}", required_fields,
                saved_file_mappings.get(filename),
            )
        file_mapping_overrides[filename] = overrides
        selected_mappings[filename] = selected

# Build a deterministic signature from every input that can change the result.
# This prevents a previous check from being processed after edits to data,
# dataset classification, company, currency or mapping selections.
signature_payload = {
    "fingerprint": st.session_state.get("connect_upload_fingerprint"),
    "company_id": str(company_id),
    "company_name": company_name,
    "target_group_id": target_group_id,
    "currency": currency,
    "kinds": sorted(kinds.items()),
    "mappings": selected_mappings,
}
check_signature = hashlib.sha256(repr(signature_payload).encode("utf-8")).hexdigest()
if st.session_state.get("connect_check_signature") != check_signature:
    st.session_state.pop("connect_check", None)
    st.session_state.pop("_done", None)

# Keep one stable dataset identity for this exact upload + mapping configuration.
# Generating a fresh UUID on every Streamlit rerun invalidates the workspace and
# can repeatedly rebuild the same analysis.
previous_signature = st.session_state.get("connect_dataset_group_signature")
previous_group_id = st.session_state.get("connect_dataset_group_id")
if target_group_id:
    dataset_group_id = target_group_id
elif previous_signature == check_signature and previous_group_id:
    dataset_group_id = previous_group_id
else:
    dataset_group_id = uuid.uuid4().hex
st.session_state["connect_dataset_group_signature"] = check_signature
st.session_state["connect_dataset_group_id"] = dataset_group_id

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
                mapped_files = {}
                grouped_frames = {}
                for filename, kind in core_files.items():
                    choices = selected_mappings.get(filename, {})
                    file_map = {
                        field: {"column": column}
                        for field, column in choices.items()
                        if column != NOT_MAPPED and column in raw[filename].columns
                    }
                    mapped = engine.apply_mapping(raw[filename], file_map)
                    mapped_files[filename] = mapped
                    grouped_frames.setdefault(kind, []).append(mapped)

                tables = {}
                table_overrides = {}
                merge_report = {}
                for kind, frames in grouped_frames.items():
                    combined, details = engine.combine_dataset_frames(kind, frames)
                    tables[kind] = combined
                    table_overrides[kind] = {
                        field: field for field in combined.columns
                    }
                    merge_report[kind] = details

                result = engine.onboard_tables(
                    tables,
                    overrides=table_overrides,
                    config=config,
                    verbose=False,
                )
                result["dataset_merge"] = merge_report
                st.session_state["connect_file_normalized_tables"] = mapped_files
            if single_file:
                filename = next(iter(core_files))
                st.session_state["connect_file_normalized_tables"] = {
                    filename: result.get("normalized_tables", {}).get("orders", raw[filename])
                }
        st.session_state["connect_check"] = result
        st.session_state["connect_check_signature"] = check_signature
        st.session_state.pop("_done", None)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    except Exception:
        st.error("We could not validate these records. Check the file structure and mappings, then try again.")
        st.stop()

result = st.session_state.get("connect_check")
if result and st.session_state.get("connect_check_signature") == check_signature:
    quality = result.get("quality", {})
    merge_report = result.get("dataset_merge", {})
    if merge_report:
        with st.expander("Review multi-file merge results"):
            for dataset_name, details in merge_report.items():
                st.write(f"**{DATASET_LABELS.get(dataset_name, dataset_name)}**")
                st.caption(
                    f"{details.get('files_combined', 0)} files · "
                    f"{details.get('rows_before_deduplication', 0):,} input rows · "
                    f"{details.get('exact_duplicate_rows_removed', 0):,} exact duplicate rows removed · "
                    f"{details.get('duplicate_order_ids_removed', 0):,} equivalent PO IDs consolidated · "
                    f"{details.get('rows_after_deduplication', 0):,} rows retained"
                )
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
                    "Unmatched keys": details.get("orphan_keys", max(details.get("source_keys", 0) - details.get("matched_keys", 0), 0)),
                    "Source keys": details.get("source_keys", 0),
                    "Coverage": f"{details.get('coverage', 0):.0%}",
                })
            st.dataframe(pd.DataFrame(relationship_rows), hide_index=True, width="stretch")
        else:
            st.caption("No cross-dataset key relationships could be assessed from the mapped fields supplied.")

        st.markdown("**Detector coverage**")
        st.caption("All uploaded dataset types are ingested and quality-checked where mapped. Findings are currently generated by the four established detector families listed below.")

        st.markdown("### Step 6. Open your company workspace")
        st.caption("Your results will stay in this session." if DEMO_MODE else "Your results will be attached to the signed-in company identity shown at the top of this page.")
        if DEMO_MODE and not (
            st.session_state.get("_done")
            and isinstance(st.session_state.get("mine"), dict)
            and st.session_state["mine"].get("session_only")
            and st.session_state["mine"].get("dataset_group_id") == dataset_group_id
        ):
            try:
                with st.spinner("Building your session-only procurement intelligence..."):
                    normalized_tables = st.session_state.get("connect_file_normalized_tables", {})
                    for source_filename, source_frame in raw.items():
                        normalized_frame = normalized_tables.get(source_filename)
                        if not isinstance(source_frame, pd.DataFrame) or not isinstance(normalized_frame, pd.DataFrame):
                            raise RuntimeError(f"Validated data for {source_filename} is missing. Run validation again.")
                    pack = workspace.from_result(result, company_name, company_id)
                    pack["dataset_group_id"] = dataset_group_id
                    pack["analysis_id"] = dataset_group_id
                    pack["session_only"] = True
                    pack["source_files"] = list(raw.keys())
                    pack["source_rows"] = {name: int(len(frame)) for name, frame in raw.items()}
                    pack["normalized_rows"] = {name: int(len(normalized_tables[name])) for name in raw}
                    st.session_state["mine"] = pack
                    st.session_state["seepsight_demo_workspace"] = pack
                    st.session_state["cases"] = {}
                    st.session_state["_done"] = True
                st.success("Session-only procurement workspace is ready.")
                st.rerun()
            except Exception as exc:
                logging.exception("Session-only demo workspace build failed")
                st.error(f"Could not prepare the demo workspace: {type(exc).__name__}: {exc}")
        elif not DEMO_MODE:
                try:
                    status_message = "Saving original files and preparing your company workspace..."
                    stage = "Starting company workspace persistence"
                    stage_started_at = time.perf_counter()
                    support_id = uuid.uuid4().hex[:12].upper()
                    saved_upload_ids = []
                    upload_started_at = time.perf_counter()
                    stage_started_at = upload_started_at
                    with st.status(status_message, expanded=True) as status:
                        for source_filename, source_frame in raw.items():
                            source_bytes = source_file_bytes[source_filename]
                            source_sha256 = hashlib.sha256(source_bytes).hexdigest()
                            upload_id = hashlib.sha256(
                                (dataset_group_id + ":" + source_filename + ":" + source_sha256).encode("utf-8")
                            ).hexdigest()[:32]
                            dataset_kind = kinds[source_filename]
                            dataset_metadata = {
                                "dataset_type": dataset_kind,
                                "filename": source_filename,
                                "status": "saving",
                                "record_count": int(len(source_frame)),
                                "source_sha256": source_sha256,
                                "dataset_group_id": dataset_group_id,
                                "company_name": company_name,
                            }
                            normalized_tables = st.session_state.get("connect_file_normalized_tables", {})
                            normalized_frame = normalized_tables.get(source_filename)
                            source_frame = raw[source_filename]
                            if not isinstance(normalized_frame, pd.DataFrame) or not isinstance(source_frame, pd.DataFrame):
                                raise RuntimeError(
                                    f"Validated source and normalized records for {DATASET_LABELS.get(dataset_kind, dataset_kind)} "
                                    "were not returned by the ingestion engine."
                                )
                            dataset_metadata["source_record_count"] = int(len(source_frame))
                            dataset_metadata["normalized_record_count"] = int(len(normalized_frame))
                            dataset_metadata["schema_version"] = "1"
                            stage = "Saving dataset metadata"
                            stage_started_at = time.perf_counter()
                            status.write("Saving dataset metadata")
                            save_company_dataset(company_id, upload_id, dataset_metadata)
                            stage = "Saving original file chunks"
                            stage_started_at = time.perf_counter()
                            status.write("Saving original file")
                            save_original_file(company_id, upload_id, source_filename, source_bytes)
                            stage = "Saving confirmed column mapping"
                            stage_started_at = time.perf_counter()
                            save_company_mapping(company_id, upload_id, selected_mappings.get(source_filename, selected_mappings.get(dataset_kind, {})))
                            source_records = source_frame.astype(object).where(
                                pd.notna(source_frame), None
                            ).to_dict("records")
                            # Preserve Excel numeric source cells as their displayed
                            # string representation; CSV and JSON retain their source
                            # text/Decimal representation from engine.read_any().
                            for source_record in source_records:
                                for field, value in list(source_record.items()):
                                    if isinstance(value, float):
                                        source_record[field] = str(value)
                            stage = "Saving original source rows in compact chunks"
                            stage_started_at = time.perf_counter()
                            status.write(f"Saving {len(source_records):,} original source rows")
                            save_dataset_records(
                                company_id, upload_id, source_records,
                                collection_name="source_records",
                            )
                            saved_records = normalized_frame.astype(object).where(
                                pd.notna(normalized_frame), None
                            ).to_dict("records")
                            stage = "Saving normalized procurement rows in compact chunks"
                            stage_started_at = time.perf_counter()
                            status.write(f"Saving {len(saved_records):,} normalized rows")
                            save_dataset_records(company_id, upload_id, saved_records)
                            saved_upload_ids.append(upload_id)
                        st.write(f"Saved {len(saved_upload_ids)} original file(s), source rows and normalized records to the company's Firestore workspace.")
                        stage = "Building findings and supporting evidence"
                        stage_started_at = time.perf_counter()
                        status.write("Preparing findings and supporting evidence")
                        pack = workspace.from_result(result, company_name, company_id)
                        analysis_id = dataset_group_id
                        pack["dataset_group_id"] = dataset_group_id
                        stage = "Saving the analysis workspace"
                        stage_started_at = time.perf_counter()
                        status.write("Saving analysis workspace")
                        workspace.persist(pack, analysis_id)
                        pack["analysis_id"] = analysis_id
                        st.session_state["mine"] = pack
                        status.update(label="Your procurement review is ready", state="complete")
                    st.session_state["_ws_next"] = "mine"
                    st.session_state["_done"] = True
                    st.rerun()
                except Exception as exc:
                    logging.exception(
                        "Company workspace persistence failed at stage=%s support_id=%s "
                        "stage_duration_seconds=%.2f total_duration_seconds=%.2f",
                        stage,
                        support_id,
                        time.perf_counter() - stage_started_at,
                        time.perf_counter() - upload_started_at,
                    )
                    st.error(
                        "Company workspace setup did not finish. "
                        f"Failed stage: {stage}. "
                        f"Error type: {type(exc).__name__}. "
                        f"Support reference: {support_id}."
                    )
                    if saved_upload_ids:
                        st.warning(
                            f"{len(saved_upload_ids)} file(s) reached the saved-record stage before this failure. "
                            "The incomplete workspace has not been activated. Do not delete the saved dataset; "
                            "share the support reference so the failure can be diagnosed safely."
                        )
                    else:
                        st.caption("No complete file upload was confirmed before the failure. Your original upload remains available in this session.")

if st.session_state.get("_done"):
    st.success("Your review is ready. Open Overview in the navigation menu to view your procurement intelligence.")
