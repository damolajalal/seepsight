from datetime import datetime

import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
cur, f = w["cur"], w["findings"]
ui.page_header("Findings", "The issues our checks identified, with the records behind each one.")
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
        min_pattern = int(thresholds.get("min_pattern", 2) or 2)
        st.info(
            "The available procurement checks ran, but no finding met the configured "
            f"reporting rules. Pattern-based checks require at least {min_pattern} "
            "matching orders for the same supplier or group. Review the check coverage "
            "and source records before treating this as a clean bill of health."
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
st.caption(f"Showing the {min(25, len(ev))} largest of {len(ev)} records.")

st.markdown("#### What may have caused this")
st.write(plain.CAUSE[r["finding_type"]])
st.caption("These are possibilities until someone investigates.")
st.markdown("#### What we recommend")
st.write(plain.ACTION[r["finding_type"]])

ex = w["explanations"]
if ex is not None:
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
