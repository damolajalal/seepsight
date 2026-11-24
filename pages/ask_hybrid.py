"""Company-scoped conversational entry point for Seepsight Hybrid AI."""

import pandas as pd
import streamlit as st

from seepsight import hybrid_ai, plain, ui, workspace

w = workspace.current(allow_empty=True)
ui.page_header(
    "Ask Hybrid AI",
    "Ask evidence-grounded questions about your company's procurement findings, risks and next checks.",
)

if w is None:
    st.info("Connect your company's procurement data before asking Hybrid AI to analyse it.")
    st.page_link(
        "pages/connect.py",
        label="Connect your data",
        icon=":material/database_upload:",
    )
    st.stop()

findings = w.get("findings")
evidence = w.get("evidence")
findings = findings if isinstance(findings, pd.DataFrame) else pd.DataFrame()
evidence = evidence if isinstance(evidence, pd.DataFrame) else pd.DataFrame()
currency = str(w.get("cur") or "NGN")
company_name = str(w.get("name") or "Your company")

# Build a compact deterministic summary. Never pass raw source tables or full files.
summary_lines = [
    f"Company workspace: {company_name}",
    f"Reporting currency: {currency}",
    f"Findings in the latest saved analysis: {len(findings)}",
]
if findings.empty:
    summary_lines.append(
        "No procurement findings are present in the latest saved analysis. "
        "Do not infer that all procurement activity is risk-free."
    )
else:
    summary_lines.append("Selected finding summaries from the latest saved analysis:")
    for index, (_, finding) in enumerate(findings.head(12).iterrows(), start=1):
        finding_id = finding.get("finding_id")
        if "finding_id" in evidence.columns and finding_id is not None:
            related = evidence[evidence["finding_id"].astype(str) == str(finding_id)]
        else:
            related = evidence.iloc[0:0]
        try:
            description = plain.what_we_found(finding, related, currency)
            heading = plain.title(finding)
        except (KeyError, TypeError, ValueError):
            heading = str(finding.get("finding_type", "Procurement finding"))
            description = str(finding.get("evidence", "Verified summary unavailable"))
        severity = str(finding.get("severity", "Not recorded"))
        summary_lines.append(f"{index}. {heading} | Priority: {severity} | {description}")

run_log = w.get("log") or {}
detectors = run_log.get("detectors") or {}
incomplete = [
    str(name) for name, status in detectors.items()
    if str(status).casefold() != "ready"
]
if incomplete:
    summary_lines.append(
        "Detector coverage is incomplete for: " + ", ".join(incomplete)
        + ". Do not treat missing checks as clean results."
    )

verified_summary = "\n".join(summary_lines)[:5000]

st.markdown(
    """
    <div class="sp-card">
      <h4>Company evidence context</h4>
      <p>Hybrid AI receives a compact summary of this authenticated company's saved findings.
      It does not receive the original procurement files or full source tables.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
with st.expander("Review the verified summary sent to Hybrid AI", expanded=False):
    st.text(verified_summary)

if incomplete:
    st.warning(
        "Some procurement checks did not complete. Hybrid AI will be instructed "
        "to identify this limitation rather than treating missing checks as clear."
    )
else:
    st.caption("The summary is built from the active company's latest saved analysis.")

hybrid_ai.render_workspace_assistant(company_name, verified_summary)
