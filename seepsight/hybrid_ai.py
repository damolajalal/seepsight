"""Safe hand-off from the authenticated Streamlit workspace to Hybrid AI."""

import base64
import json
import os
from urllib.parse import urlparse

import streamlit as st


def render_finding_explainer(finding, evidence, currency):
    """Embed Hybrid AI and pass only a bounded, human-readable finding summary."""
    hybrid_url = os.getenv("SEEPSIGHT_HYBRID_AI_URL", "").strip()
    parsed = urlparse(hybrid_url)
    if parsed.scheme != "https" or not parsed.netloc:
        st.info(
            "Hybrid AI is not configured for embedding yet. Set "
            "SEEPSIGHT_HYBRID_AI_URL to the deployed HTTPS Hybrid AI URL."
        )
        return

    from seepsight import plain

    facts = str(plain.what_we_found(finding, evidence, currency)).strip()
    if not facts:
        st.warning("There is no verified finding summary to send to Hybrid AI.")
        return
    facts = facts[:5000]
    supplier = str(finding.get("supplier", finding.get("entity", "")) or "")[:160]
    finding_type = str(finding.get("finding_type", "") or "")[:160]
    payload = {
        "type": "seepsight:explain-finding",
        "version": 1,
        "supplier": supplier,
        "findingType": finding_type,
        "verifiedFacts": facts,
        "requestedAction": "Explain this finding and identify the next evidence checks for the reviewer.",
    }
    encoded = base64.b64encode(
        json.dumps(payload, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")

    # Base64 keeps untrusted supplier/evidence text out of the HTML/JS source.
    html = f"""
    <div style="font-family: sans-serif; color: inherit;">
      <iframe id="seepsight-hybrid-frame"
        src="{hybrid_url}"
        title="Seepsight Hybrid AI finding explainer"
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
            frame.contentWindow.postMessage(payload, '*');
          }}, {{ once: true }});
        }})();
      </script>
    </div>
    """
    st.components.v1.html(html, height=840, scrolling=True)
