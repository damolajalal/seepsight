import io

import streamlit as st

from seepsight import plain, ui, workspace


@st.cache_data(ttl=300, show_spinner=False)
def _build_excel_report(summary_csv, records_csv):
    """Build identical report workbooks once per distinct report payload."""
    import pandas as pd

    summary_frame = pd.read_csv(io.StringIO(summary_csv))
    records_frame = pd.read_csv(io.StringIO(records_csv))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        summary_frame.to_excel(xw, sheet_name="Issues identified", index=False)
        records_frame.to_excel(xw, sheet_name="Supporting records", index=False)
    return buf.getvalue()

w = workspace.current()
cur, f, ev = w["cur"], w["findings"], w["evidence"]
ui.page_header("Reports", "A summary you can share, with the records behind it.")
cs = workspace.cases()
summary = f.assign(Issue=f.apply(plain.title, axis=1),
                   Priority=f["severity"].map(ui.SEV_LABEL),
                   Status=f["finding_id"].map(lambda i: cs.get(i, {}).get("status", "Open")),
                   **{"Assigned to": f["finding_id"].map(lambda i: cs.get(i, {}).get("owner", "") or "Nobody yet")},
                   **{f"Potential extra cost to review ({cur})": f["identified_exposure"].round(0),
                      f"Value of orders awaiting attention ({cur})": f["order_value_held_up"].round(0)})
summary = summary[["finding_id", "Issue", "Priority", "Status", "Assigned to",
                   f"Potential extra cost to review ({cur})", f"Value of orders awaiting attention ({cur})"]].rename(columns={"finding_id": "Reference"})
st.markdown("### Issues identified")
st.dataframe(summary, hide_index=True, width="stretch")
st.caption("Amounts are potential extra costs to review, not confirmed or recovered money.")

records = ev.rename(columns={**plain.EVIDENCE_LABELS, "finding_id": "Reference", "exposure_basis": "What the amount means"})
with st.spinner("Preparing your report..."):
    report_xlsx = _build_excel_report(
        summary.to_csv(index=False),
        records.to_csv(index=False),
    )
a, b, c = st.columns(3)
a.download_button("Download report (Excel)", report_xlsx, file_name="seepsight_report.xlsx",
                  mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
b.download_button("Download issues (CSV)", summary.to_csv(index=False), file_name="seepsight_issues.csv", mime="text/csv")
c.download_button("Download records (CSV)", records.to_csv(index=False), file_name="seepsight_records.csv", mime="text/csv")
st.caption("PDF reports are planned for a later version.")
