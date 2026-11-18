import streamlit as st

from seepsight import ui

ui.page_header("Settings", "Manage the information held for this visit.")
st.markdown("### Clear my information")
st.write("This removes any records you uploaded, and the case notes you entered, from this visit.")
if st.button("Clear my uploaded data and notes"):
    for k in ("mine", "cases", "chat", "raw", "check", "_done", "selected"):
        st.session_state.pop(k, None)
    st.session_state["ws_key"] = "A"
    st.success("Your information has been cleared.")
st.markdown("### About")
st.write("Seepsight · See the gaps. Show the impact. Act with confidence.")
st.caption("Version 0.1 (early preview). Demonstration companies use simulated data only.")
