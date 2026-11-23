import streamlit as st

from seepsight import ui

ui.page_header("Settings", "Manage the analysis data held in your current session.")
st.markdown("### Clear my session")
st.write("This clears the active analysis workspace, session data and case notes from this visit. It does not delete company account records, Firestore dataset metadata or any original files already saved to configured cloud storage.")
if st.button("Clear my uploaded data and notes"):
    for k in ("mine", "cases", "chat", "raw", "check", "_done", "selected"):
        st.session_state.pop(k, None)
    st.session_state["ws_key"] = "A"
    st.success("Your information has been cleared.")
st.markdown("### About")
st.write("Seepsight · See the gaps. Show the impact. Act with confidence.")
st.caption("Version 0.1 (early preview). Demonstration companies use simulated data only.")
