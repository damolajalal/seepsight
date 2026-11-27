"""Evidence-grounded procurement question and Gemini Hybrid AI workspace."""
import os
import uuid

import streamlit as st

from seepsight import ask_engine, bigquery_enrichment, hybrid_ai, hybrid_retrieval, ui, workspace

w = workspace.current()
company_id = w.get("company_id")
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

workspace_key = (
    f"{company_id}:{w.get('dataset_group_id') or w.get('analysis_id') or 'legacy'}"
)
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

with st.container(border=True):
    st.markdown("#### Your question")
    with st.form(f"ask_question_form_{workspace_key}", clear_on_submit=True):
        question = st.text_area(
            "Ask Seepsight",
            height=90,
            max_chars=1000,
            placeholder="e.g. Which supplier has the highest potential exposure, and what evidence supports it?",
            label_visibility="collapsed",
        )
        submitted = st.form_submit_button(
            "Ask Seepsight",
            type="primary",
            use_container_width=True,
        )
question = (question or "").strip() if submitted else picked
if question:
    result = ask_engine.answer_question(w, question)
    response = result["answer"]
    table = result.get("table")
    # Optional BigQuery context is additive. Any connection/query failure leaves
    # the existing workspace answer and supporting table unchanged.
    bigquery_result = bigquery_enrichment.enrich_question(question, company_id)
    if bigquery_result.get("status") == "ok":
        response += (
            "\n\n**Additional BigQuery reference** "
            f"(`{bigquery_result['project_id']}.{bigquery_result['dataset_id']}."
            f"{bigquery_result['view']}`):\n"
            "The following read-only records come from the separately configured "
            "BigQuery dataset; they are supplementary and are not merged with "
            "the current session upload.\n\n"
            "```json\n"
            + bigquery_result["records_text"]
            + "\n```"
        )
    elif bigquery_result.get("status") == "unavailable":
        # Deliberately keep the fallback quiet: the original answer remains valid.
        pass
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
# Native Firebase Hybrid AI assistant (no iframe / no nested app)
# ---------------------------------------------------------
st.divider()
st.markdown("### Ask Seepsight with Gemini Hybrid AI")
st.caption(
    "Ask a follow-up using evidence retrieved from the active company workspace. "
    "Gemini explains the evidence; Seepsight remains the source of verified figures."
)

latest_question = ""
latest_answer = ""
latest_table = None
if len(chat) >= 2 and chat[-2].get("role") == "user" and chat[-1].get("role") == "assistant":
    latest_question = str(chat[-2].get("content") or "")
    latest_answer = str(chat[-1].get("content") or "")
    latest_table = chat[-1].get("table")

hybrid_form_key = f"ask_hybrid_form_{workspace_key}_{len(chat)}"
hybrid_question_key = f"ask_hybrid_question_{workspace_key}_{len(chat)}"
hybrid_consent_key = f"ask_hybrid_consent_{workspace_key}_{len(chat)}"
hybrid_pending_key = f"ask_hybrid_pending_{workspace_key}"
hybrid_response_key = f"ask_hybrid_response_{workspace_key}"
hybrid_review_key = f"ask_hybrid_review_{workspace_key}"

with st.form(hybrid_form_key, clear_on_submit=False):
    hybrid_question = st.text_area(
        "Question for Gemini Hybrid AI",
        value=latest_question,
        key=hybrid_question_key,
        max_chars=500,
        height=90,
        placeholder="e.g. Why does this supplier rank highest, and what evidence should finance review?",
    )
    allow_cloud = st.checkbox(
        "I consent to cloud fallback for this request if on-device inference cannot run.",
        value=False,
        key=hybrid_consent_key,
    )
    st.caption(
        "On-device inference requires a supported desktop Chrome environment. "
        "Cloud processing is disabled unless you explicitly give consent above."
    )
    hybrid_submitted = st.form_submit_button(
        "Ask Gemini Hybrid AI",
        type="primary",
        use_container_width=True,
    )

