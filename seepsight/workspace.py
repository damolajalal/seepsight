
"""Company-aware workspaces for Seepsight.

Customer workspaces contain only data uploaded or connected by
the authenticated company. Demonstration datasets are not loaded here.
"""

import json
import os
import tempfile

import pandas as pd
import streamlit as st

from seepsight import case_store, engine, firestore_db


# =========================================================
# 1. ANALYSIS DATA LOADING
# =========================================================

def _read(folder, name):
    """Read an analysis CSV when it exists."""

    path = os.path.join(folder, name)

    if not os.path.exists(path):
        return None

    return pd.read_csv(path)


def load_pack(folder, name, kind):
    """Load a Seepsight analysis data pack."""

    with open(
        os.path.join(folder, "run_log.json"),
        encoding="utf-8",
    ) as fh:
        log = json.load(fh)

    return {
        "name": name,
        "kind": kind,
        "cur": log.get("currency", "NGN"),
        "log": log,
        "findings": _read(folder, "findings.csv"),
        "evidence": _read(folder, "evidence.csv"),
        "exposure": _read(folder, "exposure_by_supplier.csv"),
        "monthly": _read(folder, "monthly_trend.csv"),
        "supplier_month": _read(folder, "supplier_month.csv"),
        "risk": _read(folder, "risk_orders.csv"),
        "explanations": _read(folder, "explanations.csv"),
        "scorecard": _read(folder, "scorecard.csv"),
    }


# =========================================================
# 2. BUILD A COMPANY WORKSPACE
# =========================================================

def from_result(result, company, company_id):
    """
    Build an analysis workspace for the authenticated company.

    Generated analysis files are temporary. DataFrames are loaded
    into the current Streamlit session.
    """

    if not isinstance(company_id, str) or not company_id.strip():
        raise ValueError(
            "Your authenticated company ID is missing. "
            "Please sign in again."
        )

    company_id = company_id.strip()
    company = (company or "").strip()

    if not company:
        raise ValueError("Please provide a company name.")

    with tempfile.TemporaryDirectory() as folder:

        engine.build_data_pack(
            result,
            company,
            "connected company data",
            out_dir=folder,
            zip_it=False,
        )

        pack = load_pack(
            folder,
            company,
            "company",
        )

    pack["company_id"] = company_id

    return pack




# =========================================================
# 3. DURABLE WORKSPACE RESTORATION
# =========================================================

def persist(pack, analysis_id):
    """Persist normally, or retain the pack in session-only demo mode."""
    if st.session_state.get("seepsight_demo_mode"):
        st.session_state["mine"] = pack
        st.session_state["seepsight_demo_workspace"] = pack
        return True
    if not isinstance(pack, dict):
        raise TypeError("A valid company workspace is required.")
    company_id = pack.get("company_id")
    table_names = ("findings", "evidence", "exposure", "monthly", "supplier_month", "risk", "explanations", "scorecard")
    tables = {}
    for name in table_names:
        frame = pack.get(name)
        if frame is None:
            tables[name] = []
        elif isinstance(frame, pd.DataFrame):
            tables[name] = frame.astype(object).where(pd.notna(frame), None).to_dict("records")
        else:
            raise TypeError(f"Workspace table '{name}' is not a DataFrame.")
    summary = {"company_name": pack.get("name", ""), "currency": pack.get("cur", "NGN"), "run_log": pack.get("log", {}), "kind": pack.get("kind", "company")}
    dataset_group_id = pack.get("dataset_group_id")
    return firestore_db.save_analysis_workspace(company_id, analysis_id, summary, tables, dataset_group_id=dataset_group_id)


def restore_latest(company_id, analysis_id=None):
    """Rebuild a dashboard workspace from the authenticated company's latest run."""
    saved = firestore_db.get_latest_analysis_workspace(company_id, analysis_id=analysis_id)
    if not saved:
        return None
    summary, tables = saved["summary"], saved["tables"]
    pack = {"name": summary.get("company_name", "Your company"), "kind": summary.get("kind", "company"), "cur": summary.get("currency", "NGN"), "log": summary.get("run_log", {}), "company_id": company_id, "analysis_id": saved["analysis_id"], "dataset_group_id": summary.get("dataset_group_id")}
    for name in ("findings", "evidence", "exposure", "monthly", "supplier_month", "risk", "explanations", "scorecard"):
        pack[name] = pd.DataFrame(tables.get(name, []))
    return pack

# =========================================================
# 4. AUTHENTICATED COMPANY ACCESS
# =========================================================

def _authenticated_company():
    """Return the authenticated company identity."""

    account = st.session_state.get("seepsight_auth", {})

    if not isinstance(account, dict):
        return None, None

    company_id = account.get("company_id")
    company_name = account.get("company_name")

    if not company_id:
        return None, company_name

    return str(company_id).strip(), company_name


def has_company_data():
    """Check whether this company has an active analysis workspace."""

    company_id, _ = _authenticated_company()
    mine = st.session_state.get("mine")

    if st.session_state.get("seepsight_demo_mode"):
        return bool(isinstance(mine, dict) and mine.get("session_only"))

    if company_id and not isinstance(mine, dict):
        mine = restore_latest(company_id)
        if mine is not None:
            st.session_state["mine"] = mine

    return bool(
        company_id
        and isinstance(mine, dict)
        and mine.get("company_id") == company_id
    )


# =========================================================
# 4. CUSTOMER WORKSPACE DISPLAY
# =========================================================

