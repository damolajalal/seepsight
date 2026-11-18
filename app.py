import streamlit as st

st.set_page_config(page_title="Seepsight", page_icon="🔎", layout="wide")

from seepsight import ui  # noqa: E402

ui.inject_css()
pages = {
    "": [
        st.Page("pages/overview.py", title="Overview", icon=":material/home:", default=True),
        st.Page("pages/connect.py", title="Connect your data", icon=":material/upload_file:"),
        st.Page("pages/findings.py", title="Findings", icon=":material/search:"),
        st.Page("pages/suppliers.py", title="Suppliers", icon=":material/local_shipping:"),
        st.Page("pages/cases.py", title="Cases and actions", icon=":material/task_alt:"),
        st.Page("pages/ask.py", title="Ask Seepsight", icon=":material/chat:"),
        st.Page("pages/reports.py", title="Reports", icon=":material/description:"),
    ],
    "Account": [
        st.Page("pages/profile.py", title="Company profile", icon=":material/business:"),
        st.Page("pages/settings.py", title="Settings", icon=":material/settings:"),
    ],
}
page = st.navigation(pages)
ui.sidebar_header()
page.run()
