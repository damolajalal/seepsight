import os
import tempfile

import pandas as pd
import streamlit as st

from seepsight import engine, plain, ui, workspace

ui.page_header("Connect your data", "Bring your company's purchasing records into Seepsight so we can review them and identify issues that may need your attention.")
st.warning("Please use only sample or simulated records in this early version. Your files are used for this visit only and are not saved, "
           "but company logins and private storage are not built yet.")

ONE, ORDERS, GRN, INV, APP = ("One file with a row for each order (simplest)", "Orders", "Deliveries received", "Invoices", "Approvals")
KEY = {ORDERS: "orders", GRN: "receipts", INV: "invoices", APP: "approvals"}
BASE = workspace.BASE
CURRENCIES = ["NGN", "KES", "GHS", "ZAR", "USD", "EUR", "GBP"]


def read_upload(f):
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(f.name)[1]) as t:
        t.write(f.getvalue())
        path = t.name
    try:
        return engine.read_any(path)
    finally:
        os.unlink(path)


def template():
    names = [plain.FIELD_LABELS[k] for k in engine.FLAT_FIELDS]
    row = ["PO-0001", "Example Supplies Ltd", "2026-01-15", 100, 250.00, "Main branch", "Operations", "Cartons", "2026-01-25", "2026-01-24",
           95, 100, 250.00, "2026-01-30", "2026-01-15 09:00", "2026-01-16 14:00"]
    return pd.DataFrame([row], columns=names).to_csv(index=False)


st.markdown("### Step 1. Choose your files")
a, b = st.columns(2)
company = a.text_input("Company name", "My company")
cur = b.selectbox("Currency used in your files", CURRENCIES)
files = st.file_uploader("Upload Excel or CSV files. You can choose several at once.", type=["csv", "tsv", "xlsx", "xls"], accept_multiple_files=True)
c1, c2, c3 = st.columns(3)
if c1.button("Try a sample (one file)"):
    st.session_state["raw"] = {"sample_company_one_file.xlsx": engine.read_any(os.path.join(BASE, "data/samples/sample_company_one_file.xlsx"))}
    st.session_state.pop("check", None)
if c2.button("Try a sample (four files)"):
    d = os.path.join(BASE, "data/samples/four_files")
    st.session_state["raw"] = {n: engine.read_any(os.path.join(d, n)) for n in sorted(os.listdir(d))}
    st.session_state.pop("check", None)
c3.download_button("Download a blank template", template(), file_name="seepsight_template.csv", mime="text/csv")
st.caption("Sample currencies: the one-file sample uses KES, the four-file sample uses NGN.")
if files:
    sig = tuple((f.name, f.size) for f in files)
    if st.session_state.get("_sig") != sig:
        st.session_state["raw"] = {f.name: read_upload(f) for f in files}
        st.session_state["_sig"] = sig
        st.session_state.pop("check", None)
raw = st.session_state.get("raw")
if not raw:
    st.info("Choose your files, or try one of the samples, to continue.")
    st.stop()

st.markdown("### Step 2. Tell us what each file contains")
kinds = {}
for i, (name, df) in enumerate(raw.items()):
    low = name.lower()
    guess = 0 if len(raw) == 1 else 2 if any(k in low for k in ("grn", "receiv", "deliver")) else 3 if "inv" in low else 4 if "approv" in low else 1
    kinds[name] = st.selectbox(f"{name}  ({len(df):,} rows)", [ONE, ORDERS, GRN, INV, APP], index=guess, key=f"kind_{name}")

