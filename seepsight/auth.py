
"""Seepsight public landing page and Firebase company authentication."""

import requests
import streamlit as st

from seepsight import company_store

TIMEOUT = 20
BASE_URL = "https://identitytoolkit.googleapis.com/v1/accounts"


# ---------------------------------------------------------
# FIREBASE AUTHENTICATION
# ---------------------------------------------------------

def _api_key():
    try:
        return st.secrets["firebase"]["api_key"]
    except Exception:
        st.error(
            "Firebase is not configured. Add your Firebase API key "
            "to Streamlit secrets before using authentication."
        )
        return None


def _request(endpoint, payload):
    key = _api_key()
    if not key:
        return None

    url = f"{BASE_URL}:{endpoint}?key={key}"

    try:
        response = requests.post(
            url,
            json=payload,
            timeout=TIMEOUT,
        )
        data = response.json()

        if response.ok:
            return data

        message = data.get("error", {}).get("message", "UNKNOWN_ERROR")
        st.error(_friendly_error(message))
        return None

    except requests.RequestException:
        st.error("Unable to contact the authentication service. Please try again.")
        return None
    except ValueError:
        st.error("The authentication service returned an invalid response.")
        return None


def _friendly_error(message):
    errors = {
        "EMAIL_EXISTS": "This email already has an account. Please sign in.",
        "INVALID_EMAIL": "Please enter a valid email address.",
        "WEAK_PASSWORD": "Use a password with at least 6 characters.",
        "INVALID_LOGIN_CREDENTIALS": "Email or password is incorrect.",
        "EMAIL_NOT_FOUND": "No account was found for this email.",
        "USER_DISABLED": "This account has been disabled.",
        "TOO_MANY_ATTEMPTS_TRY_LATER": "Too many attempts. Please try again later.",
        "INVALID_PASSWORD": "Email or password is incorrect.",
        "OPERATION_NOT_ALLOWED": (
            "Email and password sign-in is not enabled in Firebase."
        ),
        "API_KEY_INVALID": "The Firebase API key is invalid.",
    }
    return errors.get(message, f"Authentication error: {message}")


def _send_verification(id_token):
    return _request(
        "sendOobCode",
        {
            "requestType": "VERIFY_EMAIL",
            "idToken": id_token,
        },
    )


def _get_user(id_token):
    result = _request("lookup", {"idToken": id_token})

    if result and result.get("users"):
        return result["users"][0]

    return None


def _set_auth_view(view):
    st.session_state["seepsight_auth_view"] = view
    st.rerun()


# ---------------------------------------------------------
# COMPANY REGISTRATION
# ---------------------------------------------------------

def _register():
    st.subheader("Create your company account")
    st.write(
        "Set up your company's secure procurement intelligence workspace."
    )

    with st.form("company_registration"):
        company_name = st.text_input("Company name")
        email = st.text_input("Official company email")
        password = st.text_input("Password", type="password")
        confirm = st.text_input("Confirm password", type="password")

        submitted = st.form_submit_button(
            "Create company account",
            use_container_width=True,
        )

    if not submitted:
        return

    company_name = company_name.strip()
    email = email.strip().lower()

    if not company_name or not email or not password:
        st.warning("Please complete all fields.")
        return

    if password != confirm:
        st.warning("Your passwords do not match.")
        return

    if len(password) < 6:
        st.warning("Your password must contain at least 6 characters.")
        return

    account = _request(
        "signUp",
        {
            "email": email,
            "password": password,
            "returnSecureToken": True,
        },
    )

    if not account:
        return

    update_result = _request(
        "update",
        {
            "idToken": account["idToken"],
            "displayName": company_name,
            "returnSecureToken": True,
        },
    )

    if not update_result:
        st.warning(
            "Your account was created, but the company name could not be saved. "
            "Please contact support before proceeding."
        )
        return

    verification = _send_verification(account["idToken"])

    if verification:
        st.success(
            "Your company account has been created. Check your email "
            "and verify your address before signing in."
        )
        st.info("If the message is not in your inbox, check your spam folder.")
    else:
        st.warning(
            "Your account was created, but the verification email could not "
            "be sent. Please try again or contact support."
        )


# ---------------------------------------------------------
# EMAIL VERIFICATION
# ---------------------------------------------------------

def _resend_pending_verification():
    token = st.session_state.get("seepsight_pending_verification_token")

    if not token:
        return

    if st.button(
        "Resend verification email",
        use_container_width=True,
        key="resend_verification",
    ):
        result = _send_verification(token)

        if result:
            st.success("A new verification email has been sent.")


# ---------------------------------------------------------
# COMPANY SIGN IN
# ---------------------------------------------------------

