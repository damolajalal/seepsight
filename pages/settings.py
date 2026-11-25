"""Company settings and session administration."""

import streamlit as st

from seepsight import ui

ui.page_header(
    "Settings",
    "Manage your current session and application preferences.",
)

st.markdown("### Clear my session")
st.write(
    "This clears the active analysis workspace, session data and case notes "
    "from this visit. It does not delete company account records, Firestore "
    "dataset metadata or original files already saved to configured cloud storage."
)
if st.button("Clear my session data"):
    for key in (
        "mine", "cases", "chat", "raw", "check", "_done", "selected",
        "connect_raw", "connect_source_file_bytes", "connect_upload_fingerprint",
        "connect_check", "connect_check_signature", "connect_dataset_types",
        "connect_load_errors",
    ):
        st.session_state.pop(key, None)
    st.session_state["ws_key"] = "A"
    st.success("Your information has been cleared.")

st.divider()
st.markdown("### About")
st.write("Seepsight · See the gaps. Show the impact. Act with confidence.")
st.caption("Version 0.1 (early preview). Demonstration companies use simulated data only.")