st.markdown("### Step 3. Check how we matched your columns")
single = len(raw) == 1 and next(iter(kinds.values())) == ONE
overrides, tables = {}, {}
if single:
    df = next(iter(raw.values()))
    auto, _, _ = engine.suggest_mapping(df, engine.DEFAULT_CONFIG["accept_score"], engine.FLAT_FIELDS)
    options = ["(not in my file)"] + list(df.columns)
    sig = abs(hash(tuple(df.columns)))
    left, right = st.columns(2)
    for i, fld in enumerate(engine.FLAT_FIELDS):
        default = auto[fld]["column"] if fld in auto else "(not in my file)"
        label = plain.FIELD_LABELS[fld] + (" (needed)" if fld in plain.REQUIRED else "")
        choice = (left if i % 2 == 0 else right).selectbox(label, options, index=options.index(default), key=f"m_{fld}_{sig}")
        if fld in auto and auto[fld]["confidence"] < 0.8:
            (left if i % 2 == 0 else right).caption("Please check this match.")
        if choice != default:
            overrides[fld] = None if choice == "(not in my file)" else choice
    st.caption("Fields marked “needed” must be matched. Other fields are optional, but each one lets us run more checks.")
else:
    st.caption("With several files, we match columns automatically and show the result after the check below.")
    for name, k in kinds.items():
        if k == ONE:
            st.error(f"“{name}” is marked as a one-file upload. With several files, choose what each one contains.")
            st.stop()
        if KEY[k] in tables:
            st.error(f"Two files are marked “{k}”. Please combine them or mark them differently.")
            st.stop()
        tables[KEY[k]] = raw[name]
    if "orders" not in tables:
        st.error("Please mark one file as “Orders”.")
        st.stop()

st.markdown("### Step 4. Check your records")
if st.button("Check my records", type="primary"):
    with st.spinner("Checking your information..."):
        cfg = {"currency": cur}
        res = (engine.onboard(df=next(iter(raw.values())), overrides=overrides, config=cfg, verbose=False) if single
               else engine.onboard_tables(tables, config=cfg, verbose=False))
    st.session_state["check"] = (res, company)
    st.session_state.pop("_done", None)

chk = st.session_state.get("check")
if chk:
    res, company = chk
    q = res["quality"]
    if res.get("stopped"):
        miss = [plain.FIELD_LABELS[f] for f in plain.REQUIRED if f in res["needs_choice"]]
        st.error("We could not find these essential details: " + (", ".join(miss) or "some required columns") + ". "
                 "Please choose the matching column above and check again.")
    else:
        st.success(f"Your records are readable. We can use {q['rows_used']:,} of {q['rows_in_file']:,} rows.")
        d = q["dropped"]
        if d.get("rows_without_order_number"):
            st.write(f"• {d['rows_without_order_number']} rows had no order number and were left out.")
        if d.get("duplicate_orders_removed"):
            st.write(f"• {d['duplicate_orders_removed']} repeated orders were removed.")
        for wmsg in q["warnings"]:
            st.write("• " + wmsg)
        st.markdown("**What we will check**")
        for k, v in q["detectors"].items():
            if v == "ready":
                st.write(f"✅ {plain.CHECK_LABELS[k]}")
            else:
                needs = [plain.FIELD_LABELS.get(x.strip(), x.strip()) for x in v.replace("skipped - needs:", "").split(",")]
                st.write(f"⚪ {plain.CHECK_LABELS[k]}: we need {', '.join(needs)}")
        if not single:
            with st.expander("How your columns were matched"):
                st.dataframe(pd.DataFrame([{"Information": k, "Column in your file": v["column"],
                                            "How sure we are": "Sure" if v["confidence"] >= 0.8 else "Please check"}
                                           for k, v in res["mapping"].items()]), hide_index=True, width="stretch")
        st.markdown("### Step 5. Review my purchasing activities")
        if st.button("Review my records now", type="primary"):
            with st.status("Reviewing your purchasing activities...", expanded=True) as s:
                st.write("Files received")
                st.write("Checking your information")
                st.write("Preparing your results")
                st.session_state["mine"] = workspace.from_result(res, company)
                s.update(label="Review completed", state="complete")
            st.session_state["_ws_next"] = "mine"
            st.session_state["_done"] = True
            st.rerun()
if st.session_state.get("_done"):
    st.success("Review completed. Open **Overview** in the menu to see your results.")
