import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace

w, f = workspace.current(), workspace.current()["findings"]
ui.page_header("Cases and actions", "Who is looking into each issue, and what has happened so far.")
cs = workspace.cases()
rows = []
for _, r in f.iterrows():
    c = cs.get(r["finding_id"], {"status": "Open", "owner": "", "history": []})
    rows.append({"Issue": plain.title(r), "Priority": ui.SEV_LABEL[r["severity"]], "Status": c["status"],
                 "Assigned to": c["owner"] or "Nobody yet", "Last update": (c["history"][-1] if c["history"] else "No activity yet")})
df = pd.DataFrame(rows)
if df.empty:
    st.success("There are no issues to follow up.")
    st.stop()
c = st.columns(3)
for col, s in zip(c, ["Open", "Investigating", "Resolved"]):
    col.metric(s, int((df["Status"] == s).sum()))
pick = st.multiselect("Show", ["Open", "Investigating", "Resolved"], default=["Open", "Investigating", "Resolved"])
st.dataframe(df[df["Status"].isin(pick)], hide_index=True, width="stretch")
st.caption("To change a status, assign someone or add notes, open the issue under **Findings**. "
           "A resolved case keeps its original records and history.")
