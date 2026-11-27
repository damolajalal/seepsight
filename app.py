import streamlit as st

st.set_page_config(
    page_title="Seepsight",
    page_icon="📦",
    layout="wide",
)

from seepsight import auth, ui, workspace  # noqa: E402


# Apply the application-wide design system.
ui.inject_css()


# ---------------------------------------------------------
# PUBLIC WEBSITE
# ---------------------------------------------------------

def public_welcome():
    """Display the public landing page to logged-out visitors."""
    auth.require_auth()


# ---------------------------------------------------------
# AUTHENTICATED WORKSPACE
# ---------------------------------------------------------

def authenticated_pages():
    """Define navigation available to authenticated company users."""

    return {
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


# ---------------------------------------------------------
# DYNAMIC NAVIGATION AND ACCESS CONTROL
# ---------------------------------------------------------

account = st.session_state.get("seepsight_auth")

if not account:
    # Logged-out visitors can access only the public welcome page.
    page = st.navigation(
        [
            st.Page(
                public_welcome,
                title="Welcome",
                icon=":material/home:",
                default=True,
            )
        ]
    )

    page.run()

else:
    # Authenticated users receive the complete company workspace.
    page = st.navigation(authenticated_pages())

    # Display authenticated account information and branding.
    auth.require_auth()

    # Demonstration mode: procurement data exists only in this browser session.
    # Clear any workspace restored by an earlier persistent-mode release once
    # when this authenticated session starts; never query saved analyses here.
    st.session_state["seepsight_demo_mode"] = True
    if not st.session_state.get("_seepsight_session_workspace_initialized"):
        for key in (
            "mine", "seepsight_demo_workspace", "cases", "chat",
            "_workspace_list_cache", "_workspace_restore_cache",
            "_show_saved_analysis_picker",
        ):
            st.session_state.pop(key, None)
        st.session_state["_seepsight_session_workspace_initialized"] = True

    ui.sidebar_header()
    st.sidebar.caption("SESSION-ONLY DEMONSTRATION")
    st.sidebar.caption("Uploaded procurement data is cleared when this session ends.")

    # Render the selected workspace page.
    page.run()
