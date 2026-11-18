import streamlit as st

from seepsight import ui, workspace

w = workspace.current()
ui.page_header("Company profile", "Details of the workspace you are viewing.")
log = w["log"]
ui.card(f"<h4>{w['name']}</h4>Workspace type: <b>{'Demonstration (simulated data)' if w['kind'] == 'demo' else 'Your uploaded records'}</b><br>"
        f"Currency: <b>{w['cur']}</b><br>Records reviewed: <b>{log['rows_used']:,}</b><br>Reviewed on: <b>{log['analysed_at_utc']} (UTC)</b>")
st.markdown("### Your information and privacy")
st.write("Records you upload are used only during your visit. They are not saved and are not shared with any other company or visitor. "
         "When you close the page or clear your data, they are gone.")
st.warning("This early version does not have company logins or private storage yet. Please upload only sample or simulated records until those are built and tested.")