def workspace_picker():
    """
    Display the authenticated company's workspace identity.

    There is no customer-facing demo selector.
    """

    company_id, company_name = _authenticated_company()

    if st.session_state.get("seepsight_demo_mode"):
        mine = st.session_state.get("mine")
        st.caption("TEMPORARY DEMO · SESSION ONLY")
        if isinstance(mine, dict):
            st.write(mine.get("name", company_name or "Your company"))
            st.caption("This analysis is held in memory and is not saved to Firestore.")
        else:
            st.caption("Upload and validate data to start the demo.")
        return

    if not company_id:
        st.caption("Company workspace unavailable.")
        return

    mine = st.session_state.get("mine")
    try:
        saved_workspaces = firestore_db.get_company_analysis_workspaces(company_id)
    except Exception:
        saved_workspaces = []

    if saved_workspaces:
        labels = {}
        for item in saved_workspaces:
            updated = item.get("updated_at")
            stamp = updated.strftime("%Y-%m-%d %H:%M") if hasattr(updated, "strftime") else item["analysis_id"][:8]
            labels[item["analysis_id"]] = f'{item.get("company_name") or company_name or "Dataset"} · {stamp}'
        ids = [item["analysis_id"] for item in saved_workspaces]
        active_id = mine.get("analysis_id") if isinstance(mine, dict) and mine.get("company_id") == company_id else None
        selected_default = active_id if active_id in ids else ids[0]
        selected = st.selectbox(
            "Active dataset",
            ids,
            index=ids.index(selected_default),
            format_func=lambda value: labels.get(value, value),
            key=f"company_dataset_selector_{company_id}_{selected_default}",
        )
        if selected != active_id:
            # A reviewed or pending Gemini request is tied to the dataset that
            # produced its evidence. Never carry it across an active-dataset switch.
            for key in list(st.session_state.keys()):
                if not isinstance(key, str):
                    continue
                if key.startswith((
                    f"ask_hybrid_pending_{company_id}",
                    f"ask_hybrid_review_{company_id}",
                    f"ask_hybrid_response_{company_id}",
                )):
                    st.session_state.pop(key, None)
            restored = restore_latest(company_id, selected)
            if restored is not None:
                st.session_state["mine"] = restored
                st.session_state.pop("cases", None)
                st.rerun()
        st.caption("Switching changes the active procurement analysis for this company.")
    elif isinstance(mine, dict) and mine.get("company_id") == company_id:
        st.caption("ACTIVE COMPANY")
        st.write(mine.get("name", company_name or "Your company"))
    else:
        st.caption("COMPANY WORKSPACE")
        st.write(company_name or "Your company")
        st.caption("No procurement data connected yet.")


# =========================================================
# 5. GET THE CURRENT COMPANY WORKSPACE
# =========================================================

def current(allow_empty=False):
    """
    Return the active company's analysis workspace.

    If no data has been connected:
    - allow_empty=True returns None.
    - allow_empty=False shows a friendly connection message
      and stops the current page.

    A workspace belonging to another company is never returned.
    """

    company_id, _ = _authenticated_company()

    if not company_id:
        raise PermissionError(
            "Please sign in to access your company workspace."
        )

    mine = st.session_state.get("mine")

    if st.session_state.get("seepsight_demo_mode"):
        if isinstance(mine, dict) and mine.get("session_only") and mine.get("company_id") == company_id:
            return mine
        if allow_empty:
            return None
        st.info("No session-only analysis is loaded. Connect your data to begin.")
        st.page_link("pages/connect.py", label="Connect your data", icon=":material/upload_file:")
        st.stop()

    if not isinstance(mine, dict):
        mine = None

    if mine is not None:
        if mine.get("company_id") != company_id:
            raise PermissionError(
                "This workspace does not belong to your company."
            )

    if mine is None:
        # Restore only the latest workspace belonging to this authenticated company.
        mine = restore_latest(company_id)
        if mine is not None:
            st.session_state["mine"] = mine

    if mine is None:
        if allow_empty:
            return None

        st.info(
            "Your procurement workspace is ready. "
            "Connect your company's data to start analysing "
            "purchasing activity, identifying risks and "
            "monitoring supplier performance."
        )

        st.page_link(
            "pages/connect.py",
            label="Connect your data",
            icon=":material/upload_file:",
        )

        st.stop()

    # Never use a simulated or fallback workspace.
    return mine


# =========================================================
# 6. COMPANY-SPECIFIC CASES
# =========================================================

def cases():
    """Return cases belonging only to the authenticated company."""

    company_id, _ = _authenticated_company()

    if not company_id:
        raise PermissionError(
            "A company login is required to access these cases."
        )

    mine = current()
    dataset_group_id = mine.get("dataset_group_id") or mine.get("analysis_id")
    cache_key = f"{company_id}:{dataset_group_id}"
    all_cases = st.session_state.setdefault("cases", {})

    if cache_key not in all_cases:
        if st.session_state.get("seepsight_demo_mode"):
            all_cases[cache_key] = {}
        else:
            all_cases[cache_key] = case_store.get_company_cases(company_id, dataset_group_id=dataset_group_id)

    return all_cases[cache_key]


def save_case(finding_id, case):
    """Persist a case update for the authenticated company."""
    company_id, _ = _authenticated_company()
    if not company_id:
        raise PermissionError(
            "A company login is required to update cases."
        )
    mine = current()
    dataset_group_id = mine.get("dataset_group_id") or mine.get("analysis_id")
    if st.session_state.get("seepsight_demo_mode"):
        st.session_state.setdefault("cases", {}).setdefault(cache_key, {})[finding_id] = case
        return True
    case_store.save_company_case(company_id, finding_id, case, dataset_group_id=dataset_group_id)
    cache_key = f"{company_id}:{dataset_group_id}"
    st.session_state.setdefault("cases", {}).setdefault(
        cache_key, {}
    )[finding_id] = case
    return True
