"""Safe hand-off from the authenticated Streamlit workspace to Hybrid AI."""

import base64
import html as html_lib
import json
import os
from urllib.parse import urlparse

import streamlit as st


def render_verified_context(supplier, finding_type, verified_facts, requested_action):
    """Embed Hybrid AI and pass only bounded, verified, human-readable context."""
    hybrid_url = os.getenv("SEEPSIGHT_HYBRID_AI_URL", "").strip()
    parsed = urlparse(hybrid_url)
    if parsed.scheme != "https" or not parsed.netloc:
        st.info(
            "Hybrid AI is not configured for embedding yet. Set "
            "SEEPSIGHT_HYBRID_AI_URL to the deployed HTTPS Hybrid AI URL."
        )
        return

    facts = str(verified_facts or "").strip()[:5000]
    if not facts:
        st.warning("There is no verified company context to send to Hybrid AI.")
        return

    payload = {
        "type": "seepsight:explain-finding",
        "version": 1,
        "supplier": str(supplier or "")[:160],
        "findingType": str(finding_type or "")[:160],
        "verifiedFacts": facts,
        "requestedAction": str(requested_action or "")[:300],
    }
    iframe_src = html_lib.escape(hybrid_url, quote=True)
    target_origin = f"{parsed.scheme}://{parsed.netloc}"
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    # Base64 keeps untrusted supplier/evidence text out of the HTML/JS source.
    # postMessage is restricted to the configured HTTPS companion origin.
    html = f"""
    <div style="font-family: sans-serif; color: inherit;">
      <iframe id="seepsight-hybrid-frame"
        src="{iframe_src}"
        title="Seepsight Hybrid AI"
        style="width:100%; height:820px; border:0; border-radius:12px;"
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
    st.components.v1.html(html, height=840, scrolling=True)


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
