import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
cur = w.get("cur", "NGN")
ui.page_header("Suppliers", "Review supplier exposure, performance records and suppliers that may need attention.")

ex = w.get("exposure")
if isinstance(ex, pd.DataFrame) and not ex.empty:
    if {"supplier", "total"}.issubset(ex.columns):
        st.markdown("### Potential extra cost to review, by supplier")
        show = ex.rename(columns={**plain.CHECK_LABELS, "supplier": "Supplier", "total": "Total to review"})
        st.dataframe(
            show.style.format({c: "{:,.0f}" for c in show.columns if c != "Supplier"}),
            hide_index=True,
            width="stretch",
        )
        st.caption(f"Amounts are in {cur}. They are amounts to review, not confirmed losses.")
    else:
        st.info("Supplier exposure records exist, but the expected supplier and amount fields are unavailable.")
else:
    st.info("No supplier had a potential extra cost to review in these records.")

findings = w.get("findings")
if isinstance(findings, pd.DataFrame) and not findings.empty and "finding_type" in findings.columns:
    watch = findings[findings["finding_type"] == "Supplier performance decline"]
    if not watch.empty:
        st.markdown("### Suppliers to watch")
        for _, row in watch.iterrows():
            st.warning(plain.what_we_found(row, None, cur))

sm = w.get("supplier_month")
st.markdown("### Monthly delivery performance records")
required_columns = {"supplier", "po_month"}
if isinstance(sm, pd.DataFrame) and not sm.empty and required_columns.issubset(sm.columns):
    suppliers = sorted(sm["supplier"].dropna().astype(str).unique())
    if suppliers:
        sup = st.selectbox("Choose a supplier", suppliers)
        monthly = sm[sm["supplier"].astype(str) == sup].sort_values("po_month").copy()
        display_columns = [
            column for column in ["po_month", "avg_days_late", "fill_rate"]
            if column in monthly.columns
        ]
        labels = {
            "po_month": "Month",
            "avg_days_late": "Average days late",
            "fill_rate": "Share of ordered goods received",
        }
        st.dataframe(
            monthly[display_columns].rename(columns=labels),
            hide_index=True,
            width="stretch",
        )
        st.caption("Trend charts are available on the Findings page; this page keeps the supplier-level records.")
    else:
        st.info("No supplier names are available in the monthly delivery records.")
elif isinstance(sm, pd.DataFrame) and not sm.empty:
    st.info("Monthly delivery records exist, but supplier or month fields are missing.")
else:
    st.info("Monthly delivery performance records are not available for this workspace.")
