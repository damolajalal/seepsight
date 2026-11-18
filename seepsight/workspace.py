"""A workspace holds one company's results for the current visit. Nothing is saved to disk or shared between visitors."""
import json
import os
import tempfile

import pandas as pd
import streamlit as st

from seepsight import engine

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMOS = {"A": ("Demo company A · Nigeria (simulated)", "data/demo/company_a"),
         "B": ("Demo company B · Kenya (simulated)", "data/demo/company_b")}


def _read(folder, name):
    path = os.path.join(folder, name)
    return pd.read_csv(path) if os.path.exists(path) else None


def load_pack(folder, name, kind):
    with open(os.path.join(folder, "run_log.json")) as fh:
        log = json.load(fh)
    return dict(name=name, kind=kind, cur=log["currency"], log=log, findings=_read(folder, "findings.csv"),
                evidence=_read(folder, "evidence.csv"), exposure=_read(folder, "exposure_by_supplier.csv"),
                monthly=_read(folder, "monthly_trend.csv"), supplier_month=_read(folder, "supplier_month.csv"),
                risk=_read(folder, "risk_orders.csv"), explanations=_read(folder, "explanations.csv"),
                scorecard=_read(folder, "scorecard.csv"))


@st.cache_data(show_spinner=False)
def demo(key):
    label, rel = DEMOS[key]
    return load_pack(os.path.join(BASE, rel), label, "demo")


def from_result(result, company):
    """Turn an engine result into a workspace held only in this visitor's session."""
    with tempfile.TemporaryDirectory() as folder:
        engine.build_data_pack(result, company, "uploaded files", out_dir=folder, zip_it=False)
        return load_pack(folder, company, "upload")


def workspace_picker():
    if "_ws_next" in st.session_state:
        st.session_state["ws_key"] = st.session_state.pop("_ws_next")
    options = {k: v[0] for k, v in DEMOS.items()}
    if "mine" in st.session_state:
        options["mine"] = "Your company · " + st.session_state["mine"]["name"]
    if st.session_state.get("ws_key") not in options:
        st.session_state["ws_key"] = "A"
    st.selectbox("Workspace", list(options), format_func=options.get, key="ws_key")


def current():
    key = st.session_state.get("ws_key", "A")
    return st.session_state["mine"] if key == "mine" and "mine" in st.session_state else demo(key if key in DEMOS else "A")


def cases():
    key = st.session_state.get("ws_key", "A")
    return st.session_state.setdefault("cases", {}).setdefault(key, {})
