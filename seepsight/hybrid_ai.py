"""Safe hand-off from the authenticated Streamlit workspace to Hybrid AI."""

import base64
import html as html_lib
import json
import os
from urllib.parse import urlparse

import streamlit as st


def _configured_hybrid_url():
    """Return only a configured HTTPS Hybrid AI origin."""
    default_url = "https://seepsight-hybrid-ai.web.app/"
    hybrid_url = os.getenv("SEEPSIGHT_HYBRID_AI_URL", "").strip()
    if not hybrid_url:
        try:
            hybrid_url = str(st.secrets.get("SEEPSIGHT_HYBRID_AI_URL", default_url)).strip()
        except Exception:
            hybrid_url = default_url
    parsed = urlparse(hybrid_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return "", None
    return hybrid_url, parsed


def _render_context(payload, missing_context_message):
    """Embed Hybrid AI and pass bounded, question-specific verified context."""
    hybrid_url, parsed = _configured_hybrid_url()
    if not hybrid_url:
        st.info(
            "Hybrid AI is not configured for embedding yet. Set "
            "SEEPSIGHT_HYBRID_AI_URL to the deployed HTTPS Hybrid AI URL."
        )
        return

    facts = str(payload.get("verifiedFacts") or "").strip()[:12000]
    if not facts:
        st.warning(missing_context_message)
        return

    safe_payload = {
        "type": payload["type"],
        "version": 1,
        "supplier": str(payload.get("supplier") or "")[:160],
        "findingType": str(payload.get("findingType") or "")[:160],
        "verifiedFacts": facts,
        "requestedAction": str(payload.get("requestedAction") or "")[:500],
    }
    iframe_src = html_lib.escape(hybrid_url, quote=True)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    encoded = base64.b64encode(
        json.dumps(safe_payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    st.link_button("Open Hybrid AI separately for on-device testing", hybrid_url)

    # Base64 keeps untrusted company/evidence text out of the HTML/JS source.
    # postMessage is restricted to the configured HTTPS companion origin.
    html = f"""
    <div style="font-family: sans-serif; color: inherit;">
      <iframe id="seepsight-hybrid-frame"
        src="{iframe_src}"
        title="Seepsight Hybrid AI"
        allow="language-model"
        style="width:100%; height:700px; border:0; border-radius:12px;"
        referrerpolicy="strict-origin-when-cross-origin"
        loading="lazy"></iframe>
      <script>
        (() => {{
          const frame = document.getElementById('seepsight-hybrid-frame');
          const encoded = '{encoded}';
          const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
          const payload = JSON.parse(new TextDecoder().decode(bytes));
          frame.addEventListener('load', () => {{
            frame.contentWindow.postMessage(payload, '{target_origin}');
          }}, {{ once: true }});
        }})();
      </script>
    </div>
    """
    st.components.v1.html(html, height=720, scrolling=True)


def render_verified_context(supplier, finding_type, verified_facts, requested_action):
    """Pass a deterministic Seepsight finding to the existing Hybrid AI app."""
    _render_context(
        {
            "type": "seepsight:explain-finding",
            "supplier": supplier,
            "findingType": finding_type,
            "verifiedFacts": verified_facts,
            "requestedAction": requested_action,
        },
        "There is no verified company context to send to Hybrid AI.",
    )


def render_finding_explainer(finding, evidence, currency):
    """Pass a deterministic Seepsight finding and its summary to Hybrid AI."""
    from seepsight import plain

    facts = plain.what_we_found(finding, evidence, currency)
    supplier = finding.get("supplier", finding.get("entity", ""))
    render_verified_context(
        supplier,
        finding.get("finding_type", ""),
        facts,
        "Explain this finding and identify the next evidence checks for the reviewer.",
    )


def render_answer_explainer(question, answer, company_name=""):
    """Pass a deterministic Ask Seepsight answer for AI-assisted explanation."""
    render_verified_context(
        company_name,
        "Grounded Ask Seepsight answer",
        answer,
        question or "Explain the verified answer and suggest the next review step.",
    )


def render_workspace_assistant(company_name, verified_facts, question=""):
    """Open Ask Hybrid AI with question-specific records from the active company."""
    _render_context(
        {
            "type": "seepsight:ask-hybrid-ai",
            "supplier": company_name,
            "findingType": "Question-specific company procurement evidence",
            "verifiedFacts": verified_facts,
            "requestedAction": question or "Explain the retrieved company procurement evidence.",
        },
        "There is no verified procurement context available for this question.",
    )