def _login():
    st.subheader("Welcome back")
    st.write("Sign in to access your company's procurement workspace.")

    with st.form("company_login"):
        email = st.text_input("Company email")
        password = st.text_input("Password", type="password")

        submitted = st.form_submit_button(
            "Sign in",
            use_container_width=True,
        )

    if submitted:
        account = _request(
            "signInWithPassword",
            {
                "email": email.strip().lower(),
                "password": password,
                "returnSecureToken": True,
            },
        )

        if not account:
            return

        user = _get_user(account["idToken"])

        if not user:
            return

        if not user.get("emailVerified", False):
            st.session_state["seepsight_pending_verification_token"] = (
                account["idToken"]
            )
            st.warning("Please verify your email address before signing in.")
            _resend_pending_verification()
            return

        st.session_state.pop(
            "seepsight_pending_verification_token",
            None,
        )

        try:
            company = company_store.ensure_company_for_user(
                uid=user["localId"],
                email=user["email"],
                company_name=user.get("displayName", "Company"),
            )
        except Exception as exc:
            st.error(
                "Your sign-in succeeded, but your company workspace "
                f"could not be loaded: {exc}"
            )
            return

        st.session_state["seepsight_auth"] = {
            "uid": user["localId"],
            "email": user["email"],
            "company_name": company["company_name"],
            "company_id": company["company_id"],
            "role": company["role"],
            "id_token": account["idToken"],
            "refresh_token": account["refreshToken"],
        }

        st.session_state.pop("seepsight_auth_view", None)
        st.rerun()

    _resend_pending_verification()

    st.write("")

    if st.button(
        "Forgot your password?",
        key="forgot_password_link",
    ):
        _set_auth_view("reset")

    if st.button(
        "Don't have a company account? Create one",
        key="register_from_login",
    ):
        _set_auth_view("register")


# ---------------------------------------------------------
# PASSWORD RESET
# ---------------------------------------------------------

def _password_reset():
    st.subheader("Reset your password")
    st.write("Enter your company email to receive a password reset link.")

    with st.form("password_reset"):
        email = st.text_input("Company email")

        submitted = st.form_submit_button(
            "Send reset email",
            use_container_width=True,
        )

    if submitted:
        if not email.strip():
            st.warning("Enter your company email.")
            return

        result = _request(
            "sendOobCode",
            {
                "requestType": "PASSWORD_RESET",
                "email": email.strip().lower(),
            },
        )

        if result:
            st.success(
                "If the account exists, a password reset email has been sent."
            )


# ---------------------------------------------------------
# PUBLIC WEBSITE
# ---------------------------------------------------------

