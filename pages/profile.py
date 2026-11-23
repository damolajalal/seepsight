import streamlit as st

from seepsight import ui, workspace

w = workspace.current()
ui.page_header("Company profile", "Details of the workspace you are viewing.")
log = w["log"]
ui.card(f"<h4>{w['name']}</h4>Workspace type: <b>{'Demonstration (simulated data)' if w['kind'] == 'demo' else 'Your uploaded records'}</b><br>"
        f"Currency: <b>{w['cur']}</b><br>Records reviewed: <b>{log['rows_used']:,}</b><br>Reviewed on: <b>{log['analysed_at_utc']} (UTC)</b>")
st.markdown("### Your information and privacy")
st.write("Your account and company membership are managed through Firebase. Dataset metadata and confirmed column mappings may be stored in your company's Firestore workspace. "
         "When private file storage is not configured, original uploads and the active analysis workspace remain in the current app session and are not durably stored.")
st.warning("Private file storage and durable analysis history are not yet available in this deployment. Use sample or simulated records only; do not upload sensitive live company data.")