if hybrid_submitted:
    question_text = str(hybrid_question or "").strip()
    if not question_text:
        st.warning("Enter a question for Gemini Hybrid AI first.")
    else:
        try:
            retrieved_context = hybrid_retrieval.retrieve_workspace_context(
                w,
                question_text,
                cases=workspace.cases(),
                company_id=company_id,
            )
            evidence = str(retrieved_context or "").strip()
            if not evidence:
                st.warning(
                    "No relevant saved company evidence was retrieved. "
                    "Connect or refresh your data before asking Gemini Hybrid AI."
                )
            else:
                # Include the deterministic answer and its displayed table only
                # when this AI request explains the same latest Ask Seepsight question.
                if latest_question and question_text.casefold() == latest_question.casefold():
                    evidence += "\n\nDeterministic Ask Seepsight answer:\n" + latest_answer
                    if latest_table is not None:
                        try:
                            table_text = latest_table.to_string(
                                index=False, max_rows=25, max_cols=12
                            )
                        except (AttributeError, TypeError, ValueError):
                            table_text = ""
                        if table_text:
                            evidence += "\n\nSupporting result table displayed by Seepsight:\n"
                            evidence += table_text[:12000]

                st.session_state[hybrid_review_key] = {
                    "question": question_text,
                    "context": evidence[:40000],
                    "allow_cloud": bool(allow_cloud),
                }
                st.session_state.pop(hybrid_pending_key, None)
                st.session_state.pop(hybrid_response_key, None)
        except ValueError as exc:
            st.warning(str(exc))
        except Exception:
            st.error(
                "Could not retrieve evidence from the active company workspace. "
                "Refresh the workspace and try again."
            )

review_payload = st.session_state.get(hybrid_review_key)
if isinstance(review_payload, dict):
    with st.expander("Review retrieved evidence before sending", expanded=True):
        st.caption("Check the company evidence below. Only this retrieved context will be sent to Gemini.")
        st.text_area(
            "Retrieved evidence",
            value=review_payload.get("context", ""),
            height=260,
            disabled=True,
            key=f"ask_hybrid_review_context_{workspace_key}_{len(chat)}",
        )
        if st.button("Send reviewed evidence to Gemini", type="primary", key=f"send_reviewed_hybrid_evidence_{workspace_key}"):
            try:
                prompt = hybrid_ai.build_native_prompt(review_payload.get("question", ""), review_payload.get("context", ""))
                st.session_state[hybrid_pending_key] = {
                    "request_id": uuid.uuid4().hex,
                    "prompt": prompt,
                    "allow_cloud": bool(review_payload.get("allow_cloud")),
                }
                st.session_state.pop(hybrid_review_key, None)
                st.session_state.pop(hybrid_response_key, None)
                st.rerun()
            except ValueError as exc:
                st.warning(str(exc))

hybrid_pending = st.session_state.get(hybrid_pending_key)
if isinstance(hybrid_pending, dict):
    component_result = hybrid_ai.render_native_ai_request(
        hybrid_pending,
        key=f"native_hybrid_engine_{workspace_key}",
    )
    component_response = (
        getattr(component_result, "response", None)
        if component_result is not None
        else None
    )
    if (
        isinstance(component_response, dict)
        and component_response.get("requestId") == hybrid_pending.get("request_id")
    ):
        st.session_state[hybrid_response_key] = component_response

    hybrid_response = st.session_state.get(hybrid_response_key)
    if (
        isinstance(hybrid_response, dict)
        and hybrid_response.get("requestId") == hybrid_pending.get("request_id")
    ):
        st.markdown("#### Gemini Hybrid AI response")
        if hybrid_response.get("status") == "success":
            st.markdown(hybrid_response.get("text", ""))
            route = hybrid_response.get("inferenceSource")
            if route == "on_device":
                st.caption("Processed on this device. Firebase AI Logic confirmed the on-device route.")
            elif route == "in_cloud":
                st.caption("Processed in the cloud through Firebase AI Logic after your consent.")
        else:
            st.warning(
                "Gemini Hybrid AI could not complete this request. "
                "Your original Seepsight answer and evidence have not been changed."
            )
            if hybrid_response.get("message"):
                st.caption(hybrid_response["message"])
    elif component_result is not None:
        st.info("Gemini Hybrid AI is preparing an evidence-based response. This may take a moment.")

with st.expander("Standalone Hybrid AI testing"):
    st.caption(
        "The standalone studio remains available for separate browser testing. "
        "The main Ask Seepsight experience above no longer embeds it."
    )
    st.link_button(
        "Open standalone Hybrid AI Studio",
        os.getenv("SEEPSIGHT_HYBRID_AI_URL", "https://seepsight-hybrid-ai.web.app/"),
    )

if chat:
    if st.button("Clear conversation", key=f"clear_{workspace_key}"):
        st.session_state[chat_key] = []
        st.session_state.pop(hybrid_pending_key, None)
        st.session_state.pop(hybrid_review_key, None)
        st.session_state.pop(hybrid_response_key, None)
        st.rerun()
