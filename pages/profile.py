import streamlit as st

from seepsight import ui, workspace

w = workspace.current()
ui.page_header("Company profile", "Details of the workspace you are viewing.")
log = w["log"]
ui.card(f"<h4>{w['name']}</h4>Workspace type: <b>{'Demonstration (simulated data)' if w['kind'] == 'demo' else 'Your uploaded records'}</b><br>"
        f"Currency: <b>{w['cur']}</b><br>Records reviewed: <b>{log['rows_used']:,}</b><br>Reviewed on: <b>{log['analysed_at_utc']} (UTC)</b>")

st.markdown("### Your information and privacy")
st.write(
    "Your account and company membership are managed through Firebase. "
    "In Persistent Mode, uploaded original files, source records, normalized "
    "procurement records, confirmed mappings and completed analysis workspaces "
    "are stored in your company's Firestore workspace. In Temporary Demo Mode, "
    "uploaded data and analysis remain in the current app session only."
)
if st.session_state.get("seepsight_demo_mode", True):
    st.warning(
        "Temporary Demo Mode is active. Data is held in session memory and may "
        "be lost when the session is refreshed or restarted. Switch to Persistent "
        "Mode on Connect Your Data when you are ready to save company data."
    )
else:
    st.info(
        "Persistent Mode is active. Data is stored in the authenticated company's "
        "Firestore workspace. Access is company-scoped and subject to your "
        "organisation's data-governance and retention requirements."
    )
st.caption(
    "Only upload company information that you are authorised to process and "
    "that your organisation permits you to store in this environment."
)
