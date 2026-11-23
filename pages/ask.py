"""Evidence-grounded procurement assistant for the active company workspace."""
import os

import streamlit as st

from seepsight import ask_engine, ui, workspace

w = workspace.current()
ui.page_header(
    "Ask Seepsight",
    "Ask questions about your procurement records. Answers are grounded in the latest analysis saved to your company workspace.",
)

# Keep the optional companion link, but do not imply that it powers these answers.
hybrid_ai_url = os.getenv("SEEPSIGHT_HYBRID_AI_URL", "").strip()
if hybrid_ai_url.startswith(("https://", "http://localhost", "http://127.0.0.1")):
    st.link_button("Open Seepsight Hybrid AI Studio", hybrid_ai_url)

log = w.get("log") or {}
detectors = log.get("detectors") or {}
skipped = [name for name, status in detectors.items() if str(status).casefold() != "ready"]
if skipped:
    st.warning(
        "This analysis has incomplete detector coverage. I will identify that limitation "
        "in answers rather than treating missing checks as clean results."
    )
    st.caption("Checks needing attention: " + ", ".join(skipped))
else:
    st.caption("Answers use your company's latest saved findings, evidence and analysis metrics.")

workspace_key = str(w.get("company_id") or w.get("name") or "company")
chat_key = f"ask_chat_{workspace_key}"
chat = st.session_state.setdefault(chat_key, [])

suggestions = [
    "Which supplier has the highest potential exposure?",
    "How many findings were identified?",
    "Show me the invoice price discrepancies.",
    "Which issues are high priority?",
    "What should we investigate first?",
]
st.markdown("### Suggested questions")
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

if chat:
    if st.button("Clear conversation", key=f"clear_{workspace_key}"):
        st.session_state[chat_key] = []
        st.rerun()
