
"""Company-aware workspaces for Seepsight.

Customer workspaces contain only data uploaded or connected by
the authenticated company. Demonstration datasets are not loaded here.
"""

import json
import os
import tempfile

import pandas as pd
import streamlit as st

from seepsight import engine


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
# 3. AUTHENTICATED COMPANY ACCESS
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

    if not company_id:
        st.caption("Company workspace unavailable.")
        return

    mine = st.session_state.get("mine")

    if (
        isinstance(mine, dict)
        and mine.get("company_id") == company_id
    ):
        workspace_name = mine.get("name", company_name or "Your company")

        st.caption("ACTIVE COMPANY")
        st.write(workspace_name)

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

    if not isinstance(mine, dict):
        mine = None

    if mine is not None:
        if mine.get("company_id") != company_id:
            raise PermissionError(
                "This workspace does not belong to your company."
            )

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

    all_cases = st.session_state.setdefault("cases", {})

    return all_cases.setdefault(company_id, {})
