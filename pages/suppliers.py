import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
cur = w["cur"]
ui.page_header("Suppliers", "Review supplier exposure, performance records and suppliers that may need attention.")
ex = w["exposure"]
if ex is not None and len(ex):
    st.markdown("### Potential extra cost to review, by supplier")
    show = ex.rename(columns={**plain.CHECK_LABELS, "supplier": "Supplier", "total": "Total to review"})
    st.dataframe(show.style.format({c: "{:,.0f}" for c in show.columns if c != "Supplier"}), hide_index=True, width="stretch")
    st.caption(f"Amounts are in {cur}. They are amounts to review, not confirmed losses.")
else:
    st.info("No supplier had a potential extra cost to review in these records.")

watch = w["findings"][w["findings"]["finding_type"] == "Supplier performance decline"]
if len(watch):
    st.markdown("### Suppliers to watch")
    for _, r in watch.iterrows():
        st.warning(plain.what_we_found(r, None, cur))

sm = w["supplier_month"]
st.markdown("### Monthly delivery performance records")
if sm is not None and len(sm):
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
    st.info("Monthly delivery performance records are not available for this workspace.")
