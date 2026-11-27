import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
f = w.get("findings")
if not isinstance(f, pd.DataFrame):
    f = pd.DataFrame()

ui.page_header("Cases and actions", "Who is looking into each issue, and what has happened so far.")
cs = workspace.cases()
rows = []
for _, row in f.iterrows():
    finding_id = row.get("finding_id")
    case = cs.get(finding_id, {"status": "Open", "owner": "", "history": []})
    severity = str(row.get("severity", "Low"))
    priority = ui.SEV_LABEL.get(severity, "Review")
    history = case.get("history") or []
    rows.append({
        "Issue": plain.title(row),
        "Priority": priority,
        "Status": case.get("status", "Open"),
        "Assigned to": case.get("owner") or "Nobody yet",
        "Last update": history[-1] if history else "No activity yet",
    })

df = pd.DataFrame(rows)
if df.empty:
    st.success("There are no issues to follow up.")
    st.stop()

columns = st.columns(3)
for column, status in zip(columns, ["Open", "Investigating", "Resolved"]):
    column.metric(status, int((df["Status"] == status).sum()))

pick = st.multiselect(
    "Show",
    ["Open", "Investigating", "Resolved"],
    default=["Open", "Investigating", "Resolved"],
)
st.dataframe(df[df["Status"].isin(pick)], hide_index=True, width="stretch")
st.caption(
    "To change a status, assign someone or add notes, open the issue under **Findings**. "
    "A resolved case keeps its original records and history."
)