def _public_welcome():
    """Render the public Seepsight landing page."""

    st.markdown(
        """
        <style>
        /* Give the page enough room below Streamlit's top toolbar. */
        .stApp [data-testid="stMainBlockContainer"] {
            max-width: 1160px;
            padding-top: 3.5rem !important;
            padding-bottom: 3rem !important;
        }

        /* Brand header */
        .ss-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
            min-height: 76px;
            padding: 8px 0 18px 0;
            box-sizing: border-box;
        }

        .ss-brand-group {
            display: flex;
            align-items: center;
            gap: 14px;
            min-height: 60px;
        }

        .ss-logo {
            width: 54px;
            height: 54px;
            border-radius: 11px;
            background: #173449;
            color: #FFFFFF;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 29px;
            font-weight: 800;
            flex-shrink: 0;
        }

        .ss-brand {
            color: #173449;
            font-size: 2.25rem;
            font-weight: 800;
            letter-spacing: -1.3px;
            line-height: 1.2;
            white-space: nowrap;
        }

        .ss-brand-subtitle {
            color: #A66C3F;
            font-size: 0.68rem;
            font-weight: 750;
            letter-spacing: 2px;
            margin-top: 3px;
            white-space: nowrap;
        }

        /* Hero */
        .ss-eyebrow {
            color: #A66C3F;
            font-size: 0.76rem;
            font-weight: 700;
            letter-spacing: 2px;
            text-transform: uppercase;
            margin-bottom: 0.7rem;
        }

        .ss-hero {
            font-size: clamp(2.5rem, 5vw, 4.1rem);
            line-height: 1.08;
            letter-spacing: -2px;
            font-weight: 750;
            color: #173449;
            margin: 1.2rem 0;
        }

        .ss-lead {
            font-size: 1.12rem;
            line-height: 1.8;
            color: #586773;
            max-width: 700px;
        }

        /* Feature panels */
        .ss-panel {
            background: #F5F3ED;
            border: 1px solid #E5E0D6;
            border-radius: 14px;
            padding: 1.5rem;
            min-height: 150px;
            box-sizing: border-box;
        }

        .ss-panel h4 {
            color: #173449;
            margin-top: 0.5rem;
            font-size: 1.05rem;
        }

        .ss-panel p {
            color: #64717A;
            line-height: 1.6;
            font-size: 0.92rem;
        }

        .ss-number {
            color: #B5794B;
            font-weight: 750;
            font-size: 0.82rem;
            letter-spacing: 1px;
        }

        .ss-section-intro {
            color: #64717A;
            line-height: 1.7;
            max-width: 760px;
        }

        /* Avoid clipping on smaller screens. */
        @media (max-width: 700px) {
            .ss-brand {
                font-size: 1.7rem;
            }

            .ss-brand-subtitle {
                font-size: 0.55rem;
                letter-spacing: 1.2px;
            }

            .ss-logo {
                width: 46px;
                height: 46px;
                font-size: 24px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Brand and account navigation.
    header_brand, header_signin, header_register = st.columns(
        [3, 1, 1.55],
        vertical_alignment="center",
        gap="small",
    )

    with header_brand:
        st.markdown(
            """
            <div class="ss-brand-group">
                <div class="ss-logo">S</div>
                <div>
                    <div class="ss-brand">Seepsight</div>
                    <div class="ss-brand-subtitle">
                        PROCUREMENT INTELLIGENCE
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with header_signin:
        if st.button(
            "Sign in",
            use_container_width=True,
            key="header_signin",
        ):
            _set_auth_view("signin")

    with header_register:
        if st.button(
            "Create account",
            type="primary",
            use_container_width=True,
            key="header_register",
        ):
            _set_auth_view("register")

    st.divider()

    # Hero section.
    hero_left, hero_right = st.columns(
        [1.45, 0.75],
        gap="large",
    )

    with hero_left:
        st.markdown(
            '<div class="ss-eyebrow">A clearer view of procurement</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="ss-hero">'
            'See the gaps.<br>'
            'Show the impact.<br>'
            'Act with confidence.'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="ss-lead">'
            'Understand your procurement operations, uncover potential '
            'financial leakage and identify risks that deserve attention. '
            'Seepsight helps turn purchasing data into clearer decisions.'
            '</div>',
            unsafe_allow_html=True,
        )

    with hero_right:
        st.markdown(
            """
            <div class="ss-panel">
                <div class="ss-eyebrow">The Seepsight approach</div>
                <h4>From purchasing records to better decisions.</h4>
                <p>
                    Bring procurement information into focus, examine
                    important signals, review supporting evidence and
                    coordinate the actions that follow.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")
    st.divider()

    # Capabilities.
    st.markdown("## Procurement deserves a clearer picture")

    st.markdown(
        '<div class="ss-section-intro">'
        'Important procurement issues can be difficult to spot when '
        'purchasing information is scattered across different records '
        'and processes.'
        '</div>',
        unsafe_allow_html=True,
    )

    feature_columns = st.columns(4, gap="medium")

    features = [
        (
            "01",
            "Financial visibility",
            "Examine purchasing activity and investigate potential financial leakage.",
        ),
        (
            "02",
            "Risk detection",
            "Bring potential price, quantity and delivery discrepancies to attention.",
        ),
        (
            "03",
            "Supplier intelligence",
            "Understand supplier activity and identify performance concerns.",
        ),
        (
            "04",
            "Action management",
            "Review findings, supporting evidence and follow-up actions.",
        ),
    ]

    for column, (number, heading, description) in zip(
        feature_columns,
        features,
    ):
        with column:
            st.markdown(
                f"""
                <div class="ss-panel">
                    <div class="ss-number">{number}</div>
                    <h4>{heading}</h4>
                    <p>{description}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")
    st.divider()

    # Workflow.
    st.markdown("## How Seepsight works")

    steps = st.columns(3, gap="large")

    workflow = [
        (
            "01 · CONNECT",
            "Bring your data together",
            "Start by connecting your company's procurement records.",
        ),
        (
            "02 · ANALYSE",
            "Understand what is happening",
            "Examine purchasing activity and review potential risk signals.",
        ),
        (
            "03 · TAKE ACTION",
            "Move from insight to action",
            "Investigate findings, examine evidence and track corrective actions.",
        ),
    ]

    for column, (number, heading, description) in zip(
        steps,
        workflow,
    ):
        with column:
            st.caption(number)
            st.subheader(heading)
            st.write(description)

    st.divider()

    # Footer.
    footer_left, footer_right = st.columns([2, 1])

    with footer_left:
        st.markdown("**Seepsight**")
        st.caption(
            "See the gaps. Show the impact. Act with confidence."
        )

    with footer_right:
        if st.button(
            "Access your workspace",
            use_container_width=True,
            key="footer_signin",
        ):
            _set_auth_view("signin")


# ---------------------------------------------------------
# AUTHENTICATION PAGE ROUTING
# ---------------------------------------------------------

def _authentication_screen():
    view = st.session_state.get("seepsight_auth_view", "welcome")

    if view == "welcome":
        _public_welcome()
        return

    st.markdown("### Seepsight")
    st.caption("See the gaps. Show the impact. Act with confidence.")

    if st.button("← Back to welcome page", key="auth_back"):
        _set_auth_view("welcome")

    st.divider()

    if view == "signin":
        _login()
    elif view == "register":
        _register()
    elif view == "reset":
        _password_reset()
    else:
        _public_welcome()


# ---------------------------------------------------------
# LOGOUT AND AUTHENTICATION GATE
# ---------------------------------------------------------

def logout():
    st.session_state.pop("seepsight_auth", None)
    st.rerun()


def require_auth():
    """Display the public website or authenticate company users."""

    account = st.session_state.get("seepsight_auth")

    if account:
        st.sidebar.markdown("---")
        st.sidebar.caption("SIGNED IN AS")
        st.sidebar.write(account["company_name"])
        st.sidebar.caption(account["email"])

        if st.sidebar.button(
            "Sign out",
            use_container_width=True,
        ):
            logout()

        return True

    _authentication_screen()
    return False
