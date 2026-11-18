import pandas as pd
import streamlit as st

from seepsight import plain, ui, workspace

w = workspace.current()
cur, f, mo = w["cur"], w["findings"], w["monthly"]
ui.page_header("Welcome to Seepsight", f"Here is what is happening across the purchasing activities of {w['name']} "
                                       "and the issues that may need your attention.")
if w["kind"] == "demo":
    st.info("You are looking at simulated demonstration data, not a real company. To review your own records, open **Connect your data**.")

c = st.columns(4)
c[0].metric("Purchasing spend reviewed", ui.money(cur, mo["spend"].sum()), help="The total value of all the orders we reviewed.")
c[1].metric("Potential extra cost to review", ui.money(cur, f["identified_exposure"].sum()),
            help="Money that may have been overpaid, or paid for goods that did not arrive. It is not a confirmed loss until the company checks.")
c[2].metric("Issues identified", len(f), help="Problems our checks found in the records.")
c[3].metric("Value of orders awaiting attention", ui.money(cur, f["order_value_held_up"].sum()),
            help="The value of orders that waited a long time for approval.")

st.markdown("### What needs your attention")
if len(f) == 0:
    st.success("Our checks did not find any issues in these records.")
rank = {"High": 0, "Medium": 1, "Low": 2}
for _, r in f.assign(_o=f["severity"].map(rank)).sort_values(["_o", "identified_exposure"], ascending=[True, False]).head(3).iterrows():
    ev = w["evidence"][w["evidence"]["finding_id"] == r["finding_id"]]
    with st.container(border=True):
        a, b = st.columns([6, 1])
        a.markdown(f"{ui.chip(ui.SEV_LABEL[r['severity']], ui.SEV_KIND[r['severity']])} &nbsp; **{plain.title(r)}**", unsafe_allow_html=True)
        a.write(plain.what_we_found(r, ev, cur))
        if b.button("Open", key=f"open_{r['finding_id']}"):
            st.session_state["selected"] = r["finding_id"]
            st.switch_page("pages/findings.py")


def trend_note(series, unit, worse):
    s = series.dropna()
    if len(s) < 6:
        return ""
    a, b = s.iloc[:3].mean(), s.iloc[-3:].mean()
    trend = worse if b > a + 0.5 else "stayed about the same" if abs(b - a) <= 0.5 else "improved"
    return f"At the start it averaged {a:.1f} {unit}; recently {b:.1f} {unit}. This has {trend}."


st.markdown("### How things are changing")
x, y = st.columns(2)
with x:
    st.markdown("**How late are deliveries arriving?**")
    st.line_chart(mo.set_index("po_month")["avg_days_late"], height=220, color="#1d6fb8")
    st.caption(trend_note(mo["avg_days_late"], "days late", "got worse"))
with y:
    st.markdown("**How long do orders wait for approval?**")
    if mo["avg_approval_days"].notna().any():
        st.line_chart(mo.set_index("po_month")["avg_approval_days"], height=220, color="#d97706")
        st.caption(trend_note(mo["avg_approval_days"], "days", "got worse"))
    else:
        st.caption("Approval dates were not included in these records.")

st.markdown("### Early warnings")
st.caption("Orders our system warned about during testing. They are warnings for a person to review, not confirmed problems.")
risk = w["risk"]
if risk is None or len(risk) == 0:
    st.write("There are no early warnings for these records.")
else:
    st.dataframe(pd.DataFrame({"Order number": risk["po_id"], "Supplier": risk["entity"],
                               "Warning level": risk["risk_score"].map(plain.warning_level),
                               "Main reasons": risk["key_drivers"].map(plain.driver_text),
                               "What actually happened": risk["actual_problem"].map({1: "Late or incomplete", 0: "As expected"})}),
                 hide_index=True, width="stretch")

with st.expander("How well did our checks perform in testing?"):
    log, rm, sc = w["log"], w["log"].get("risk_model"), w["log"].get("scorecard")
    if sc:
        st.write(f"In this simulated company, {sc['planted']} issues were deliberately included to test us. We identified {sc['found']} of them "
                 f"and raised {sc['false_alarms']} false alarms. This does not prove we will find every problem in a real company.")
    if rm:
        st.write(f"About {round(rm['precision'] * 10)} in 10 of our early warnings were correct, and we caught about {round(rm['recall'] * 10)} in 10 "
                 "of the orders that really had problems.")
        st.caption(f"Technical details: precision {rm['precision']}, recall {rm['recall']}, AUC {rm['auc']}, tested on {rm['tested_on']:,} orders.")
    st.caption("Results on real companies will differ. Please have a person review every warning.")
