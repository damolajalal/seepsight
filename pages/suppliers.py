import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
cur = w["cur"]
ui.page_header("Suppliers", "Which suppliers may need your attention, and how their deliveries are changing.")
ex = w["exposure"]
if ex is not None and len(ex):
    st.markdown("### Potential extra cost to review, by supplier")
    show = ex.rename(columns={**plain.CHECK_LABELS, "supplier": "Supplier", "total": "Total to review"})
    st.dataframe(show.style.format({c: "{:,.0f}" for c in show.columns if c != "Supplier"}), hide_index=True, width="stretch")
    st.bar_chart(ex.set_index("supplier")["total"], height=240, color="#0f8b7d")
    st.caption(f"Amounts are in {cur}. They are amounts to review, not confirmed losses.")
else:
    st.info("No supplier had a potential extra cost to review in these records.")

watch = w["findings"][w["findings"]["finding_type"] == "Supplier performance decline"]
if len(watch):
    st.markdown("### Suppliers to watch")
    for _, r in watch.iterrows():
        st.warning(plain.what_we_found(r, None, cur))

sm = w["supplier_month"]
st.markdown("### How a supplier's deliveries are changing")
sup = st.selectbox("Choose a supplier", sorted(sm["supplier"].unique()))
d = sm[sm["supplier"] == sup].set_index("po_month")
a, b = st.columns(2)
a.markdown("**Average days late**")
a.line_chart(d["avg_days_late"], height=200, color="#1d6fb8")
b.markdown("**Share of ordered goods that arrived**")
b.line_chart(d["fill_rate"], height=200, color="#15803d")
