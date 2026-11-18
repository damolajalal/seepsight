import re

import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
cur, f, ev = w["cur"], w["findings"], w["evidence"]
ui.page_header("Ask Seepsight", "Ask questions about your company's purchasing activities. Seepsight uses your records and findings to give evidence-based answers.")
st.caption("Answers come only from the records and findings in this workspace. If the information is not there, Seepsight will say so.")


def answer(q):
    t = q.lower()
    ex = w["exposure"]
    if re.search(r"supplier|who|most", t) and re.search(r"cost|extra|exposure|overpa|most|highest", t):
        if ex is None or len(ex) == 0:
            return "No supplier has a potential extra cost to review in these records.", None
        top = ex.head(3)
        text = "The suppliers with the highest potential extra cost to review are " + ", ".join(
            f"{r['supplier']} ({cur} {r['total']:,.0f})" for _, r in top.iterrows()) + ". These are amounts to check, not confirmed losses."
        return text, top.rename(columns={**plain.CHECK_LABELS, "supplier": "Supplier", "total": "Total to review"})
    if re.search(r"warning|predict|risk|accura|trust|correct|reliable are", t):
        rm = w["log"].get("risk_model")
        if not rm:
            return "Early warnings are not available for these records.", None
        return (f"In testing, about {round(rm['precision'] * 10)} in 10 early warnings were correct, and we caught about {round(rm['recall'] * 10)} in 10 "
                "of the orders that really had problems. Please have a person review each warning."), None
    if re.search(r"high|serious|urgent|priority|worst", t):
        hi = f[f["severity"] == "High"]
        return (f"{len(hi)} issue(s) are high priority:\n" + "\n".join("• " + plain.title(r) for _, r in hi.iterrows())) if len(hi) else "No issues are high priority.", None
    if re.search(r"approv|slow|waiting|branch", t):
        r = f[f["finding_type"] == "Slow approvals"]
        if r.empty:
            return "Our checks did not find slow approvals, or approval dates were not included in the records.", None
        r = r.iloc[0]
        why = (" Possible reasons to check: " + plain.CAUSE["Slow approvals"]) if "why" in t else ""
        return plain.what_we_found(r, ev[ev["finding_id"] == r["finding_id"]], cur) + why, None
    if re.search(r"late|delay|decline|deliver|supplier.*(worse|reliab)", t):
        r = f[f["finding_type"] == "Supplier performance decline"]
        if r.empty:
            return "Our checks did not find a supplier whose deliveries are clearly getting worse.", None
        return "\n".join(plain.what_we_found(x, None, cur) for _, x in r.iterrows()), None
    if re.search(r"total|how much|amount|exposure|cost", t):
        return (f"The potential extra cost to review is {cur} {f['identified_exposure'].sum():,.0f}, and the value of orders awaiting attention is "
                f"{cur} {f['order_value_held_up'].sum():,.0f}. These are amounts to check, not confirmed or recovered money."), None
    if re.search(r"how many|issues|findings|problems|list", t):
        return f"We identified {len(f)} issue(s):\n" + "\n".join("• " + plain.title(r) for _, r in f.iterrows()), None
    return ("I can answer questions about the potential extra cost, which suppliers need attention, high priority issues, slow approvals, "
            "late deliveries and how reliable the early warnings are. I don't have information to answer that question."), None


key = st.session_state.get("ws_key", "A")
chat = st.session_state.setdefault("chat", {}).setdefault(key, [])
examples = ["Which supplier has the highest potential extra cost?", "Which issues are high priority?",
            "Why are approvals slow?", "How reliable are the early warnings?"]
cols = st.columns(len(examples))
picked = None
for col, e in zip(cols, examples):
    if col.button(e, key=f"ex_{e}"):
        picked = e
q = st.chat_input("Ask a question about your purchasing records") or picked
if q:
    text, table = answer(q)
    chat += [{"role": "user", "content": q}, {"role": "assistant", "content": text, "table": table}]
for m in chat:
    with st.chat_message(m["role"]):
        st.write(m["content"])
        if m.get("table") is not None:
            st.dataframe(m["table"], hide_index=True, width="stretch")
