"""Evidence-grounded procurement assistant with visual company analytics."""
import os

import pandas as pd
import streamlit as st

from seepsight import ask_engine, hybrid_ai, hybrid_retrieval, ui, workspace

w = workspace.current()
ui.page_header(
    "Ask Seepsight",
    "Explore your procurement performance, inspect visual trends and ask questions grounded in your company's saved analysis.",
)

# ---------------------------------------------------------
# Visual analytics: use only the active company's saved tables.
# ---------------------------------------------------------
findings = w.get("findings")
monthly = w.get("monthly")
exposure = w.get("exposure")

findings = findings if isinstance(findings, pd.DataFrame) else pd.DataFrame()
monthly = monthly if isinstance(monthly, pd.DataFrame) else pd.DataFrame()
exposure = exposure if isinstance(exposure, pd.DataFrame) else pd.DataFrame()
currency = w.get("cur", "NGN")

st.markdown("### Visual procurement insights")
st.caption("Charts below are generated from this company's latest saved analysis. A chart is withheld when its required data is unavailable.")

# Time-series charts
if not monthly.empty and "po_month" in monthly.columns:
    trend = monthly.copy()
    trend["po_month"] = trend["po_month"].astype(str)
    trend = trend.sort_values("po_month").set_index("po_month")
    trend_cols = st.columns(2)

    with trend_cols[0]:
        st.markdown("**Monthly purchasing spend**")
        if "spend" in trend.columns and pd.to_numeric(trend["spend"], errors="coerce").notna().any():
            spend_series = pd.to_numeric(trend["spend"], errors="coerce").dropna()
            st.line_chart(spend_series, height=260, y_label=f"Spend ({currency})")
            st.caption(f"{len(spend_series)} month(s) of purchasing spend.")
        else:
            st.info("Monthly spend is not available in the saved analysis.")

    with trend_cols[1]:
        st.markdown("**Monthly order volume**")
        if "orders" in trend.columns and pd.to_numeric(trend["orders"], errors="coerce").notna().any():
            st.bar_chart(pd.to_numeric(trend["orders"], errors="coerce").dropna(), height=260, y_label="Orders")
            st.caption("Number of purchase orders analysed in each month.")
        else:
            st.info("Monthly order counts are not available.")

    performance_cols = st.columns(2)
    with performance_cols[0]:
        st.markdown("**Average delivery delay by month**")
        if "avg_days_late" in trend.columns and pd.to_numeric(trend["avg_days_late"], errors="coerce").notna().any():
            st.line_chart(pd.to_numeric(trend["avg_days_late"], errors="coerce").dropna(), height=230, y_label="Days")
        else:
            st.info("Delivery dates are insufficient for a monthly delay trend.")

    with performance_cols[1]:
        st.markdown("**Average approval turnaround by month**")
        if "avg_approval_days" in trend.columns and pd.to_numeric(trend["avg_approval_days"], errors="coerce").notna().any():
            st.line_chart(pd.to_numeric(trend["avg_approval_days"], errors="coerce").dropna(), height=230, y_label="Days")
        else:
            st.info("Approval timestamps are insufficient for this trend.")
else:
    st.info("A monthly time series cannot be displayed because the saved analysis has no monthly trend records. Reanalyse the connected procurement data after confirming that purchase dates are mapped.")

# Supplier exposure and finding composition
chart_cols = st.columns(2)
with chart_cols[0]:
    st.markdown("**Potential exposure by supplier**")
    if not exposure.empty and {"supplier", "total"}.issubset(exposure.columns):
        supplier_chart = exposure[["supplier", "total"]].copy()
        supplier_chart["total"] = pd.to_numeric(supplier_chart["total"], errors="coerce")
        supplier_chart = supplier_chart.dropna(subset=["total"]).sort_values("total", ascending=False).head(10)
        if not supplier_chart.empty:
            st.bar_chart(supplier_chart.set_index("supplier"), height=300, y_label=f"Potential exposure ({currency})")
            st.caption("Top 10 suppliers by recorded potential exposure; these are amounts to investigate, not confirmed losses.")
        else:
            st.info("No supplier exposure values are available.")
    else:
        st.info("Supplier-level exposure is not available in this analysis.")

with chart_cols[1]:
    st.markdown("**Findings by issue type**")
    if not findings.empty and "finding_type" in findings.columns:
        type_counts = findings["finding_type"].fillna("Unclassified").value_counts().rename("Findings")
        st.bar_chart(type_counts, height=300, y_label="Number of findings")
    else:
        st.info("No finding categories are available to chart.")

severity_cols = st.columns(2)
with severity_cols[0]:
    st.markdown("**Findings by priority**")
    if not findings.empty and "severity" in findings.columns:
        severity_counts = findings["severity"].fillna("Unclassified").value_counts().rename("Findings")
        st.bar_chart(severity_counts, height=240, y_label="Number of findings")
    else:
        st.info("Finding priority data is not available.")

with severity_cols[1]:
    st.markdown("**Potential exposure by issue type**")
    if not findings.empty and {"finding_type", "identified_exposure"}.issubset(findings.columns):
        issue_exposure = findings[["finding_type", "identified_exposure"]].copy()
        issue_exposure["identified_exposure"] = pd.to_numeric(issue_exposure["identified_exposure"], errors="coerce").fillna(0)
        issue_exposure = issue_exposure.groupby("finding_type")["identified_exposure"].sum().sort_values(ascending=False)
        if issue_exposure.abs().sum() > 0:
            st.bar_chart(issue_exposure, height=240, y_label=f"Potential exposure ({currency})")
        else:
            st.info("The saved findings do not contain a positive exposure amount.")
    else:
        st.info("Exposure by issue type cannot be calculated from the saved fields.")

