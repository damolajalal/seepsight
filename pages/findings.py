from datetime import datetime

import pandas as pd
import streamlit as st

from seepsight import hybrid_ai, plain, ui, workspace

w = workspace.current()
cur, f = w["cur"], w["findings"]
ui.page_header("Findings", "Grouped procurement issues, with affected orders and supporting evidence.")

# ---------------------------------------------------------
# Findings analytics: visual summaries live on this page.
# ---------------------------------------------------------
findings_chart = f.copy() if isinstance(f, pd.DataFrame) else pd.DataFrame()
currency = cur or "NGN"

st.markdown("### Findings at a glance")
st.caption(
    "Each issue groups the same procurement problem across the company; it can include many purchase orders and suppliers. "
    "Potential exposure is an amount to investigate, not a confirmed loss."
)
if findings_chart.empty:
    st.info("There are no saved findings to visualise. Review detector coverage below before treating this as a clear result.")
else:
    chart_left, chart_right = st.columns(2, gap="large")
    with chart_left:
        st.markdown("**Findings by issue type**")
        if "finding_type" in findings_chart.columns:
            issue_counts = findings_chart["finding_type"].fillna("Unclassified").value_counts()
            st.bar_chart(issue_counts, height=260, horizontal=True)
        else:
            st.caption("Issue-type information is unavailable.")

    with chart_right:
        st.markdown("**Findings by priority**")
        if "severity" in findings_chart.columns:
            priority_counts = findings_chart["severity"].fillna("Unclassified").value_counts()
            st.bar_chart(priority_counts, height=260)
        else:
            st.caption("Priority information is unavailable.")

    if {"finding_type", "identified_exposure"}.issubset(findings_chart.columns):
        exposure_chart = findings_chart[["finding_type", "identified_exposure"]].copy()
        exposure_chart["identified_exposure"] = pd.to_numeric(
            exposure_chart["identified_exposure"], errors="coerce"
        ).fillna(0)
        exposure_by_type = exposure_chart.groupby("finding_type")["identified_exposure"].sum()
        if exposure_by_type.abs().sum() > 0:
            st.markdown("**Potential exposure by issue type**")
            st.bar_chart(exposure_by_type.sort_values(ascending=False), height=260)
            st.caption(f"Amounts shown in {currency}; verify supporting transactions before treating them as losses.")
        else:
            st.caption("No recorded potential exposure values are available for charting.")

    exposure = w.get("exposure")
    if isinstance(exposure, pd.DataFrame) and {"supplier", "total"}.issubset(exposure.columns):
        supplier_chart = exposure[["supplier", "total"]].copy()
        supplier_chart["total"] = pd.to_numeric(supplier_chart["total"], errors="coerce")
        supplier_chart = supplier_chart.dropna(subset=["total"]).sort_values("total", ascending=False).head(10)
        if not supplier_chart.empty:
            st.markdown("**Potential exposure by supplier**")
            st.bar_chart(supplier_chart.set_index("supplier"), height=280, horizontal=True)
            st.caption("Leading suppliers by recorded potential exposure; these amounts require review.")

    supplier_month = w.get("supplier_month")
    required_trend_columns = {"supplier", "po_month", "avg_days_late", "fill_rate"}
    if isinstance(supplier_month, pd.DataFrame) and required_trend_columns.issubset(supplier_month.columns):
        supplier_names = sorted(supplier_month["supplier"].dropna().astype(str).unique())
        if supplier_names:
            st.markdown("**Supplier delivery performance signals**")
            selected_supplier = st.selectbox(
                "Supplier delivery trend",
                supplier_names,
                key="findings_supplier_trend",
            )
            trend = supplier_month[supplier_month["supplier"].astype(str) == selected_supplier].copy()
            trend["avg_days_late"] = pd.to_numeric(trend["avg_days_late"], errors="coerce")
            trend["fill_rate"] = pd.to_numeric(trend["fill_rate"], errors="coerce")
            trend = trend.sort_values("po_month").set_index("po_month")
            trend_left, trend_right = st.columns(2, gap="large")
            with trend_left:
                st.markdown("Average days late")
                if trend["avg_days_late"].notna().any():
                    st.line_chart(trend[["avg_days_late"]], height=220)
                else:
                    st.caption("Average delivery delay is unavailable.")
            with trend_right:
                st.markdown("Share of ordered goods received")
                if trend["fill_rate"].notna().any():
                    st.line_chart(trend[["fill_rate"]], height=220)
                else:
                    st.caption("Delivery fill-rate data is unavailable.")

