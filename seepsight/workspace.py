
"""Company-aware workspaces for Seepsight."""

import json
import os
import tempfile

import pandas as pd
import streamlit as st

from seepsight import engine

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEMOS = {
    "A": (
        "Demo company A · Nigeria (simulated)",
        "data/demo/company_a",
    ),
    "B": (
        "Demo company B · Kenya (simulated)",
        "data/demo/company_b",
    ),
}


def _read(folder, name):
    path = os.path.join(folder, name)
    return pd.read_csv(path) if os.path.exists(path) else None


def load_pack(folder, name, kind):
    """Load an existing Seepsight analysis data pack."""

    with open(
        os.path.join(folder, "run_log.json"),
        encoding="utf-8",
    ) as fh:
        log = json.load(fh)

    return {
        "name": name,
        "kind": kind,
        "cur": log["currency"],
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


@st.cache_data(show_spinner=False)
def demo(key):
    """Load a simulated demonstration workspace."""

    if key not in DEMOS:
        raise ValueError("Unknown demonstration workspace.")

    label, rel = DEMOS[key]

    return load_pack(
        os.path.join(BASE, rel),
        label,
        "demo",
    )


def from_result(result, company, company_id):
    """
    Build an analysis workspace associated with an authenticated company.

    Analysis files are temporary. The resulting DataFrames remain available
    in the current Streamlit session only.
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
            "uploaded files",
            out_dir=folder,
            zip_it=False,
        )

        pack = load_pack(
            folder,
            company,
            "upload",
        )

    pack["company_id"] = company_id

    return pack


def workspace_picker():
    """
    Display available workspaces.

    Real company uploads are associated with the authenticated company.
    Demonstration workspaces remain separate.
    """

    if "_ws_next" in st.session_state:
        st.session_state["ws_key"] = st.session_state.pop("_ws_next")

    options = {
        key: value[0]
        for key, value in DEMOS.items()
    }

    account = st.session_state.get("seepsight_auth", {})
    company_id = account.get("company_id")

    mine = st.session_state.get("mine")

    if (
        mine
        and company_id
        and mine.get("company_id") == company_id
    ):
        options["mine"] = "Your company · " + mine["name"]

    if st.session_state.get("ws_key") not in options:
        st.session_state["ws_key"] = (
            "mine" if "mine" in options else "A"
        )

    st.selectbox(
        "Workspace",
        list(options),
        format_func=options.get,
        key="ws_key",
    )


def current():
    """Return the active workspace."""

    account = st.session_state.get("seepsight_auth", {})
    company_id = account.get("company_id")

    key = st.session_state.get("ws_key", "A")
    mine = st.session_state.get("mine")

    # A real company workspace must belong to the signed-in company.
    if key == "mine":
        if not company_id:
            raise PermissionError(
                "Please sign in to access your company workspace."
            )

        if not mine or mine.get("company_id") != company_id:
            raise PermissionError(
                "This workspace does not belong to your company."
            )

        return mine

    # Keep the demonstration datasets separate.
    if key in DEMOS:
        return demo(key)

    # Do not silently substitute another company's data.
    raise PermissionError("The requested workspace is unavailable.")


def cases():
    """Return the current session's cases for the active workspace."""

    account = st.session_state.get("seepsight_auth", {})
    company_id = account.get("company_id")

    key = st.session_state.get("ws_key", "A")

    if key == "mine":
        if not company_id:
            raise PermissionError(
                "A company login is required to access these cases."
            )

        mine = st.session_state.get("mine")

        if not mine or mine.get("company_id") != company_id:
            raise PermissionError(
                "This workspace does not belong to your company."
            )

        key = company_id

    return st.session_state.setdefault(
        "cases", {}
    ).setdefault(key, {})