st.divider()

# ---------------------------------------------------------
# Grounded question answering
# ---------------------------------------------------------
hybrid_ai_url = os.getenv("SEEPSIGHT_HYBRID_AI_URL", "").strip()
if hybrid_ai_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
    st.link_button("Open Seepsight Hybrid AI Studio", hybrid_ai_url)

log = w.get("log") or {}
detectors = log.get("detectors") or {}
skipped = [name for name, status in detectors.items() if str(status).casefold() != "ready"]
if skipped:
    st.warning(
        "This analysis has incomplete detector coverage. Answers will identify that limitation "
        "rather than treating missing checks as clean results."
    )
    st.caption("Checks needing attention: " + ", ".join(skipped))
else:
    st.caption("Answers use your company's latest saved findings, evidence and analysis metrics.")

workspace_key = str(w.get("company_id") or w.get("name") or "company")
chat_key = f"ask_chat_{workspace_key}"
chat = st.session_state.setdefault(chat_key, [])

suggestions = [
    "Which supplier has the highest potential exposure?",
    "How has purchasing spend changed over time?",
    "Which issue type contributes the most exposure?",
    "How many findings were identified?",
    "What should we investigate first?",
]
st.markdown("### Ask a procurement question")
cols = st.columns(2)
picked = None
for index, suggestion in enumerate(suggestions):
    if cols[index % 2].button(suggestion, key=f"ask_suggestion_{index}", use_container_width=True):
        picked = suggestion

for message in chat:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        if message.get("table") is not None:
            st.dataframe(message["table"], hide_index=True, use_container_width=True)

question = st.chat_input("Ask about suppliers, invoices, deliveries, approvals or costs")
question = question or picked
if question:
    result = ask_engine.answer_question(w, question)
    response = result["answer"]
    table = result.get("table")
    chat.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": response, "table": table},
    ])
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        st.markdown(response)
        if table is not None:
            st.dataframe(table, hide_index=True, use_container_width=True)


# ---------------------------------------------------------
# Integrated Firebase Hybrid AI assistant
# ---------------------------------------------------------
st.divider()
st.markdown("### Ask Seepsight with Gemini Hybrid AI")
st.caption(
    "Use the same Ask Seepsight workspace to ask evidence-based questions. "
    "Relevant saved records are retrieved from the active company before they are sent "
    "to Firebase AI Logic. Cloud fallback remains subject to the consent choice in the panel."
)

hybrid_request_key = f"ask_hybrid_pending_{workspace_key}"
with st.form(f"ask_hybrid_form_{workspace_key}", clear_on_submit=False):
    hybrid_question = st.text_area(
        "Question for the Hybrid AI assistant",
        key=f"ask_hybrid_question_{workspace_key}",
        max_chars=500,
        height=90,
        placeholder="e.g. Compare Cedarline Traders and Northstar Supplies using all available evidence.",
    )
    hybrid_submitted = st.form_submit_button(
        "Prepare evidence for Gemini",
        type="primary",
        use_container_width=True,
    )

if hybrid_submitted:
    st.session_state.pop(hybrid_request_key, None)
    if not hybrid_question.strip():
        st.warning("Enter a question first.")
    else:
        try:
            company_cases = workspace.cases()
            company_id = (st.session_state.get("seepsight_auth") or {}).get("company_id")
            retrieved_context = hybrid_retrieval.retrieve_workspace_context(
                w,
                hybrid_question.strip(),
                cases=company_cases,
                company_id=company_id,
            )
            if not str(retrieved_context or "").strip():
                st.warning("No relevant saved company evidence was retrieved. Connect or refresh your data before asking Hybrid AI.")
            else:
                st.session_state[hybrid_request_key] = {
                    "question": hybrid_question.strip(),
                    "context": retrieved_context,
                    "company_name": str(w.get("name") or "Your company"),
                }
        except Exception:
            st.error(
                "Could not prepare evidence from the active company workspace. "
                "Refresh the workspace and try again."
            )

hybrid_pending = st.session_state.get(hybrid_request_key)
if isinstance(hybrid_pending, dict):
    st.caption("Evidence retrieved from the active company's saved workspace:")
    with st.expander("Review retrieved evidence before sending", expanded=False):
        st.text(hybrid_pending.get("context", ""))
    hybrid_ai.render_workspace_assistant(
        hybrid_pending["company_name"],
        hybrid_pending["context"],
        question=hybrid_pending["question"],
    )

if len(chat) >= 2 and chat[-2].get("role") == "user" and chat[-1].get("role") == "assistant":
    with st.expander("Explain the latest answer with Hybrid AI", expanded=False):
        st.caption(
            "Hybrid AI receives the latest question and Seepsight's deterministic, "
            "company-scoped answer—not the full conversation or source dataset."
        )
        hybrid_ai.render_answer_explainer(
            chat[-2].get("content", ""),
            chat[-1].get("content", ""),
            w.get("name", "Your company"),
        )

if chat:
    if st.button("Clear conversation", key=f"clear_{workspace_key}"):
        st.session_state[chat_key] = []
        st.rerun()