st.divider()
if len(f) == 0:
    # A zero-row findings table does not necessarily mean every detector ran.
    # Surface the detector coverage saved with this analysis so missing inputs
    # cannot be mistaken for a clean procurement review.
    run_log = w.get("log", {}) or {}
    detector_status = run_log.get("detectors", {}) or {}
    thresholds = run_log.get("thresholds", {}) or {}
    skipped = {
        name: status for name, status in detector_status.items()
        if str(status).lower() != "ready"
    }

    st.markdown("### Findings status")
    if skipped:
        st.warning(
            "No findings were generated, but not all procurement checks could run. "
            "This is an incomplete review, not confirmation that the records are clear."
        )
        st.markdown("**Checks requiring more data or corrected mappings**")
        for name, status in skipped.items():
            st.write(f"- **{name}:** {status}")
    elif detector_status:
        st.info(
            "The available checks completed and did not identify a qualifying discrepancy "
            "in the fields they could examine. Transaction-level checks do not require "
            "repeated occurrences or a minimum financial amount. Review the coverage below "
            "to see exactly which checks ran."
        )
        st.markdown("**Checks run**")
        for name, status in detector_status.items():
            st.write(f"- **{name}:** {status}")
    else:
        st.warning(
            "No findings are available and detector coverage was not recorded for this "
            "analysis. Re-run validation from Connect your data to produce a traceable result."
        )

    st.page_link("pages/connect.py", label="Review data and run checks again",
                 icon=":material/database_upload:")
    st.stop()

ids = list(f["finding_id"])
want = st.session_state.pop("selected", None)
if want in ids:
    st.session_state["pick_issue"] = want
if st.session_state.get("pick_issue") not in ids:
    st.session_state["pick_issue"] = ids[0]
fid = st.selectbox("Choose an issue to review", ids, key="pick_issue",
                   format_func=lambda i: f"{plain.title(f[f['finding_id'] == i].iloc[0])}")
r = f[f["finding_id"] == fid].iloc[0]
ev = w["evidence"][w["evidence"]["finding_id"] == fid]
case = workspace.cases().setdefault(fid, {"status": "Open", "owner": "", "note": "", "history": []})

st.markdown(f"## {plain.title(r)}")
st.markdown(f"{ui.chip(ui.SEV_LABEL[r['severity']], ui.SEV_KIND[r['severity']])} &nbsp; "
            f"{ui.chip(case['status'], ui.STATUS_KIND[case['status']])}", unsafe_allow_html=True)

st.markdown("#### What we found")
st.write(plain.what_we_found(r, ev, cur))
st.markdown("#### Why it matters")
st.write(plain.WHY[r["finding_type"]] + " This is a possible problem to check, not a confirmed loss.")

st.markdown("#### Records supporting this finding")
cols = [c for c in plain.EVIDENCE_COLUMNS[r["finding_type"]] if c in ev.columns]
view = ev.sort_values("exposure", ascending=False) if "exposure" in ev.columns else ev
st.dataframe(view[cols].head(25).rename(columns=plain.EVIDENCE_LABELS), hide_index=True, width="stretch")
st.caption(f"This grouped issue contains {len(ev):,} supporting purchase-order record(s). Showing up to 25 records.")

with st.expander("Explain this finding with Hybrid AI", expanded=False):
    st.caption(
        "Hybrid AI receives only this finding's verified summary from your authenticated "
        "company workspace. Review the summary and choose whether cloud fallback is allowed."
    )
    hybrid_ai.render_finding_explainer(r, ev, cur)


st.markdown("#### What may have caused this")
st.write(plain.CAUSE[r["finding_type"]])
st.caption("These are possibilities until someone investigates.")
st.markdown("#### What we recommend")
st.write(plain.ACTION[r["finding_type"]])

ex = w.get("explanations")
# Older or optional explanation exports may exist without the legacy lookup
# columns. They must never prevent the verified findings and evidence from loading.
required_explanation_columns = {"record_ref", "entity", "explanation"}
if ex is not None and required_explanation_columns.issubset(set(ex.columns)):
    row = ex[(ex["record_ref"] == fid) & (ex["entity"] == r["entity"])]
    if len(row):
        with st.expander("Detailed AI summary (earlier wording, being simplified)"):
            st.write(row.iloc[0]["explanation"])
            st.caption("AI summaries can contain mistakes. Check them against the records above.")

st.markdown("#### Investigation status")
with st.form(f"case_{fid}"):
    status = st.selectbox("Status", ["Open", "Investigating", "Resolved"], index=["Open", "Investigating", "Resolved"].index(case["status"]))
    owner = st.text_input("Assigned to", case["owner"])
    note = st.text_area("Investigation notes", case["note"])
    if st.form_submit_button("Save"):
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        if status != case["status"]:
            case["history"].append(f"{stamp}: status changed from {case['status']} to {status}")
        if owner != case["owner"]:
            case["history"].append(f"{stamp}: assigned to {owner or 'nobody'}")
        if note != case["note"]:
            case["history"].append(f"{stamp}: notes updated")
        case.update(status=status, owner=owner, note=note)
        workspace.save_case(fid, case)
        st.rerun()
if case["history"]:
    with st.expander("History of this case"):
        for h in reversed(case["history"]):
            st.write("• " + h)
