"""Company-scoped, question-aware entry point for Seepsight Hybrid AI."""

import streamlit as st

from seepsight import hybrid_ai, hybrid_retrieval, ui, workspace

w = workspace.current(allow_empty=True)
ui.page_header(
    "Ask Hybrid AI",
    "Ask one question. Hybrid AI retrieves the relevant saved records from your company's workspace.",
)

if w is None:
    st.info("Connect your company's procurement data before asking Hybrid AI to analyse it.")
    st.page_link(
        "pages/connect.py",
        label="Connect your data",
        icon=":material/database_upload:",
    )
    st.stop()

company_name = str(w.get("name") or "Your company")
question_key = "hybrid_ai_question"
with st.form("hybrid_ai_question_form", clear_on_submit=False):
    question = st.text_area(
        "Ask a question",
        key=question_key,
        height=100,
        max_chars=500,
        placeholder="e.g. Which suppliers have the highest exposure, and what evidence supports that?",
    )
    submitted = st.form_submit_button("Continue to Hybrid AI", type="primary", use_container_width=True)

if submitted:
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        try:
            company_cases = workspace.cases()
            context = hybrid_retrieval.retrieve_workspace_context(
                w, question.strip(), cases=company_cases
            )
            st.session_state["hybrid_ai_pending_request"] = {
                "company_name": company_name,
                "question": question.strip(),
                "context": context,
            }
        except (PermissionError, ValueError, RuntimeError) as exc:
            st.error(f"Could not prepare company evidence for this question: {exc}")

pending = st.session_state.get("hybrid_ai_pending_request")
if isinstance(pending, dict):
    st.caption("The question-specific evidence has been prepared from the active company's saved workspace.")
    with st.expander("See which evidence context will be used", expanded=False):
        st.text(pending.get("context", ""))
    st.info(
        "Choose your privacy setting in the Hybrid AI panel below. "
        "Unchecked means on-device inference only. Checked allows Google cloud fallback "
        "for this request if on-device inference is unavailable."
    )
    hybrid_ai.render_workspace_assistant(
        pending["company_name"],
        pending["context"],
        question=pending["question"],
    )
else:
    st.caption(
        "Ask a question to retrieve matching findings, evidence, supplier exposure, "
        "delivery and order risks, explanations, scorecards, and case activity. "
        "Only relevant saved records are sent to the Hybrid AI panel."
    )
