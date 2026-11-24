"""Evidence-grounded procurement question and Gemini Hybrid AI workspace."""
import os

import streamlit as st

from seepsight import ask_engine, hybrid_ai, hybrid_retrieval, ui, workspace

w = workspace.current()
ui.page_header(
    "Ask Seepsight",
    "Ask questions grounded in your company's saved procurement analysis and evidence.",
)

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
            # workspace.current() has already verified this workspace belongs to the signed-in company.
            company_id = w.get("company_id")
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
