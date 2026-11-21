
import streamlit as st

st.set_page_config(
    page_title="Seepsight",
    page_icon="📦",
    layout="wide",
)

from seepsight import auth  # noqa: E402

# Require authentication before accessing application pages.
if not auth.require_auth():
    st.stop()

from seepsight import ui  # noqa: E402

# Apply the application-wide design system.
ui.inject_css()

# Application navigation.
pages = {
    "": [
        st.Page(
            "pages/overview.py",
            title="Overview",
            icon=":material/dashboard:",
            default=True,
        ),
        st.Page(
            "pages/connect.py",
            title="Connect your data",
            icon=":material/database:",
        ),
        st.Page(
            "pages/findings.py",
            title="Findings",
            icon=":material/troubleshoot:",
        ),
        st.Page(
            "pages/suppliers.py",
            title="Suppliers",
            icon=":material/local_shipping:",
        ),
        st.Page(
            "pages/cases.py",
            title="Cases and actions",
            icon=":material/task_alt:",
        ),
        st.Page(
            "pages/ask.py",
            title="Ask Seepsight",
            icon=":material/chat:",
        ),
        st.Page(
            "pages/reports.py",
            title="Reports",
            icon=":material/analytics:",
        ),
    ],
    "Account": [
        st.Page(
            "pages/profile.py",
            title="Company profile",
            icon=":material/business:",
        ),
        st.Page(
            "pages/settings.py",
            title="Settings",
            icon=":material/settings:",
        ),
    ],
}

page = st.navigation(pages)

# Application branding and sidebar layout.
ui.sidebar_header()

# Render the selected page.
page.run()
